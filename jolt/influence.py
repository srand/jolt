import datetime
import os

from jolt import utils
from jolt import log


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
            content.append("Influence-{0}: {1}".format(provider.name, provider.get_influence(task)))
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
monthly = _date_influence("%Y-%m")
daily = _date_influence("%Y-%m-%d")
hourly = _date_influence("%Y-%m-%d %H")



class TaskEnvironmentInfluence(HashInfluenceProvider):
    name = "Environment"

    def __init__(self, variable):
        self.variable = variable

    def get_influence(self, task):
        return self.variable + "=" + os.environ.get(self.variable, "<unset>")


def environ(variable):
    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            self.influence.append(TaskEnvironmentInfluence(variable))
        cls.__init__ = _init
        return cls

    return _decorate



# class FileInfluence(HashInfluenceProvider):
#     name = "File"
#     path = "."
#     pattern = "*"
#
#     def __init__(self, path=None, pattern=None):
#         self.path = path or self.__class__.path
#         self.pattern = pattern or self.__class__.pattern
#
#     def get_influence(self, task):
#         try:
#             with Tools(task, task.joltdir) as tools:
#                 path = task._get_expansion(self.path)
#                 with tools.cwd(path):
#                     return tools.run("find -type f -name '{0}' | LC_ALL=C sort | xargs -n1 sha1sum"
#                                      .format(self.pattern),
#                                      output=False, output_on_error=True)
#         except KeyError as e:
#             pass
#         assert False, "failed to change directory to {0}".format(self.path)
#
#
# def file(path, pattern=None):
#     def _decorate(taskcls):
#         if "influence" not in taskcls.__dict__:
#             taskcls.influence = copy(taskcls.influence)
#         provider = FileInfluence(path, pattern)
#         taskcls.influence.append(provider)
#         return taskcls
#     return _decorate
#
