import utils
import log


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
        for provider in self._providers + task.influence:
            content = "Influence-{}: {}".format(provider.name, provider.influence(task))
            sha.update(content)
            log.hysterical("{}: {}", task.name, content)


class HashInfluenceProvider(object):
    name = "X"
    def influence(self, task):
        raise NotImplemented()


@HashInfluenceRegistry.Register
class TaskNameInfluence(HashInfluenceProvider):
    name = "Name"
    def influence(self, task):
        return task.name


@HashInfluenceRegistry.Register
class TaskParameterInfluence(HashInfluenceProvider):
    name = "Parameters"
    def influence(self, task):
        return ",".join(["{}={}".format(key, value)
                         for key, value in task._get_parameters().iteritems()])

    
@HashInfluenceRegistry.Register
class TaskSourceInfluence(HashInfluenceProvider):
    name = "Source"
    def influence(self, task):
        return task._get_source_hash()

