"""
This module provides the :class:`GTestRunner` task base class, a derivation
of :class:`jolt.tasks.Runner` for running Google Test applications.
Several parameters can be assigned or overidden to control the behavior.

Example:

  .. literalinclude:: ../examples/googletest/runner.jolt
    :language: python
    :caption: examples/googletest/runner.jolt

The module also provides a set of task decorators for use with standalone
task classes. They set different ``GTEST_*`` environment variables to control
the behavior of Google Test executables in the same manner as the parameters in
:class:`GTestRunner` do.


Example:

  .. code-block:: python

    from jolt import Task
    from jolt.plugins import googletest

    # ....

    @googletest.fail_fast(default=True)
    @googletest.repeat(default=10)
    @googletest.filter()
    @googletest.junit_report()
    class TestRunner(Task):
        requires = ["test"]

        def run(self, deps, tools):
            tools.run("unittest")

  .. code-block:: bash

    $ jolt build testrunner:repeat=1,filter=TestModule.*

"""

from functools import wraps
from os import path
import json

from jolt import BooleanParameter, IntParameter, Parameter, Runner
from jolt import influence
from jolt.error import raise_task_error, raise_task_error_if
from jolt.plugins import junit
from jolt.utils import deprecated, ignore_exception


@deprecated
def import_failures(xml, report):
    return junit.import_junit_report(xml, report, errors=True, failures=True)


def break_on_failure(default: bool = False, param: bool = True, attr: str = "break_on_failure"):
    """
    Task class decorator controlling the GTEST_BREAK_ON_FAILURE environment variable.

    When the variable is set, test applications failures trigger breakpoints. On Linux,
    this typically results in a core dump that can be loaded into the debugger.

    The value is taken from the parameter ``break_on_failure`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            with tools.environ(GTEST_BREAK_ON_FAILURE=str(int(bool(getattr(self, attr, default))))):
                _old_run(self, deps, tools)

        if param:
            break_on_failure_param = BooleanParameter(default, help="Trigger breakpoint on failures.")
            break_on_failure_param.__set_name__(cls, attr)
            setattr(cls, attr, break_on_failure_param)

        cls.run = run
        return influence.source("googletest.break_on_failure", break_on_failure)(cls)

    return decorator


def brief(default: bool = False, param: bool = True, attr: str = "brief"):
    """
    Task class decorator controlling the GTEST_BRIEF environment variable.

    When the variable is set, only failed test-cases are logged.

    The value is taken from the parameter ``brief`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    GoogleTest version >= 1.11 is required.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            with tools.environ(GTEST_BRIEF=str(int(bool(getattr(self, attr, default))))):
                _old_run(self, deps, tools)

        if param:
            brief_param = BooleanParameter(default, help="Only print failed test-cases.")
            brief_param.__set_name__(cls, attr)
            setattr(cls, attr, brief_param)

        cls.run = run
        return influence.source("googletest.brief", brief)(cls)

    return decorator


def disabled(default: bool = False, param: bool = True, attr: str = "disabled"):
    """
    Task class decorator controlling the GTEST_ALSO_RUN_DISABLED_TESTS environment variable.

    When the variable is set, disabled test-cases are also run.

    The value is taken from the parameter ``disabled`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            with tools.environ(GTEST_ALSO_RUN_DISABLED_TESTS=str(int(bool(getattr(self, attr, default))))):
                _old_run(self, deps, tools)

        if param:
            disabled_param = BooleanParameter(default, help="Also run disabled test-cases.")
            disabled_param.__set_name__(cls, attr)
            setattr(cls, attr, disabled_param)

        cls.run = run
        return influence.source("googletest.disabled", disabled)(cls)

    return decorator


