from contextlib import contextmanager, ExitStack
import functools

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

    @contextmanager
    def task_run(self, task):
        yield


class TaskHookFactory(object):
    @staticmethod
    def register(cls):
        TaskHookRegistry.factories.append((cls, 0))
        TaskHookRegistry.factories.sort(key=lambda x: x[1])

    @staticmethod
    def register_with_prio(prio):
        def decorator(cls):
            TaskHookRegistry.factories.append((cls, prio))
            TaskHookRegistry.factories.sort(key=lambda x: x[1])
        return decorator

    def create(self, env):
        raise NotImplementedError()


@utils.Singleton
class TaskHookRegistry(object):
    factories = []

    def __init__(self, env=None):
        self.env = env
        self.hooks = [factory().create(env) for factory, _ in TaskHookRegistry.factories]
        self.hooks = list(filter(lambda n: n, self.hooks))

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

    @contextmanager
    def task_run(self, task):
        tasks = [task] if type(task) != list else task
        with ExitStack() as stack:
            for task in tasks:
                if task.is_resource():
                    continue
                for ext in self.hooks:
                    stack.enter_context(ext.task_run(task))
            yield


class CliHook(object):
    @contextmanager
    def cli_build(self, *args, **kwargs):
        yield


class CliHookFactory(object):
    @staticmethod
    def register(cls):
        CliHookRegistry.factories.append(cls)

    def create(self, env):
        raise NotImplementedError()


@utils.Singleton
class CliHookRegistry(object):
    factories = []

    def __init__(self, env=None):
        self.env = env
        self.hooks = [factory().create(env) for factory in CliHookRegistry.factories]
        self.hooks = list(filter(lambda n: n, self.hooks))

    @contextmanager
    def cli_build(self, *args, **kwargs):
        with ExitStack() as stack:
            for ext in self.hooks:
                stack.enter_context(ext.cli_build(*args, **kwargs))
            yield


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


def task_run(task):
    return TaskHookRegistry.get().task_run(task)


def cli_build(cmd):
    @functools.wraps(cmd)
    def decorator(*args, **kwargs):
        with CliHookRegistry.get().cli_build():
            return cmd(*args, **kwargs)
    return decorator
