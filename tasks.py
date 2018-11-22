import hashlib
import utils
import inspect
from cache import *
from copy import copy
from contextlib import contextmanager
import unittest as ut
import functools as ft
import types
from tools import Tools


class Parameter(object):
    def __init__(self, default=None, values=None, help=None):
        self._default = default
        self._value = default
        self._accepted_values = values
        self.__doc__ = help
        if default:
            self._validate(default)

    def __str__(self):
        return str(self._value) if self._value is not None else ''

    def _validate(self, value):
        assert self._accepted_values is None or value in self._accepted_values, \
            "illegal value '{0}' assigned to parameter"\
            .format(value)

    def get_default(self):
        return self._default

    def is_default(self):
        return self._default == self._value

    def is_unset(self):
        return self._value is None

    def get_value(self):
        return self._value

    def set_value(self, value):
        self._validate(value)
        self._value = value


class TaskRegistry(object):
    _instance = None

    def __init__(self):
        self.tasks = {}
        self.tests = {}
        self.instances = {}

    @staticmethod
    def get():
        if not TaskRegistry._instance:
            TaskRegistry._instance = TaskRegistry()
        return TaskRegistry._instance

    def add_task_class(self, cls):
        self.tasks[cls.name] = cls

    def add_test_class(self, cls):
        self.tests[cls.name] = cls

    def get_task_class(self, name):
        return self.tasks.get(name)

    def get_test_class(self, name):
        return self.tests.get(name)

    def get_task_classes(self):
        return self.tasks.values()

    def get_test_classes(self):
        return self.tests.values()

    def get_task(self, name, extra_params=None):
        name, params = utils.parse_task_name(name)
        params.update(extra_params or {})
        full_name = utils.format_task_name(name, params)

        task = self.instances.get(full_name)
        if task:
            return task

        cls = self.tasks.get(name)
        if cls:
            task = cls(parameters=params)
            self.instances[full_name] = task
            return task

        cls = self.tests.get(name)
        if cls:
            task = _Test(cls, parameters=params)
            self.instances[full_name] = task
            return task

        assert task, "no such task: {0}".format(full_name)

    def _create_parents(self, name):
        names = name.split("/")

        if len(names) <= 1:
            return

        prev = None
        for i in reversed(range(0, len(names))):
            name = "/".join(names[:i + 1])
            task = self.instances.get(name) or Task(name)
            if prev:
                task.requires += [prev.name]
            prev = task



class TaskBase(object):
    def __init__(self, *args, **kwargs):
        super(TaskBase, self).__init__(*args, **kwargs)

    def _create_parameters(self):
        for key, param in self.__class__.__dict__.items():
            if isinstance(param, Parameter):
                param = copy(param)
                setattr(self, key, param)

    def _set_parameters(self, params):
        params = params or {}
        for key, value in params.items():
            param = self.__dict__.get(key)
            if isinstance(param, Parameter):
                param.set_value(value)
                continue
            assert False, "no such parameter for task {0}: {1}".format(self.name, key)

    def _get_parameters(self, unset=False):
        return {key: getattr(self, key).get_value()
                for key in dir(self)
                if isinstance(getattr(self, key), Parameter) and \
                 (unset or not getattr(self, key).is_unset()) }

    def _get_properties(self):
        return {key: str(getattr(self, key))
                for key in dir(self)
                if utils.is_str(getattr(self, key)) }


