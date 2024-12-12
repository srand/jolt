from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import copy
from functools import wraps
import os
import queue
from threading import Lock

from jolt import common_pb2 as common_pb
from jolt import config
from jolt import hooks
from jolt import log
from jolt import utils
from jolt import tools
from jolt.error import raise_task_error
from jolt.error import raise_task_error_if
from jolt.graph import PruneStrategy
from jolt.manifest import ManifestExtension
from jolt.manifest import ManifestExtensionRegistry
from jolt.options import JoltOptions
from jolt.timer import Timer


class JoltEnvironment(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TaskQueue(object):
    def __init__(self):
        self.futures = {}
        self.futures_lock = Lock()
        self.duration_acc = utils.duration_diff(0)
        self._aborted = False
        self._timer = Timer(60, self._log_task_running_time)
        self._timer.start()

    def _log_task_running_time(self):
        with self.futures_lock:
            for future in self.futures:
                self.futures[future].task.log_running_time()

    def submit(self, executor):
        if self._aborted:
            return None

        env = JoltEnvironment(queue=self)
        future = executor.schedule(env)
        self.futures[future] = executor
        return future

    def wait(self):
        for future in as_completed(self.futures):
            task = self.futures[future].task
            try:
                future.result()
            except Exception as error:
                return task, error
            finally:
                self.duration_acc += task.duration_running or 0
                with self.futures_lock:
                    del self.futures[future]
            return task, None
        return None, None

    def abort(self):
        self._aborted = True
        with self.futures_lock:
            for future, executor in self.futures.items():
                executor.cancel()
                future.cancel()
            if len(self.futures):
                log.info("Waiting for tasks to finish, please be patient")
        self._timer.cancel()

    def shutdown(self):
        self._timer.cancel()

    def is_aborted(self):
        return self._aborted

    def in_progress(self, task):
        with self.futures_lock:
            return task in self.futures.values()

    def empty(self):
        with self.futures_lock:
            return len(self.futures) == 0


class Executor(object):
    """
    Base class for all executors.

    An executor is responsible for running a task. It is created by an executor
    factory and is submitted to a task queue. The factory is also
    responsible for hosting a thread pool that will run the executors it creates.

    The type of executor created by the factory depends on the execution strategy
    selected by the user through command line options. The strategy is responsible
    for deciding which executor to create for each task.

    An implementation of an executor must implement the run method, which is called
    from the thread pool. The run method is responsible for running the task and
    handling any exceptions that may occur during execution.
    """

    def __init__(self, factory):
        self.factory = factory

    def schedule(self, env):
        """ Schedule the task for execution.

        This method is called by the task queue to schedule the task for execution
        in the factory thread pool. The method must return a Future object that
        represents the task execution. The Future object is used to track the
        execution of the task and to retrieve the result of the execution
        once it is completed.

        The method must be implemented by all executors. They must call the
        factory submit method to schedule the task for execution and also
        mark the task as in progress with set_in_progress().

        Args:
            env: The JoltEnvironment object that contains the queue and cache objects.

        """
        return self.factory.submit(self, env)

    def cancel(self):
        """
        Cancel the task.

        This method is optional and may be implemented by executors that support
        cancellation of tasks, such as network executors where a remote scheduler
        may be able to cancel a task that is already running.

        By default, the method does nothing.
        """
        pass

    def is_aborted(self):
        """ Check if executor has been aborted. """
        return self.factory.is_aborted()

    def run(self, env):
        """
        Run the task.

        This method must be implemented by all executors. It is called from the
        factory thread pool and is responsible for running the task
        and handling any exceptions that may occur during execution.
        Any exceptions raised by the task must, if caught, be re-raised to
        the caller unless the task is marked as unstable, in which case the
        exception should be logged and ignored.

        The task run() method shall be run within a hooks.task_run()
        context manager to ensure that the task status is recognized by
        the report hooks and other plugins.

        Network executors have additional requirements. See the
        NetworkExecutor class for more information.
        """
        raise NotImplementedError


class LocalExecutor(Executor):
    """
    An Executor that runs a task locally.

    The executor runs the task on the local machine. The task is run
    by calling the task.run() method.

    The executor is created by the local executor factory and is
    typically run sequentially with other executors.
    """

    def __init__(self, factory, task, force_upload=False, force_build=False):
        super().__init__(factory)
        self.task = task
        self.force_build = force_build
        self.force_upload = force_upload

    def schedule(self, env):
        """
        Schedule the task for execution.

        The task is marked as in progress before scheduling.
        """
        self.task.set_in_progress()
        return super().schedule(env)

    def _run(self, env, task):
        if self.is_aborted():
            return
        try:
            with hooks.task_run(task):
                self.task.run(
                    env,
                    force_build=self.force_build,
                    force_upload=self.force_upload)

        except Exception as e:
            log.exception(e, error=False)
            if not task.is_unstable:
                self.task.raise_for_status(log_error=getattr(env, "worker", False))
                raise e

    def get_all_extensions(self, task):
        extensions = copy.copy(task.extensions)
        for ext in extensions:
            extensions.extend(self.get_all_extensions(ext))
        return extensions

    def run(self, env):
        tasks = [self.task] + self.get_all_extensions(self.task)
        for task in tasks:
            task.queued()

        self._run(env, self.task)


class NetworkExecutor(Executor):
    def run(self, env):
        """
        Run the task.

        See the Executor class for basic information.

        Network executors have additional requirements. Before scheduling
        the task to a remote scheduler, the executor must call
        run_resources() on the task. This acquires any Resources marked
        local=True and uploads the resulting session artifacts
        to the remote cache.

        Once the task has been submitted to the remote scheduler, the executor
        must run task.queued() on the task and its extensions. This is done
        to ensure that the task status is correctly reported to the
        user.

        For any change in state of task, the executor must run one of:

        - task.running_execution(remote=True) - when the task has started
        - task.failed_execution(remote=True) - when the task has failed
        - task.failed_execution(remote=True, interrupt=True) - when the
          task has been interrupted, e.g. by a user request or rescheduling
        - task.finished_execution(remote=True) - when the task has passed

        Upon completion of the task, whether successful or not, task
        session artifacts must be downloaded to the local cache, if
        the task is marked as downloadable. This is done by calling
        task.download() with the session_only flag set to True.

        Persistent artifacts are downloaded only if the task is successful
        and the task is marked as downloadable.
        """
        raise NotImplementedError


class SkipTask(Executor):
    """
    An Executor that skips a task.

    This executor is created by the concurrent executor factory when a task
    is skipped, i.e. when the task artifacts are already available locally or
    remotely and the task does not need to be run.
    """

    def __init__(self, factory, task, *args, **kwargs):
        super().__init__(factory, *args, **kwargs)
        self.task = task

    def run(self, env):
        """
        Skip the task.

        The task and its extensions are marked as skipped.
        """
        self.task.skipped()
        for ext in self.task.extensions:
            ext.skipped()
        return self.task


class Downloader(Executor):
    """
    An Executor that downloads task artifacts.

    The executor downloads the task artifacts and its extensions from the
    remote cache to the local cache. Failure to download the artifacts
    is reported by raising an exception.

    Downloader executors are typically run in parallel with other executors.

    """
    def __init__(self, factory, task, *args, **kwargs):
        super().__init__(factory, *args, **kwargs)
        self.task = task

    def schedule(self, env):
        """
        Schedule the task for execution.

        The task is marked as in progress before scheduling.
        """
        self.task.set_in_progress()
        return super().schedule(env)

    def _download(self, task):
        if self.is_aborted():
            return
        if not task.is_downloadable():
            return
        try:
            task.started_download()
            raise_task_error_if(
                not task.download(persistent_only=True),
                task, "Failed to download task artifact")
        except Exception as e:
            with task.task.report() as report:
                report.add_exception(e)
            task.failed_download()
            raise e
        else:
            task.finished_download()

    def run(self, env):
        """ Downloads artifacts. """

        self._download(self.task)
        for ext in self.task.extensions:
            self._download(ext)
        return self.task


class Uploader(Executor):
    """
    An Executor that uploads task artifacts.

    The executor uploads the task artifacts and its extensions from the
    local cache to the remote cache. Failure to upload the artifacts
    is reported by raising an exception.

    Uploader executors are typically run in parallel with other executors.
    """

    def __init__(self, factory, task, *args, **kwargs):
        super().__init__(factory, *args, **kwargs)
        self.task = task

    def schedule(self, env):
        """
        Schedule the task for execution.

        The task is marked as in progress before scheduling.
        """
        self.task.set_in_progress()
        return super().schedule(env)

    def _upload(self, task):
        if self.is_aborted():
            return
        try:
            task.started_upload()
            raise_task_error_if(
                not task.upload(persistent_only=True),
                task, "Failed to upload task artifact")
        except Exception as e:
            with task.task.report() as report:
                report.add_exception(e)
            task.failed_upload()
            raise e
        else:
            task.finished_upload()

    def run(self, env):
        """ Uploads artifacts. """

        self._upload(self.task)
        for ext in self.task.extensions:
            self._upload(ext)

        return self.task


@utils.Singleton
class ExecutorRegistry(object):
    executor_factories = []
    extension_factories = []

    def __init__(self, options=None):
        self._options = options or JoltOptions()
        self._factories = [factory(self._options) for factory in self.__class__.executor_factories]
        self._local_factory = LocalExecutorFactory(self._options)
        self._concurrent_factory = ConcurrentLocalExecutorFactory(self._options)
        self._extensions = [factory().create() for factory in self.__class__.extension_factories]

    def shutdown(self):
        for factory in self._factories:
            factory.shutdown()
        self._local_factory.shutdown()
        self._concurrent_factory.shutdown()

    def create_session(self, graph):
        return {factory: factory.create_session(graph) for factory in self._factories}

    def create_skipper(self, task):
        return SkipTask(self._concurrent_factory, task)

    def create_downloader(self, task):
        # TODO: Switch to concurrent factory once the progress bar can handle it
        return Downloader(self._concurrent_factory, task)

    def create_uploader(self, task):
        # TODO: Switch to concurrent factory once the progress bar can handle it
        return Uploader(self._concurrent_factory, task)

    def create_local(self, task, force=False):
        task.set_locally_executed()
        return self._local_factory.create(task, force=force)

    def create_network(self, session, task):
        for factory in self._factories:
            executor = factory.create(session[factory], task)
            if executor is not None:
                task.set_remotely_executed()
                return executor
        return self.create_local(task)

    def get_network_parameters(self, task):
        parameters = {}
        for extension in self._extensions:
            parameters.update(extension.get_parameters(task))
        return parameters


class NetworkExecutorExtensionFactory(object):
    @staticmethod
    def Register(cls):
        ExecutorRegistry.extension_factories.insert(0, cls)
        return cls

    def create(self):
        raise NotImplementedError()


class NetworkExecutorExtension(object):
    def get_parameters(self, task):
        return {}


class Job(object):
    def __init__(self, priority, future, executor, env):
        self.priority = priority
        self.future = future
        self.executor = executor
        self.env = env

    def __le__(self, o):
        return self.priority <= o.priority

    def __ge__(self, o):
        return self.priority >= o.priority

    def __lt__(self, o):
        return self.priority < o.priority

    def __gt__(self, o):
        return self.priority > o.priority

    def __eq__(self, o):
        return self.priority == o.priority


class ExecutorFactory(object):
    @staticmethod
    def Register(cls):
        ExecutorRegistry.executor_factories.insert(0, cls)
        return cls

    def __init__(self, options=None, max_workers=None):
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self._aborted = False
        self._queue = queue.PriorityQueue()
        self._options = options or JoltOptions()

    def is_aborted(self):
        return self._aborted

    def is_keep_going(self):
        return self._options.keep_going

    def shutdown(self):
        self._aborted = True
        self.pool.shutdown()

    def create(self, task):
        raise NotImplementedError()

    def _run(self):
        job = self._queue.get(False)
        self._queue.task_done()
        try:
            if not self.is_aborted():
                job.executor.run(job.env)
        except KeyboardInterrupt as e:
            self._aborted = True
            job.future.set_exception(e)
        except Exception as e:
            if not self.is_keep_going():
                self._aborted = True
            job.future.set_exception(e)
        else:
            job.future.set_result(job.executor)

    def submit(self, executor, env):
        future = Future()
        self._queue.put(Job(-executor.task.weight, future, executor, env))
        self.pool.submit(self._run)
        return future


class LocalExecutorFactory(ExecutorFactory):
    def __init__(self, options=None):
        max_workers = config.getint(
            "jolt", "parallel_tasks",
            os.getenv("JOLT_PARALLEL_TASKS", 1 if options is None else options.jobs))
        super().__init__(
            options=options,
            max_workers=max_workers)

    def create(self, task, force=False):
        return LocalExecutor(self, task, force_build=force)


class ConcurrentLocalExecutorFactory(ExecutorFactory):
    def __init__(self, options=None):
        max_workers = tools.Tools().thread_count()
        super().__init__(
            options=options,
            max_workers=max_workers)

    def create(self, task):
        raise NotImplementedError()


class NetworkExecutorFactory(ExecutorFactory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def create(self, session, task):
        raise NotImplementedError()


def ensure_executor_return(func):
    @wraps(func)
    def wrapper(self, session, task):
        executor = func(self, session, task)
        raise_task_error_if(
            not executor, task,
            "no executor can execute the task; "
            "requesting a distributed network build without proper configuration?")
        return executor
    return wrapper


class ExecutionStrategy(object):
    def create_executor(self, session, task):
        raise NotImplementedError()


class LocalStrategy(ExecutionStrategy, PruneStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        if task.is_alias() or task.is_resource():
            return self.executors.create_skipper(task)
        if not task.is_cacheable():
            return self.executors.create_local(task)
        if task.is_available_locally():
            return self.executors.create_skipper(task)
        if self.cache.download_enabled() and task.is_available_remotely():
            return self.executors.create_downloader(task)
        return self.executors.create_local(task)

    def should_prune_requirements(self, task):
        if task.is_alias() or not task.is_cacheable():
            return False
        if task.is_available_locally():
            return True
        if self.cache.download_enabled() and task.is_available_remotely():
            return True
        return False


class DownloadStrategy(ExecutionStrategy, PruneStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        if task.is_alias():
            return self.executors.create_skipper(task)
        if task.is_resource():
            return self.executors.create_local(task)
        if not task.is_cacheable():
            return self.executors.create_skipper(task)
        if task.is_available_locally():
            return self.executors.create_skipper(task)
        if self.cache.download_enabled() and task.is_available_remotely(cache=False):
            return self.executors.create_downloader(task)
        raise_task_error(task, "Task must be built first")

    def should_prune_requirements(self, task):
        return False


class DistributedStrategy(ExecutionStrategy, PruneStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        if task.is_alias() or task.is_resource():
            return self.executors.create_skipper(task)

        if task.is_local():
            return self.executors.create_local(task)

        if not task.is_cacheable():
            return self.executors.create_network(session, task)

        if not self.cache.upload_enabled():
            return self.executors.create_network(session, task)

        if not task.is_goal(with_extensions=False):
            task.disable_download()
        for extension in task.extensions:
            if not extension.is_goal(with_extensions=False):
                extension.disable_download()

        remote = task.is_available_remotely()
        if remote:
            if task.is_goal() and self.cache.download_enabled() and \
               not task.is_available_locally():
                return self.executors.create_downloader(task)
            return self.executors.create_skipper(task)
        else:
            if task.is_available_locally() and task.is_uploadable():
                return self.executors.create_uploader(task)
            if task.is_fast() and task.deps_available_locally():
                return self.executors.create_local(task, force=True)

        return self.executors.create_network(session, task)

    def should_prune_requirements(self, task):
        if task.is_alias() or not task.is_cacheable():
            return False
        if task.is_available_remotely():
            return True
        return False


class WorkerStrategy(ExecutionStrategy, PruneStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        if task.is_alias() or task.is_resource():
            return self.executors.create_skipper(task)

        raise_task_error_if(
            not self.cache.upload_enabled(), task,
            "Artifact upload must be enabled for workers, fix configuration")

        if not task.is_cacheable():
            return self.executors.create_local(task)

        if task.is_available_locally():
            if task.is_goal() and not task.is_available_remotely():
                # Unpacked artifacts may become unpacked before we manage to upload.
                # To keep the implementation simple we take the easy road and rebuild
                # all artifacts that have not been unpacked, even if they are uploadable.
                if task.is_unpacked() and task.is_uploadable():
                    return self.executors.create_uploader(task)
                else:
                    return self.executors.create_local(task, force=True)
            return self.executors.create_skipper(task)

        if not self.cache.download_enabled():
            return self.executors.create_local(task)

        if task.is_available_remotely():
            return self.executors.create_downloader(task)
        elif not task.is_goal():
            raise_task_error(task, "Task artifact removed from global cache, cannot continue")

        return self.executors.create_local(task)

    def should_prune_requirements(self, task):
        if task.is_alias() or not task.is_cacheable():
            return False
        if task.is_available_locally():
            # Unpacked artifacts may become unpacked before we manage to upload.
            # To keep the implementation simple we take the easy road and rebuild
            # all artifacts that have not been unpacked, even if they are uploadable.
            if task.is_unpacked() and task.is_uploadable():
                return True
        if not task.is_goal() and task.task.selfsustained:
            return True
        return False


def get_exported_task_set(task):
    children = [task] + task.descendants
    for ext in task.extensions:
        children.extend(get_exported_task_set(ext))
    return list(set(children))


class TaskIdentityExtension(ManifestExtension):
    def export_manifest(self, manifest, tasks):
        # Generate a list of all tasks that must be evaluated
        # for inclusion in the manifest
        all_tasks = []
        for task in tasks:
            all_tasks += get_exported_task_set(task)
        all_tasks = list(set(all_tasks))

        for child in all_tasks:
            manifest_task = manifest.find_task(child.qualified_name)
            if manifest_task is None:
                manifest_task = manifest.create_task()
                manifest_task.name = child.qualified_name
            manifest_task.identity = child.identity
            manifest_task.instance = child.instance


ManifestExtensionRegistry.add(TaskIdentityExtension())


class TaskExportExtension(ManifestExtension):
    def export_manifest(self, manifest, tasks):
        short_task_names = set()

        # Generate a list of all tasks that must be evaluated
        # for inclusion in the manifest
        all_tasks = []
        for task in tasks:
            all_tasks += get_exported_task_set(task)
        all_tasks = list(set(all_tasks))

        # Add all tasks with export attributes to the manifest
        for child in all_tasks:
            manifest_task = manifest.find_task(child.qualified_name)
            if manifest_task is None:
                manifest_task = manifest.create_task()
                manifest_task.name = child.qualified_name
            for key, export in child.task._get_export_objects().items():
                attrib = manifest_task.create_attribute()
                attrib.name = key
                attrib.value = export.export(child.task)
            short_task_names.add(child.name)

        # Figure out if any task with an overridden default parameter
        # value was included in the manifest. If so, add info about it.
        default_task_names = set()
        for task in all_tasks:
            for task in task.options.default:
                short_name, _ = utils.parse_task_name(task)
                if short_name in short_task_names:
                    default_task_names.add(task)
        if default_task_names:
            build = manifest.create_build()
            for task in default_task_names:
                default = build.create_default()
                default.name = task


ManifestExtensionRegistry.add(TaskExportExtension())


def export_tasks(tasks):
    pb_tasks = {}

    for task in tasks:
        properties = []
        for key, export in task.task._get_export_objects().items():
            value = export.export(task.task)
            if value is not None:
                pb_attrib = common_pb.Property(key=key, value=str(value))
                properties.append(pb_attrib)

        platform = common_pb.Platform(
            properties=[
                common_pb.Property(key=key, value=value)
                for key, value in task.task.platform.items()
            ]
        )

        args = dict(
            identity=task.identity,
            instance=task.instance,
            taint=str(task.task.taint),
            name=task.short_qualified_name,
            platform=platform,
            properties=properties,
        )

        pb_tasks[task.exported_name] = common_pb.Task(**args)

    return pb_tasks


def export_task_default_params(tasks):
    default_task_names = {}

    for task in tasks:
        for task in task.options.default:
            short_name, params = utils.parse_task_name(task)
            if short_name in default_task_names:
                default_task_names[short_name].update(params)
            else:
                default_task_names[short_name] = params

    return [
        utils.format_task_name(name, params)
        for name, params in default_task_names.items()
    ]
