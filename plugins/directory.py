from influence import *
import tools
import utils
from copy import copy


class DirectoryInfluenceProvider(HashInfluenceProvider):
    name = "Directory"
    path = "."
    pattern = "*"

    def __init__(self, path=None, pattern=None):
        self.path = path or self.__class__.path
        self.pattern = pattern or self.__class__.pattern

    def get_influence(self, task):
        try:
            path = task._get_expansion(self.path)
            with tools.cwd(path):
                return tools.run("find -type f -name '{}' | xargs md5sum".format(self.pattern))
        except KeyError as e:
            pass
        assert False, "failed to change directory to {}".format(self.path)


def global_influence(path, pattern=None, cls=DirectoryInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path, pattern))


def influence(path, pattern=None, cls=DirectoryInfluenceProvider):
    def _decorate(taskcls):
        if "influence" not in taskcls.__dict__:
            taskcls.influence = copy(taskcls.influence)
        provider = cls(path, pattern)
        taskcls.influence.append(provider)
        return taskcls
    return _decorate
