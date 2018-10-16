import sys
import inspect
import cache
import log
import utils


class Executor(object):
    def run(self, task):
        pass


class LocalExecutor(Executor):
    def __init__(self, cache, force_upload=False):
        super(LocalExecutor, self).__init__()
        self.cache = cache
        self.force_upload = force_upload
        
    def run(self, task):
        task.run(self.cache, self.force_upload)


class NetworkExecutor(Executor):
    pass


@utils.Singleton
class ExecutorRegistry(object):
    executor_factories = []
    extension_factories = []

    def __init__(self, network=True):
        self._factories = [factory() for factory in self.__class__.executor_factories]
        self._extensions = [factory().create() for factory in self.__class__.extension_factories]
        self._network = network

    def create(self, cache, task):
        for factory in self._factories:
            if not task.is_cacheable() and factory.is_network():
                continue
            if not self._network and factory.is_network():
                continue
            if self._network and not factory.is_network():
                if task.is_cacheable():
                    continue
            if factory.is_eligable(cache, task):
                return factory.create(cache)
        return None

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

    def is_network(self):
        return False
    
    def is_eligable(self, cache, task):
        raise NotImplemented()

    def create(self, cache):
        raise NotImplemented()


    
    
@ExecutorFactory.Register
class LocalExecutorFactory(ExecutorFactory):
    def is_network(self):
        return False

    def is_eligable(self, cache, task):
        return True

    def create(self, cache):
        return LocalExecutor(cache)


class NetworkExecutorFactory(ExecutorFactory):
    def is_network(self):
        return True

    def is_eligable(self, cache, task):
        return True

