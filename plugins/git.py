from tasks import *
from influence import *
from tools import *
from scheduler import *
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
                return tools.run("git rev-parse HEAD: && git diff HEAD",
                                 output_on_error=True)
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


class Git(Resource):
    """ Clones a Git repo.

    Also influences the hash of consuming tasks, causing tasks to
    be re-executed if the cloned repo is modified.

    """

    name = "git"
    url = Parameter(help="URL to the git repo to clone. Required.")
    sha = Parameter(help="Specific commit sha to be checked out. Optional.")

    def __init__(self):
        super(Git, self).__init__()
        class GitInfluence(HashInfluenceProvider):
            name = "Tree"

            def influence(self, task):
                if not task._is_cloned():
                    assert not fs.path.exists(task._get_name()), \
                        "destination folder '{}' already exists but is not a git repo"\
                        .format(task._get_name())
                    run("git clone --depth 1 {}", task.url, output_on_error=True)
                    assert fs.path.exists(task._get_git_folder()),\
                        "failed to clone git repo '{}'".format(self._get_name())
                if not task.sha.is_unset():
                    return task._get_tree_hash(task.sha.get_value())
                return task._get_tree_hash() + task._get_diff()
        self.influence.append(GitInfluence())

    def _get_name(self):
        repo = fs.path.basename(self.url.get_value())
        name, _ = fs.path.splitext(repo)
        return name

    def _get_git_folder(self):
        return fs.path.join(self._get_name(), ".git")

    @utils.cached.instance
    def _get_tree_hash(self, sha="HEAD"):
        with cwd(self._get_name()):
            return run("git rev-parse {}:".format(sha), output_on_error=True)
        return ""

    @utils.cached.instance
    def _get_diff(self):
        with cwd(self._get_name()):
            return run("git diff HEAD", output_on_error=True)
        return ""

    @utils.cached.instance
    def _is_synced(self):
        with cwd(self._get_name()):
            return True if run("git branch -r --contains HEAD", output_on_error=True) else False
        return True

    @utils.cached.instance
    def _is_cloned(self):
        return fs.path.exists(self._get_git_folder())

    def acquire(self, artifact, env, tools):
        if not self.sha.is_unset():
            assert self._is_synced(),\
                "explicit sha requested but git repo '{}' has local commits"\
                .format(self._get_name())
            assert not self._get_diff(), \
                "explicit sha requested but git repo '{}' has local changes"\
                .format(self._get_name())
            # Should be safe to do this now
            with cwd(self._get_name()):
                run("git checkout {}", self.sha, output_on_error=True)

TaskRegistry.get().add_task_class(Git)


class GitNetworkExecutorExtension(NetworkExecutorExtension):
    """ Sanity check that a local git repo can be built remotely """

    def get_parameters(self, task):
        for child in task.children:
            if isinstance(child.task, Git):
                task = child.task
                if task._is_cloned() and task.sha.is_unset():
                    assert task._is_synced(),\
                        "local commit found in git repo '{}'; "\
                        "push before building remotely"\
                        .format(task._get_name())
                    assert not task._get_diff(),\
                        "local changes found in git repo '{}'; "\
                        "commit and push before building remotely"\
                        .format(task._get_name())
        return {}


@NetworkExecutorExtensionFactory.Register
class GitNetworkExecutorExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return GitNetworkExecutorExtension()
