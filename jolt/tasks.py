import hashlib
import inspect
import copy
from contextlib import contextmanager
import unittest as ut
import functools as ft
import types
import base64

from jolt import utils
from jolt.cache import *
from jolt.tools import Tools
from jolt.influence import TaskSourceInfluence


class Export(object):
    def __init__(self, value, encoded=False):
        self.value = None
        self.exported_value = value
        self.encoded = encoded

    def assign(self, value):
        value = value or ""
        self.value = base64.decodestring(value.encode()).decode() if self.encoded else value

    def export(self, task):
        value = self.value if self.value is not None else self.exported_value(task)
        if value:
            value = base64.encodestring(value.encode()).decode() if self.encoded else value
        return value


class Parameter(object):
    """ Generic task parameter type. """

    def __init__(self, default=None, values=None, required=True, help=None):
        """
        Creates a new parameter.

        Args:
            default (str, optional): An optional default value.
            values (list, optional): A list of accepted values. An
                assertion is raised if an unlisted value is assigned to the parameter.
            required (boolean, optional): If required, the parameter must be assigned
                a value before the task can be executed. The default is ``True``.
            help (str, optional): Documentation for the parameter.
                This text is displayed when running the ``info`` command on the
                associated task.

        Raises:
            AssertionError: If the parameter is assigned an illegal value
                during task execution.
        """

        self._default = default
        self._value = default
        self._accepted_values = values
        self._required = required
        self.__doc__ = help
        if default:
            self._validate(default)

    def __str__(self):
        """ Returns the parameter value as a string """
        return str(self._value) if self._value is not None else ''

    def _validate(self, value):
        assert self._accepted_values is None or value in self._accepted_values, \
            "illegal value '{0}' assigned to parameter"\
            .format(value)

    def get_default(self):
        """ Get the default value of the parameter.

        Returns:
            The default value or None if no default was given.
        """
        return self._default

    def set_default(self, value):
        """ Set the default value of the parameter.

        Args:
            value (str): The new default value of the parameter.
        """
        self._validate(value)
        if self.is_default():
            self._value = value
        self._default = value

    def is_required(self):
        """ Check if the parameter must be set to a value.

        Returns:
            True if the parameter must be assigned a value, False otherwise.
        """
        return self._required

    def is_default(self):
        """ Check if parameter is set to its default value.

        Returns:
            True if the assigned value is the default value.
        """
        return self._default == self._value

    def is_unset(self):
        """ Check if the parameter is unset.

        Returns:
            True if the assigned value is None.
        """
        return self._value is None

    def is_set(self):
        """ Check if the parameter is set to a non-default value.

        Returns:
            True if the assigned value is not the default value.
        """
        return not self.is_unset() and not self.is_default()

    def get_value(self):
        """ Get the parameter value. """
        return self._value

    def set_value(self, value):
        """ Set the parameter value.

        Args:
            value (str): The new parameter value.

        Raises:
            AssertionError: If the parameter is assigned an illegal value.
        """
        self._validate(value)
        self._value = value


class BooleanParameter(Parameter):
    """ Boolean task parameter type. """

    def __init__(self, default=None, required=True, help=None):
        """
        Creates a new parameter.

        Args:
            default (boolean, optional): An optional default boolean value.
            required (boolean, optional): If required, the parameter must be assigned
                a value before the task can be executed. The default is ``True``.
            help (str, optional): Documentation for the parameter.
                This text is displayed when running the ``info`` command on the
                associated task.

        Raises:
            AssertionError: If the parameter is assigned an illegal value
                during task execution.
        """
        default = str(default).lower() if default is not None else None
        super(BooleanParameter, self).__init__(
            default, values=["false", "true", "0", "1"],
            required=required, help=help)

    def _validate(self, value):
        assert self._accepted_values is None or value in self._accepted_values, \
            "illegal value '{0}' assigned to boolean parameter"\
            .format(value)

    def set_value(self, value):
        """ Set the parameter value.

        Args:
            value (boolean): The new parameter value. Accepted values are:
                False, True, "false, and "true", 0 and 1.

        Raises:
            AssertionError: If the parameter is assigned an illegal value.
        """
        value = str(value).lower()
        super(BooleanParameter, self).set_value(value)

    @property
    def is_true(self):
        """ The parameter value is True. """
        return str(self.get_value()) in ["true", "1"]

    @property
    def is_false(self):
        """ The parameter value is False. """
        return not self.is_true


