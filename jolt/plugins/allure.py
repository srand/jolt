import jolt
from jolt import filesystem as fs
from jolt import log
from jolt import utils
import time

import allure
import allure_commons
from allure_commons import plugin_manager
from allure_commons.logger import AllureFileLogger
from allure_commons.lifecycle import AllureLifecycle
from allure_commons.model2 import Attachment
from allure_commons.model2 import Status
from allure_commons.model2 import StatusDetails
from allure_commons.model2 import Label
from allure_commons.types import AttachmentType
from allure_commons.types import LabelType
from allure_commons.utils import host_tag, thread_tag
from allure_commons.utils import platform_label, md5
from allure_commons.utils import format_traceback
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
            self._task.tools.write_file(logpath, content)
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
            result.start = time.time()*1000
            result.fullName = self._task.__class__.__name__ + "." + name
            result.testCaseId = utils.sha1(result.fullName)
            result.historyId = utils.sha1(self._task.identity + result.testCaseId)
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
                    result.stop = time.time()*1000
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
