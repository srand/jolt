from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
try:
    import asyncio
    has_asyncio = True
except:
    has_asyncio = False


from jolt import log
from jolt import utils
from jolt.options import JoltOptions
from jolt.manifest import ManifestExtension
from jolt.manifest import ManifestExtensionRegistry
from jolt.error import raise_error
from jolt.error import raise_task_error_if


class JoltEnvironment(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TaskQueue(object):
    def __init__(self, strategy):
        self.futures = {}
        self.strategy = strategy
        self.duration_acc = utils.duration_diff(0)
        self._aborted = False

    def submit(self, cache, task):
        if self._aborted:
            return None

        env = JoltEnvironment(cache=cache)
        executor = self.strategy.create_executor(task)
        raise_task_error_if(
            not executor, task,
            "no executor can execute the task; "
            "requesting a distributed network build without proper configuration?")

        task.set_in_progress()
        future = executor.submit(env)
        self.futures[future] = task
        return future

    def wait(self):
        for future in as_completed(self.futures):
            task = self.futures[future]
            try:
                future.result()
            except Exception as error:
                log.exception()
                return task, error
            finally:
                self.duration_acc += task.duration_running or 0
                del self.futures[future]
            return task, None
        return None, None

    def abort(self):
        self._aborted = True
        for future, task in self.futures.items():
            task.info("Execution cancelled")
            future.cancel()
        if len(self.futures):
            log.info("Waiting for tasks to finish, please be patient")
        self.strategy.executors.shutdown()

    def is_aborted(self):
        return self._aborted

    def in_progress(self, task):
        return task in self.futures.values()


class Executor(object):
    def __init__(self, factory):
        self.factory = factory

    def submit(self, env):
        return self.factory.submit(self, env)

    def is_aborted(self):
        return self.factory.is_aborted()

    def run(self, env):
        pass


class LocalExecutor(Executor):
    def __init__(self, factory, task, force_upload=False):
        super(LocalExecutor, self).__init__(factory)
        self.task = task
        self.force_upload = force_upload

    def run(self, env):
        if has_asyncio:
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)

        try:
            self.task.started()
            self.task.running()
            self.task.run(env.cache, self.force_upload)
        except Exception as e:
            self.task.failed()
            log.exception()
            raise e
        else:
            self.task.finished()
        return self.task


class NetworkExecutor(Executor):
    pass


class SkipTask(Executor):
    def __init__(self, factory, task, *args, **kwargs):
        super(SkipTask, self).__init__(factory, *args, **kwargs)
        self.task = task

    def run(self, env):
        self.task.skipped()
        for ext in self.task.extensions:
            ext.skipped()
        return self.task


class Downloader(Executor):
    def __init__(self, factory, task, *args, **kwargs):
        super(Downloader, self).__init__(factory, *args, **kwargs)
        self.task = task

    def _download(self, env, task):
        try:
            task.started("Download")
            raise_task_error_if(
                not env.cache.download(task),
                task, "failed to download task artifact")
        except Exception as e:
            task.failed("Download")
            raise e
        else:
            task.finished("Download")

    def run(self, env):
        self._download(env, self.task)
        for ext in self.task.extensions:
            self._download(env, ext)
        return self.task


class Uploader(Executor):
    def __init__(self, factory, task, *args, **kwargs):
        super(Uploader, self).__init__(factory, *args, **kwargs)
        self.task = task

    def _upload(self, env, task):
        try:
            task.started("Upload")
            raise_task_error_if(
                not env.cache.upload(task),
                task, "failed to upload task artifact")
        except Exception as e:
            task.failed("Upload")
            raise e
        else:
            task.finished("Upload")

    def run(self, env):
        self._upload(env, self.task)
        for ext in self.task.extensions:
            self._upload(env, ext)

        return self.task


@utils.Singleton
class ExecutorRegistry(object):
    executor_factories = []
    extension_factories = []

    def __init__(self, options=None):
        self._options = options or JoltOptions()
        self._factories = [factory(self._options) for factory in self.__class__.executor_factories]
        self._local_factory = LocalExecutorFactory(self._options)
        self._extensions = [factory().create() for factory in self.__class__.extension_factories]

    def shutdown(self):
        for factory in self._factories:
            factory.shutdown()

    def create_skipper(self, task):
        return SkipTask(self._local_factory, task)

    def create_downloader(self, task):
        return Downloader(self._local_factory, task)

    def create_uploader(self, task):
        return Uploader(self._local_factory, task)

    def create_local(self, task):
        return self._local_factory.create(task)

    def create_network(self, task):
        for factory in self._factories:
            executor = factory.create(task)
            if executor is not None:
                return executor
        return self._local_factory.create(task)

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
        raise NotImplemented()