class TaskRegistry(object):
    _instance = None

    def __init__(self, env=None):
        self.env = env
        self.tasks = {}
        self.tests = {}
        self.instances = {}

    @staticmethod
    def get(*args, **kwargs):
        if not TaskRegistry._instance:
            TaskRegistry._instance = TaskRegistry(*args, **kwargs)
        return TaskRegistry._instance

    def add_task_class(self, cls):
        self.tasks[cls.name] = cls

    def add_test_class(self, cls):
        self.tests[cls.name] = cls

    def add_task(self, task, extra_params):
        name, params = utils.parse_task_name(task.name)
        params.update(extra_params or {})
        full_name = utils.format_task_name(name, params)
        self.instances[full_name] = task

    def get_task_class(self, name):
        return self.tasks.get(name)

    def get_test_class(self, name):
        return self.tests.get(name)

    def get_task_classes(self):
        return list(self.tasks.values())

    def get_test_classes(self):
        return list(self.tests.values())

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

    def set_default_parameters(self, task):
        name, params = utils.parse_task_name(task)

        cls = self.tasks.get(name)
        if not cls:
            cls = self.tests.get(name)
        assert cls, "no such task: {0}".format(task)
        cls._set_default_parameters(cls, params)

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


class TaskGenerator(object):
    """
    Base class for task generators.

    Generators create tasks classes dynamically in runtime.
    They are used to implement concepts such as components
    where multiple similar tasks should be created.

    For example, a C++ library should not only be built, it
    should also be tested. While it is possible to add one
    task for the compilation of the library and another for
    the test, it is advisable to instead use a task generator
    when there are multiple libraries to build and test.
    The generator will ensure that all libraries are build and
    tested identically. Additional tasks, such as sourcedoc
    generation, can be added for all libraries at a later
    point in time. Refactoring is simplified by gathering
    shared code in one place.

    Generated tasks can be replaced by defining a task with
    the same name explicitly.

    """

    abstract = True
    """ An abstract task generator class indended to be subclassed.

    Abstract task generators are not invoked.
    """

    def generate(self):
        """
        Generate tasks.

        Called by Jolt during the parsing of user task
        definitions.

        Returns:
            A list of task classes to be registered with Jolt.

        """
        raise NotImplementedError()



