from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from functools import partial
import traceback
import sys
import inspect
try:
    import asyncio
    has_asyncio = True
except:
    has_asyncio = False


from jolt import cache
from jolt import log
from jolt import utils
from jolt.options import JoltOptions


class JoltEnvironment(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TaskQueue(object):
    def __init__(self, strategy):
        self.futures = {}
        self.strategy = strategy

    def submit(self, cache, task):
        env = JoltEnvironment(cache=cache)
        executor = self.strategy.create_executor(task)
        assert executor, "no executor can execute the task; "\
            "requesting a network build without proper configuration?"

        task.set_in_progress()
        future = executor.submit(env)
        self.futures[future] = task
        return future

    def wait(self):
        for future in as_completed(self.futures):
            task = self.futures[future]
            try:
                result = future.result()
            except Exception as error:
                log.exception()
                return task, error
            finally:
                del self.futures[future]
            return task, None
        return None, None

    def abort(self):
        for future, task in self.futures.items():
            task.info("Execution cancelled")
            future.cancel()
        if len(self.futures):
            log.info("Waiting for tasks to finish")
        self.strategy.executors.shutdown()

    def in_progress(self, task):
        return task in self.futures.values()


class Executor(object):
    def __init__(self, factory):
        self.factory = factory

    def submit(self, env):
        return self.factory.submit(self, env)

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
            assert env.cache.download(task), \
                "failed to download artifact of task '{0} ({1})'"\
                .format(task.qualified_name, task.identity[:8])
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
            assert env.cache.upload(task), \
                "failed to upload artifact of task '{0} ({1})'"\
                .format(task.qualified_name, task.identity[:8])
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
        self._factories = [factory() for factory in self.__class__.executor_factories]
        self._local_factory = LocalExecutorFactory()
        self._extensions = [factory().create() for factory in self.__class__.extension_factories]
        self._options = options or JoltOptions()

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
        # assert cls is Factory
        ExecutorRegistry.extension_factories.insert(0, cls)

    def create(self):
        raise NotImplemented()


class NetworkExecutorExtension(object):
    def get_parameters(self, task):
        return {}


class ExecutorFactory(object):
    @staticmethod
    def Register(cls):
        # assert cls is Factory
        ExecutorRegistry.executor_factories.insert(0, cls)

    def __init__(self, num_workers=None):
        self.pool = ThreadPoolExecutor(max_workers=num_workers)

    def shutdown(self):
        self.pool.shutdown()

    def create(self, task):
        raise NotImplemented()

    def submit(self, executor, env):
        return self.pool.submit(partial(executor.run, env))



class LocalExecutorFactory(ExecutorFactory):
    def __init__(self):
        super(LocalExecutorFactory, self).__init__(num_workers=1)

    def create(self, task):
        return LocalExecutor(self, task)


class NetworkExecutorFactory(ExecutorFactory):
    pass


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

        assert False, "unable to determine execution strategy for task '{0} ({1})'"\
            .format(task.qualified_name, task.identity[:8])


class DistributedStrategy(ExecutionStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    def create_executor(self, task):
        if task.is_resource():
            return self.executors.create_local(task)

        if not task.is_cacheable():
            return self.executors.create_network(task)

        if not self.cache.download_enabled():
            if not task.is_available_locally(self.cache):
                return self.executors.create_local(task)
            else:
                return self.executors.create_skipper(task)

        if task.is_available_remotely(self.cache):
            if not task.is_available_locally(self.cache):
                return self.executors.create_downloader(task)
            else:
                return self.executors.create_skipper(task)

        if self.cache.upload_enabled() and task.is_available_locally(self.cache):
            return self.executors.create_uploader(task)

        return self.executors.create_network(task)

        assert False, "unable to determine execution strategy for task '{0} ({1})'"\
            .format(task.qualified_name, task.identity[:8])


class WorkerStrategy(ExecutionStrategy):
    def __init__(self, executors, cache):
        self.executors = executors
        self.cache = cache

    def create_executor(self, task):
        if task.is_resource():
            return self.executors.create_local(task)

        assert self.cache.upload_enabled(),\
            "artifact upload must be enabled for workers, fix configuration"

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

        assert False, "unable to determine execution strategy for task '{0} ({1})'"\
            .format(task.qualified_name, task.identity[:8])
