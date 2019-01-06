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
