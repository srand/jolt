from contextlib import contextmanager, ExitStack
import functools

from jolt import utils


class TaskHook(object):
    def task_created(self, task):
        pass

    def task_queued(self, task):
        pass

    def task_started(self, task):
        pass

    def task_started_download(self, task):
        """ Called after task_started, if the task artifact is being downloaded """

    def task_started_execution(self, task):
        """ Called after task_started, if the task is being executed """

    def task_started_upload(self, task):
        """ Called after task_started, if the task artifact is being uploaded """

    def task_finished(self, task):
        """ Called for all tasks that finish successfully
        (executed, uploaded, downloaded) """

    def task_finished_download(self, task):
        """ Called before task_finished, if the task artifact was downloaded """

    def task_finished_execution(self, task):
        """ Called before task_finished, if the task artifact was executed """

    def task_finished_upload(self, task):
        """ Called before task_finished, if the task artifact was uploaded """

    def task_failed(self, task):
        pass

    def task_unstable(self, task):
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

    def task_queued(self, task):
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_queued, task)

    def task_started(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_started, task)

    def task_started_download(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_started_download, task)

    def task_started_execution(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_started_execution, task)

    def task_started_upload(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_started_upload, task)

    def task_finished(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_finished, task)

    def task_finished_download(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_finished_download, task)

    def task_finished_execution(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_finished_execution, task)

    def task_finished_upload(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_finished_upload, task)

    def task_failed(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_failed, task)

    def task_unstable(self, task):
        if task.is_resource():
            return
        for ext in self.hooks:
            utils.call_and_catch_and_log(ext.task_unstable, task)

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
        tasks = [task] if type(task) is not list else task
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

    @contextmanager
    def cli_clean(self, *args, **kwargs):
        yield

    @contextmanager
    def cli_download(self, *args, **kwargs):
        yield

    @contextmanager
    def cli_report(self, *args, **kwargs):
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

    @contextmanager
    def cli_clean(self, *args, **kwargs):
        with ExitStack() as stack:
            for ext in self.hooks:
                stack.enter_context(ext.cli_clean(*args, **kwargs))
            yield

    @contextmanager
    def cli_download(self, *args, **kwargs):
        with ExitStack() as stack:
            for ext in self.hooks:
                stack.enter_context(ext.cli_download(*args, **kwargs))
            yield

    @contextmanager
    def cli_report(self, *args, **kwargs):
        with ExitStack() as stack:
            for ext in self.hooks:
                stack.enter_context(ext.cli_report(*args, **kwargs))
            yield


def task_created(task):
    TaskHookRegistry.get().task_created(task)


def task_queued(task):
    TaskHookRegistry.get().task_queued(task)


def task_started(task):
    TaskHookRegistry.get().task_started(task)


def task_started_download(task):
    TaskHookRegistry.get().task_started_download(task)


def task_started_execution(task):
    TaskHookRegistry.get().task_started_execution(task)


def task_started_upload(task):
    TaskHookRegistry.get().task_started_upload(task)


def task_failed(task):
    TaskHookRegistry.get().task_failed(task)


def task_unstable(task):
    TaskHookRegistry.get().task_unstable(task)


def task_finished(task):
    TaskHookRegistry.get().task_finished(task)


def task_finished_download(task):
    TaskHookRegistry.get().task_finished_download(task)


def task_finished_execution(task):
    TaskHookRegistry.get().task_finished_execution(task)


def task_finished_upload(task):
    TaskHookRegistry.get().task_finished_upload(task)


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


def cli_clean(cmd):
    @functools.wraps(cmd)
    def decorator(*args, **kwargs):
        with CliHookRegistry.get().cli_clean():
            return cmd(*args, **kwargs)
    return decorator


def cli_download(cmd):
    @functools.wraps(cmd)
    def decorator(*args, **kwargs):
        with CliHookRegistry.get().cli_download():
            return cmd(*args, **kwargs)
    return decorator


def cli_report(cmd):
    @functools.wraps(cmd)
    def decorator(*args, **kwargs):
        with CliHookRegistry.get().cli_report():
            return cmd(*args, **kwargs)
    return decorator
