import jolt
from jolt import config
from jolt.error import raise_error_if
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.hooks import TaskHook, TaskHookFactory
from jolt.loader import JoltLoader
import time

try:
    from allure_commons.logger import AllureFileLogger
    from allure_commons.lifecycle import AllureLifecycle
    from allure_commons.model2 import Attachment
    from allure_commons.model2 import Status
    from allure_commons.model2 import StatusDetails
    from allure_commons.model2 import Label
    from allure_commons.types import LabelType
    from allure_commons.utils import host_tag, thread_tag
    from allure_commons.utils import platform_label
    from allure_commons.utils import format_traceback
except ImportError:
    import os
    log.error("Allure plugin enabled but not installed. Install it with: pip install jolt[allure]")
    os._exit(1)

from contextlib import contextmanager
import unittest as ut


__unittest = True


class _ReporterTest(object):
    def __init__(self, reporter, result):
        self._reporter = reporter
        self._task = self._reporter._task
        self._outdirfull = self._reporter._outdirfull
        self._result = result

    def attach(self, name, content, mime_type=None):
        with self._task.tools.cwd(self._outdirfull):
            logpath = utils.sha1(content) + "-" + name
            self._task.tools.write_file(logpath, content, expand=False)
            self._result.attachments.append(
                Attachment(source=logpath, name=name, type=mime_type))

    @contextmanager
    def step(self, desc, *args, **kwargs):
        with self._reporter._lifecycle.start_step() as step:
            step.name = desc

        with log.threadsink() as steplog:
            reporter = _ReporterTest(self._reporter, step)
            try:
                yield reporter
            except ut.SkipTest as e:
                with self._reporter._lifecycle.update_step() as step:
                    step.status = Status.SKIPPED
                    step.statusDetails = StatusDetails(message=str(e))
                    raise e
            except AssertionError as e:
                with self._reporter._lifecycle.update_step() as step:
                    step.status = Status.FAILED
                    step.statusDetails = StatusDetails(message=str(e))
                    raise e
            except Exception as e:
                with self._reporter._lifecycle.update_step() as step:
                    step.status = Status.BROKEN
                    step.statusDetails = StatusDetails(message=str(e))
                    raise e
            else:
                with self._reporter._lifecycle.update_step() as step:
                    step.status = Status.PASSED
            finally:
                # Attach log
                if steplog.getvalue():
                    reporter.attach("log", steplog.getvalue(), "text/plain")
                self._reporter._lifecycle.stop_step()


class Reporter(object):
    def __init__(self, task, builddir=None, results="allure-results"):
        self._host = host_tag()
        self._thread = thread_tag()
        self._task = task
        self._lifecycle = AllureLifecycle()
        self.outdir = builddir or self._task.tools.builddir("allure")
        with self._task.tools.cwd(self.outdir):
            self._outdirfull = self._task.tools.expand_path("allure-results")
        self._logger = AllureFileLogger(self._outdirfull)

    @contextmanager
    def test(self, name, description=None, suite=None):
        with self._lifecycle.schedule_test_case() as result:
            result.name = name
            result.start = time.time() * 1000
            result.fullName = self._task.__class__.__name__ + "." + name
            result.testCaseId = utils.sha1(result.fullName)
            result.historyId = utils.sha1(self._task.qualified_name + result.testCaseId)
            result.description = description
            result.labels.append(Label(name=LabelType.HOST, value=self._host))
            result.labels.append(Label(name=LabelType.THREAD, value=self._thread))
            result.labels.append(Label(name=LabelType.FRAMEWORK, value='jolt'))
            result.labels.append(Label(name=LabelType.LANGUAGE, value=platform_label()))
            if suite:
                result.labels.append(Label(name=LabelType.SUITE, value=suite))
        with log.threadsink() as testlog:
            reporter = _ReporterTest(self, result)
            try:
                yield reporter
            except ut.SkipTest as e:
                result.status = Status.SKIPPED
                result.statusDetails = StatusDetails(message=str(e))
                raise e
            except AssertionError as e:
                with self._lifecycle.update_test_case() as result:
                    result.status = Status.FAILED
                    result.statusDetails = StatusDetails(
                        message=str(e),
                        trace=format_traceback(e.__traceback__))
                    raise e
            except Exception as e:
                with self._lifecycle.update_test_case() as result:
                    result.status = Status.BROKEN
                    result.statusDetails = StatusDetails(
                        message=str(e),
                        trace=format_traceback(e.__traceback__))
                    raise e
            else:
                with self._lifecycle.update_test_case() as result:
                    result.status = Status.PASSED
                    result.statusDetails = StatusDetails()
            finally:
                if testlog.getvalue():
                    reporter.attach("log", testlog.getvalue(), "text/plain")
                with self._lifecycle.update_test_case() as result:
                    result.stop = time.time() * 1000
                self._lifecycle.write_test_case()
                self._logger.report_result(result)

    @contextmanager
    def update_test(self):
        with self._lifecycle.update_test_case() as test:
            yield test

    def publish(self, artifact):
        with self._task.tools.cwd(self.outdir):
            artifact.collect("*")


