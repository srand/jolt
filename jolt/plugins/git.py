from jolt.tasks import *
from jolt.influence import *
from jolt.tools import *
from jolt.scheduler import *
from jolt import utils
from jolt import filesystem as fs

try:
    import pygit2
    has_pygit = True
except:
    has_pygit = False


class GitInfluenceProvider(HashInfluenceProvider):
    name = "Tree"
    path = "."

    def __init__(self, path=None):
        super(GitInfluenceProvider, self).__init__()
        self.path = path or self.__class__.path

    def _get_path(self, task):
        p = task.tools.expand_path(self.path)
        return p

    def _get_relative_path(self, task):
        p = self._get_path(task)
        if p.startswith(task.joltdir):
            p = p[len(task.joltdir):]
            p = p[1:] if p[0] == fs.sep else p
        return p

    @utils.cached.instance
    def _get_tree_hash(self, task, sha="HEAD"):
        if has_pygit:
            return pygit2.Repository(self._get_path(task)).revparse_single(sha + ":").id
        else:
            with task.tools.cwd(self._get_path(task)):
                return task.tools.run("git rev-parse {0}:".format(sha), output_on_error=True)
        return ""

    @utils.cached.instance
    def _get_diff(self, task):
        with task.tools.cwd(self._get_path(task)):
            return task.tools.run("git diff HEAD", output_on_error=True)
        return ""

    @utils.cached.instance
    def _get_diff_hash(self, task):
        return utils.sha1(self._get_diff(task))

    def get_influence(self, task):
        return "{0}:{1}:{2}".format(
            self._get_relative_path(task),
            self._get_tree_hash(task),
            self._get_diff_hash(task)[:8])


def global_influence(path, cls=GitInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path))


def influence(path, cls=GitInfluenceProvider):
    def _decorate(taskcls):
        if "influence" not in taskcls.__dict__:
            taskcls.influence = copy.copy(taskcls.influence)
        provider = cls(path=path)
        taskcls.influence.append(provider)
        return taskcls
    return _decorate


class Git(Resource, GitInfluenceProvider):
    """ Clones a Git repo.

    Also influences the hash of consuming tasks, causing tasks to
    be re-executed if the cloned repo is modified.

    """

    name = "git"
    url = Parameter(help="URL to the git repo to clone. Required.")
    sha = Parameter(help="Specific commit sha to be checked out. Optional.")
    path = Parameter(help="Local path where repo should be cloned.")

    def __init__(self, *args, **kwargs):
        super(Git, self).__init__(*args, **kwargs)
        self.path = str(self.path) or self._get_name()
        self.influence.append(self)

    @utils.cached.instance
    def _get_name(self):
        repo = fs.path.basename(self.url.get_value())
        name, _ = fs.path.splitext(repo)
        return name

    @utils.cached.instance
    def _get_git_folder(self):
        return fs.path.join(self.path, ".git")

    def _clone(self):
        assert not fs.path.exists(self.path), \
            "destination folder '{0}' already exists but is not a git repo"\
            .format(self.path)
        depth = "--depth 1" if self.sha.is_unset() else ""
        log.info("Cloning into {0}", self.path)
        self.tools.run("git clone {0} {1} {2}", depth, self.url, self.path, output_on_error=True)
        assert fs.path.exists(self._get_git_folder()),\
            "failed to clone git repo '{0}'".format(self._get_name())

    @utils.cached.instance
    def _is_synced(self):
        with self.tools.cwd(self.path):
            return True if self.tools.run("git branch -r --contains HEAD", output_on_error=True) else False
        return True

    @utils.cached.instance
    def _is_cloned(self):
        return fs.path.exists(self._get_git_folder())

    def acquire(self, artifact, env, tools):
        if not self.sha.is_unset():
            assert self._is_synced(),\
                "explicit sha requested but git repo '{0}' has local commits"\
                .format(self._get_name())
            assert not self._get_diff(self), \
                "explicit sha requested but git repo '{0}' has local changes"\
                .format(self._get_name())
            # Should be safe to do this now
            with self.tools.cwd(self.path):
                self.tools.run("git checkout {0}", self.sha, output_on_error=True)

    def get_influence(self, task):
        if isinstance(task, Git):
            if not self._is_cloned():
                self._clone()
            if not self.sha.is_unset():
                return self._get_tree_hash(self, self.sha.get_value())
        return super(Git, self).get_influence(task)

TaskRegistry.get().add_task_class(Git)


class GitNetworkExecutorExtension(NetworkExecutorExtension):
    """ Sanity check that a local git repo can be built remotely """

    def get_parameters(self, task):
        for child in task.children:
            if isinstance(child.task, Git):
                task = child.task
                if task._is_cloned() and task.sha.is_unset():
                    assert task._is_synced(),\
                        "local commit found in git repo '{0}'; "\
                        "push before building remotely"\
                        .format(task._get_name())
                    assert not task._get_diff(task),\
                        "local changes found in git repo '{0}'; "\
                        "commit and push before building remotely"\
                        .format(task._get_name())
        return {}


@NetworkExecutorExtensionFactory.Register
class GitNetworkExecutorExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return GitNetworkExecutorExtension()
