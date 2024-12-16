from contextlib import contextmanager, ExitStack, nullcontext
import copy
import hashlib
from os import getenv
from threading import RLock
from collections import OrderedDict
import uuid
import socket
import sys

from jolt import cli
from jolt import common_pb2 as common_pb
from jolt import config
from jolt import log
from jolt import utils
from jolt import colors
from jolt import hooks
from jolt import filesystem as fs
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if
from jolt.influence import HashInfluenceRegistry, TaskRequirementInfluence
from jolt.options import JoltOptions
from jolt.tasks import Alias, Resource, WorkspaceResource


class TaskProxy(object):
    def __init__(self, task, graph, cache, options):
        self.task = task
        self.graph = graph
        self.cache = cache
        self.options = options

        # Direct and transitive dependencies.
        # The dependency chain is broken at
        # selfsustained dependencies that don't
        # require their own dependencies anymore
        # after being executed.
        self.children = []
        self.ancestors = set()

        # All direct and transitive dependencies.
        # Unlike 'children', this set is not filtered
        # from selfsustained tasks.
        self.descendants = set()

        # Unfiltered direct dependencies.
        self.neighbors = []

        self.extensions = []
        self.duration_queued = None
        self.duration_running = None
        self.requirement_aliases = {}

        self._extended_task = None
        self._in_progress = False
        self._completed = False
        self._goal = False
        self._download = True
        self._local = False
        self._network = False
        self._artifacts = []
        self._status = None
        self._finalized = False

        # Consumer task if this is a resource
        self._owner = None

        # List of all artifacts that are produced by this task
        self._artifacts = []

    def __hash__(self):
        return id(self)

    @property
    def artifacts(self):
        return self._artifacts

    def add_artifact(self, artifact):
        self._artifacts.append(artifact)

    def get_artifact(self, name):
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        return None

    @property
    def tools(self):
        return self.task.tools

    @property
    def name(self):
        return self.task.name

    @property
    def canonical_name(self):
        return self.task.canonical_name

    @property
    def qualified_name(self):
        return self.task.qualified_name

    @property
    def short_qualified_name(self):
        return self.task.short_qualified_name

    @property
    def exported_name(self):
        return self.task.exported_name

    @property
    def log_name(self):
        return "({0} {1})".format(self.short_qualified_name, self.identity[:8])

    def log_running_time(self):
        """ Emits an information log line every 5 mins a task has been running. """
        if not self.is_running():
            return
        minutes = int(self.duration_running.seconds / 60)
        if (minutes % 5) == 0 and minutes > 0:
            if minutes >= 60:
                fmt = f"{int(minutes / 60)}h {int(minutes % 60)}min"
            else:
                fmt = f"{int(minutes % 60)}min"
            if self.is_remotely_executed():
                self.info("Remote execution still in progress after {}", fmt)
            else:
                self.info("Execution still in progress after {}", fmt)

    @property
    def identity(self):
        raise_task_error_if(not self._finalized, self, "Task identity read prematurely")

        if self.task.identity is not None:
            return self.task.identity

        # Acquire workspace resources before calculating the identity
        for c in self.children:
            if c.is_workspace_resource():
                c.task.acquire_ws()

        sha = hashlib.sha1()
        HashInfluenceRegistry.get().apply_all(self.task, sha)
        self.task.identity = sha.hexdigest()

        return str(self.task.identity)

    @identity.setter
    def identity(self, value):
        self.task.identity = value

    @property
    def instance(self):
        return self.task.instance

    @instance.setter
    def instance(self, value):
        self.task.instance = value

    @property
    def is_unstable(self):
        return self.task.unstable

    @property
    def weight(self):
        return self.task.weight

    @weight.setter
    def weight(self, weight):
        self.task.weight = weight

    def __str__(self):
        return "{0}{1}".format(self.short_qualified_name, "*" if self.is_extension() else '')

    def info(self, fmt, *args, **kwargs):
        self.task.info(fmt + " " + self.log_name, *args, **kwargs)

    def debug(self, fmt, *args, **kwargs):
        log.debug(fmt + " " + self.log_name, *args, **kwargs)

    def verbose(self, fmt, *args, **kwargs):
        log.verbose(fmt + " " + self.log_name, *args, **kwargs)

    def warning(self, fmt, *args, **kwargs):
        self.task.warning(fmt + " " + self.log_name, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        self.task.error(fmt + " " + self.log_name, *args, **kwargs)

    def has_children(self):
        return len(self.children) > 0

    def has_ancestors(self):
        return len(self.ancestors) > 0

    def has_artifact(self):
        return self.is_cacheable() and not self.is_alias()

    def has_extensions(self):
        return len(self.extensions) > 0

    def add_extension(self, task):
        if self.is_extension():
            self.get_extended_task().add_extension(task)
        self.extensions.append(task)

    def set_extended_task(self, task):
        self._extended_task = task

    def get_extended_task(self):
        if self.is_extension():
            return self._extended_task.get_extended_task()
        return self

    def deps_available_locally(self):
        for c in self.children:
            if c.is_resource() or c.is_alias():
                continue
            if not c.is_available_locally(persistent_only=True):
                return False
        return True

    def is_alias(self):
        return isinstance(self.task, Alias)

    def is_available_locally(self, extensions=True, persistent_only=True):
        dep_artifacts = []
        if extensions:
            for dep in self.extensions:
                dep_artifacts += dep.artifacts
        artifacts = self._artifacts + dep_artifacts
        if persistent_only:
            artifacts = filter(lambda a: not a.is_session(), artifacts)
        return all(map(self.cache.is_available_locally, artifacts))

    def is_available_remotely(self, extensions=True, cache=True):
        dep_artifacts = []
        if extensions:
            for dep in self.extensions:
                dep_artifacts += dep.artifacts
        artifacts = filter(lambda a: not a.is_session(), self._artifacts + dep_artifacts)
        return all(map(lambda artifact: self.cache.is_available_remotely(artifact, cache=cache), artifacts))

    def is_cacheable(self):
        return self.task.is_cacheable()

    def is_completed(self):
        return self._completed

    def is_downloadable(self):
        return self._download

    def is_extension(self):
        return self._extended_task is not None

    def is_fast(self):
        tasks = [self.task] + [e.task for e in self.extensions]
        return all([task.fast for task in tasks])

    def is_identified(self):
        return self.task.identity is not None

    def is_goal(self, with_extensions=True):
        return self._goal or (with_extensions and any([e.is_goal() for e in self.extensions]))

    def is_local(self):
        if self.is_extension():
            return self.get_extended_task().is_local()
        tasks = [self.task] + [e.task for e in self.extensions]
        return any([task.local for task in tasks])

    def in_progress(self):
        return self._in_progress

    def is_ready(self):
        if self.in_progress():
            return False

        if self.is_extension():
            return False

        return self.graph.is_leaf(self)

    def is_locally_executed(self):
        return self._local

    def is_remotely_executed(self):
        return self._network

    def is_resource(self):
        return isinstance(self.task, Resource)

    def is_workspace_resource(self):
        return isinstance(self.task, WorkspaceResource)

    def is_running(self):
        return self.status() == common_pb.TaskStatus.TASK_RUNNING

    def is_unpackable(self):
        tasks = [self] + self.extensions
        artifacts = []
        for task in tasks:
            artifacts.extend(task._artifacts)
        return any(map(lambda artifact: artifact.is_unpackable(), artifacts))

    def is_unpacked(self):
        tasks = [self] + self.extensions
        artifacts = []
        for task in tasks:
            artifacts.extend(task._artifacts)
        return any(map(lambda artifact: artifact.is_unpacked(), artifacts))

    def is_uploadable(self, artifacts=None):
        tasks = [self] + self.extensions
        if not artifacts:
            artifacts = []
            for task in tasks:
                artifacts.extend(task._artifacts)
        return all(map(lambda artifact: artifact.is_uploadable(), artifacts))

    @contextmanager
    def lock_artifacts(self, discard=False):
        artifacts = []
        stack = ExitStack()
        try:
            for artifact in self.artifacts:
                lock = self.cache.lock_artifact(artifact, discard=discard)
                artifacts.append(stack.enter_context(lock))
            self._artifacts = artifacts
            yield artifacts
        finally:
            stack.close()

    def disable_download(self):
        self._download = False

    def download(self, force=False, session_only=False, persistent_only=False):
        """
        Downloads all artifacts of this task.

        If the task is not downloadable, the method returns True. Failure to
        download persistent artifacts is considered a failure, and the method
        returns False. Session artifacts are not required to be downloaded.

        :param force: Force download even if the artifacts are already available.
        :param session_only: Download only session artifacts.
        :param persistent_only: Download only persistent artifacts.

        """
        if not force and not self.is_downloadable():
            return True
        success = True
        artifacts = self._artifacts
        artifacts_session = list(filter(lambda a: a.is_session(), artifacts))
        artifacts_persistent = list(filter(lambda a: not a.is_session(), artifacts))
        download_all = not session_only and not persistent_only
        if session_only or download_all:
            for artifact in artifacts_session:
                if not self.cache.download(artifact, force=force):
                    self.warning("Failed to download session artifact: {}", artifact.identity)
        if persistent_only or download_all:
            success = all([self.cache.download(artifact, force=force) for artifact in artifacts_persistent])
        return success

    def upload(self, force=False, locked=False, session_only=False, persistent_only=False, artifacts=None):
        artifacts = artifacts or self._artifacts
        if session_only:
            artifacts = list(filter(lambda a: a.is_session(), artifacts))
        if persistent_only:
            artifacts = list(filter(lambda a: not a.is_session(), artifacts))
        if not artifacts:
            return True
        if not self.is_uploadable(artifacts):
            return False
        return all([self.cache.upload(artifact, force=force, locked=locked) for artifact in artifacts])

    def resolve_requirement_alias(self, name):
        return self.requirement_aliases.get(name)

    def set_cancelled(self):
        self.set_status(common_pb.TaskStatus.TASK_CANCELLED)

    def set_passed(self):
        self.set_status(common_pb.TaskStatus.TASK_PASSED)

    def set_failed(self):
        self.set_status(common_pb.TaskStatus.TASK_FAILED)

    def set_skipped(self):
        self.set_status(common_pb.TaskStatus.TASK_SKIPPED)

    def set_downloaded(self):
        self.set_status(common_pb.TaskStatus.TASK_DOWNLOADED)

    def set_uploaded(self):
        self.set_status(common_pb.TaskStatus.TASK_UPLOADED)

    def set_running(self):
        self.set_status(common_pb.TaskStatus.TASK_RUNNING)

    def set_queued(self):
        self.set_status(common_pb.TaskStatus.TASK_QUEUED)

    def status(self):
        return self._status

    def set_status(self, status):
        self._status = status

    def set_in_progress(self):
        self.set_queued()
        self._in_progress = True

    def set_locally_executed(self):
        self._local = True

    def set_remotely_executed(self):
        self._network = True

    def set_goal(self):
        self._goal = True

    def set_owner(self, owner):
        self._owner = owner
        self.task.exported_name = f"{self.short_qualified_name}@@{owner.short_qualified_name}"

    def finalize(self, dag):
        log.debug("Finalizing: " + self.short_qualified_name)

        # Find all direct and transitive dependencies
        self.ancestors = set()
        self.descendants = set()

        self.neighbors = copy.copy(self.children)
        self.neighbors = sorted(self.neighbors, key=lambda n: n.qualified_name)

        for n in self.neighbors:
            self.descendants.add(n)
            self.descendants = self.descendants.union(n.descendants)
            if not n.task.selfsustained:
                self.children.extend(n.children)
            n.ancestors.add(self)

        # Exclude transitive alias and resources dependencies.
        # Workspace resources are included as they may be required by its dependencies.
        self.children = list(
            filter(lambda n: dag.are_neighbors(self, n) or (not n.is_alias() and not n.is_resource()),
                   utils.unique_list(self.children)))

        # Prepare workspace resources for this task so that influence can be calculated
        for child in self.children:
            if not child.is_workspace_resource():
                continue
            child.task.prepare_ws_for(self.task)

        self.descendants = list(self.descendants)

        self.task.influence += [TaskRequirementInfluence(n) for n in self.neighbors]
        self._finalized = True
        self.identity

        hooks.task_created(self)

        return self.identity

    def finalize_artifacts(self):
        self._artifacts.extend(self.task._artifacts(self.cache, self))

    def taint(self, salt=None):
        self.task.taint = salt or uuid.uuid4()
        if salt is None:
            # Only recalculate identity when build is forced, not when salted
            self.identity = None
            self.identity
            # Recreate artifacts
            self._artifacts = []
            self.finalize_artifacts()

        # If this is an alias, taint all children
        if self.is_alias():
            for child in self.children:
                child.taint()

        # Taint all extensions
        for extension in self.extensions:
            extension.taint()

    def queued(self, remote=True):
        self.task.verbose("Task queued " + self.log_name)
        self.duration_queued = utils.duration()
        self.set_queued()
        hooks.task_queued(self)

    def running(self, when=None, what="Execution"):
        if what:
            self.task.info(colors.blue(what + " started " + self.log_name))
            self.set_running()
            hooks.task_started(self)
        self.duration_running = utils.duration() if not when else when

    def running_execution(self, remote=False):
        self.worker = socket.gethostname()
        hooks.task_started_execution(self)
        self.running(what="Remote execution" if remote else "Execution")

    def restarted_execution(self, remote=False):
        hooks.task_finished_execution(self)
        self.task.warning("Remote execution interrupted {}" if remote else "Execution interrupted {}", self.log_name)
        self.queued()

    def started_execution(self, remote=False):
        self.queued()
        self.running_execution(remote=remote)

    def started_download(self):
        self.queued()
        self.running(what="Download")
        hooks.task_started_download(self)

    def started_upload(self):
        self.queued()
        self.running(what="Upload")
        hooks.task_started_upload(self)

    def _failed(self, what="Execution", interrupt=False):
        if interrupt:
            how = "interrupted"
            logfn = self.warning
            self.set_cancelled()
        else:
            how = "failed"
            logfn = self.error
            self.set_failed()

        if self.duration_queued and self.duration_running:
            logfn("{0} {1} after {2} {3}", what, how,
                  self.duration_running,
                  self.duration_queued.diff(self.duration_running))
        elif self.duration_queued:
            logfn("{0} {1} after {2}", what, how, self.duration_queued or utils.duration())
        else:
            logfn("{0} {1} immediately", what, how)

        if self.is_unstable:
            try:
                self.graph.remove_node(self)
            except KeyError:
                self.warning("Pruned task was executed")
            self.graph.add_unstable(self)
            hooks.task_unstable(self)
        else:
            self.graph.add_failed(self)
            hooks.task_failed(self)

    def failed_download(self):
        self._failed("Download")

    def failed_upload(self):
        self._failed("Upload")

    def failed_execution(self, remote=False, interrupt=False):
        self._failed(what="Remote execution" if remote else "Execution", interrupt=interrupt)

    def _finished(self, what="Execution"):
        raise_task_error_if(
            self.is_completed() and not self.is_extension(),
            self, "task has already been completed")
        self._completed = True
        try:
            self.graph.remove_node(self)
        except KeyError:
            self.warning("Pruned task was executed")
        self.task.info(colors.green(what + " finished after {0} {1}" + self.log_name),
                       self.duration_running or "00s",
                       self.duration_queued.diff(self.duration_running))
        hooks.task_finished(self)

    def finished_download(self):
        self.set_downloaded()
        hooks.task_finished_download(self)
        self._finished("Download")

    def finished_upload(self):
        self.set_uploaded()
        hooks.task_finished_upload(self)
        self._finished("Upload")

    def finished_execution(self, remote=False):
        self.set_passed()
        hooks.task_finished_execution(self)
        self._finished(what="Remote execution" if remote else "Execution")

    def skipped(self):
        self._completed = True
        try:
            self.graph.remove_node(self)
        except KeyError:
            pass
        self.set_skipped()
        hooks.task_skipped(self)

    def pruned(self):
        self._completed = True
        try:
            self.graph.remove_node(self)
            self.graph.add_pruned(self)
            hooks.task_pruned(self)
        except KeyError:
            self.warning("Pruned task was already pruned")

    def clean(self, cache, if_expired, onerror=None):
        with self.tools:
            self.task.clean(self.tools)
            for artifact in self.artifacts:
                discarded = cache.discard(artifact, if_expired, onerror=fs.onerror_warning)
                if discarded:
                    log.debug("Discarded: {} ({})", self.short_qualified_name, artifact.identity)
                else:
                    log.debug(" Retained: {} ({})", self.short_qualified_name, artifact.identity)

    def _run_download_dependencies(self, resource_only=False):
        for child in self.children:
            if not child.has_artifact():
                continue

            if child.is_resource() and child.is_local():
                if child.options.worker:
                    # Resource already acquired by the client when running as worker
                    raise_task_error_if(
                        not child.download(force=True),
                        child, "Failed to download task artifact")
                else:
                    # Resource about to be acquired by the client
                    child._run_download_dependencies()
                continue

            if resource_only and not child.is_resource():
                continue

            raise_task_error_if(
                not child.is_completed() and child.is_unstable,
                self, "Task depends on failed task '{}'", child.short_qualified_name)
            if not child.is_available_locally(extensions=False):
                raise_task_error_if(
                    not child.download(force=True),
                    child, "Failed to download task artifact")

    def partially_available_locally(self):
        availability = map(lambda a: self.cache.is_available_locally(a), self.artifacts)
        return any(availability) and not all(availability)

    def _validate_platform(self):
        """ Validates that the task is runnable on the current platform. """
        platform_os, platform_arch = utils.platform_os_arch()

        os = self.task.platform.get("node.os")
        if os:
            os = self.tools.expand(os)
            raise_task_error_if(
                os != platform_os,
                self, f"Task is not runnable on current platform (wants node.os={os})")

        arch = self.task.platform.get("node.arch")
        if arch:
            arch = self.tools.expand(arch)
            raise_task_error_if(
                arch != platform_arch,
                self, f"Task is not runnable on current platform (wants node.arch={arch})")

    def run_acquire(self, artifact, owner, log_prefix=False):
        """
        Acquires a resource and publishes its artifact.

        The artifact is published to the cache even if the acquisition fails.
        """

        try:
            if not self.is_workspace_resource():
                ts = utils.duration()
                log.info(colors.blue("Resource acquisition started ({} for {})"), self.short_qualified_name, owner.short_qualified_name)

            try:
                with log.thread_prefix(owner.identity[:8]) if log_prefix else nullcontext():
                    acquire = getattr(self.task, "acquire_" + artifact.name) if artifact.name != "main" else self.task.acquire
                    acquire(artifact, self.deps, self.tools, owner.task)
            finally:
                # Always commit the resource session artifact to the cache, even if the acquisition failed.
                if not self.is_workspace_resource():
                    self.cache.commit(artifact)

            if not self.is_workspace_resource():
                log.info(colors.green("Resource acquisition finished after {} ({} for {})"), ts, self.short_qualified_name, owner.short_qualified_name)

        except (KeyboardInterrupt, Exception) as e:
            if not self.is_workspace_resource():
                log.error(colors.red("Resource acquisition failed after {} ({} for {})"), ts, self.short_qualified_name, owner.short_qualified_name)
            if self.task.release_on_error:
                with utils.ignore_exception():
                    self.run_release(artifact, owner)
            raise e

    def run_release(self, artifact, owner, log_prefix=False):
        """
        Releases a resource.
        """
        try:
            if not self.is_workspace_resource():
                ts = utils.duration()
                log.info(colors.blue("Resource release started ({} for {})"), self.short_qualified_name, owner.short_qualified_name)

            with log.thread_prefix(owner.identity[:8]) if log_prefix else nullcontext():
                release = getattr(self.task, "release_" + artifact.name) if artifact.name != "main" else self.task.release
                release(artifact, self.deps, self.tools, owner.task)

            if not self.is_workspace_resource():
                log.info(colors.green("Resource release finished after {} ({} for {})"), ts, self.short_qualified_name, owner.short_qualified_name)

        except (KeyboardInterrupt, Exception) as e:
            if not self.is_workspace_resource():
                log.error(colors.red("Resource release failed after {} ({} for {})"), ts, self.short_qualified_name, owner.short_qualified_name)
            raise e

    @contextmanager
    def run_resources(self):
        """
        Acquires and releases resources for the task.

        The method is called by executors before invoking the task proxy's run() method.
        Resource dependencies are acquired and released in reverse order. If an acquisition fails,
        already acquired resources are released in reverse order and the exception is propagated
        to the caller.

        Resource artifacts are always published and uploaded if the acquisition has been started,
        even if the acquisition fails. That way, a failed acquisition can be debugged.
        """
        self._run_download_dependencies(resource_only=True)

        with self._run_resources_no_dep_download():
            yield

    @contextmanager
    def _run_resources_no_dep_download(self):
        # Log messages are prefixed with task identity if resources are acquired in parallel
        log_prefix = False

        # Collect list of resource dependencies
        resource_deps = [child for child in self.children if child.is_resource()]

        if self.options.worker:
            # Exclude local resources when running as worker. They are already acquired by the client.
            resource_deps = [child for child in resource_deps if not child.is_local()]
        elif self.options.network and not self.is_local():
            # Exclude non-local resources in the client when running a network build.
            # They are acquired by the remote worker.
            resource_deps = [child for child in resource_deps if child.is_local()]
            log_prefix = True

        exitstack = ExitStack()
        acquired = []
        try:
            # Acquire resource dependencies in reverse order.
            for resource in reversed(resource_deps):
                # Always discard resource artifacts before acquiring the resource.
                # They should not exist in the cache when the resource is acquired,
                # but may exist if the resource was previously acquired by an interrupted build.
                with resource.lock_artifacts(discard=True) if not resource.is_workspace_resource() else nullcontext():
                    resource.deps = self.cache.get_context(resource)
                    exitstack.enter_context(resource.deps)

                    # Just like tasks, a resource may have multiple artifacts. Run acquire for each artifact.
                    for artifact in resource.artifacts:
                        try:
                            resource.run_acquire(artifact, self, log_prefix=log_prefix)
                            acquired.append(resource)
                        finally:
                            # Always upload the artifact session artifact to the cache, even if the acquisition failed.
                            if not resource.is_workspace_resource():
                                resource.upload(locked=False, session_only=True, artifacts=[artifact])

            yield

        finally:
            for resource in reversed(acquired):
                for artifact in resource.artifacts:
                    resource.run_release(artifact, self, log_prefix=log_prefix)
            exitstack.close()

    def run(self, env, force_upload=False, force_build=False):
        # Download dependency artifacts if not already done
        self._run_download_dependencies()

        with self._run_resources_no_dep_download():
            self._run_task(env, force_upload, force_build)

    def _run_task(self, env, force_upload=False, force_build=False):
        queue = env.queue

        with self.tools:
            available_locally = available_remotely = False

            # Check if task artifact is available locally or remotely,
            # either skip execution or download it if necessary.
            if not force_build:
                available_locally = self.is_available_locally()
                if available_locally and not force_upload:
                    self.skipped()
                    return

                available_remotely = self.cache.download_enabled() and self.is_available_remotely()
                if not available_locally and available_remotely:
                    available_locally = self.download()

                if not available_locally and self.partially_available_locally():
                    force_build = True

            if force_build or not available_locally:
                with log.threadsink() as buildlog:
                    if self.task.is_runnable():
                        log.verbose("Host: {0}", getenv("HOSTNAME", "localhost"))

                    with self.lock_artifacts(discard=not self.is_resource()) as artifacts:
                        exitstack = ExitStack()

                        # Indicates whether session artifacts have been published
                        upload_session_artifacts = False

                        try:
                            context = self.cache.get_context(self)
                            exitstack.enter_context(context)

                            self.running_execution()

                            self._validate_platform()

                            with self.tools.cwd(self.task.joltdir):
                                if self.is_goal() and self.options.debug:
                                    log.info("Entering debug shell")
                                    self.task.debugshell(context, self.tools)

                                try:
                                    # Run task
                                    try:
                                        hooks.task_prerun(self, context, self.tools)
                                        with self.tools.timeout(seconds=config.getint("jolt", "task_timeout")):
                                            self.task.run(context, self.tools)
                                    finally:
                                        hooks.task_postrun(self, context, self.tools)

                                    # Publish persistent artifacts
                                    if not self.is_available_locally(extensions=False):
                                        for artifact in filter(lambda a: not a.is_session(), artifacts):
                                            self.publish(context, artifact, buildlog)
                                    else:
                                        self.info("Publication skipped, already in local cache")

                                finally:
                                    # Session artifacts should be uploaded
                                    upload_session_artifacts = []

                                    # Publish session artifacts to local cache
                                    for artifact in filter(lambda a: a.is_session(), artifacts):
                                        self.publish(context, artifact)
                                        upload_session_artifacts.append(artifact)

                        except KeyboardInterrupt as e:
                            self.failed_execution(interrupt=True)
                            with utils.ignore_exception():
                                exitstack.close()

                            raise e

                        except Exception as e:
                            self.failed_execution(interrupt=queue.is_aborted() if queue else False)

                            with utils.ignore_exception():
                                exitstack.close()

                            if queue is not None and queue.is_aborted():
                                raise KeyboardInterrupt()

                            if cli.debug_enabled:
                                import pdb
                                extype, value, tb = sys.exc_info()
                                pdb.post_mortem(tb)

                            raise e

                        else:
                            self.finished_execution()
                            exitstack.close()

                            # Must upload the artifact while still holding its lock, otherwise the
                            # artifact may become unpack():ed before we have a chance to.
                            if force_upload or force_build or not available_remotely:
                                raise_task_error_if(
                                    not self.upload(force=force_upload, locked=False, persistent_only=True) \
                                    and self.cache.upload_enabled(),
                                    self, "Failed to upload task artifact")

                        finally:
                            # Upload published session artifacts to remote cache
                            raise_task_error_if(
                                upload_session_artifacts \
                                and not self.upload(force=force_upload, locked=False, session_only=True, artifacts=upload_session_artifacts) \
                                and self.cache.upload_enabled(),
                                self, "Failed to upload session artifact")

            elif force_upload or not available_remotely:
                self.started_upload()
                raise_task_error_if(
                    not self.upload(force=force_upload, persistent_only=True) \
                    and self.cache.upload_enabled(),
                    self, "Failed to upload task artifact")
                self.finished_upload()

            else:
                self.skipped()
                self.info("Execution skipped, already in local cache")

            for extension in self.extensions:
                with hooks.task_run(extension):
                    extension.run(env, force_upload, force_build)

    def publish(self, context, artifact, buildlog=None):
        hooks.task_prepublish(self, artifact, self.tools)
        publish = self.task.publish if artifact.is_main() else \
            getattr(self.task, "publish_" + artifact.name)
        publish(artifact, self.tools)
        self.task._verify_influence(context, artifact, self.tools)
        if artifact.is_main() and buildlog:
            with open(fs.path.join(artifact.path, ".build.log"), "w") as f:
                f.write(buildlog.getvalue())
        hooks.task_postpublish(self, artifact, self.tools)
        artifact.get_cache().commit(artifact)

    def raise_for_status(self, log_details=False, log_error=False):
        with self.report() as report:
            report.raise_for_status(log_details, log_error)

    def report(self):
        return self.task.report()

    def unpack(self):
        """ Unpacks all artifacts produced by this task. """
        for artifact in self.artifacts:
            self.cache.unpack(artifact)


class Graph(object):
    def __init__(self):
        self._mutex = RLock()
        self._failed = []
        self._unstable = []
        self._pruned = []
        self._children = OrderedDict()
        self._parents = OrderedDict()

    def add_node(self, node):
        with self._mutex:
            self._children[node] = OrderedDict()
            self._parents[node] = OrderedDict()

    def remove_node(self, node):
        with self._mutex:
            parents = self._parents[node].keys()
            for child in self._children[node]:
                del self._parents[child][node]
            for parent in parents:
                del self._children[parent][node]
            del self._children[node]
            del self._parents[node]

    def add_pruned(self, node):
        self._pruned.append(node)

    def add_edges_from(self, edges):
        with self._mutex:
            for src, dst in edges:
                self._children[src][dst] = None
                self._parents[dst][src] = None

    def successors(self, node):
        return self._children[node].keys()

    def predecessors(self, node):
        return self._parents[node].keys()

    @property
    def topological_nodes(self):
        with self._mutex:
            G = self.clone()
            S = G.roots
            L = []
            while S:
                for n in S:
                    L.append(n)
                    G.remove_node(n)
                S = G.roots
            if len(G.nodes) > 0:
                log.debug("[GRAPH] Graph has cycles between these nodes:")
                for node in G.nodes:
                    log.debug("[GRAPH]   " + node.short_qualified_name)
                raise_error_if(len(G.nodes) > 0, "graph has cycles")
            return L

    def clone(self):
        g = Graph()
        g._children = OrderedDict()
        g._parents = OrderedDict()
        for k, v in self._children.items():
            g._children[k] = copy.copy(v)
        for k, v in self._parents.items():
            g._parents[k] = copy.copy(v)
        return g

    @property
    def artifacts(self):
        artifacts = []
        for node in self.nodes:
            if node.is_cacheable():
                artifacts.extend(node.artifacts)
        return artifacts

    @property
    def persistent_artifacts(self):
        return list(filter(lambda a: not a.is_session(), self.artifacts))

    @property
    def nodes(self):
        with self._mutex:
            return self._children.keys()

    def number_of_tasks(self, filterfn=None):
        return len(list(filter(filterfn, self.nodes)) if filterfn else self.nodes)

    @property
    def failed(self):
        return self._failed

    def add_failed(self, task):
        self._failed.append(task)

    @property
    def unstable(self):
        return self._unstable

    def add_unstable(self, task):
        self._unstable.append(task)

    @property
    def tasks(self):
        with self._mutex:
            return [n for n in self.nodes]

    @property
    def pruned(self):
        return [p for p in self._pruned]

    @property
    def roots(self):
        with self._mutex:
            return [n for n in self.nodes if self.is_root(n)]

    def has_tasks(self):
        with self._mutex:
            return len(self.nodes) > 0

    def get_task(self, qualified_name):
        with self._mutex:
            return self._nodes_by_name.get(qualified_name)

    def get_task_by_identity(self, identity):
        with self._mutex:
            for task in self.nodes:
                if task.identity == identity:
                    return task
        return None

    def select(self, func):
        with self._mutex:
            return [n for n in self.nodes if func(self, n)]

    def debug(self):
        with self._mutex:
            log.debug("[GRAPH] Listing all nodes")
            for node in self.topological_nodes:
                log.debug("[GRAPH]   " + node.short_qualified_name + " ({})", len(self._children[node].keys()))

    def is_leaf(self, node):
        with self._mutex:
            return len(self._children[node].keys()) == 0

    def is_root(self, node):
        with self._mutex:
            return len(self._parents[node].keys()) == 0

    def is_orphan(self, node):
        with self._mutex:
            return self.is_root(node) and self.is_leaf(node)

    def are_neighbors(self, n1, n2):
        with self._mutex:
            return n2 in self._children[n1]


class GraphBuilder(object):
    def __init__(self, registry, cache, options=None, progress=False, buildenv=None):
        self.cache = cache
        self.graph = Graph()
        self.nodes = {}
        self.registry = registry
        self.buildenv = buildenv
        self.progress = progress
        self.options = options or JoltOptions()

    def _get_node(self, progress, name, parent=None):
        name = utils.stable_task_name(name)
        node = self.nodes.get(name)
        if not node:
            task = self.registry.get_task(name, buildenv=self.buildenv)
            node = self.nodes.get(task.qualified_name, None)
            if node is not None:
                return node
            node = TaskProxy(task, self.graph, self.cache, self.options)
            if not node.is_resource() or node.is_workspace_resource():
                self.nodes[node.short_qualified_name] = node
                self.nodes[node.qualified_name] = node
            elif parent:
                node.set_owner(parent)
                if self.buildenv:
                    task._apply_protobuf(self.buildenv)
            if self.options.salt:
                node.taint(self.options.salt)
            self._build_node(progress, node)
            progress.update(1)
        return node

    def _build_node(self, progress, node):
        self.graph.add_node(node)

        if node.task.extends:
            extended_node = self._get_node(progress, node.task.extends, parent=node)
            self.graph.add_edges_from([(node, extended_node)])
            node.set_extended_task(extended_node)
            extended_node.add_extension(node)
            node.children.append(extended_node)
            parent = extended_node.get_extended_task()
        else:
            parent = node

        for requirement in node.task.requires:
            alias, _, task, name = utils.parse_aliased_task_name(requirement)
            child = self._get_node(progress, utils.format_task_name(task, name), parent=node)

            # Create direct edges from alias parents to alias children
            if child.is_alias():
                for child_child in child.children:
                    self.graph.add_edges_from([(parent, child_child)])
                    node.children.append(child_child)
            self.graph.add_edges_from([(parent, child)])
            node.children.append(child)
            if alias:
                node.requirement_aliases[alias] = requirement

        node.children = utils.unique_list(node.children)

        return node

    @contextmanager
    def _progress(self, *args, **kwargs):
        if self.progress:
            with log.progress(*args, **kwargs) as p:
                yield p
        else:
            with log.progress_log(*args, **kwargs) as p:
                yield p

    def build(self, task_list, influence=True):
        with self._progress("Building graph", len(self.graph.tasks), "tasks") as progress:
            goals = [self._get_node(progress, task) for task in task_list]
            self.graph._nodes_by_name = self.nodes

        if influence:
            topological_nodes = self.graph.topological_nodes
            with self._progress("Collecting task influence", len(self.graph.tasks), "tasks") as p:
                for node in reversed(topological_nodes):
                    node.finalize(self.graph)
                    p.update(1)

                # Create artifacts in forward order so that parent identities are available
                # when creating resource artifacts that depend on them.
                for node in topological_nodes:
                    node.finalize_artifacts()

            max_time = 0
            min_time = 0
            for node in topological_nodes:
                max_time += node.task.weight
                node.task.weight += max([a.weight for a in node.ancestors] + [0])
                min_time = max(node.task.weight, min_time)

            log.verbose("Time estimate: {}- {}",
                        utils.duration_diff(min_time),
                        utils.duration_diff(max_time))

        self.graph.requested_goals = goals
        self.graph.goals = []
        for goal in goals:
            goal.set_goal()
            self.graph.goals.append(goal)
            if goal.is_alias():
                for goal_alias in goal.neighbors:
                    goal_alias.set_goal()
                    self.graph.goals.append(goal_alias)

        self.graph.all_nodes = [n for n in self.graph.nodes]

        return self.graph


class PruneStrategy(object):
    def should_prune_requirements(self, task):
        raise NotImplementedError()


class GraphPruner(object):
    def __init__(self, cache, strategy):
        self.cache = cache
        self.strategy = strategy
        self.retained = set()
        self.visited = set()

    def _check_node(self, node):
        if node in self.visited:
            return
        self._progress.update(1)
        self.visited.add(node)
        self.retained.add(node)

        prune = self.strategy.should_prune_requirements(node)
        if not node.task.selfsustained or not prune or node.is_extension():
            utils.map_concurrent(self._check_node, node.neighbors)

    def prune(self, graph):
        with log.progress("Checking availability", 0, " tasks") as p:
            self._progress = p
            for root in graph.roots:
                self._check_node(root)

        for node in graph.goals:
            self.retained.add(node)

        pruned = []
        for node in graph.nodes:
            if node not in self.retained:
                pruned.append(node)
            else:
                log.debug("Retained: {}", node.log_name)
                node.children = [c for c in node.children if c in self.retained]

        for node in pruned:
            log.debug("Excluded: {}", node.log_name)
            node.pruned()

        return graph
