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

    def task_pruned(self, task):
        pass

    def task_skipped(self, task):
        pass

    def task_prerun(self, task, deps, tools):
        pass

    def task_prepublish(self, task, artifact, tools):
        pass

    def task_prenunpack(self, task, artifact, tools):
        pass

    def task_postrun(self, task, deps, tools):
        pass

    def task_postpublish(self, task, artifact, tools):
        pass

    def task_postunpack(self, task, artifact, tools):
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
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_created, task)

    def task_started(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_started, task)

    def task_finished(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_finished, task)

    def task_failed(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_failed, task)

    def task_pruned(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_pruned, task)

    def task_skipped(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_skipped, task)

    def task_prerun(self, task, deps, tools):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_prerun, task, deps, tools)

    def task_prepublish(self, task, artifact, tools):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_prepublish, task, artifact, tools)

    def task_preunpack(self, task, artifact, tools):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_preunpack, task, artifact, tools)

    def task_postrun(self, task, deps, tools):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_postrun, task, deps, tools)

    def task_postpublish(self, task, artifact, tools):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_postpublish, task, artifact, tools)

    def task_postunpack(self, task, artifact, tools):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_postunpack, task, artifact, tools)


def task_created(task):
    TaskHookRegistry.get().task_created(task)

def task_started(task):
    TaskHookRegistry.get().task_started(task)

def task_failed(task):
    TaskHookRegistry.get().task_failed(task)

def task_finished(task):
    TaskHookRegistry.get().task_finished(task)

def task_pruned(task):
    TaskHookRegistry.get().task_pruned(task)

def task_skipped(task):
    TaskHookRegistry.get().task_skipped(task)

def task_prerun(task, deps, tools):
    TaskHookRegistry.get().task_prerun(task, deps, tools)

def task_prepublish(task, artifact, tools):
    TaskHookRegistry.get().task_prepublish(task, artifact, tools)

def task_preunpack(task, artifact, tools):
    TaskHookRegistry.get().task_preunpack(task, artifact, tools)

def task_postrun(task, deps, tools):
    TaskHookRegistry.get().task_postrun(task, deps, tools)

def task_postpublish(task, artifact, tools):
    TaskHookRegistry.get().task_postpublish(task, artifact, tools)

def task_postunpack(task, artifact, tools):
    TaskHookRegistry.get().task_postunpack(task, artifact, tools)