class Test(jolt.Test):
    def __init__(self, *args, **kwargs):
        super(Test, self).__init__(*args, **kwargs)
        self._curresult = None
        self._host = host_tag()
        self._thread = thread_tag()

    def _run(self, test):
        with self.reporter.test(test.name, test.__doc__, suite=self.short_qualified_name) as result:
            self._curresult = result
            try:
                super()._run(test)
            finally:
                self._curresult = None

    def run(self, deps, tools):
        self.reporter = Reporter(self)
        super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        self.reporter.publish(artifact)

    @contextmanager
    def step(self, name, description=None):
        assert self._curresult, "can't add step when no test is running"
        with self._curresult.step(name, description) as step:
            yield step


class AllureHooks(TaskHook):
    LOGLEVEL = {
        "INFO": log.INFO,
        "VERBOSE": log.VERBOSE,
        "DEBUG": log.DEBUG,
    }

    def __init__(self):
        loglevel = config.get("allure", "loglevel", "INFO")
        self._loglevel = AllureHooks.LOGLEVEL.get(loglevel)
        raise_error_if(not self._loglevel, "allure: illegal loglevel configured: {}", loglevel)
        self._logpath = fs.path.join(JoltLoader.get().joltdir, config.get("allure", "path", "allure-results"))
        fs.rmtree(self._logpath, ignore_errors=True)
        fs.makedirs(self._logpath)
        self._logger = AllureFileLogger(self._logpath)

    def _task_started(self, task):
        task.allure_lifecycle = AllureLifecycle()
        with task.allure_lifecycle.schedule_test_case() as result:
            result.name = task.short_qualified_name
            result.start = time.time() * 1000
            result.fullName = task.qualified_name
            result.description = task.task.__doc__
            result.testCaseId = utils.sha1(result.fullName)
            result.historyId = utils.sha1(task.qualified_name + result.testCaseId)
            result.labels.append(Label(name=LabelType.HOST, value=host_tag()))
            result.labels.append(Label(name=LabelType.THREAD, value=thread_tag()))
            result.labels.append(Label(name=LabelType.FRAMEWORK, value='jolt'))
            result.labels.append(Label(name=LabelType.LANGUAGE, value=platform_label()))
        task.allure_logsink = log.threadsink(self._loglevel)
        task.allure_logsink_buffer = task.allure_logsink.__enter__()

    def _task_ended(self, task, status):
        task.allure_logsink.__exit__(None, None, None)
        with task.allure_lifecycle.update_test_case() as result:
            with task.tools.cwd(self._logpath):
                content = task.allure_logsink_buffer.getvalue()
                if content:
                    logpath = utils.sha1(content) + "-" + "log"
                    task.tools.write_file(logpath, content, expand=False)
                    result.attachments.append(
                        Attachment(source=logpath, name="log", type="text/plain"))
            result.status = status
            if status != Status.SKIPPED:
                result.stop = time.time() * 1000
            else:
                result.start = None
                result.stop = None
            task.allure_lifecycle.write_test_case()
            self._logger.report_result(result)

    def task_started(self, task):
        self._task_started(task)

    def task_failed(self, task):
        self._task_ended(task, Status.FAILED)

    def task_unstable(self, task):
        self.task_failed(task)

    def task_finished(self, task):
        self._task_ended(task, Status.PASSED)

    def task_skipped(self, task):
        self._task_started(task)
        self._task_ended(task, Status.SKIPPED)


@TaskHookFactory.register
class AllureFactory(TaskHookFactory):
    def create(self, env):
        if "allure" in config.plugins():
            return AllureHooks()
        return None
