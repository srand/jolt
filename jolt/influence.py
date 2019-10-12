import datetime
import hashlib
import os
import uuid


from jolt import utils
from jolt import log
from jolt import filesystem as fs
from jolt import tools


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
            log.debug("{0}: {1}", task.name, influence)

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


class TaintInfluenceProvider(object):
    name = "Taint"

    def get_influence(self, task):
        return str(task.taint)


class TaskAttributeInfluence(HashInfluenceProvider):
    def __init__(self, attrib, sort=False):
        self._attrib = attrib
        self._sort = sort
        self.name = attrib.title()

    def get_influence(self, task):
        value = utils.getattr_safe(task, tools.Tools(task).expand(self._attrib), "N/A")
        try:
            value = value.__get__(task)
            if type(value) == list and self._sort:
                value.sort()
        except AttributeError:
            pass
        return value


def attribute(name, sort=False):
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
        _old_influence = cls._influence
        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(TaskAttributeInfluence(name, sort))
            return influence
        cls._influence = _influence
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


def source(name, obj=None):
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
        _old_influence = cls._influence
        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(TaskSourceInfluence(name, obj))
            return influence
        cls._influence = _influence
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
                    for key, value in task._get_parameter_objects().items()
                    if value.is_influencer()]))



class TaskDateInfluence(HashInfluenceProvider):
    name = "Date"

    def __init__(self, fmt):
        self.fmt = fmt

    def get_influence(self, task):
        now = datetime.datetime.now()
        return now.strftime(self.fmt)


def _date_influence(fmt):
    def _decorate(cls):
        _old_influence = cls._influence
        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(TaskDateInfluence(fmt))
            return influence
        cls._influence = _influence
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
        _old_influence = cls._influence
        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(TaskEnvironmentInfluence(variable))
            return influence
        cls._influence = _influence
        return cls

    return _decorate


_fi_files = {}


class FileInfluence(HashInfluenceProvider):
    def __init__(self, path):
        self.path = path
        self.name = "File"

    def get_file_influence(self, path):
        sha = hashlib.sha1()
        with open(path, "rb") as f:
            for data in iter(lambda: f.read(0x10000), b''):
                sha.update(data)
        return sha.hexdigest()

    def get_influence(self, task):
        result = []
        files = task.tools.glob(self.path)
        files.sort()
        for f in files:
            f = task.tools.expand_path(f)
            if fs.path.isdir(f):
                continue
            value = _fi_files.get(f)
            if value:
                result.append(value)
            elif fs.path.exists(f):
                _fi_files[f] = value = fs.path.basename(f) + ":" + self.get_file_influence(f)
                result.append(value)
            elif fs.path.lexists(f):
                _fi_files[f] = value = fs.path.basename(f) + ": Symlink (broken)"
                result.append(value)

        return "\n".join(result)


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
        _old_influence = cls._influence
        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(FileInfluence(pathname))
            return influence
        cls._influence = _influence
        return cls

    return _decorate


def global_files(pathname, cls=FileInfluence):
    HashInfluenceRegistry.get().register(cls(pathname))



class StringInfluence(HashInfluenceProvider):
    name = "String"

    def __init__(self, value):
        self.value = value

    def get_influence(self, task):
        return self.value


def global_string(string):
    HashInfluenceRegistry.get().register(StringInfluence(string))
