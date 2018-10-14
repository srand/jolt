import sys
import inspect
import cache
import log
import utils


class Executor(object):
    def run(self, task):
        pass


class LocalExecutor(Executor):
    def __init__(self, cache):
        super(LocalExecutor, self).__init__()
        self.cache = cache
        
    def run(self, task):
        task.run(self.cache)


class ExecutorRegistry(object):
    executor_factories = []

    def __init__(self, network=True):
        self._factories = [factory() for factory in self.__class__.executor_factories]
        self._network = network

    def create(self, cache, task):
        for factory in self._factories:
            if not task.is_cacheable() and factory.is_network():
                continue
            if not self._network and factory.is_network():
                continue
            if self._network and not factory.is_network():
                continue
            if factory.is_eligable(cache, task):
                return factory.create(cache)
        return None


def RegisterExecutor(cls):
    # assert cls is Factory
    ExecutorRegistry.executor_factories.insert(0, cls)


class ExecutorFactory(object):
    def is_network(self):
        return False
    
    def is_eligable(self, cache, task):
        raise NotImplemented()

    def create(self, cache):
        raise NotImplemented()
    
    
@RegisterExecutor
class LocalExecutorFactory(ExecutorFactory):
    def is_network(self):
        return False

    def is_eligable(self, cache, task):
        return True

    def create(self, cache):
        return LocalExecutor(cache)