def fail_fast(default: bool = False, param: bool = True, attr: str = "fail_fast"):
    """
    Task class decorator controlling the GTEST_FAIL_FAST environment variable.

    When the variable is set, test applications will abort when the first failure is found.

    The value is taken from the parameter ``fail_fast`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            with tools.environ(GTEST_FAIL_FAST=str(int(bool(getattr(self, attr, default))))):
                _old_run(self, deps, tools)

        if param:
            fail_fast_param = BooleanParameter(default, help="Stop when the first failure is found.")
            fail_fast_param.__set_name__(cls, attr)
            setattr(cls, attr, fail_fast_param)

        cls.run = run
        return influence.source("googletest.fail_fast", fail_fast)(cls)

    return decorator


def filter(default: str = "*", param: bool = True, attr: str = "filter"):
    """
    Task class decorator controlling the GTEST_FILTER environment variable.

    The variable instructs test applications to only run test-cases that matches
    a wildcard filter string (default: ``*``).

    The value is taken from the parameter ``filter`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            with tools.environ(GTEST_FILTER=str(getattr(self, attr, default))):
                _old_run(self, deps, tools)

        if param:
            filter_param = Parameter(default, help="Test-case filter")
            filter_param.__set_name__(cls, attr)
            setattr(cls, attr, filter_param)

        cls.run = run
        return influence.source("googletest.filter", filter)(cls)

    return decorator


def junit_report():
    """
    Decorator enabling JUnit test reporting in Google Test applications.

    The decorator sets the GTEST_OUTPUT environment, thereby instructing
    test applications to write a JUnit report file upon test completion.
    The task publishes the report in the task artifact under report/junit/.

    Any errors found in the report are parsed and attached to the task.
    They are included in email reports if the email plugin is enabled.
    """

    def decorator(cls):
        _old_run = cls.run
        _old_publish = cls.publish

        @wraps(cls.run)
        def run(self, deps, tools):
            raise_task_error_if(
                tools.getenv("GTEST_OUTPUT"),
                self,
                "GoogleTest output already enabled, cannot proceed with JUnit report setup")
            gtestdir = tools.builddir("gtest-junit-report")
            gtestreport = path.join(gtestdir, "report.xml")
            with tools.environ(GTEST_OUTPUT="xml:" + gtestreport):
                try:
                    _old_run(self, deps, tools)
                finally:
                    with ignore_exception(), self.report() as report:
                        junit.import_junit_report(gtestreport, report)

        @wraps(cls.publish)
        def publish(self, artifact, tools):
            _old_publish(self, artifact, tools)
            gtestdir = tools.builddir("gtest-junit-report")
            with tools.cwd(gtestdir):
                artifact.collect("*", "report/junit/")

        cls.run = run
        cls.publish = publish
        return influence.source("googletest.junit_report", junit_report)(cls)

    return decorator


def json_report():
    """
    Decorator enabling JSON test reporting in Google Test applications.

    The decorator sets the GTEST_OUTPUT environment, thereby instructing
    test applications to write a JSON report file upon test completion.
    The task publishes the report in the task artifact under report/json/.

    Any errors found in the report are parsed and attached to the task.
    They are included in email reports if the email plugin is enabled.
    """

    def decorator(cls):
        _old_run = cls.run
        _old_publish = cls.publish

        @wraps(cls.run)
        def run(self, deps, tools):
            raise_task_error_if(
                tools.getenv("GTEST_OUTPUT"),
                self,
                "GoogleTest output already enabled, cannot proceed with JSON report setup")
            gtestdir = tools.builddir("gtest-json-report")
            gtestreport = path.join(gtestdir, "report.json")
            with tools.environ(GTEST_OUTPUT="json:" + gtestreport):
                try:
                    _old_run(self, deps, tools)
                finally:
                    with ignore_exception(), self.report() as report:
                        with open(gtestreport) as fp:
                            json_report = json.load(fp)
                        for testsuite in json_report["testsuites"]:
                            for testcase in testsuite["testsuite"]:
                                failures = testcase.get("failures", [])
                                for failure in failures:
                                    name = f"{testsuite['name']}.{testcase['name']}"
                                    message = failure["failure"]
                                    report.add_error("Test Failed", name, message)

        @wraps(cls.publish)
        def publish(self, artifact, tools):
            _old_publish(self, artifact, tools)
            gtestdir = tools.builddir("gtest-json-report")
            with tools.cwd(gtestdir):
                artifact.collect("*", "report/json/")

        cls.run = run
        cls.publish = publish
        return influence.source("googletest.json_report", json_report)(cls)

    return decorator


def repeat(default: int = 1, param: bool = True, attr: str = "repeat"):
    """
    Task class decorator controlling the GTEST_REPEAT environment variable.

    The variable instructs test applications to repeat test-cases the specified
    number of times.

    The value is taken from the parameter ``repeat`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            try:
                repeat = int(getattr(self, attr, default))
            except ValueError:
                raise_task_error(self, f"Value assigned to '{attr}' is not an integer")
            with tools.environ(GTEST_REPEAT=str(repeat)):
                _old_run(self, deps, tools)

        if param:
            repeat_param = IntParameter(default, help="Test-case repetitions.")
            repeat_param.__set_name__(cls, attr)
            setattr(cls, attr, repeat_param)

        cls.run = run
        return influence.source("googletest.repeat", repeat)(cls)

    return decorator


