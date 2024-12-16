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
from jolt.options import JoltOptions
from jolt.timer import Timer


class JoltEnvironment(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TaskQueue(object):
    """
    A helper class for tracking tasks in progress and their completion.
    """

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
        """
        Submit an exeuctor to the task queue for execution.

        The method schedules the executor for execution and returns a Future object
        that may be used to track completion of the task.
        """

        if self._aborted:
            return None

        env = JoltEnvironment(queue=self)
        future = executor.schedule(env)
        with self.futures_lock:
            self.futures[future] = executor
        return future

    def wait(self):
        """
        Wait for any task to complete.

        The method waits for the next task to complete and returns the task and any
        exception that may have occurred during execution. If no task is in progress,
        the method returns None, None.
        """

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
        """
        Abort all tasks in progress.

        The method cancels all tasks in progress and prevents any new tasks from being
        submitted to the task queue. The method doesn't wait for all tasks to complete
        before returning.
        """
        self._aborted = True
        with self.futures_lock:
            for future, executor in self.futures.items():
                executor.cancel()
                future.cancel()
            if len(self.futures):
                log.info("Waiting for tasks to finish, please be patient")
        self._timer.cancel()

    def shutdown(self):
        """
        Shutdown the task queue.
        """
        self._timer.cancel()

    def is_aborted(self):
        """ Returns true if the task queue has been aborted. """
        return self._aborted

    def in_progress(self, task):
        """ Returns true if the task is in progress. """
        with self.futures_lock:
            return task in self.futures.values()

    def empty(self):
        """ Returns true if the task queue is empty. """
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
    """
    The ExecutorRegistry is responsible for creating executors.

    The types of executors that are possible to create are:

    - create_local: Runs tasks locally.
    - create_network: Schedules tasks for remote execution.
    - create_downloader: Downloads task artifacts.
    - create_uploader: Uploads task artifacts.
    - create_skipper: Skips tasks.

    The registry utilizes different ExecutorFactory objects to create executors. Plugins
    can register their own NetworkExecutorFactory objects with the help of the
    ExecutorFactory.Register decorator.
    """

    executor_factories = []

    def __init__(self, options=None):
        self._options = options or JoltOptions()
        self._factories = [factory(self._options) for factory in self.__class__.executor_factories]
        self._local_factory = LocalExecutorFactory(self._options)
        self._concurrent_factory = ConcurrentLocalExecutorFactory(self._options)

    def shutdown(self):
        """ Shuts all executor factories and thread-pools down """

        for factory in self._factories:
            factory.shutdown()
        self._local_factory.shutdown()
        self._concurrent_factory.shutdown()

    def create_session(self, graph):
        """ Creates a session for all factories. """
        return {factory: factory.create_session(graph) for factory in self._factories}

    def create_skipper(self, task):
        """ Creates an executor that skips a task. """
        return SkipTask(self._concurrent_factory, task)

    def create_downloader(self, task):
        """ Creates an executor that downloads task artifacts. """
        return Downloader(self._concurrent_factory, task)

    def create_uploader(self, task):
        """ Creates an executor that uploads task artifacts. """
        return Uploader(self._concurrent_factory, task)

    def create_local(self, task, force=False):
        """ Creates an executor that runs a task locally. """
        task.set_locally_executed()
        return self._local_factory.create(task, force=force)

    def create_network(self, session, task):
        """
        Creates an executor that schedules a task for remote execution.

        All registred network executor factories are queried to create an executor.
        The first factory that can create an executor is used. If no factory is able
        to create an executor, a local executor is created as fallback.
        """

        for factory in self._factories:
            executor = factory.create(session[factory], task)
            if executor is not None:
                task.set_remotely_executed()
                return executor
        return self.create_local(task)


class ExecutorFactory(object):
    """
    The ExecutorFactory class is responsible for creating executors.

    The factory is responsible for creating executors that run tasks. The factory
    is also responsible for hosting a thread pool that will run the executors it creates.

    """
    class QueueItem(object):
        """
        The type of item that is put into the queue thread-pool queue.

        It wraps the executor and its priority.
        """
        def __init__(self, priority: int, future: Future, executor: Executor, env: JoltEnvironment):
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

    @staticmethod
    def Register(cls):
        """
        Decorator to register an executor factory.

        The decorator is used by plugins that whish to register their own
        executor factories. Such factories are used by the ExecutorRegistry
        to create executors for tasks, as determined by the execution strategy
        selected by the user.
        """

        ExecutorRegistry.executor_factories.insert(0, cls)
        return cls

    def __init__(self, options=None, max_workers=None):
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self._aborted = False
        self._queue = queue.PriorityQueue()
        self._options = options or JoltOptions()

    def is_aborted(self):
        """ Returns true if the build and thus the factory has been aborted. """
        return self._aborted

    def is_keep_going(self):
        """ Returns true if the build should continue even if a task fails. """
        return self._options.keep_going

    def shutdown(self):
        """
        Called to shutdown the factory and its thread-pool.

        The method is called when the build is complete or when the build is aborted.
        After the method is called, no more tasks can be submitted to the factory and
        the is_aborted() method will return True.
        """
        self._aborted = True
        self.pool.shutdown()

    def create(self, task):
        """
        Create an executor for the provided task.

        Must be implemented by all executor factories. The method must return
        an executor that is capable of running the task. The executor must be
        created with the factory as its parent so that it can be submitted to
        the correct thread-pool for execution.
        """
        raise NotImplementedError()

    def _run(self):
        item = self._queue.get(False)
        self._queue.task_done()
        try:
            if not self.is_aborted():
                item.executor.run(item.env)
        except KeyboardInterrupt as e:
            self._aborted = True
            item.future.set_exception(e)
        except Exception as e:
            if not self.is_keep_going():
                self._aborted = True
            item.future.set_exception(e)
        else:
            item.future.set_result(item.executor)

    def submit(self, executor, env):
        """
        Submit an executor to the thread-pool for execution.

        The method submits the executor to the thread-pool for execution. The executor
        is wrapped in a Future object that is returned to the caller. The Future object
        is used to track the execution of the task and to retrieve the result of the
        execution once it is completed.
        """
        future = Future()
        self._queue.put(ExecutorFactory.QueueItem(-executor.task.weight, future, executor, env))
        self.pool.submit(self._run)
        return future


class LocalExecutorFactory(ExecutorFactory):
    """
    Factory for creating local executors.

    The factory creates executors that run tasks locally. Typically,
    only one LocalExecutor is allowed to run at a time, unless the
    user has specified a higher number of parallel tasks in the
    configuration file or through command line options (-j).
    """

    def __init__(self, options=None):
        max_workers = config.getint(
            "jolt", "parallel_tasks",
            os.getenv("JOLT_PARALLEL_TASKS", 1 if options is None else options.jobs))
        super().__init__(
            options=options,
            max_workers=max_workers)

    def create(self, task, force=False):
        """ Create a LocalExecutor for the task. """
        return LocalExecutor(self, task, force_build=force)


class ConcurrentLocalExecutorFactory(ExecutorFactory):
    """
    A shared factory for local executors that are allowed to run concurrently.

    The factory cannot create any executors on its own. Instead, its executors
    are created by the ExecutorRegistry. The factory thread-pool is then used to
    run executors concurrently.
    """

    def __init__(self, options=None):
        max_workers = tools.Tools().thread_count()
        super().__init__(
            options=options,
            max_workers=max_workers)

    def create(self, task):
        raise NotImplementedError()


class NetworkExecutorFactory(ExecutorFactory):
    """
    Base class for executors that schedule task executions remotely in a build cluster.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def create(self, session, task):
        raise NotImplementedError()


def ensure_executor_return(func):
    """ Decorator to ensure that an executor is returned by factories. """

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
    """
    Base class for all execution strategies.

    An execution strategy is responsible for deciding which executor to create for each task.
    The decision is based on the type of task and the availability of the task's artifacts in
    local and remote caches.

    The strategy is also responsible for deciding if task requirements should be pruned
    from the build graph. This is done to avoid processing tasks that are not needed for the build.

    Strategies are selected by the user through command line options.

    """
    def create_executor(self, session, task):
        """
        Create an executor for the task.

        The method must be implemented by all execution strategies. It is responsible for
        creating an executor that is capable of running or processing the task. Creation
        of an executor should be delegated to the ExecutorRegistry which has the knowledge
        of all available executor factories.
        """
        raise NotImplementedError()

    def should_prune_requirements(self, task):
        """
        Return True if the task requirements should be pruned from the build graph.

        The method must be implemented by all execution strategies.
        """
        raise NotImplementedError()


class LocalStrategy(ExecutionStrategy, PruneStrategy):
    """
    Strategy for local builds.

    By default, the strategy schedules tasks for local execution, unless the task
    artifacts are available in the local cache. If available remotely, the strategy
    will create a downloader executor to download the artifacts.
    """

    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        """ Create an executor for the task. """

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
        """ Prune task requirements if possible """

        if task.is_alias() or not task.is_cacheable():
            return False
        if task.is_available_locally():
            return True
        if self.cache.download_enabled() and task.is_available_remotely():
            return True
        return False


class DownloadStrategy(ExecutionStrategy, PruneStrategy):
    """
    Strategy for downloading task artifacts.

    The strategy is used when the user has requested that task artifacts be downloaded.
    If the task artifacts are available in the local cache, the strategy will skip the
    task. If the task artifacts are available in the remote cache, the strategy will
    create a downloader executor to download the artifacts. If the task artifacts are
    not available in either cache, the strategy reports an error.
    """

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
    """
    Strategy for distributed network builds.

    By default, the strategy schedules tasks for remote execution, if there is no
    artifact available. Otherwise, artifacts are either uploaded or downloaded as
    needed.
    """

    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        """ Create an executor for the task. """

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
        """ Prune task requirements if possible """

        if task.is_alias() or not task.is_cacheable():
            return False
        if task.is_available_remotely():
            return True
        return False


class WorkerStrategy(ExecutionStrategy, PruneStrategy):
    """
    Strategy for worker builds.

    This strategy is used on workers when the user has requested a network build.
    It is similar to the LocalStrategy in that it will run tasks locally if no
    artifacts are available. However, if artifacts are available locally, the
    strategy will upload them to the remote cache.
    """

    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    @ensure_executor_return
    def create_executor(self, session, task):
        """ Create an executor for the task. """

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
        """ Prune task requirements if possible """

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