class NetworkExecutorExtension(object):
    def get_parameters(self, task):
        return {}


class ExecutorFactory(object):
    @staticmethod
    def Register(cls):
        ExecutorRegistry.executor_factories.insert(0, cls)
        return cls

    def __init__(self, max_workers=None):
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self._aborted = False

    def is_aborted(self):
        return self._aborted

    def shutdown(self):
        self._aborted = True
        self.pool.shutdown()

    def create(self, task):
        raise NotImplemented()

    def _run(self, executor, env):
        try:
            if not self.is_aborted():
                executor.run(env)
        except KeyboardInterrupt:
            raise_error("Interrupted by user")

    def submit(self, executor, env):
        return self.pool.submit(partial(self._run, executor, env))



class LocalExecutorFactory(ExecutorFactory):
    def __init__(self, options=None):
        super(LocalExecutorFactory, self).__init__(max_workers=1)
        self._options = options or JoltOptions()

    def create(self, task):
        return LocalExecutor(self, task)


class NetworkExecutorFactory(ExecutorFactory):
    def __init__(self, *args, **kwargs):
        super(NetworkExecutorFactory, self).__init__(*args, **kwargs)


class ExecutionStrategy(object):
    def create_executor(self, task):
        raise NotImplemented()


class LocalStrategy(ExecutionStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    def create_executor(self, task):
        if not task.is_cacheable():
            return self.executors.create_local(task)
        if task.is_available_locally(self.cache):
            return self.executors.create_skipper(task)
        if self.cache.download_enabled() and task.is_available_remotely(self.cache):
            return self.executors.create_downloader(task)
        return self.executors.create_local(task)


class DistributedStrategy(ExecutionStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    def create_executor(self, task):
        if task.is_resource():
            return self.executors.create_local(task)

        if not task.is_cacheable():
            return self.executors.create_network(task)

        # Check remote availability first so that the availability of
        # remote storage providers is made known when checking if
        # artifacts can be downloaded or not.
        remote = task.is_available_remotely(self.cache)

        if not self.cache.download_enabled():
            if not task.is_available_locally(self.cache):
                return self.executors.create_local(task)
            else:
                return self.executors.create_skipper(task)

        if remote:
            if not task.is_available_locally(self.cache):
                return self.executors.create_downloader(task)
            else:
                return self.executors.create_skipper(task)

        if task.is_available_locally(self.cache):
            if self.cache.upload_enabled():
                if task.is_uploadable(self.cache):
                    return self.executors.create_uploader(task)
                else:
                    return self.executors.create_network(task)
            else:
                return self.executors.create_skipper(task)

        if task.is_fast():
            if not self.cache.upload_enabled():
                return self.executors.create_network(task)
            else:
                return self.executors.create_local(task)

        return self.executors.create_network(task)


class WorkerStrategy(ExecutionStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    def create_executor(self, task):
        if task.is_resource():
            return self.executors.create_local(task)

        raise_task_error_if(
            not self.cache.upload_enabled(), task,
            "artifact upload must be enabled for workers, fix configuration")

        if not task.is_cacheable():
            return self.executors.create_local(task)

        if task.is_available_locally(self.cache):
            if not task.is_available_remotely(self.cache):
                return self.executors.create_uploader(task)
            else:
                return self.executors.create_skipper(task)

            return self.executors.create_downloader(task)

        if not self.cache.download_enabled():
            return self.executors.create_local(task)

        if task.is_available_remotely(self.cache):
            return self.executors.create_downloader(task)

        return self.executors.create_local(task)



class TaskIdentityExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        for child in [task] + task.descendants:
            manifest_task = manifest.find_task(child.qualified_name)
            if manifest_task is None:
                manifest_task = manifest.create_task()
                manifest_task.name = child.qualified_name
            manifest_task.identity = child.identity

ManifestExtensionRegistry.add(TaskIdentityExtension())


class TaskExportExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        for child in [task] + task.children:
            manifest_task = manifest.find_task(child.qualified_name)
            if manifest_task is None:
                manifest_task = manifest.create_task()
                manifest_task.name = child.qualified_name
            for key, export in child.task._get_export_objects().items():
                attrib = manifest_task.create_attribute()
                attrib.name = key
                attrib.value = export.export(child.task)

ManifestExtensionRegistry.add(TaskExportExtension())
