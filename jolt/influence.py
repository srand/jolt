import datetime
import hashlib
import os

from jolt import utils
from jolt import log
from jolt import filesystem as fs
from jolt.tools import Tools

_providers = []

@utils.Singleton
class HashInfluenceRegistry(object):
    @staticmethod
    def Register(cls):
        _providers.append(cls)

    def __init__(self):
        self._providers = [provider() for provider in _providers]

    def register(self, provider):
        self._providers.append(provider)

    def apply_all(self, task, sha):
        for influence in self.get_strings(task):
            sha.update(influence.encode())
            log.hysterical("{0}: {1}", task.name, influence)

    def get_strings(self, task):
        content = []
        for provider in self._providers + task.influence:
            for line in str(provider.get_influence(task)).splitlines():
                content.append("Influence-{0}: {1}".format(provider.name, line))
        return content


class HashInfluenceProvider(object):
    name = "X"
    def get_influence(self, task):
        raise NotImplemented()


class TaskAttributeInfluence(HashInfluenceProvider):
    def __init__(self, attrib):
        self._attrib = attrib
        self.name = attrib.title()

    def get_influence(self, task):
        return getattr(task, self._attrib)


def attribute(name):
    """ Add task attribute value as hash influence.

    Args:
        name (str): Name of task class attribute/property.

    Example:

    .. code-block:: python

        from jolt import influence

        @influence.source("attribute")
        class Example(Task):
            attribute = False
    """

    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            self.influence.append(TaskAttributeInfluence(name))
        cls.__init__ = _init
        return cls
    return _decorate


class TaskSourceInfluence(HashInfluenceProvider):
    def __init__(self, funcname, obj=None):
        self.name = "Source:" + funcname
        self.funcname = funcname
        self.obj = obj

    def get_influence(self, task):
        obj = self.obj or task
        return utils.sha1(task._get_source(getattr(obj, self.funcname)))


def source(name):
    """ Add function source code as hash influence.

    Args:
        name (str): Name of function in task class.

    Example:

    .. code-block:: python

        from jolt import influence

        @influence.source("method")
        class Example(Task):
            def method(self):
                return False

    """
    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            self.influence.append(TaskSourceInfluence(name))
        cls.__init__ = _init
        return cls
    return _decorate


@HashInfluenceRegistry.Register
class TaskNameInfluence(HashInfluenceProvider):
    name = "Name"
    def get_influence(self, task):
        return task.name


@HashInfluenceRegistry.Register
class TaskParameterInfluence(HashInfluenceProvider):
    name = "Parameters"
    def get_influence(self, task):
        return ",".join(
            sorted(["{0}={1}".format(key, value)
                    for key, value in task._get_parameters().items()]))



class TaskDateInfluence(HashInfluenceProvider):
    name = "Date"

    def __init__(self, fmt):
        self.fmt = fmt

    def get_influence(self, task):
        now = datetime.datetime.now()
        return now.strftime(self.fmt)


def _date_influence(fmt):
    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            self.influence.append(TaskDateInfluence(fmt))
        cls.__init__ = _init
        return cls
    return _decorate


yearly = _date_influence("%Y")
""" Add yearly hash influence.

If nothing else changes, the task is re-executed once every year.

Example:

    .. code-block:: python

        from jolt import influence

        @influence.yearly
        class Example(Task):

"""

weekly = _date_influence("%Y-%w")
""" Add weekly hash influence.

If nothing else changes, the task is re-executed once every week.

Example:

    .. code-block:: python

        from jolt import influence

        @influence.weekly
        class Example(Task):

"""

monthly = _date_influence("%Y-%m")
""" Add monthly hash influence.

If nothing else changes, the task is re-executed once every month.

Example:

    .. code-block:: python

        from jolt import influence

        @influence.monthly
        class Example(Task):

"""

daily = _date_influence("%Y-%m-%d")
""" Add daily hash influence.

If nothing else changes, the task is re-executed once every day.

Example:

    .. code-block:: python

        from jolt import influence

        @influence.daily
        class Example(Task):

"""

hourly = _date_influence("%Y-%m-%d %H")
""" Add hourly hash influence.

If nothing else changes, the task is re-executed once every hour.

Example:

    .. code-block:: python

        from jolt import influence

        @influence.hourly
        class Example(Task):

"""



class TaskEnvironmentInfluence(HashInfluenceProvider):
    name = "Environment"

    def __init__(self, variable):
        self.variable = variable

    def get_influence(self, task):
        return self.variable + "=" + os.environ.get(self.variable, "<unset>")


def environ(variable):
    """ Add environment variable hash influence.

    Args:
        variable (str): Name of an environment variable that will
            influence the hash of the task.

    Example:

    .. code-block:: python

        from jolt import influence

        @influence.environ("CFLAGS")
        class Example(Task):

    """
    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            self.influence.append(TaskEnvironmentInfluence(variable))
        cls.__init__ = _init
        return cls

    return _decorate



class FileInfluence(HashInfluenceProvider):
    def __init__(self, path):
        self.path = path
        self.name = "File:" + fs.path.basename(path)

    def get_influence(self, task):
        sha = hashlib.sha1()
        with open(self.path, "rb") as f:
            for data in iter(lambda: f.read(4096), ''):
                sha.update(data)
        return sha.hexdigest()


def files(pathname):
    """ Add file content hash influence.

    Args:
        pathname (str): A pathname pattern used to find files that will
                influence the hash of the task
                The pattern may contain simple shell-style
                wildcards such as '*' and '?'. Note: files starting with a
                dot are not matched by these wildcards.

    Example:

    .. code-block:: python

        from jolt import influence

        @influence.files("*.cpp")
        class Example(Task):

    """
    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            f = []
            with Tools(self, self.joltdir) as tools:
                f = tools.glob(pathname)
            f.sort()
            for i in f:
                self.influence.append(FileInfluence(i))
        cls.__init__ = _init
        return cls

    return _decorate
