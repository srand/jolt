import base64
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, ExitStack
import copy
import fnmatch
import functools
import hashlib
import platform
from threading import RLock
import subprocess
from os import environ
import sys
import unittest as ut
from urllib.parse import urlparse
import uuid
import re
import traceback

from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.cache import ArtifactAttributeSetProvider
from jolt.error import raise_error, raise_error_if, raise_task_error, raise_task_error_if
from jolt.error import raise_unreported_task_error_if
from jolt.error import JoltError, JoltCommandError, LoggedJoltError
from jolt.expires import Immediately
from jolt.influence import FileInfluence, TaintInfluenceProvider
from jolt.influence import TaskClassSourceInfluence
from jolt.influence import CallbackInfluence
from jolt.influence import attribute as attribute_influence
from jolt.influence import environ as environ_influence
from jolt.influence import source as source_influence
from jolt.influence import files as file_influence
from jolt.manifest import _JoltTask
from jolt.tools import Tools
from jolt import colors


class Export(object):

    def __init__(self, value, encoded=False):
        self._imported = False
        self._task = None
        self._value = None
        self.exported_value = value
        self.encoded = encoded

    @staticmethod
    def __get_exports__(obj):
        exports = {}
        for mro in reversed(obj.__class__.__mro__):
            for key, export in getattr(mro, "__export_list", {}).items():
                attr = getattr(obj.__class__, key)
                if isinstance(attr, Export):
                    exports[key] = attr
        return exports

    def __set_name__(self, owner, name):
        if "__export_list" not in owner.__dict__:
            setattr(owner, "__export_list", {})
        getattr(owner, "__export_list")[name] = self

    @property
    def value(self):
        if self._value is None:
            self._value = self.exported_value(self._task)
        return self._value

    @property
    def is_imported(self):
        return self._imported

    def assign(self, value):
        value = value or ""
        self._value = base64.decodebytes(value.encode()).decode() if self.encoded else value
        self._imported = True

    def export(self, task):
        value = self.value
        if value:
            value = base64.encodebytes(value.encode()).decode() if self.encoded else value
        return value

    def set_task(self, task):
        self._task = task

    def __str__(self):
        return str(self.value)


class EnvironExport(Export):
    def __init__(self, envname):
        super().__init__(value=lambda self: environ.get(envname))
        self._envname = envname

    def assign(self, value):
        super().assign(value)
        self._task.tools.setenv(self._envname, value)


class ParameterValueError(JoltError):
    """ Raised if an illegal value is assigned to a parameter """
    def __init__(self, param, value, what=None, detail=None):
        what = what + " " if what is not None else ""
        detail = ", " + detail if detail is not None else ""
        if hasattr(param, "name"):
            super().__init__(f"Illegal {what}value '{value}' assigned to parameter '{param.name}'{detail}")
        else:
            super().__init__(f"Illegal {what}value '{value}' assigned to {type(param).__name__}{detail}")


class ParameterImmutableError(JoltError):
    """ Raised if an immutable (const=True) parameter is reassigned """
    def __init__(self, param):
        super().__init__(f"Cannot reassign immutable parameter '{param.name}'")


class Parameter(object):
    """ Generic task parameter type. """

    @staticmethod
    def __get_params__(obj):
        params = {}
        for mro in reversed(obj.__class__.__mro__):
            for key, param in getattr(mro, "__param_list", {}).items():
                attr = getattr(obj.__class__, key)
                if isinstance(attr, Parameter):
                    params[key] = attr
        return params

    def __set_name__(self, owner, name):
        if "__param_list" not in owner.__dict__:
            setattr(owner, "__param_list", {})
        getattr(owner, "__param_list")[name] = self
        self.name = name

    def __init__(self, default=None, values=None, required=True,
                 const=False, influence=True, help=None):
        """
        Creates a new parameter.

        Args:
            default (str, optional): An optional default value.
            values (list, optional): A list of accepted values. An
                assertion is raised if an unlisted value is assigned to the parameter.
            required (boolean, optional): If required, the parameter must be assigned
                a value before the task can be executed. The default is ``True``.
            const (boolean, optional): If const is True, the parameter is immutable
                and cannot be assigned a non-default value. This is useful in
                a class hierarchy where a subclass may want to impose restrictions
                on a parent class parameter. The default is ``False``.
            influence (boolean, optional): If influence is False, the parameter value
                will not influence the identity of the task artifact. The default is
                True.
            help (str, optional): Documentation for the parameter.
                This text is displayed when running the ``info`` command on the
                associated task.

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.

        """

        self._default = default
        self._value = default
        self._accepted_values = values
        self._required = required
        self._const = const
        self._influence = influence
        self._help = help
        if default is not None:
            self._validate(default, "default")

    @property
    def help(self):
        values = self._help_values()
        if values:
            return f"{self._help} {values}"if self._help else values
        elif self._default is not None:
            return f"{self._help} [default: {self._help_default}]" if self._help else f"[default: {self._help_default}]"
        return self._help or ""

    @property
    def _help_default(self):
        return colors.bright(str(self._default))

    def _help_values(self, accepted=None):
        accepted = accepted or self._accepted_values or []

        def highlight(value):
            return colors.bright(value) if self._is_default(value) else colors.dim(value)

        return "[{}]".format(", ".join([highlight(value) for value in accepted])) if accepted else ""

    def __str__(self):
        """ Returns the parameter value as a string """
        return str(self._value) if self._value is not None else ''

    def _validate(self, value, what=None):
        if self._accepted_values is not None and value not in self._accepted_values:
            raise ParameterValueError(self, value, what=what)

    def get_default(self):
        """ Get the default value of the parameter.

        Returns:
            The default value or None if no default was given.
        """
        return self._default

    @property
    def default(self):
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

    def is_influencer(self):
        """ Check if the parameter value influences the identitiy of the task artifact.

        Returns:
            True if the parameter influences the identity, False otherwise.
        """
        return self._influence

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

    def _is_default(self, value):
        return self._default and value == self._default

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

    def is_const(self):
        """ Check if the parameter can be assigned or not.

        Returns:
            True if the parameter is immutable.
        """
        return self._const

    def get_value(self):
        """ Get the parameter value. """
        return self._value

    @property
    def value(self):
        """ Get the parameter value. """
        return self._value

    def __bool__(self):
        """ Returns True if the parameter value is a non-empty string. """
        return self._value is not None and self._value != ""

    def __eq__(self, value):
        """ Compare parameter value """
        return self._value == value

    def set_value(self, value):
        """ Set the parameter value.

        Args:
            value (str): The new parameter value.

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.
        """
        self._validate(value)
        if self._const and value != self._default:
            raise ParameterImmutableError(self)
        self._value = value


class BooleanParameter(Parameter):
    """
    Boolean task parameter.

    Accepted values are:

      - False
      - True
      - "false"
      - "true"
      - "no"
      - "yes"
      - "0"
      - "1"

    """

    def __init__(self, default=None, required=True, const=False, influence=True, help=None):
        """
        Creates a new parameter.

        Args:
            default (boolean, optional): An optional default boolean value.
            required (boolean, optional): If required, the parameter must be assigned
                a value before the task can be executed. The default is ``True``.
            const (boolean, optional): If const is True, the parameter is immutable
                and cannot be assigned a non-default value. This is useful in
                a class hierarchy where a subclass may want to impose restrictions
                on a parent class parameter. The default is ``False``.
            influence (boolean, optional): If influence is False, the parameter value
                will not influence the identity of the task artifact. The default is
                True.
            help (str, optional): Documentation for the parameter.
                This text is displayed when running the ``inspect`` command on the
                associated task.

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.

        """
        default = str(default).lower() if default is not None else None
        super().__init__(
            default,
            values=["false", "true", "0", "1", "no", "yes"],
            required=required,
            const=const,
            influence=influence,
            help=help)

    def _help_values(self, accepted=None):
        return super()._help_values(["true", "false"])

    def set_value(self, value):
        """ Set the parameter value.

        Args:
            value (boolean): The new parameter value. Accepted values are:
                False, True, "false, and "true", 0 and 1, "no" and "yes".

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.
        """
        value = str(value).lower()
        super().set_value(value)

    @property
    def is_true(self):
        """ The parameter value is True. """
        return str(self.get_value()) in ["true", "1", "yes"]

    @property
    def is_false(self):
        """ The parameter value is False. """
        return not self.is_true

    def __bool__(self):
        """ Returns the boolean parameter value """
        return self.is_true

    def __getitem__(self, key):
        """
        Returns a substitution string depending on the parameter value.

        Args:
            key (str): A special key syntax, ``enabled,disabled``, where
            and either ``enabled`` or ``disabled`` would be returned
            depending on the paramter value. See the example below.

        Returns:
            Substitution string.

        Example:

          .. code-block:: python

            class Example(Task):
               debug = BooleanParameter()

               def run(self, deps, tools):
                   self.info("debug is {debug[enabled,disabled]}")

          .. code-block:: bash

            $ jolt build example:debug=true
            [INFO] debug is enabled (example)

            $ jolt build example:debug=false
            [INFO] debug is disabled (example)

        """
        key = key.split(",")
        if len(key) != 2:
            raise KeyError(key)
        return key[0] if self.is_true else key[1]