class TaskBase(object):
    cacheable = True
    """ Whether the task produces an artifact or not. """

    def __init__(self, *args, **kwargs):
        super(TaskBase, self).__init__(*args, **kwargs)
        self.cacheable = self.__class__.cacheable
        self._identity = None

    @property
    def identity(self):
        return self._identity

    @identity.setter
    def identity(self, identity):
        self._identity = identity

    def _create_exports(self):
        for key, export in self.__class__.__dict__.items():
            if isinstance(export, Export):
                export = copy.copy(export)
                setattr(self, key, export)

    def _create_parameters(self):
        for key in dir(self):
            param = utils.getattr_safe(self, key)
            if isinstance(param, Parameter):
                param = copy.copy(param)
                setattr(self, key, param)

    def _set_parameters(self, params):
        params = params or {}
        for key, value in params.items():
            param = utils.getattr_safe(self, key)
            if isinstance(param, Parameter):
                param.set_value(value)
                continue
            assert False, "no such parameter for task {0}: {1}".format(self.name, key)
        self._assert_required_parameters_assigned()

    @staticmethod
    def _set_default_parameters(cls, params):
        params = params or {}
        for key, value in params.items():
            param = utils.getattr_safe(cls, key)
            if isinstance(param, Parameter):
                param = copy.copy(param)
                param.set_default(value)
                setattr(cls, key, param)
                continue
            assert False, "no such parameter for task {0}: {1}".format(cls.name, key)

    def _assert_required_parameters_assigned(self):
        for key, param in self._get_parameter_objects().items():
            assert not param.is_required() or not param.is_unset(), \
                "required parameter '{0}' has not been set for '{1}'".format(key, self.name)

    @utils.cached.instance
    def _get_export_objects(self):
        return { key: getattr(self, key) for key in dir(self)
                 if isinstance(utils.getattr_safe(self, key), Export) }

    @utils.cached.instance
    def _get_parameter_objects(self, unset=False):
        return { key: getattr(self, key) for key in dir(self)
                 if isinstance(utils.getattr_safe(self, key), Parameter) }

    def _get_parameters(self, unset=False):
        return {key: param.get_value()
                for key, param in self._get_parameter_objects().items()
                if unset or not param.is_unset() }

    def _get_explicitly_set_parameters(self):
        return {key: param.get_value()
                for key, param in self._get_parameter_objects().items()
                if param.is_set() }

    def _get_properties(self):
        return {key: str(getattr(self, key))
                for key in dir(self)
                if utils.is_str(getattr(self, key)) }


