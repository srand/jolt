from copy import copy

from jolt.influence import *
from jolt.tools import Tools
from jolt import utils


class DirectoryInfluenceProvider(HashInfluenceProvider):
    name = "Directory"
    path = "."
    pattern = "*"

    def __init__(self, path=None, pattern=None):
        self.path = path or self.__class__.path
        self.pattern = pattern or self.__class__.pattern

    def get_influence(self, task):
        try:
            with Tools(task, task.joltdir) as tools:
                path = task._get_expansion(self.path)
                with tools.cwd(path):
                    return tools.run("find -type f -name '{0}' | LC_ALL=C sort | xargs -n1 md5sum"
                                     .format(self.pattern),
                                     output=False, output_on_error=True)
        except KeyError as e:
            pass
        assert False, "failed to change directory to {0}".format(self.path)


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