class IntParameter(Parameter):
    """
    Integer task parameter.

    Implements all regular unary and binary integer operators.

    """

    def __init__(self, default=None, min=None, max=None, values=None, required=True, const=False,
                 influence=True, help=None):
        """
        Creates a new parameter.

        Args:
            default (int, optional): An optional default integer value.
            min (int, optional): Minimum allowed value.
            max (int, optional): Maximum allowed value.
            values (list, optional): A list of accepted values. An
                assertion is raised if an unlisted value is assigned to the parameter.
            required (boolean, optional): If required, the parameter must be assigned
                a value before the task can be executed. The default is ``True``.
            const (boolean, optional): If const is True, the parameter is immutable
                and cannot be assigned a non-default value. This is useful in
                a class hierarchy where a subclass may want to impose restrictions
                on a parent class parameter. The default is ``False``.
            influence (boolean, optional): If influence is False, the parameter value
                will not influence the identity of the task artifact. The default is
                True.
            help (str, optional): Documentation for the parameter.
                This text is displayed when running the ``inspect`` command on the
                associated task.

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.

        """
        try:
            default = int(default) if default is not None else None
        except ValueError:
            raise ParameterValueError(self, default, what="default")

        try:
            self._min = int(min) if min is not None else None
        except ValueError:
            raise ParameterValueError(self, min, what="minimum")

        try:
            self._max = int(max) if max is not None else None
        except ValueError:
            raise ParameterValueError(self, max, what="maximum")

        super().__init__(
            default,
            values,
            required=required,
            const=const,
            influence=influence,
            help=help)

    def _validate(self, value, what=None):
        if self._min is not None and value < self._min:
            raise ParameterValueError(self, value, what=what, detail=f"less than minimum value '{self._min}'")
        if self._max is not None and value > self._max:
            raise ParameterValueError(self, value, what=what, detail=f"greater than maximum value '{self._max}'")
        super()._validate(value, what)

    def set_value(self, value):
        """ Set the parameter value.

        Args:
            value (boolean): The new parameter value. Accepted values are:
                False, True, "false, and "true", 0 and 1, "no" and "yes".

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.
        """
        try:
            value = int(value)
        except ValueError:
            raise ParameterValueError(self, value)
        super().set_value(value)

    def __bool__(self):
        """ Evaluates to False if the value is 0, True otherwise """
        return self.get_value() != 0

    def __int__(self):
        """ Returns the integer parameter value """
        return int(self.get_value())

    def __lt__(self, other):
        """ Less-than comparison with another integer value """
        return int(self.get_value()) < int(other)

    def __le__(self, other):
        """ Less-or-equal comparison with another integer value """
        return int(self.get_value()) <= int(other)

    def __gt__(self, other):
        """ Greater-than comparison with another integer value """
        return int(self.get_value()) > int(other)

    def __ge__(self, other):
        """ Greater-or-equal comparison with another integer value """
        return int(self.get_value()) >= int(other)

    def __add__(self, other):
        return int(self.get_value()).__add__(other)

    def __sub__(self, other):
        return int(self.get_value()).__sub__(other)

    def __mul__(self, other):
        return int(self.get_value()).__mul__(other)

    def __truediv__(self, other):
        return int(self.get_value()).__truediv__(other)

    def __floordiv__(self, other):
        return int(self.get_value()).__floordiv__(other)

    def __mod__(self, other):
        return int(self.get_value()).__mod__(other)

    def __divmod__(self, other):
        return int(self.get_value()).__divmod__(other)

    def __pow__(self, other, modulo=None):
        return int(self.get_value()).__pow__(other, modulo)

    def __lshift__(self, other):
        return int(self.get_value()).__lshift__(other)

    def __rshift__(self, other):
        return int(self.get_value()).__rshift__(other)

    def __and__(self, other):
        return int(self.get_value()).__and__(other)

    def __xor__(self, other):
        return int(self.get_value()).__xor__(other)

    def __or__(self, other):
        return int(self.get_value()).__or__(other)

    def __radd__(self, other):
        return int(self.get_value()).__radd__(other)

    def __rsub__(self, other):
        return int(self.get_value()).__rsub__(other)

    def __rmul__(self, other):
        return int(self.get_value()).__rmul__(other)

    def __rtruediv__(self, other):
        return int(self.get_value()).__rtruediv__(other)

    def __rfloordiv__(self, other):
        return int(self.get_value()).__rfloordiv__(other)

    def __rmod__(self, other):
        return int(self.get_value()).__rmod__(other)

    def __rlshift__(self, other):
        return int(self.get_value()).__rlshift__(other)

    def __rrshift__(self, other):
        return int(self.get_value()).__rrshift__(other)

    def __rand__(self, other):
        return int(self.get_value()).__rand__(other)

    def __rxor__(self, other):
        return int(self.get_value()).__rxor__(other)

    def __ror__(self, other):
        return int(self.get_value()).__ror__(other)

    def __neg__(self):
        return int(self.get_value()).__neg__()

    def __pos__(self):
        return int(self.get_value()).__pos__()

    def __abs__(self):
        return int(self.get_value()).__abs__()

    def __invert__(self):
        return int(self.get_value()).__invert__()


class ListParameter(Parameter):
    """ List parameter type.

    A list parameter allows multiple values to be assigned to it. Values are
    separated by the '+' character in qualified task names. Each assigned value
    is validated against the list of accepted values. They are sorted in
    alphabetical order before the task is executed.

    Example:

      .. code-block:: python

        class Example(Task):
            arg = ListParameter(default=["c"], values=["a", "b", "c"], help="A list parameter")

            def run(self, deps, tools):
                for item in self.arg:
                    print(item)

      .. code-block:: bash

        $ jolt build example example:arg=a example:arg=a+b

    """

    def __init__(self, *args, **kwargs):
        """
        Creates a new list parameter.

        Args:
            default (boolean, optional): An optional list of default values.
            values (list, optional): A list of accepted values. An
                assertion is raised if an unlisted value is assigned to the parameter.
            required (boolean, optional): If required, the parameter must be assigned
                a value before the task can be executed. The default is ``True``.
            const (boolean, optional): If const is True, the parameter is immutable
                and cannot be assigned a non-default value. This is useful in
                a class hierarchy where a subclass may want to impose restrictions
                on a parent class parameter. The default is ``False``.
            influence (boolean, optional): If influence is False, the parameter value
                will not influence the identity of the task artifact. The default is
                True.
            help (str, optional): Documentation for the parameter.
                This text is displayed when running the ``inspect`` command on the
                associated task.

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.

        """
        super().__init__(*args, **kwargs)

    def set_value(self, value):
        """ Set the parameter value.

        Args:
            value (str): A list of accepted values, separated by '+'.

        Raises:
            ParameterValueError: If the parameter is assigned an illegal value.
        """
        value = str(value).split("+") if type(value) is str else value
        value.sort()
        super().set_value(value)

    def _validate(self, value, what=None):
        if self._accepted_values is not None:
            for item in value:
                if item not in self._accepted_values:
                    raise ParameterValueError(self, item, what=what)

    def get_value(self):
        return "+".join(self._value)

    def _is_default(self, value):
        return self._default and value in self._default

    def __bool__(self):
        """ Returns True if the list is non-empty. """
        return len(self._value) > 0

    def __iter__(self):
        """ Returns a sequence iterator. """
        return iter(self._value)

    def __len__(self):
        """ Returns the length of the list. """
        return len(self._value)

    def __getitem__(self, key):
        """
        Returns an element or a slice from the list.

        Args:
            key (int, slice, str): Element index or slice. A key string can
                be used to check for the existence of that value in the list.
                If the key is present the same value is returned, otherwise None.

                A special key syntax is also available to request an alternate return
                value depending on the presence of the key. Instead of a list value
                you pass ``value,present,absent`` and either ``present`` or ``absent``
                will be returned. See the example below.

        Returns:
            Element value, or substitution.

        Example:

          .. code-block:: python

            class Example(Task):
               features = ListParameter(values=["optimize", "strip"], required=False)

               def run(self, deps, tools):
                   if len(self.features) > 0:
                       self.info("first feature is {features[0]}")
                       self.info("optimize == {features[optimize]}")
                       self.info("optimization is {features[optimize,enabled,disabled]}")

          .. code-block:: bash

            $ jolt build example:features=optimize+strip
            [INFO] first feature is optimize (example)
            [INFO] optimize = optimize (example)
            [INFO] optimization is enabled (example)

            $ jolt build example:features=strip
            [INFO] first feature is debug (example)
            [INFO] optimize = None (example)
            [INFO] optimization is disabled (example)

        """
        if type(key) is str:
            key = key.split(",")
            if len(key) == 1:
                true = key[0]
                false = None
            else:
                true = key[1] if len(key) > 1 else key[0]
                false = key[2] if len(key) > 2 else None
            return true if key[0] in self._value else false
        return self._value[key]


class TaskRegistry(object):
    _instance = None

    def __init__(self, env=None):
        self.env = env
        self.tasks = {}
        self.instances = {}

    @staticmethod
    def get(*args, **kwargs):
        if not TaskRegistry._instance:
            TaskRegistry._instance = TaskRegistry(*args, **kwargs)
        return TaskRegistry._instance

    def add_task_class(self, cls):
        self.tasks[cls.name] = cls

    def add_task(self, task, extra_params):
        name, params = utils.parse_task_name(task.name)
        params.update(extra_params or {})
        full_name = utils.format_task_name(name, params)
        self.instances[full_name] = task

    def get_task_class(self, name):
        return self.tasks.get(name)

    def get_task_classes(self):
        return list(self.tasks.values())

    def get_task(self, name, extra_params=None, manifest=None, buildenv=None):
        name, params = utils.parse_task_name(name)
        params.update(extra_params or {})
        full_name = utils.format_task_name(name, params)

        task = self.instances.get(full_name)
        if task:
            return task

        cls = self.tasks.get(name)
        if cls:
            task = cls(parameters=params, manifest=manifest, buildenv=buildenv)
            task = self.instances.get(task.qualified_name, task)
            self.instances[task.qualified_name] = task
            self.instances[full_name] = task
            return task

        raise_task_error_if(not task, full_name, "No such task")

    def set_default_parameters(self, task):
        name, params = utils.parse_task_name(task)

        cls = self.tasks.get(name)
        raise_task_error_if(not cls, task, "No such task")
        cls._set_default_parameters(cls, params)

    def set_joltdir(self, joltdir):
        for task in list(self.tasks.values()):
            task.joltdir = joltdir

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
    The generator will ensure that all libraries are built and
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


