from influence import *
import tools
import utils
from copy import copy


class GitInfluenceProvider(HashInfluenceProvider):
    name = "Git"
    path = "."

    def __init__(self, path=None):
        self.path = path or self.__class__.path

    def influence(self, task):
        try:
            with tools.cwd(task._get_expansion(self.path)):
                return tools.run("git rev-parse HEAD && git diff")
        except KeyError as e:
            pass
        assert False, "failed to change directory to {}".format(self.path)


def global_influence(path, cls=GitInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path))


def influence(path, cls=GitInfluenceProvider):
    def _decorate(taskcls):
        if "influence" not in taskcls.__dict__:
            taskcls.influence = copy(taskcls.influence)
        provider = cls(path)
        taskcls.influence.append(provider)
        return taskcls
    return _decorate