class Task(TaskBase):
    joltdir = "."
    name = None
    requires = []
    extends = ""
    influence = []

    def __init__(self, parameters=None):
        super(Task, self).__init__()
        self.tools = Tools(self, self.joltdir)
        self._create_parameters()
        self._set_parameters(parameters)
        self.influence = utils.as_list(self.__class__.influence)
        self.requires = utils.as_list(utils.call_or_return(self, self.__class__.requires))
        self.extends = utils.as_list(utils.call_or_return(self, self.__class__.extends))
        assert len(self.extends) == 1, "{0} extends multiple tasks, only one allowed".format(self.name)
        self.extends = self.extends[0]
        self.name = self.__class__.name

    def _get_source(self, func):
        source, lines = inspect.getsourcelines(func)
        return "\n".join(source)

    def _get_source_functions(self):
        return [self.run, self.publish, self.unpack]

    def _get_source_hash(self):
        sha = hashlib.sha1()
        for func in self._get_source_functions():
            sha.update(self._get_source(func).encode())
        return sha.hexdigest()

    def _get_requires(self):
        try:
            return [self._get_expansion(req) for req in self.requires]
        except KeyError as e:
            assert False, "invalid macro expansion used in task {0}: {1} - "\
                "forgot to set the parameter?".format(self.name, e)

    def _get_extends(self):
        try:
            return self._get_expansion(self.extends)
        except KeyError as e:
            assert False, "invalid macro expansion used in task {0}: {1} - "\
                "forgot to set the parameter?".format(self.name, e)

    def _get_expansion(self, string, *args, **kwargs):
        try:
            kwargs.update(**self._get_parameters())
            kwargs.update(**self._get_properties())
            return utils.expand(string, *args, **kwargs)
        except KeyError as e:
            assert False, "invalid macro expansion used in task {0}: {1} - "\
                "forgot to set the parameter?".format(self.name, e)

    def is_cacheable(self):
        return True

    def is_runnable(self):
        return True

    def info(self, fmt, *args, **kwargs):
        log.info(fmt, *args, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        log.warn(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        log.error(fmt, *args, **kwargs)

    def run(self, deps, tools):
        """
        Performs the work of the task.

        Dependencies specified with "requires" are passed as the
        deps dictionary. The tools argument provides a set of low
        level tool functions that may be useful.

        with tools.cwd("path/to/subdir"):
            tools.run("make {target}")

        When using methods from the toolbox, task parameters, such
        as 'target' above,  are automatically expanded to their values.
        """
        pass

    def publish(self, artifact, tools):
        """
        Publishes files produced by run().

        Files can be collected in to the artifact by calling
        artifact.collect().

        Additional metadata can be provided, such as environment
        variables that should be set whenever the task artifact is
        consumed. Example:

          # Append <artifact-path>/bin to the PATH
          artifact.environ.PATH.append("bin")

          # Pass an arbitrary string to a consumer
          artifact.strings.foo = "bar"
        """
        pass

    def unpack(self, artifact, tools):
        """
        Unpacks files published by publish() .

        The intention of this hook is to make necessary adjustments
        to artifact files and directories once they have been downloaded
        into the local cache on a different machine. For example,
        paths may have to be adjusted or an installer executed.

        This hook is executed in the context of a consuming task.
        """
        pass


class Resource(Task):
    def __init__(self, *args, **kwargs):
        super(Resource, self).__init__(*args, **kwargs)

    def _get_source_functions(self):
        return super(Resource, self)._get_source_functions() + \
            [self.acquire, self.release]

    def is_cacheable(self):
        return False

    def is_runnable(self):
        return False

    def info(self, fmt, *args, **kwargs):
        pass

    def acquire(self, artifact, env, tools):
        pass

    def release(self, artifact, env, tools):
        pass

    def run(self, env, tools):
        self._run_env = env


class TaskException(Exception):
    def __init__(self, *args, **kwargs):
        super(TaskException, self).__init__(*args, **kwargs)


class _Test(Task):
    def __init__(self, test_cls, *args, **kwargs):
        self.test_cls = test_cls
        self.__class__.name = test_cls.name
        self.__class__.joltdir = test_cls.joltdir
        self.__class__.requires = test_cls.requires
        self.__class__.influence = test_cls.influence
        super(_Test, self).__init__(*args, **kwargs)

    def _create_parameters(self):
        for key, param in self.test_cls.__dict__.items():
            if isinstance(param, Parameter):
                param = copy(param)
                setattr(self, key, param)

    def _get_test_names(self):
        return [attrib for attrib in dir(self.test_cls)
                if attrib.startswith("test_")]

    def _get_test_funcs(self):
        return [getattr(self.test_cls, func)
                for func in self._get_test_names()]

    def _get_source_functions(self):
        funcs = super(_Test, self)._get_source_functions()
        return funcs + self._get_test_funcs() + [self.test_cls.setup, self.test_cls.cleanup]

    def run(self, deps, tools):
        testsuite = ut.TestSuite()
        for test in self._get_test_names():
            testsuite.addTest(self.test_cls(
                test, parameters=self._get_parameters(), deps=deps, tools=tools))
        self.testresult = ut.TextTestRunner(verbosity=2).run(testsuite)
        assert self.testresult.wasSuccessful(), "tests failed"


class Test(ut.TestCase, TaskBase):
    joltdir = "."
    name = None
    requires = []
    extends = ""
    influence = []

    def __init__(self, method="runTest", parameters=None, deps=None, tools=None, *args, **kwargs):
        ut.TestCase.__init__(self, method)
        TaskBase.__init__(self)
        self.deps = deps
        self.tools = tools
        self.influence = utils.as_list(self.__class__.influence)
        self.requires = utils.as_list(utils.call_or_return(self, self.__class__.requires))
        self.extends = utils.as_list(utils.call_or_return(self, self.__class__.extends))
        assert len(self.extends) == 1, "{0} extends multiple tasks, only one allowed".format(self.name)
        self.extends = self.extends[0]
        self.name = self.__class__.name
        self._create_parameters()
        self._set_parameters(parameters)

    def setUp(self):
        self.setup(self.deps, self.tools)

    def tearDown(self):
        self.cleanup()

    def setup(self, deps, tools):
        """ Implement this method to make preparations before a test """

    def cleanup(self):
        """ Implement this method to clean up after a test """


@ArtifactAttributeSetProvider.Register
class ResourceAttributeSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        pass

    def parse(self, artifact, content):
        pass

    def format(self, artifact, content):
        pass

    def apply(self, task, artifact):
        task = artifact.get_task()
        if isinstance(task, Resource):
            deps = task._run_env
            deps.__enter__()
            task.acquire(artifact, deps, artifact.tools)

    def unapply(self, task, artifact):
        task = artifact.get_task()
        if isinstance(task, Resource):
            env = task._run_env
            task.release(artifact, env, artifact.tools)
            env.__exit__(None, None, None)