class attributes:
    @staticmethod
    def artifact(name, session=False):
        """Decorator adding an additional artifact to a task.

        Jolt calls the new publish method `publish_<name>` with the
        new artifact as argument. Non-alphanumeric characters in the
        name are replaced with underscores (_). The new artifact is
        consumable from another task by using the string format
        `<artifact-name>@<task-name>` to index dependencies.  The
        standard artifact is named `main`. See the example below.

        If `session` is `True`, the new artifact will be a session
        artifact that is only valid during a single Jolt invokation.
        Session artifacts are published even if the task fails and may
        be used to save logs and data for post-mortem analysis.

        Args:
          name (str): Name of artifact. Used as reference from
              consuming tasks.
          session (boolean, False): Session artifact.

        Example:

          .. literalinclude:: ../examples/artifacts/build.jolt
            :language: python
            :caption: examples/artifacts/build.jolt

        """
        name = utils.canonical(name)

        def decorate(cls):
            _old_artifacts = cls._artifacts

            @functools.wraps(cls._artifacts)
            def _artifacts(self, cache, node):
                artifacts = _old_artifacts(self, cache, node)
                artifacts += [cache.get_artifact(node, name, session=session)]
                return artifacts

            cls._artifacts = _artifacts
            return cls

        return decorate

    @staticmethod
    def artifact_upload(uri, name="main", condition=None):
        """
        Decorator to add uploading of an artifact to a server.

        Upon successful completion of the task, the resulting
        artifact uploaded to the specified URI. The URI should
        be in the format `protocol://user:password@host/path`.

        The following protocols are supported:

          - `http://`
          - `https://`
          - `file://`

        Local path are also supported in which case the artifact
        is copied to the specified location.

        If the path ends with a slash, the artifact is treated as
        a directory and copied into the root of the directory.

        If the path ends with a supported archive extension, the
        artifact is archived and optionally compressed before being
        copied. See :func:`jolt.Tools.archive` for supported archive
        and compression formats.

        Usernames and passwords are optional. If omitted, the
        artifact is uploaded anonymously. Environment variables
        can be used to store sensitive information, such as
        passwords. Specify the environment variable name in the
        URI as `protocol://{environ[USER]}:{environ[PASS]}@host/path`.

        The upload can be conditioned on the return value of a
        function. The function is passed the task instance as
        an argument and should return a boolean value. If the
        function returns ``False``, the upload is skipped. The value
        of the condition influences the hash of the task.

        Args:
            condition (str): Condition function to evaluate before
                uploading the artifact. The function is passed the
                task instance as an argument and should return a
                boolean value. By default, the artifact is always
                uploaded.
            name (str): Name of the artifact to upload.
            uri (str): Destination URI for the artifact.

        Example:

            .. literalinclude:: ../examples/artifacts/upload.jolt
                :language: python
                :caption: examples/artifacts/upload.jolt
        """

        def decorate(cls):
            if name == "main":
                old_publish = cls.publish
            else:
                old_publish = getattr(cls, "publish_" + name, None)

            raise_error_if(old_publish is None, f"Cannot upload artifact '{name}' from task '{cls.name or cls.__name__.lower()}', it does not exist")

            def upload_file(self, tools, cwd, src, dst):
                with tools.cwd(cwd):
                    tools.upload(src, dst + src)

            def copy_file(self, tools, cwd, src, dst):
                with tools.cwd(cwd):
                    tools.copy(src, dst + src)

            def list_files(self, artifact, tools):
                with tools.cwd(artifact.path):
                    for path in tools.glob("**"):
                        # Skip directories
                        if tools.isdir(path):
                            continue
                        yield artifact.path, path

            def archive_files(self, artifact, tools, filename):
                out = tools.builddir(artifact.identity)
                with tools.cwd(out):
                    tools.archive(artifact.path, filename)
                    yield out, filename

            @functools.wraps(cls.publish)
            def publish(self, artifact, tools):
                old_publish(self, artifact, tools)

                if condition and not bool(condition(self)):
                    return

                # Expand keywords
                uri_exp = tools.expand(uri)

                # Parse URI to determine protocol
                uri_parsed = urlparse(uri_exp)
                if uri_parsed.scheme in ["http", "https"]:
                    action = upload_file
                elif uri_parsed.scheme in ["", "file"]:
                    uri_exp = uri_parsed.path
                    action = copy_file
                else:
                    raise_task_error(self, f"Unsupported protocol '{uri_parsed.scheme}' in URI '{uri_exp}'")

                if uri_exp.endswith("/"):
                    generator = list_files
                else:
                    generator = functools.partial(archive_files, filename=fs.path.basename(uri_parsed.path))
                    uri_exp = fs.path.dirname(uri_exp) + "/"

                if action is copy_file:
                    uri_exp = tools.expand_path(uri_exp) + "/"

                for cwd, file in generator(self, artifact, tools):
                    action(self, tools, cwd, file, uri_exp)

            if name == "main":
                setattr(cls, "publish", publish)
            else:
                setattr(cls, "publish_" + name, publish)

            if condition:
                old_init = cls.__init__

                @functools.wraps(cls.__init__)
                def new_init(self, *args, **kwargs):
                    old_init(self, *args, **kwargs)

                    def make_bool(fn, *args, **kwargs):
                        return bool(fn(*args, **kwargs))

                    self.influence.append(CallbackInfluence(f"Upload {name}", make_bool, condition, self))

                cls.__init__ = new_init

            return cls

        return decorate

    @staticmethod
    def attribute(alias, target, influence=True, default=False):
        """
        Decorates a task with an alias for another attribute.

        Args:
            attrib (str): Name of alias attribute.
            target (str): Name of target attribute.
                Keywords are expanded.
            influence (boolean): Add value of target
                attribute as influence of the task.
            default (boolean): Return alias attribute if
                target attribute does not exist. Value is
                accessed through the alias attribute name
                with a leading underscore, e.g. '_alias'.

        """
        def _decorate(cls):
            def _get(self):
                if default:
                    return getattr(self, self.expand(target), getattr(self, self.expand(alias)))
                return getattr(self, self.expand(target))
            if default:
                setattr(cls, "_" + alias, property(_get))
            else:
                setattr(cls, alias, property(_get))
            if influence:
                attribute_influence(target)(cls)
            return cls
        return _decorate

    @staticmethod
    def environ(envname, influence=True):
        """
        Decorator marking the task as dependent on an environment variable.

        The value of the environment variable will be automatically
        transferred to workers in distributed network builds.

        Args:
            envname (str): Name of the environment variable.
            influence (boolean): Add value of environment
                variable as influence of the task. Default: True.

        """
        def _decorate(cls):
            if influence:
                environ_influence(envname)(cls)
            name = "_environ_" + utils.canonical(envname.lower())
            export = EnvironExport(envname)
            export.__set_name__(cls, name)
            setattr(cls, name, export)
            return cls
        return _decorate

    @staticmethod
    def publish_files(attrib):
        """
        Decorator adding a list attribute where file publication can be specified.

        Each item in the list is a set of arguments passed directly to
        :func:`jolt.Artifact.collect`. Tuples, dictionaries and strings are
        accepted.

        Example:

        .. code-block:: python

          @jolt.attributes.publish_files("collect")
          class Example(Task):
              collect = [
                  # Publish file.txt into artifact root
                  "file.txt",

                  # Publish file.txt into artifact dir/ directory
                  ("file.txt", "dir/"),

                  # Publish files from dir/ into artifact root
                  {"files": "*", "cwd": "dir"},
              ]

        """

        def decorate(cls):
            if not hasattr(cls, "__publish_files"):
                old_pub = cls.publish

                def publish(self, artifact, tools):
                    old_pub(self, artifact, tools)
                    for args in getattr(self, "__publish_files")():
                        if type(args) is tuple:
                            artifact.collect(*args)
                        elif type(args) is dict:
                            artifact.collect(**args)
                        else:
                            artifact.collect(args)

                cls.publish = publish

            return utils.concat_attributes("_publish_files", attrib)(cls)
        return decorate

    @staticmethod
    def requires(attrib):
        """
        Decorates a task with an alternative ``requires`` attribute.

        The new attribute will be concatenated with the regular
        ``requires`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
        """
        return utils.concat_attributes("requires", attrib)

    @staticmethod
    def load(filepath):
        """
        Decorator which loads task class attributes from a file.

        The loaded file is Python source file declaring a dictionary
        with keys and values to be assigned to the task instance.

        The file is automatically registered as task hash influence.

        Example:

        .. code-block:: python

          @attributes.load("attributes-{os}.py")
          class Print(Task):
              os = Parameter()

              def run(self, deps, tools):
                  print("OS Author: ", self.os_author)

        .. code-block:: python

          # attributes-linux.py
          {
              "os_author": "Torvalds",
          }

        .. code-block:: bash

          $ jolt build print:os=linux

        """
        def decorate(cls):
            cls = file_influence(filepath)(cls)
            old_init = cls.__init__

            def new_init(self, *args, **kwargs):
                old_init(self, *args, **kwargs)
                for key, val in eval(self.tools.read_file(filepath)).items():
                    setattr(self, key, val)
                    self.requires = utils.unique_list(
                        utils.call_or_return_list(self, self.__class__._requires))
                self.requires = self.expand(self.requires)

            cls.__init__ = new_init
            return cls
        return decorate

    @staticmethod
    def method(alias, target, influence=True):
        """
        Decorates a task with an alias for another method.

        Args:
            attrib (str): Name of alias method.
            target (str): Name of target method.
                Keywords are expanded.
            influence (boolean): Add source of target
                method as influence of the task.

        """
        def _decorate(cls):
            def _call(self, *args, **kwargs):
                return getattr(self, self.expand(target))(*args, **kwargs)
            setattr(cls, alias, _call)
            if influence:
                source_influence(target)(cls)
            return cls
        return _decorate

    @staticmethod
    def platform(attrib):
        """
        Decorates a task with an alternative ``platform`` attribute.

        The new attribute will be concatenated with the regular
        ``platform`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
        """
        return utils.concat_attributes("platform", attrib)

    @staticmethod
    def system(cls):
        """
        Decorates a task with a property returning the operating system name.

        Examples: "linux", "windows"
        """
        cls._system = Export(lambda t: platform.system().lower())
        cls.system = property(lambda t: t._system.value)
        return cls

    @staticmethod
    def timeout(seconds):
        """
        Decorator setting a timeout for a task.

        The timeout applies to the task's run method. A JoltTimeoutError
        is raised if the task does not complete within the specified time.

        Args:
            seconds (int): Timeout in seconds.

        Example:

        .. code-block:: python

            @attributes.timeout(5)
            class Example(Task):
                def run(self, deps, tools):
                    time.sleep(10)

        """
        def decorate(cls):
            _old_run = cls.run

            @functools.wraps(cls.run)
            def run(self, deps, tools):
                with tools.timeout(seconds):
                    _old_run(self, deps, tools)

            cls.run = run
            return cls

        return decorate