def seed(default: int = 0, param: bool = True, attr: str = "seed"):
    """
    Task class decorator controlling the GTEST_RANDOM_SEED environment variable.

    The variable sets an initial value for the random number generator used to
    shuffle test-cases. In order to reproduce ordering issues, a user may assign
    a specific seed to get the same test-case order. The default value is 0
    which causes Google Test to use time as the seed.

    The value is taken from the parameter ``seed`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            try:
                seed = int(getattr(self, attr, default))
            except ValueError:
                raise_task_error(self, f"Value assigned to '{attr}' is not an integer")
            with tools.environ(GTEST_RANDOM_SEED=str(seed)):
                _old_run(self, deps, tools)

        if param:
            seed_param = IntParameter(default, min=0, max=99999, help="Random number generator seed.")
            seed_param.__set_name__(cls, attr)
            setattr(cls, attr, seed_param)

        cls.run = run
        return influence.source("googletest.seed", seed)(cls)

    return decorator


def shuffle(default: bool = False, param: bool = True, attr: str = "shuffle"):
    """
    Task class decorator controlling the GTEST_SHUFFLE environment variable.

    When set, the test application runs its test-cases in random order.
    In order to reproduce test-case ordering issues, a user may assign a specific
    random number generator seed to get the same test-case execution order.
    See :func:`seed`.

    The value is taken from the parameter ``shuffle`` which is created
    by default. If no parameter is created, the value is instead taken from the class
    attribute with the same name. The name of the paramter/attribute can be changed.

    Args:
        default (boolean): Default value of the parameter and env. variable.
            Default: False.
        param (boolean): Create a task parameter. Default: True.
        attr (str): Name of parameter or class attribute.

    """

    def decorator(cls):
        _old_run = cls.run

        @wraps(cls.run)
        def run(self, deps, tools):
            with tools.environ(GTEST_SHUFFLE=str(int(bool(getattr(self, attr, default))))):
                _old_run(self, deps, tools)

        if param:
            shuffle_param = BooleanParameter(default, help="Randomize test-case execution order.")
            shuffle_param.__set_name__(cls, attr)
            setattr(cls, attr, shuffle_param)

        cls.run = run
        return influence.source("googletest.shuffle", shuffle)(cls)

    return decorator


@break_on_failure()
@brief()
@disabled()
@fail_fast()
@filter()
@junit_report()
@repeat()
@seed()
@shuffle()
class GTestRunner(Runner):
    """
    Abstract task base class that runs Google Test applications.

    Test executables are consumed from requirement artifacts. The
    artifacts must export metadata indicating the name of the binary,
    using ``artifact.strings.executable``.

    A number of parameters can be assigned from the command line
    to control the behavior of the task. Parameters can also be
    overridden using regular Python class attributes in subclasses.

    A JUnit test report is generated and published in the task artifact.
    The results of the report are also imported into Jolt and distributed
    with report emails if the email plugin has been enabled.

    Example:

    .. literalinclude:: ../examples/googletest/runner.jolt
      :language: python
      :caption: examples/googletest/runner.jolt
    """

    abstract = True

    break_on_failure = BooleanParameter(False, help="Trigger breakpoint on failures.")
    """ Trigger breakpoint on test-case failure. """

    brief = BooleanParameter(False, help="Only print failed test-cases.")
    """ Only print failed test-cases. """

    disabled = BooleanParameter(False, help="Also run disabled test-cases.")
    """ Also run disabled test-cases. """

    fail_fast = BooleanParameter(False, help="Stop when the first failure is found.")
    """ Stop when the first failure is found. """

    filter = Parameter("*", help="Test-case filter.")
    """ Test-case filter. """

    repeat = IntParameter(1, help="Test-case repetitions.")
    """ Test-case repetitions. """

    seed = IntParameter(0, min=0, max=99999, help="Random number generator seed.")
    """ Random number generator seed. """

    shuffle = BooleanParameter(True, help="Randomize test-case execution order.")
    """ Randomize test-case execution order. """
