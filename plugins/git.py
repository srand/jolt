from tasks import *
from influence import *
from tools import *
import utils
from copy import copy
import filesystem as fs

class GitInfluenceProvider(HashInfluenceProvider):
    name = "Git"
    path = "."

    def __init__(self, path=None):
        self.path = path or self.__class__.path

    def influence(self, task):
        try:
            with cwd(task._get_expansion(self.path)):
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


class Git(Task):
    name = "git"
    url = Parameter()
    rev = Parameter()

    def __init__(self):
        super(Git, self).__init__()
        class GitInfluence(HashInfluenceProvider):
            def influence(self, task):
                if not fs.path.exists(task._get_name()):
                    run("git clone --depth 1 {}", task.url)
                with cwd(task._get_name()):
                    if not task.rev.is_unset():
                        run("git reset --hard {}", task.rev)
                    return run("git rev-parse HEAD && git diff")
                return ""
        self.influence.append(GitInfluence())
        
    def _get_name(self):
        repo = fs.path.basename(self.url.get_value())
        name, _ = fs.path.splitext(repo)
        return name

    def _get_rev(self):
        return "{}\n".format(self.rev)
        
    def run(self, env, tools):
        if not self.rev.is_unset():
            assert tools.run("git rev-parse") == self._get_rev(), \
                "wrong revision checked out in git repo"
            assert tools.run("git diff") == "\n", \
                "modifications found in git repo"

TaskRegistry.get().add_task_class(Git)