class TaskBase(object):
    """ Task base class. """

    cacheable = True
    """ Whether the task produces an artifact or not. """

    expires = Immediately()
    """An expiration strategy, defining when the artifact may be evicted from the cache.

    When the size of the artifact cache exceeds the configured limit
    an attempt will be made to evict artifacts from the cache. The eviction
    algorithm processes artifacts in least recently used (LRU) order until
    an expired artifact is found.

    By default, an artifact expires immediately and may be evicted at any time
    (in LRU order). An exception to this rule is if the artifact is required by
    a task in the active task set. For example, if a task A requires the output
    of task B, B will never be evicted by A while A is being executed.

    There are several expiration strategies to choose from:

     - :class:`jolt.expires.WhenUnusedFor`
     - :class:`jolt.expires.After`
     - :class:`jolt.expires.Never`

    Examples:

        .. code-block:: python

          # May be evicted if it hasn't been used for 15 days
          expires = WhenUnusedFor(days=15)

        .. code-block:: python

          # May be evicted 1h after creation
          expires = After(hours=1)

        .. code-block:: python

          # Never evicted
          expires = Never()

    """

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
    """ List of influence provider objects """

    joltdir = "."
    """ Path to the directory of the .jolt file where the task was defined. """

    joltproject = None
    """ Name of project this task belongs to. """

    name = None
    """ Name of the task. Derived from class name if not set. """

    platform = {}
    """
    Dictionary of task platform requirements.

    Platform requirements control where tasks are allowed to execute.
    Multiple requirement key/values may be specified in which case all
    must be fulfilled in order for the task to be schedulable on a node.

    The following builtin requirement labels exist:

      - node.arch ["arm", "amd64"]
      - node.os ["linux", "windows"]

    Example:

      .. code-block:: python

        class Hello(Task):
            # This task must run on Linux.
            platform = {
                "node.os": "linux",
            }

    """

    requires = []
    """ List of dependencies to other tasks. """

    selfsustained = False
    """ Consume this task independently of its requirements.

    Requirements of a self-sustained task will be pruned if the task artifact
    is present in a cache. In other words, if the task is not executed its
    requirements are considered unnecessary.

    For example, consider the task graph A -> B -> C. If B is self-sustained
    and present in a cache, C will never be executed. C will also never be a
    transitive requirement of A. If A requires C, it should be listed
    as an explicit requirement.

    Using this attribute speeds up execution and reduces network
    traffic by allowing the task graph to be reduced.
    """

    taint = None
    """ An arbitrary value used to change the identity of the task.

    It may be hard to remove bad artifacts in a distributed build
    environment. A better method is to taint the task and let the
    artifact be recreated with a different identity.
    """

    weight = 0
    """
    Indication of task execution time.

    The weight is used to optimize the order in which tasks are
    executed using a heuristic scheduling algorithm where ready
    tasks along the critical path are favored.
    """

    _instance = Export(lambda t: str(uuid.uuid4()))
    """
    Task instance identifier.

    The instance ID identifies an execution request and is always unique.

    While the task hash identity may be identical for multiple parallel
    execution requests, the instance ID won't be.
    """

    def __init__(self, parameters=None, manifest=None, buildenv=None, **kwargs):
        self._identity = None
        self._report = _JoltTask()
        self.name = self.__class__.name

        self._create_exports_and_parameters()
        self._set_parameters(parameters)

        self.cacheable = self.__class__.cacheable
        self.extends = self.expand(utils.call_or_return_list(self, self.__class__.extends))
        raise_task_error_if(
            len(self.extends) != 1, self,
            "Multiple tasks extended, only one allowed")
        self.extends = self.extends[0]
        self.influence = utils.call_or_return_list(self, self.__class__._influence)
        self.influence.append(TaskClassSourceInfluence())
        self.influence.append(TaintInfluenceProvider())
        self.requires = utils.unique_list(utils.call_or_return_list(self, self.__class__._requires))
        self.selfsustained = utils.call_or_return(self, self.__class__._selfsustained)
        self.tools = Tools(self, self.joltdir)
        self._apply_manifest(manifest)
        self._apply_protobuf(buildenv)
        self.requires = self.expand(self.requires)

    def _apply_manifest(self, manifest):
        if manifest is None:
            return
        manifest_task = manifest.find_task(self.qualified_name)
        if manifest_task is not None:
            if manifest_task.identity:
                self.identity = manifest_task.identity
            for attrib in manifest_task.attributes:
                export = utils.getattr_safe(self, attrib.name)
                assert isinstance(export, Export), \
                    "'{0}' is not an exportable attribute of task '{1}'"\
                    .format(attrib.name, self.qualified_name)
                export.assign(attrib.value)

    def _apply_protobuf(self, buildenv):
        if buildenv is None:
            return
        task = buildenv.tasks.get(self.short_qualified_name)
        if not task:
            return
        if task.identity:
            self.identity = task.identity
        if task.taint:
            self.taint = task.taint
        for prop in task.properties:
            export = utils.getattr_safe(self, prop.key)
            assert isinstance(export, Export), \
                "'{0}' is not an exportable attribute of task '{1}'"\
                .format(prop.key, self.qualified_name)
            export.assign(prop.value)

    def _artifacts(self, cache, node):
        return [cache.get_artifact(node, "main")]

    def _influence(self):
        return utils.as_list(self.__class__.influence)

    def _requires(self):
        return utils.call_or_return_list(self, self.__class__.requires)

    def _selfsustained(self):
        return utils.call_or_return(self, self.__class__.selfsustained)

    def _create_exports_and_parameters(self):
        self._exports = {}
        self._parameters = {}

        for key, export in Export.__get_exports__(self).items():
            export = copy.copy(export)
            export.set_task(self)
            setattr(self, key, export)
            self._exports[key] = export

        for key, param in Parameter.__get_params__(self).items():
            param = copy.copy(param)
            setattr(self, key, param)
            self._parameters[key] = param

    def _set_parameters(self, params):
        params = params or {}
        for key, value in params.items():
            try:
                param = utils.getattr_safe(self, key)
            except AttributeError:
                raise_task_error(self, "No such parameter '{0}'", key)
            if isinstance(param, Parameter):
                try:
                    param.set_value(value)
                except (ParameterValueError, ParameterImmutableError) as e:
                    raise_task_error(self, str(e))
                continue
            raise_task_error(self, "No such parameter '{0}'", key)
        self._assert_required_parameters_assigned()

    @staticmethod
    def _set_default_parameters(cls, params):
        params = params or {}
        for key, value in params.items():
            param = utils.getattr_safe(cls, key, None)
            if isinstance(param, Parameter):
                param = copy.copy(param)
                param.set_default(value)
                setattr(cls, key, param)
                continue
            raise_task_error(cls.name, "No such parameter '{0}'", key)

    def _assert_required_parameters_assigned(self):
        for key, param in self._get_parameter_objects().items():
            raise_task_error_if(
                param.is_required() and param.is_unset(), self,
                "Required parameter '{0}' has not been set", key)

    def _verify_influence(self, deps, artifact, tools, sources=None):
        # Verify that any transformed sources are influencing
        sources = set(map(tools.expand_path, sources or []))

        # Verify that published files are influencing
        for src, _ in artifact.files.items():
            src = tools.expand_path(src)
            if fs.path.isdir(src):
                sources.update(fs.scandir(src))
            else:
                sources.add(src)

        def _subpath_filter(rootpath):
            def _filter(fname):
                return not fs.is_relative_to(fname, rootpath)
            return _filter

        for _, dep in deps.items():
            deptask = dep.task
            if isinstance(deptask, FileInfluence):
                # Resource dependencies may cover the influence implicitly
                deppath = self.tools.expand_path(str(deptask.path))
                sources = set(filter(lambda d: not deptask.is_influenced_by(self, d), sources))
            else:
                # Ignore any files in artifacts
                deppath = self.tools.expand_path(dep.path)
                sources = set(filter(_subpath_filter(deppath), sources))

        # Ignore any files in build directories
        sources = filter(_subpath_filter(tools.expand_path(tools.buildroot)), sources)
        sources = set(sources)

        for ip in self.influence:
            if not isinstance(ip, FileInfluence):
                continue
            ok = [source for source in sources if ip.is_influenced_by(self, source)]
            sources.difference_update(ok)
        for source in sources:
            log.warning("Missing influence: {} ({})", source, self.name)
        raise_task_error_if(sources, self, "Task is missing source influence")

    def _get_export_objects(self):
        return self._exports

    def _get_parameter_objects(self, unset=False):
        return self._parameters

    def _get_parameters(self, unset=False):
        return {
            key: param.get_value()
            for key, param in self._get_parameter_objects().items()
            if unset or not param.is_unset()
        }

    def _get_explicitly_set_parameters(self):
        return {
            key: param.get_value()
            for key, param in self._get_parameter_objects().items()
            if param.is_set()
        }

    def __str__(self):
        return str(self.name)

    @property
    def canonical_name(self):
        return utils.canonical(self.name)

    @property
    def qualified_name(self):
        return utils.format_task_name(
            self.name,
            self._get_parameters())

    @property
    def short_qualified_name(self):
        return utils.format_task_name(
            self.name,
            self._get_explicitly_set_parameters())

    def expand(self, string_or_list, *args, **kwargs):
        """ Expands keyword arguments/macros in a format string.

        See :func:`jolt.Tools.expand` for details.
        """

        try:
            kwargs["_instance"] = self
            if type(string_or_list) is list:
                return [utils.expand(string, *args, **kwargs) for string in string_or_list]
            return utils.expand(string_or_list, *args, **kwargs)
        except KeyError as e:
            raise_task_error(self, "Invalid macro '{0}' encountered - forgot to set a parameter?", e)

    @property
    def identity(self):
        return self._identity

    @identity.setter
    def identity(self, identity):
        self._identity = identity

    def is_cacheable(self):
        return self.cacheable

    def is_runnable(self):
        return True