class Task(TaskBase):
    #: Path to the .jolt file where the task was defined.
    joltdir = "."
    """ Path to the .jolt file where the task was defined. """

    name = None
    """ Name of the task. Derived from class name if not set. """

    requires = []
    """ List of dependencies to other tasks. """

    extends = ""
    """
    Name of extended task.

    A task with this attribute set is called an extension. An extension
    is executed in the context of the extended task, immediately after
    the extended task has executed.

    A common use-case for extensions is to produce additional artifacts
    from the output of another task. Also, for long-running tasks, it is
    sometimes beneficial to utilize the intermediate output from an extended
    task. The extension artifact can then be acquired more cheaply than if the
    extension had performed all of the work from scratch.

    An extension can only extend one other task.
    """

    abstract = True
    """ An abstract task class indended to be subclassed.

    Abstract tasks can't be executed and won't be listed.
    """


    fast = False
    """
    Indication of task speed.

    The information is used by the distributed execution strategy to
    optimize how tasks are scheduled. Scheduling tasks remotely is always
    associated with some overhead and sometimes it's beneficial to instead
    schedule fast tasks locally if possible.

    An extended task is only considered fast if all extensions are fast.
    """

    influence = []

    def __init__(self, parameters=None, **kwargs):
        super(Task, self).__init__()
        self.name = self.__class__.name
        self.tools = Tools(self, self.joltdir)
        self._create_exports()
        self._create_parameters()
        self._set_parameters(parameters)
        self.influence = utils.as_list(self.__class__.influence)
        self.requires = utils.as_list(utils.call_or_return(self, self.__class__._requires))
        self.extends = utils.as_list(utils.call_or_return(self, self.__class__.extends))
        assert len(self.extends) == 1, "{0} extends multiple tasks, only one allowed".format(self.name)
        self.extends = self.extends[0]
        self.influence.append(TaskSourceInfluence("publish"))
        self.influence.append(TaskSourceInfluence("run"))
        self.influence.append(TaskSourceInfluence("unpack"))

    def _requires(self):
        return utils.as_list(utils.call_or_return(self, self.__class__.requires))

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
    @property
    def canonical_name(self):
        return self.name.replace("/", "_")

    def is_cacheable(self):
        return self.cacheable

    def is_runnable(self):
        return True

    def info(self, fmt, *args, **kwargs):
        """
        Log information about the task.
        """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.info(fmt, *args, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        """ Log a warning concerning the task """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.warn(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        """ Log an error concerning the task """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.error(fmt, *args, **kwargs)

    def run(self, deps, tools):
        """
        Performs the work of the task.

        Dependencies specified with "requires" are passed as the
        deps dictionary. The tools argument provides a set of low
        level tool functions that may be useful.

        .. code-block:: python

          with tools.cwd("path/to/subdir"):
              tools.run("make {target}")

        When using methods from the toolbox, task parameters, such
        as ``target`` above,  are automatically expanded to their values.
        """
        pass

    def publish(self, artifact, tools):
        """
        Publishes files produced by :func:`~run`.

        Files can be collected in to the artifact by calling
        artifact.collect().

        Additional metadata can be provided, such as environment
        variables that should be set whenever the task artifact is
        consumed. Example:

        .. code-block:: python

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
        raise NotImplementedError()


class Resource(Task):
    """
    A resource task.

    Resources are special tasks executed in the :class:`~jolt.Context` of other tasks.
    They are invoked to acquire and release a resource, such as hardware equipment,
    before and after the execution of a task. No artifact is produced by a resource.

    Implementors should override :func:`~acquire` and :func:`~release`.

    """

    cacheable = False
    abstract = True
    """ An abstract resource class indended to be subclassed. """

    def __init__(self, *args, **kwargs):
        super(Resource, self).__init__(*args, **kwargs)
        self.influence.append(TaskSourceInfluence("acquire"))
        self.influence.append(TaskSourceInfluence("release"))

    def is_runnable(self):
        return False

    def info(self, fmt, *args, **kwargs):
        pass

    def acquire(self, artifact, deps, tools):
        """ Called to acquire the resource.

        An implementor overrides this method in a subclass. The acquired
        resource must be released manually if an exception occurs before the
        method has returned.

        Args:
            artifact (:class:`~jolt.Artifact`): The artifact associated with the resource.
                It is not possible to publish files from a resource, but the implementor
                can still use the resource to pass information to consuming tasks.
            deps (:class:`~jolt.Context`): Task execution context used to access the
                artifacts of dependencies.
            tools (:class:`~jolt.Tools`): A task specific toolbox.

        """
        pass

    def release(self, artifact, deps, tools):
        """ Called to release the resource.

        An implementor overrides this method in a subclass.

        Args:
            artifact (:class:`~jolt.Artifact`): The artifact associated with the resource.
                It is not possible to publish files from a resource, but the implementor
                can still use the resource to pass information to consuming tasks.
            deps (:class:`~jolt.Context`): Task execution context used to access the
                artifacts of dependencies.
            tools (:class:`~jolt.Tools`): A task specific toolbox.
        """
        pass

    def run(self, env, tools):
        self._run_env = env


class TaskException(Exception):
    def __init__(self, *args, **kwargs):
        super(TaskException, self).__init__(*args, **kwargs)


class _Test(Task):
    abstract = True
    """ An abstract test class indended to be subclassed.

    Abstract test tasks can't be executed and won't be listed.
    """

    def __init__(self, test_cls, *args, **kwargs):
        self.test_cls = test_cls
        self.__class__.name = test_cls.name
        self.__class__.joltdir = test_cls.joltdir
        self.__class__.requires = test_cls.requires
        self.__class__.influence = test_cls.influence
        super(_Test, self).__init__(*args, **kwargs)
        self.influence.append(TaskSourceInfluence("setup", self.test_cls))
        self.influence.append(TaskSourceInfluence("cleanup", self.test_cls))
        for name in self._get_test_names():
            self.influence.append(TaskSourceInfluence(name, self.test_cls))

    @property
    def identity(self):
        return self.test_cls.identity

    @identity.setter
    def identity(self, identity):
        self.test_cls.identity = identity

    def _create_parameters(self):
        for key, param in self.test_cls.__dict__.items():
            if isinstance(param, Parameter):
                param = copy.copy(param)
                setattr(self, key, param)

    def _get_test_names(self):
        return [attrib for attrib in dir(self.test_cls)
                if attrib.startswith("test_")]

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

    abstract = True
    """ An abstract test class indended to be subclassed.

    Abstract test tasks can't be executed and won't be listed.
    """

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
        self._create_exports()
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
