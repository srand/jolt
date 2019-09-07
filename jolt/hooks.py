from jolt import utils


class TaskHook(object):
    def task_created(self, task):
        pass

    def task_started(self, task):
        pass

    def task_finished(self, task):
        pass

    def task_failed(self, task):
        pass



class TaskHookFactory(object):
    @staticmethod
    def register(cls):
        TaskHookRegistry.factories.append(cls)

    def create(self, env):
        raise NotImplementedError()


@utils.Singleton
class TaskHookRegistry(object):
    factories = []

    def __init__(self, env=None):
        self.env = env
        self.hooks = [factory().create(env) for factory in TaskHookRegistry.factories]

    def task_created(self, task):
        if self.env and not self.env.worker:
            for ext in self.hooks:
                utils.call_and_catch(ext.task_created, task)

    def task_started(self, task):
        if self.env and not self.env.worker:
            for ext in self.hooks:
                utils.call_and_catch(ext.task_started, task)

    def task_finished(self, task):
        if self.env and not self.env.worker:
            for ext in self.hooks:
                utils.call_and_catch(ext.task_finished, task)

    def task_failed(self, task):
        if self.env and not self.env.worker:
            for ext in self.hooks:
                utils.call_and_catch(ext.task_failed, task)


def task_created(task):
    TaskHookRegistry.get().task_created(task)

def task_started(task):
    TaskHookRegistry.get().task_started(task)

def task_failed(task):
    TaskHookRegistry.get().task_failed(task)

def task_finished(task):
    TaskHookRegistry.get().task_finished(task)