class Task(TaskBase):
    #: Path to the .jolt file where the task was defined.

    abstract = True
    """ An abstract task class indended to be subclassed.

    Abstract tasks can't be executed and won't be listed.
    """

    unstable = False
    """
    An unstable task is allowed to fail without stopping or failing the entire build.

    The unstable task is still reported as a failure at the end of the build.
    """

    def __init__(self, parameters=None, **kwargs):
        super().__init__(parameters, **kwargs)

    def info(self, fmt, *args, **kwargs):
        """
        Log information about the task.
        """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.info(fmt, *args, **kwargs)

    def warning(self, fmt, *args, **kwargs):
        """ Log a warning concerning the task """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.warning(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        """ Log an error concerning the task """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.error(fmt, *args, **kwargs)

    def verbose(self, fmt, *args, **kwargs):
        """
        Log verbose information about the task.
        """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.verbose(fmt, *args, **kwargs)

    def clean(self, tools):
        """
        Cleans up resources and intermediate files created by the task.

        The method is invoked in response to the user running clean
        on the command line. It should restore the environment to its
        original state. The next execution of the task should behave
        as if the task is executed for the first time.

        An implementation must not clean any local or remote artifact cache.
        """

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

    def nopublish(self, artifact, tools):
        raise NotImplementedError()

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

    def debugshell(self, deps, tools):
        """
        Invoked to start a debug shell.

        The method prepares the environment with attributes exported by task requirement
        artifacts. The shell is entered by passing the ``-g`` flag to the build command.

        Task execution resumes normally when exiting the shell.
        """
        with tools.environ(PS1="jolt$ ") as env:
            from jolt import config
            subprocess.call(config.get_shell().split(), env=env, cwd=tools._cwd)

    @contextmanager
    def report(self):
        """
        Provide error analysis for task.

        Intentionally undocumented. Use at own risk.
        """
        yield ReportProxy(self, self._report)


class SubTask(object):
    def __init__(self, task):
        self._deps = []
        self._identity = []
        self._influence = []
        self._message = None
        self._outputs = []
        self._task = task
        self._tools = copy.copy(task.tools)

    def __str__(self):
        if self.message:
            return self.message
        if self._outputs:
            return " ".join(self._outputs)
        return None

    @property
    def dependencies(self):
        return self._deps

    @functools.cached_property
    def identity(self):
        sha = hashlib.sha1()
        for ident in self._identity:
            sha.update(ident.encode())
        for output in self._outputs:
            sha.update(output.encode())
        if self.message:
            sha.update(self.message.encode())
        return sha.hexdigest()

    @functools.cached_property
    def influence(self):
        sha = hashlib.sha1()
        for infl in self._influence:
            if callable(infl):
                sha.update(infl().encode())
            else:
                sha.update(infl.encode())
        for dep in self._deps:
            sha.update(dep.influence.encode())
        return sha.hexdigest()

    @functools.cached_property
    def is_outdated(self):
        try:
            with self._tools.cwd(self._tools.builddir("subtasks", incremental=True)):
                if self.influence != self._tools.read_file(self.identity):
                    return True
                for output in self.outputs:
                    output = fs.as_canonpath(output)
                    assert self._tools.read_file(output + ".identity") == self.identity

                # FIXME: Check hash content of output file
                for output in self.outputs:
                    if not fs.path.exists(fs.path.join(self._task.joltdir, output)):
                        return True
                for dep in self.dependencies:
                    if dep.is_outdated:
                        return True
            return False
        except Exception:
            return True

    def set_uptodate(self):
        try:
            del self.influence
            del self.is_outdated
        except AttributeError:
            pass
        with self._tools.cwd(self._tools.builddir("subtasks", incremental=True)):
            self._tools.write_file(self.identity, self.influence)

            for output in self.outputs:
                output = fs.as_canonpath(output)
                self._tools.mkdirname(output)
                self._tools.write_file(output + ".identity", self.identity)

    def run(self):
        pass

    def add_dependency(self, dep):
        deps = utils.as_list(dep)
        subtasks = [self._task._add_input(dep) for dep in deps]
        self._deps.extend(subtasks)

    def add_identity(self, infl):
        self._identity.append(infl)

    def add_influence(self, infl):
        self._influence.append(infl)

    def add_influence_file(self, path):
        path = self._tools.expand_path(path)
        self.add_influence(utils.filesha1(path))

    def add_influence_depfile(self, path):
        def depfile():
            result = ""
            try:
                deps = self._tools.read_depfile(fs.path.join(self._task.joltdir, path))
            except OSError:
                return "N/A"
            with self._tools.cwd(self._task.joltdir):
                for output in self.outputs:
                    for input in deps.get(output, []):
                        input = self._tools.expand_path(input)
                        result += utils.filesha1(input)
            return result
        self.add_influence(depfile)

    def add_output(self, output):
        self.add_identity(output)
        if type(output) is list:
            self._outputs.extend(output)
        else:
            self._outputs.append(output)

    @property
    def message(self):
        return self._message

    def set_message(self, message):
        self._message = message

    @property
    def outputs(self):
        return self._outputs


class Input(SubTask):
    def __init__(self, task, input):
        super().__init__(task)
        self._outputs = [input]
        self.add_influence_file(input)
        self.set_uptodate()

    @property
    def message(self):
        return f"[IN] {self._outputs[0]}"

    def run(self):
        raise_task_error(self._task, "Input file '{}' does not exist", self._outputs[0])


class CommandSubtask(SubTask):
    def __init__(self, task, command):
        super().__init__(task)
        self.add_identity(command)
        self._command = command

    def __str__(self):
        s = super().__str__()
        return s if s is not None and not log.is_verbose() else self._tools.expand(self._command)

    def run(self):
        self._tools.run(self._command)


class FunctionSubtask(SubTask):
    def __init__(self, task, fn):
        super().__init__(task)
        self.add_identity(fn.__name__)
        self.fn = fn

    def run(self):
        self.fn(self)


class RenderSubtask(SubTask):
    def __init__(self, task, template, **kwargs):
        super().__init__(task)
        self._data = self._tools.render(template, **kwargs)
        self.add_identity(template)
        self.add_influence(self._data)

    def run(self):
        for output in self.outputs:
            self._tools.write_file(output, self._data, expand=False)


class FileRenderSubtask(SubTask):
    def __init__(self, task, path, **kwargs):
        super().__init__(task)
        self.add_identity(path)
        self._path = path

    def run(self):
        data = self._tools.render_file(self._path)
        for output in self.outputs:
            self._tools.write_file(output, data, expand=False)


class MultiTask(Task):
    """
    A task with subtasks that are executed in parallel with intermediate caching.

    A MultiTask is useful for tasks with many subtasks that benefit from intermediate
    caching, such as compilation tasks where multiple source files are compiled into
    object files and then either linked into an executable or archived into a library.

    Subtasks are executed in parallel and their output is cached locally in a build
    directory. The output is not automatically shared with other Jolt clients, only
    the files published by the MultiTask is shared. A subtask is only re-executed
    if the influence one of its dependencies change.

    Subtasks are defined in the MultiTask method generate() and they can be either
    a shell command or a python function. Helper methods in the class allow
    implementors to define outputs and inter-subtask dependencies.

    Example:

        .. code-block:: python

          flags = ["-DDEBUG"]

          def generate(self, deps, tools):
              sources = ["a.cpp", "b.cpp", "c.cpp"]
              objects = []

              # Create compilation subtasks for each source file
              for source in sources:
                  object = self.command(
                      "g++ {flags} -c {inputs} -o {outputs} ",
                      inputs=[source],
                      outputs=[source  +".o"])
                  objects.append(object)

              # Create linker subtask
              executable = self.command(
                  "g++ {inputs} -o {output}",
                  inputs=objects,
                  outputs=["executable"])

    """

    abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subtasks = set()
        self._subtasks_by_output = {}

    def _add_subtask(self, subtask):
        self._subtasks.add(subtask)

        for output in subtask.outputs:
            if output in self._subtasks_by_output:
                othersubtask = self._subtasks_by_output
                raise_task_error(
                    self,
                    "'{}' is generated by both '{}' and '{}'",
                    output, subtask.command, othersubtask.command)
            self._subtasks_by_output[output] = subtask

        return subtask

    def _find_subtask(self, output):
        return self._subtasks_by_output.get(output)

    def _add_input(self, input):
        raise_task_error_if(not input, self, "Input is None")
        if not isinstance(input, SubTask):
            inputsubtask = self._find_subtask(input)
            if inputsubtask:
                return inputsubtask
            inputsubtask = Input(self, input)
        else:
            inputsubtask = input
        self._subtasks.add(inputsubtask)
        self._subtasks_by_output[input] = inputsubtask
        return inputsubtask

    def _to_subtask_list(self, inputs):
        inputs = utils.as_list(inputs)
        return utils.unique_list([self._add_input(input) for input in inputs])

    def _to_output_files(self, subtasks):
        subtasks = utils.as_list(subtasks)
        outputs = []
        for subtask in subtasks:
            if isinstance(subtask, SubTask):
                outputs.extend(subtask.outputs)
            else:
                outputs.append(subtask)
        return outputs

    def _to_input_subtasks(self, inputs, **kwargs):
        inputs = utils.as_list(inputs)
        subtasks = []
        for input in inputs:
            input = self.expand(input, **kwargs)
            subtasks.append(self._add_input(input))
        return subtasks

    def command(self, command, inputs=None, outputs=None, message=None, mkdir=True, **kwargs):
        """
        Create shell command subtask.

        The subtask executes the specified command. String format specifiers may be used and
        are resolved primarily by kwargs and secondarily by task attributes.

        Args:
            inputs (str, list): files or subtasks that the command depends on.
            outputs (str, list): list of files that the subtasks produces.
            message (str): custom message that the subtask will print when executed.
            mkdir (boolean): automatically create directories for outputs. If False,
                the caller must ensure that the directories exist before the the subtask
                is executed.
            kwargs: additional keyword values used to format the command line string.

        Returns:
            Subtask object.

        Example:

            .. code-block:: python

              executable = self.command(
                  "g++ {inputs} -o {output}",
                  inputs=["main.cpp"],
                  outputs=["executable"])

        """
        input_jobs = self._to_input_subtasks(inputs, **kwargs)
        inputfiles = self._to_output_files(inputs)

        outputs = utils.as_list(outputs)
        outputs = [self.tools.expand_relpath(output, self.joltdir, **kwargs) for output in outputs]

        dirs = set()
        if mkdir:
            for output in outputs:
                dirs.add(self.mkdirname(output, inputs=inputfiles, outputs=outputs, **kwargs))

        command = self.expand(command, inputs=inputfiles, outputs=outputs, **kwargs)
        subtask = CommandSubtask(self, command)

        for dir in dirs:
            subtask.add_dependency(dir)
        for input in input_jobs:
            subtask.add_dependency(input)
        for output in outputs:
            output = self.expand(output, inputs=inputfiles, outputs=outputs, **kwargs)
            subtask.add_output(output)

        if message:
            subtask.set_message(self.expand(message, inputs=inputfiles, outputs=outputs, **kwargs))

        self._add_subtask(subtask)

        return subtask

    def call(self, fn, outputs, **kwargs):
        """
        Create a Python function call subtask.

        The subtask executes the specified Python function, passing the subtask as argument.

        Args:
            fn (func): Python function to execute.
            outputs (str, list): list of files that the subtasks produces.
            kwargs: additional keyword values used to format the output file paths.

        Returns:
            Subtask object.

        Example:

            .. code-block:: python

              def mkdir(subtask):
                  for output in subtask.outputs:
                      self.tools.mkdir(output)

              dirtask = self.call(mkdir, outputs=["newly/created/directory"])

        """
        subtask = FunctionSubtask(self, fn)
        outputs = utils.as_list(outputs)
        for output in outputs:
            output = self.tools.expand_relpath(output, self.joltdir, outputs=outputs, **kwargs)
            subtask.add_output(output)
        self._add_subtask(subtask)
        return subtask

    def mkdir(self, path, *args, **kwargs):
        """
        Create a subtask that creates a directory.

        Args:
            path (str): Path to directory.
            kwargs: additional keyword values used to format the directory path string.

        Returns:
            Subtask object.

        Example:

            .. code-block:: python

              dirtask = self.mkdir("{outdir}/directory", outdir=tools.builddir())
        """
        path = self.expand(path, *args, **kwargs)
        subtask = self._find_subtask(path)
        if not subtask:
            subtask = self.call(lambda subtask: self.tools.mkdir(path), [path])
        return subtask

    def mkdirname(self, path, *args, **kwargs):
        """
        Create a subtask that creates a parent directory.

        Args:
            path (str): Path for which the parent directory shall be created.
            kwargs: additional keyword values used to format the directory path string.

        Returns:
            Subtask object.

        Example:

            .. code-block:: python

              # Creates {outdir}/directory
              dirtask = self.mkdir("{outdir}/directory/object.o", outdir=tools.builddir())

        """
        path = self.expand(path, *args, **kwargs)
        path = fs.path.dirname(path)
        return self.mkdir(path, *args, **kwargs)

    def render(self, template, outputs, **kwargs):
        """
        Create a subtask that renders a Jinja template string to file.

        Args:
            template (str): Jinja template string.
            outputs (str, list): list of files that the subtasks produces.
            kwargs: additional keyword values used to render the template and output file paths.

        Returns:
            Subtask object.

        Example:

            .. code-block:: python

              # Creates file.list with two lines containing "a.o" and "b.o"

              template_task = self.render(
                  "{% for line in lines %}{{ line }}\\n{% endfor %}",
                  outputs=["file.list"],
                  lines=["a.o", "b.o"])

        """
        outputs = utils.as_list(outputs)
        subtask = RenderSubtask(self, template, **kwargs)
        for output in outputs:
            output = self.tools.expand_relpath(output, self.joltdir, outputs=outputs, **kwargs)
            subtask.add_output(output)
        self._add_subtask(subtask)
        return subtask

    def render_file(self, template, outputs, **kwargs):
        """
        Create a subtask that renders a Jinja template file to file.

        Args:
            template (str): Jinja template file path.
            outputs (str, list): list of files that the subtasks produces.
            kwargs: additional keyword values used to format the output file paths.

        Returns:
            Subtask object.

        Example:

            .. code-block:: python

              # Render file.list.template into file.list
              template_task = self.render_file("file.list.template", outputs=["file.list"])

        """
        template = self._to_subtask_list(template)
        templatefiles = self._to_output_files(template)
        raise_task_error_if(len(templatefiles) > 1, "Can only render one template at a time")

        outputs = utils.as_list(outputs)
        subtask = FileRenderSubtask(self, templatefiles[0], **kwargs)
        for output in outputs:
            output = self.tools.expand_relpath(output, outputs=outputs, **kwargs)
            subtask.add_output(output)
        for input in templatefiles:
            subtask.add_dependency(input)
        self._add_subtask(subtask)
        return subtask

    def generate(self, deps, tools):
        """
        Called to generate subtasks.

        An implementer can override this method in order to create subtasks
        that will later be executed during the :func:`~run` stage of the task.

        Subtasks can be defined using either of these helper methods:

          - :func:`~call`
          - :func:`~command`
          - :func:`~mkdir`
          - :func:`~mkdirname`
          - :func:`~render`
          - :func:`~render_file`

        """
        pass

    def run(self, deps, tools):
        """
        Executes subtasks defined in :func:`~generate`.

        This method should typically not be overridden in subclasses.
        """
        self.generate(deps, tools)

        log.debug("About to start executing these subtasks:")
        for subtask in self._subtasks:
            for subtaskout in subtask.outputs:
                if not subtask.dependencies:
                    log.debug("  {}", subtaskout)
                for dep in subtask.dependencies:
                    for depout in dep.outputs:
                        log.debug("  {}: {}", subtaskout, depout)

        subtasks = {}
        deps = {}

        # Build graph of inverse dependencies
        for subtask in self._subtasks:
            if subtask not in subtasks:
                subtasks[subtask] = []
            if subtask not in deps:
                deps[subtask] = []
            for dep in subtask.dependencies:
                if dep not in deps:
                    deps[dep] = []
                deps[dep].append(subtask)
                subtasks[subtask].append(dep)

        # Prune up-to-date subtasks
        for subtask in list(filter(lambda subtask: not subtask.is_outdated, subtasks.keys())):
            log.debug("Pruning {}", subtask)
            del subtasks[subtask]
            for dep in deps[subtask]:
                try:
                    subtasks[dep].remove(subtask)
                except KeyError:
                    pass

        self.subtaskindex = 0
        self.subtaskcount = len(subtasks)

        lock = RLock()

        with ThreadPoolExecutor(max_workers=tools.cpu_count()) as pool:
            futures = {}

            while subtasks or futures:
                completed = []
                candidates = [subtask for subtask, deps in subtasks.items() if not deps]

                if not candidates and not futures:
                    break

                for subtask in candidates:
                    del subtasks[subtask]
                    if subtask.is_outdated:
                        def runner(subtask):
                            with lock:
                                self.subtaskindex += 1
                                log.info("[{}/{}] {}", self.subtaskindex, self.subtaskcount, str(subtask))
                            subtask.run()
                        futures[pool.submit(functools.partial(runner, subtask))] = subtask
                    else:
                        completed.append(subtask)

                for future in as_completed(futures.keys()):
                    subtask = futures[future]
                    del futures[future]
                    completed.append(subtask)

                    try:
                        future.result()
                        subtask.set_uptodate()
                    except Exception as e:
                        for future in futures:
                            future.cancel()
                        raise e
                    break

                for subtask in completed:
                    for dep in deps[subtask]:
                        subtasks[dep].remove(subtask)

            if subtasks:
                log.debug("These remaining subtasks could not be started due to unresolved dependencies")
                for subtask in subtasks:
                    log.debug("  {}", str(subtask))
                    for dep in subtask.dependencies:
                        log.debug("   - {}", str(dep))

            raise_task_error_if(subtasks, self, "Subtasks with unresolved dependencies could not be executed")

    def inputs(self, jobs):
        return self._to_subtask_list(jobs)

    def outputs(self, jobs):
        jobs = utils.as_list(jobs)
        return [output for job in jobs for output in job.outputs]


class Runner(Task):
    """
    A Runner task executes applications packaged by other tasks.

    It is typically used to run test applications compiled and linked
    by other tasks. The Runner finds the executable through the artifact
    metadata string ``artifact.strings.executable`` which must be exported
    by the consumed task artifact.

    Example:

      .. code-block:: python

        from jolt import Runner, Task

        class Exe(Task):
            \"\"\" Publish a script printing 'Hello world' to stdout \"\"\"
            def publish(self, artifact, tools):
                with tools.cwd(tools.builddir()):
                    # Create Hello world script
                    tools.write_file("hello.sh", "#!/bin/sh\\necho Hello world")

                    # Make it executable
                    tools.chmod("hello.sh", 0o555)

                    # Publish script in artifact
                    artifact.collect("hello.sh")

                    # Inform consuming Runner task about executable's name
                    artifact.strings.executable = "hello.sh"

        class Run(Runner):
            \"\"\" Runs the 'Hello world' script \"\"\"
            requires = ["exe"]

    The Ninja CXXExecutable task class automatically sets the required artifact metadata.

    Example:

      .. code-block:: python

        from jolt import Task
        from jolt.plugins.ninja import CXXExecutable

        class Exe(CXXExecutable):
            \"\"\" Compiles and links the test application \"\"\"
            sources = ["test.cpp"]

        class Run(Runner):
            \"\"\" Runs the test application \"\"\"
            requires = ["exe"]

    """

    abstract = True

    args = []
    """
    List of arguments to pass to executables.

    The arguments are passed the same way to all executables if there
    are multiple task requirements.
    """

    requires = []
    """ List of tasks packaging executables to run. """

    shell = True
    """ Launch the executables through a shell. """

    timeout = None
    """ Time after which the executable will be terminated """

    def run(self, deps, tools):
        args = tools.expand(self.args)
        timeout = int(self.timeout) if self.timeout is not None else None
        found = False

        for task, artifact in deps.items():
            if not artifact.task.is_cacheable():
                continue
            if artifact.strings.executable.get_value() is None:
                self.verbose("No executable found in task artifact for '{}'", task)
                continue
            with tools.cwd(artifact.path):
                found = True
                exe = tools.expand_path(str(artifact.strings.executable))
                exe = [exe] + args
                exe = " ".join(exe) if self.shell else exe
                tools.run(exe, shell=bool(self.shell), timeout=timeout)

        raise_task_error_if(
            not found, self,
            "No executable found in any requirement artifact")


class ErrorProxy(object):
    def __init__(self, error):
        self._error = error

    @property
    def type(self):
        return self._error.type

    @type.setter
    def type(self, value):
        self._error.type = value

    @property
    def details(self):
        return self._error.details

    @property
    def location(self):
        return self._error.location

    @property
    def message(self):
        return self._error.message


class ReportProxy(object):
    def __init__(self, task, report):
        self._task = task
        self._report = report

    def add_error(self, type, location, message, details=""):
        """ Add an error to the build report. """
        error = self._report.create_error()
        error.type = type
        error.location = location
        error.message = message
        error.details = details
        return error

    def add_regex_errors(self, type, regex, logbuf):
        """
        Find errors in log using regex and add them to build report.

        The regex should contain these named match groups:

         - location - origin of the error
         - message  - a brief description of the error
         - details  - futher error details

        """
        for match in re.finditer(regex, logbuf, re.MULTILINE):
            error = match.groupdict()
            self.add_error(
                type,
                error.get("location", ""),
                error.get("message", ""),
                error.get("details", ""))

    def add_regex_errors_with_file(self, type, regex, logbuf, reldir, filterfn=lambda n: True):
        """
        Find errors in log using regex and add them to build report.

        Instead of using error details from the regex match,
        file content is used. For this to work the regex match
        must contain these named groups:

         - file - path to file
         - line - line number of error

        In case file is a relative path, reldir is the working directory.
        """
        errors_by_location = OrderedDict()
        for match in re.finditer(regex, logbuf, re.MULTILINE):
            error = match.groupdict()
            if not filterfn(error):
                continue
            if error["location"] not in errors_by_location:
                errors_by_location[error["location"]] = (error, [error["message"]], error["details"])
            else:
                errors_by_location[error["location"]][1].append(error["message"])

        for error, msgs, details in errors_by_location.values():
            message = "\n".join(utils.unique_list(msgs))
            if not details:
                with self._task.tools.cwd(self._task.tools.wsroot):
                    try:
                        details = self._task.tools.read_file(error["file"])
                        details = details.splitlines()
                        details = str(error["line"]) + ": " + details[int(error["line"]) - 1]
                    except Exception:
                        details = ""

            location = error.get("location", "")
            if location:
                with self._task.tools.cwd(self._task.tools.wsroot):
                    location = self._task.tools.expand_path(location)
                location = self._task.tools.expand_relpath(location, self._task.tools.wsroot)

            self.add_error(type, location, message, details)

    def add_exception(self, exc, errtype=None, location=None):
        """
        Add an exception to the build report.

        The exception traceback is included in the error details, but
        frames inside Jolt may be filtered out if the exception
        originated in a task recipe.

        No traceback is included if the exception is derived from JoltError.

        """
        tb = traceback.format_exception(type(exc), value=exc, tb=exc.__traceback__)

        installdir = fs.path.dirname(__file__)
        if any(map(lambda frame: installdir not in frame, tb[1:-1])):
            while len(tb) > 2 and installdir in tb[1]:
                del tb[1]
        loc = re.findall("(\".*?\", line [0-9]+, in .*?)\n", tb[1])
        location = location or (loc[0] if loc and len(loc) > 0 else "")
        message = log.format_exception_msg(exc)
        if isinstance(exc, JoltCommandError):
            details = "\n".join(exc.stderr)
        elif isinstance(exc, JoltError):
            details = ""
        else:
            details = "".join(tb)

        self.add_error(
            type=errtype or ("Exception" if not isinstance(exc, JoltError) else "Error"),
            location=location,
            message=message,
            details=details)

    @property
    def errors(self):
        return [ErrorProxy(error) for error in self._report.errors]

    @errors.setter
    def errors(self, errlist):
        assert all(isinstance(err, ErrorProxy) for err in errlist), "Invalid error list"
        self._report.clear_errors()
        for err in errlist:
            self.add_error(err.type, err.location, err.message, err.details)

    @property
    def manifest(self):
        return self._report

    def raise_for_status(self, log_details=False, log_error=False):
        for error in self.errors:
            if log_error:
                log.error("{}: {}", error.type, error.message, context=self._task.identity[:7])
            if log_details:
                for line in error.details.splitlines():
                    log.transfer(line, context=self._task.identity[:7])
            raise LoggedJoltError(JoltError(f"{error.type}: {error.message}"))


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

    release_on_error = False
    """ Call release if an exception occurs during acquire. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def is_runnable(self):
        return False

    def info(self, fmt, *args, **kwargs):
        pass

    def acquire(self, artifact, deps, tools, owner):
        """ Called to acquire the resource.

        An implementor overrides this method in a subclass. The acquired
        resource must be released manually if an exception occurs before the
        method has returned. If this method returns successfully, the :func:`~release`
        method is guaranteed to be called in the future upon completion of the
        consuming task (unless the process is forcibly interrupted or killed).

        Args:
            artifact (:class:`~jolt.Artifact`): The artifact associated with the resource.
                It is not possible to publish files from a resource, but the implementor
                can still use the resource to pass information to consuming tasks.
            deps (:class:`~jolt.Context`): Task execution context used to access the
                artifacts of dependencies.
            tools (:class:`~jolt.Tools`): A task specific toolbox.
            owner (:class:`~jolt.Task`): The owner task for which the resource is acquired.

        """

    def release(self, artifact, deps, tools, owner):
        """ Called to release the resource.

        An implementor overrides this method in a subclass.

        Args:
            artifact (:class:`~jolt.Artifact`): The artifact associated with the resource.
                It is not possible to publish files from a resource, but the implementor
                can still use the resource to pass information to consuming tasks.
            deps (:class:`~jolt.Context`): Task execution context used to access the
                artifacts of dependencies.
            tools (:class:`~jolt.Tools`): A task specific toolbox.
            owner (:class:`~jolt.Task`): The owner task for which the resource is released.
        """

    def run(self, env, tools):
        self._run_env = env


class WorkspaceResource(Resource):
    """
    A workspace resource task.

    A workspace resource is a similiar to a regular resource and may be used as such,
    but it can also be used from a workspace manifest to acquire project resources
    before any task recipes are parsed. A common use-case is to retrieve project
    sources from SCM. Workspace resources cannot have any dependencies.
    No artifact is produced.

    Implementors should override :func:`~acquire_ws` and :func:`~release_ws`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        raise_task_error_if(len(self.requires) > 0, self,
                            "Workspace resource is not allowed to have requirements")

    def acquire(self, **kwargs):
        return self.acquire_ws()

    def release(self, **kwargs):
        return self.release_ws()

    def prepare_ws_for(self, task):
        """ Called to prepare the workspace for a task.

        An implementor overrides this method in a subclass. The method
        is called before the task influence is calculated and the workspace
        resource is acquired.
        """

    def acquire_ws(self, force=False):
        """ Called to acquire the resource.

        An implementor overrides this method in a subclass. The acquired
        resource must be released manually if an exception occurs before the
        method has returned. """

    def release_ws(self):
        """ Called to release the resource.

        An implementor overrides this method in a subclass.

        """


@attributes.requires("_image")
class Chroot(Resource):
    """
    Resource to use task artifact or directory path as chroot in consumers.

    Example:

      .. code-block:: python

        from jolt import Chroot, Task
        from jolt.plugins.podman import ContainerImage

        class SdkImage(ContainerImage):
            dockerfile = \"\"\"
            FROM debian:sid-slim
            ARG DEBIAN_FRONTEND=noninteractive
            RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && apt-get clean
            \"\"\"
            output = "directory"

        class Sdk(Chroot):
            chroot = "sdkimage"

        class Compile(Task):
            requires = ["sdk"]

            def run(self, deps, tools):
                tools.run("gcc -v")

    """
    abstract = True

    chroot = None
    """ Task name or directory path to use as chroot """

    @property
    def _image(self):
        registry = TaskRegistry.get()
        if registry.get_task_class(self.expand(self.chroot)):
            return [self.chroot]
        return []

    def acquire(self, artifact, deps, tools, owner):
        try:
            rootfs = deps[self.chroot]
        except Exception:
            rootfs = tools.expand(self.image)
        self._context_stack = ExitStack()
        self._context_stack.enter_context(
            owner.tools.chroot(rootfs))

    def release(self, artifact, deps, tools, owner):
        self._context_stack.close()


class Alias(Task):
    """
    An alias task.

    Aliases are a special kind of task which can be used to introduce new
    names for other tasks or groups of tasks. They are useful as milestones
    when building continuous integration pipelines since they won't
    be executed, thus saving time compared to a regular task.
    """

    cacheable = False

    abstract = True
    """ An abstract alias class indended to be subclassed. """

    def __init__(self, *args, **kwargs):
        super(Alias, self).__init__(*args, **kwargs)
        raise_task_error_if(
            self.extends, self, "Aliases cannot be extensions")

    def is_runnable(self):
        return False

    def info(self, fmt, *args, **kwargs):
        pass


class Download(Task):
    """
    Downloads file(s) over HTTP(S).

    Once downloaded, archives are extracted and all of their files are published.
    If the file is not an archive it is published as is. Recognized archive extensions are:

        - .tar
        - .tar.bz2
        - .tar.gz
        - .tar.xz
        - .tgz
        - .zip

    Example:

      .. code-block:: python

        class NodeJS(Download):
            \"\"\" Downloads and publishes Node.js. Adds binaries to PATH. \"\"\"

            version = Parameter("14.16.1")
            url = "https://nodejs.org/dist/v{version}/node-v{version}-win-x64.zip"

            def publish(self, artifact, tools):
                super(publish).publish(artifact, tools)
                artifact.environ.PATH.append("node-v{version}-win-x64")
    """

    abstract = True

    collect = ["*"]
    """
    A list of file publication instructions.

    Items in the list are passed directly to :func:`Artifact.collect() <jolt.Artifact.collect>`
    and can be either strings, tuples or dictionaries.

    Example:

      .. code-block:: python

            collect = [
                "*",                           # Collect all files
                ("*", "src/"),                 # Collect all files into the artifact's src/ directory
                {"files": "*", cwd="subdir"},  # Collect all files from the archive's subdir/ directory
            ]

    """

    extract = True
    """ Automatically extract archives. """

    url = None
    """
    URL(s) of file(s) to download.

    A single URL string is accepted, as well as a list of URL strings.
    """

    symlinks = True
    """ Publish symlinks (True) """

    def _filename_from_url(self, tools, url):
        from urllib.parse import urlparse
        url = urlparse(tools.expand(url))
        return fs.posixpath.basename(url.path) or "file"

    def run(self, deps, tools):
        supported_formats = [".tar", ".tar.bz2", ".tar.gz", ".tar.xz", ".tgz", ".zip"]

        raise_task_error_if(not self.url, self, "No URL(s) specified")

        self._downloaddir = tools.builddir()
        self._extractdir = tools.builddir("extracted")
        for url in utils.as_list(self.url):
            filename = self._filename_from_url(tools, url)
            with tools.cwd(self._downloaddir):
                tools.download(url, filename)

            if self.extract and any(map(lambda n: filename.endswith(n), supported_formats)):
                with tools.cwd(self._extractdir):
                    self.info("Extracting {}", filename)
                    tools.extract(fs.path.join(self._downloaddir, filename), ".")
            else:
                with tools.cwd(self._downloaddir):
                    tools.copy(filename, self._extractdir)

    def publish(self, artifact, tools):
        with tools.cwd(self._extractdir):
            for files in self.collect:
                if type(files) is tuple:
                    artifact.collect(*files, symlinks=self.symlinks)
                elif type(files) is dict:
                    artifact.collect(**files, symlinks=self.symlinks)
                else:
                    artifact.collect(files, symlinks=self.symlinks)


class Script(Task):
    """
    A simple shell script task.

    The script source is extracted directly from the task class documentation.
    All text following a ``---`` separator will be executed.

    A temporary build directory is automatically created and can be accessed
    with ``{builddir}``. All other task attributes are also expanded as usual.
    Dependency artifacts are accessible through the ``deps`` dictionary.

      .. code-block:: python

        echo {deps[task].path}

    By default, all files in the build directory are published in the task artifact.
    The :attr:`collect` attribute can be used to customize file collection.
    Alternatively, the publish method may be overridden.

    Keep in mind that shell scripts are not necessarily portable between
    host operating systems. Implement your tasks in Python code if portability
    is a concern.

    Example:

      .. code-block:: python

        class Hello(Script):
            \"\"\"
            Classic Hello World!
            ---
            # Script source

            echo "Hello world!" > {builddir}/hello.txt
            \"\"\"
    """
    abstract = True

    collect = [{"files": "*", "cwd": "{builddir}"}]
    """
    A list of file publication instructions.

    Items in the list are passed directly to :func:`Artifact.collect() <jolt.Artifact.collect>`
    and can be either strings, tuples or dictionaries.

    By default, all files in the build directory are published.

    Example:

      .. code-block:: python

        collect = [
            "*",                              # Collect all files
            ("*", "src/"),                    # Collect all files into the artifact's src/ directory
            {"files": "*", "cwd": "subdir"},  # Collect all files from the archive's subdir/ directory
        ]

    """

    source = None

    def _source(self, tools):
        if self.source is not None:
            return self.source
        doc = self.__doc__.split("---", 1)
        script = doc[1] if len(doc) > 1 else doc[0]
        script = script.splitlines()
        script = [line[4:] for line in script]
        script = "\n".join(script)
        script = script.lstrip()
        if not script.startswith("#!"):
            script = "#!" + tools.getenv("SHELL", "/bin/sh") + "\n" + script
        return script

    def run(self, deps, tools):
        self.builddir = tools.builddir()
        self.deps = deps
        self._scriptdir = tools.builddir("script")

        tools.write_file("{_scriptdir}/script", self._source(tools))
        tools.chmod("{_scriptdir}/script", 0o555)
        tools.run("{_scriptdir}/script")

    def publish(self, artifact, tools):
        with tools.cwd(self.builddir):
            for files in self.collect:
                if type(files) is tuple:
                    artifact.collect(*files)
                elif type(files) is dict:
                    artifact.collect(**files)
                else:
                    artifact.collect(files)


__unittest = True


class _TestCase(ut.FunctionTestCase):
    def __init__(self, task, deps, tools, testfunc, *args, **kwargs):
        super().__init__(testfunc, *args, **kwargs)
        self.task = task
        self.deps = deps
        self.tools = tools
        self.testfunc = testfunc

    @property
    def name(self):
        return self.testfunc.__name__

    @property
    def fullname(self):
        return "{}.{}".format(self.task.__class__.__name__, self.name)

    def runTest(self):
        self.task._run(self)

    def __str__(self):
        return "{} ({})".format(self.task.__class__.__name__, self.testfunc.__name__)

    @property
    def __doc__(self):
        return self.testfunc.__doc__


class _TestResult(ut.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successes = []
        self.errors_exc = []

    def _begin(self):
        log.stdout(ut.TextTestResult.separator1)

    def _end(self):
        log.stdout(ut.TextTestResult.separator2)
        log.stdout("")

    def startTest(self, test):
        self._begin()
        super().startTest(test)
        log.stdout(ut.TextTestResult.separator2)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)
        self._end()

    def addError(self, test, err):
        _, exc, tb = err
        self.errors_exc.append((test, exc))
        super().addError(test, err)
        self._end()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._end()

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._end()


class Test(Task):
    """ A test task.

    The test task combines a regular Jolt task with a Python ``unittest.TestCase``.
    As such, a test task is a collection of similar test-cases where each test-case
    is implemented as an instancemethod named with a ``test_`` prefix. When executed,
    the task runs all test-case methods and summarizes the result.

    All regular ``unittest`` assertions and decorators can be used in the test methods.
    For details about inherited task attributes, see :class:`jolt.tasks.Task` and
    Python unittest.TestCase.

    Example:

    .. code-block:: python

      class OperatorTest(Test):

          def test_add(self):
              self.assertEqual(1+1, 2)

          def test_sub(self):
              self.assertEqual(2-1, 1)

    """

    abstract = True
    """ An abstract test class indended to be subclassed.

    Abstract test tasks can't be executed and won't be listed.
    """

    pattern = Parameter(required=False, help="Test-case filter wildcard.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def parameterized(args):
        """
        Parameterizes a test method.

        The test method is instantiated and called once with each argument tuple in the list.

        Example:

          .. code-block:: python

            class Example(Test):
               @Test.parameterized([
                   (1, 1, 1),  # 1*1 == 1
                   (1, 2, 2),  # 1*2 == 2
                   (2, 1, 2),  # 2*1 == 2
                   (2, 2, 4),  # 2*2 == 4
               ])
               def test_multiply(self, factor1, factor2, product):
                   self.assertEqual(factor1*factor2, product)

        """
        raise_error_if(type(args) is not list, "Test.parameterized() expects a list as argument")

        class partialmethod(functools.partialmethod):
            def __init__(self, index, func, *args):
                super().__init__(func, *args)
                self.__index = index

            def __get__(self, obj, cls=None):
                retval = super().__get__(obj, cls)
                retval.__name__ = f"{self.func.__name__}[{self.__index}]"
                retval.__doc__ = self.func.__doc__
                return retval

        def decorate(method):
            frame = sys._getframe().f_back.f_locals
            for index, arg in enumerate(args):
                testmethod = partialmethod(index, method, *utils.as_list(arg))
                name = f"{method.__name__}[{index}]"
                frame[name] = testmethod
            return None
        return decorate

    def setup(self, deps, tools):
        """ Implement this method to make preparations before a test """

    def cleanup(self):
        """ Implement this method to clean up after a test """

    def skip(self, reason=""):
        raise ut.SkipTest(self.tools.expand(reason))

    def _get_test_names(self):
        return [attrib for attrib in dir(self) if attrib.startswith("test_")]

    def _setup(self, test):
        self._curtest = test
        self._testMethodName = test.testfunc.__name__
        self._testMethodDoc = test.testfunc.__doc__
        self.setup(test.deps, test.tools)

    def _test(self, test):
        test.testfunc()

    def _cleanup(self, test):
        self.cleanup()

    def _run(self, test):
        try:
            self._setup(test)
            self._test(test)
        finally:
            self._cleanup(test)

    def assertTrue(self, *args, **kwargs):
        return self._curtest.assertTrue(*args, **kwargs)

    def assertFalse(self, *args, **kwargs):
        return self._curtest.assertFalse(*args, **kwargs)

    def assertIn(self, *args, **kwargs):
        return self._curtest.assertIn(*args, **kwargs)

    def assertNotIn(self, *args, **kwargs):
        return self._curtest.assertNotIn(*args, **kwargs)

    def assertIs(self, *args, **kwargs):
        return self._curtest.assertIs(*args, **kwargs)

    def assertIsNot(self, *args, **kwargs):
        return self._curtest.assertIsNot(*args, **kwargs)

    def assertIsInstance(self, *args, **kwargs):
        return self._curtest.assertIsInstance(*args, **kwargs)

    def assertIsNotInstance(self, *args, **kwargs):
        return self._curtest.assertIsNotInstance(*args, **kwargs)

    def assertIsNone(self, *args, **kwargs):
        return self._curtest.assertIsNone(*args, **kwargs)

    def assertIsNotNone(self, *args, **kwargs):
        return self._curtest.assertIsNotNone(*args, **kwargs)

    def assertEqual(self, *args, **kwargs):
        return self._curtest.assertEqual(*args, **kwargs)

    def assertNotEqual(self, *args, **kwargs):
        return self._curtest.assertNotEqual(*args, **kwargs)

    def assertAlmostEqual(self, *args, **kwargs):
        return self._curtest.assertAlmostEqual(*args, **kwargs)

    def assertAlmostNotEqual(self, *args, **kwargs):
        return self._curtest.assertAlmostNotEqual(*args, **kwargs)

    def assertGreater(self, *args, **kwargs):
        return self._curtest.assertGreater(*args, **kwargs)

    def assertGreaterEqual(self, *args, **kwargs):
        return self._curtest.assertGreaterEqual(*args, **kwargs)

    def assertLess(self, *args, **kwargs):
        return self._curtest.assertLess(*args, **kwargs)

    def assertLessEqual(self, *args, **kwargs):
        return self._curtest.assertLessEqual(*args, **kwargs)

    def assertRaises(self, *args, **kwargs):
        return self._curtest.assertRaises(*args, **kwargs)

    def assertRaisesRegex(self, *args, **kwargs):
        return self._curtest.assertRaisesRegex(*args, **kwargs)

    def assertRegex(self, *args, **kwargs):
        return self._curtest.assertRegex(*args, **kwargs)

    def assertCountEqual(self, *args, **kwargs):
        return self._curtest.assertCountEqual(*args, **kwargs)

    def skipTest(self, *args, **kwargs):
        return self._curtest.skipTest(*args, **kwargs)

    def subTest(self, *args, **kwargs):
        return self._curtest.subTest(*args, **kwargs)

    def run(self, deps, tools):
        testsuite = ut.TestSuite()
        for test in self._get_test_names():
            if self.pattern.is_unset() or fnmatch.fnmatch(test, str(self.pattern)):
                testfunc = getattr(self, test)
                if not testfunc:
                    continue
                testsuite.addTest(
                    _TestCase(self, deps, tools, testfunc))
        with log.stream() as logstream:
            self.testresult = ut.TextTestRunner(resultclass=_TestResult, stream=logstream, verbosity=2).run(testsuite)
        with self.report() as report:
            for tc, exc in self.testresult.errors_exc:
                report.add_exception(exc, "Test Error", tc.name)
            for tc, tb in self.testresult.failures:
                report.add_error("Test Failed", tc.name, tb.splitlines()[-1], tb)
        raise_unreported_task_error_if(
            not self.testresult.wasSuccessful(), self,
            "{} tests out of {} were successful".format(
                len(self.testresult.successes),
                self.testresult.testsRun))


@ArtifactAttributeSetProvider.Register
class ResourceAttributeSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        pass

    def parse(self, artifact, content):
        pass

    def format(self, artifact, content):
        pass

    def apply(self, task, artifact):
        resource = artifact.task
        if isinstance(resource, Resource):
            if not hasattr(resource, "_run_env"):
                raise_error("Internal scheduling error, resource has not been prepared: {}", task.short_qualified_name)

            deps = resource._run_env
            deps.__enter__()

            try:
                if not isinstance(resource, WorkspaceResource):
                    ts = utils.duration()
                    log.info(colors.blue("Resource acquisition started ({})"),
                             resource.short_qualified_name)
                resource.acquire(artifact=artifact, deps=deps, tools=resource.tools, owner=task)
                if not isinstance(resource, WorkspaceResource):
                    log.info(colors.green("Resource acquisition finished after {} ({})"),
                             ts, resource.short_qualified_name)
            except (KeyboardInterrupt, Exception) as e:
                if not isinstance(resource, WorkspaceResource):
                    log.error("Resource acquisition failed after {} ({})",
                              ts, resource.short_qualified_name)
                    if resource.release_on_error:
                        with utils.ignore_exception():
                            self.unapply(task, artifact)
                raise e

    def unapply(self, task, artifact):
        resource = artifact.task
        if isinstance(resource, Resource):
            deps = resource._run_env
            try:
                if not isinstance(resource, WorkspaceResource):
                    ts = utils.duration()
                    log.info(colors.blue("Resource release started ({})"),
                             resource.short_qualified_name)
                resource.release(artifact=artifact, deps=deps, tools=resource.tools, owner=task)
                if not isinstance(resource, WorkspaceResource):
                    log.info(colors.green("Resource release finished after {} ({})"),
                             ts, resource.short_qualified_name)
            except Exception as e:
                if not isinstance(resource, WorkspaceResource):
                    log.error("Resource release failed after {} ({})",
                              ts, resource.short_qualified_name)
                raise e
            deps.__exit__(None, None, None)
