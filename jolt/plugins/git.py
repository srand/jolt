import copy

from jolt.tasks import Resource, Parameter, Export, TaskRegistry
from jolt.influence import HashInfluenceProvider, HashInfluenceRegistry
from jolt.tools import Tools
from jolt.loader import JoltLoader
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.error import JoltCommandError
from jolt.error import raise_error
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if



_tree = {}
_tree_hash_cache = {}



class GitRepository(object):
    def __init__(self, url, path, relpath, refspecs=None):
        self.path = path
        self.relpath = relpath
        self.tools = Tools()
        self.url = url
        self.refspecs = utils.as_list(refspecs or [])

    @utils.cached.instance
    def _get_git_folder(self):
        return fs.path.join(self.path, ".git")

    def is_cloned(self):
        return fs.path.exists(self._get_git_folder())

    def _is_synced(self):
        with self.tools.cwd(self.path):
            return True if self.tools.run("git branch -r --contains HEAD", output_on_error=True) else False
        return True

    def clone(self):
        raise_error_if(
            fs.path.exists(self.path),
            "git: destination folder '{0}' already exists and is not a git repository",
            self.path)
        log.info("Cloning into {0}", self.path)
        self.tools.run("git clone {0} {1}", self.url, self.path, output_on_error=True)
        raise_error_if(
            not fs.path.exists(self._get_git_folder()),
            "git: failed to clone repository '{0}'", self.relpath)

    @utils.cached.instance
    def _diff(self, path="/"):
        with self.tools.cwd(self.path):
            return self.tools.run("git diff --no-ext-diff HEAD .{0}".format(path),
                                  output_on_error=True,
                                  output_rstrip=False)

    def diff(self, path="/"):
        return self._diff(path) if self.is_cloned() else ""

    def patch(self, patch):
        if not patch:
            return
        with self.tools.cwd(self.path), self.tools.tmpdir("git") as t:
            patchfile = fs.path.join(t.path, "jolt.diff")
            with open(patchfile, "wb") as f:
                f.write(patch.encode())
            log.info("Applying patch to {0}", self.path)
            self.tools.run("git apply --whitespace=nowarn {patchfile}", patchfile=patchfile)

    @utils.cached.instance
    def _head(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git rev-parse HEAD", output_on_error=True)

    def head(self):
        return self._head() if self.is_cloned() else ""

    def write_tree(self):
        tools = Tools()
        index = fs.path.join(self.path, ".git", "jolt-index")
        gitpath = fs.path.dirname(index)

        tree = _tree.get(gitpath)
        if tree is not None:
            return tree

        with tools.environ(GIT_INDEX_FILE=index):
            with tools.cwd(gitpath):
                tools.copy("index", "jolt-index")
            with tools.cwd(fs.path.dirname(gitpath)):
                _tree[gitpath] = tree = tools.run("git add -u && git write-tree", output_on_error=True)

        return tree

    def tree_hash(self, sha="HEAD", path="/"):
        full_path = fs.path.join(self.path, path)
        value = _tree_hash_cache.get((full_path, sha))
        if value is None:
            if sha == "HEAD":
                tree = self.write_tree()
            else:
                try:
                    tree = self.tools.run("git rev-parse {0}^{tree}".format(sha), output=False)
                except:
                    self.fetch()
                    tree = self.tools.run("git rev-parse {0}^{tree}".format(sha), output_on_error=True)
            if path == "/":
                return tree
            with self.tools.cwd(self.path):
                _tree_hash_cache[(full_path, sha)] = value = self.tools.run(
                    "git rev-parse {0}:{1}".format(tree, path), output=False)
        return value

    def clean(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git clean -fd", output_on_error=True)

    def reset(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git reset --hard", output_on_error=True)

    def fetch(self):
        refspecs = self.refspecs or []
        for refspec in [''] + refspecs:
            self.tools.run("git fetch {url} {refspec}",
                           url=self.url,
                           refspec=refspec or '')

    def checkout(self, rev):
        log.info("Checking out {0} in {1}", rev, self.path)
        with self.tools.cwd(self.path):
            try:
                return self.tools.run("git checkout -f {rev}", rev=rev, output=False)
            except:
                self.fetch()
                return self.tools.run("git checkout -f {rev}", rev=rev, output_on_error=True)


class LocalGitRepository(GitRepository):
    def fetch(self):
        pass

    def clone(self):
        raise_error("attempt to clone local git repository at '{}'", self.relpath)


class GitInfluenceProvider(HashInfluenceProvider):
    name = "Git"

    def __init__(self, path):
        super(GitInfluenceProvider, self).__init__()
        self.path = fs.path.join(self.joltdir, path)

    @property
    def joltdir(self):
        return JoltLoader.get().joltdir

    def _find_dotgit(self, path):
        while path != self.joltdir:
            if fs.path.isdir(fs.path.join(path, ".git")):
                return path
            path = fs.path.dirname(path)
        raise_error("no git repository found at '{}'", self.path)

    @utils.cached.instance
    def get_influence(self, task):
        tools = Tools(task)

        path = tools.expand_path(self.path)
        git_abs = self._find_dotgit(path)
        git_rel = git_abs[len(self.joltdir)+1:]
        relpath = path[len(git_abs)+1:]

        if not fs.path.exists(path):
            return "{0}/{1}: N/A".format(git_rel, relpath)
        try:
            git = LocalGitRepository(None, git_abs, git_rel)

            return "{0}/{1}: {2}".format(git_rel, relpath, git.tree_hash(path=relpath or "/"))
        except JoltCommandError as e:
            stderr = "\n".join(e.stderr)
            if "exists on disk, but not in" in stderr:
                return "{0}/{1}: N/A".format(git_rel, relpath)
            for line in e.stderr:
                log.stderr(line)
            raise e

def global_influence(path, cls=GitInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path))


def influence(path, git_cls=GitInfluenceProvider):
    def _decorate(cls):
        _old_init = cls.__init__
        def _init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            self.influence.append(git_cls(path=path))
        cls.__init__ = _init
        return cls
    return _decorate


class GitSrc(Resource):
    """ Clones a Git repo.
    """

    name = "git-src"
    url = Parameter(help="URL to the git repo to be cloned. Required.")
    sha = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    _revision = Export(value=lambda self: self._get_revision() or self.git.head())
    _diff = Export(value=lambda self: self.git.diff(), encoded=True)

    def __init__(self, *args, **kwargs):
        super(GitSrc, self).__init__(*args, **kwargs)
        self.joltdir = JoltLoader.get().joltdir
        self.relpath = str(self.path) or self._get_name()
        self.abspath = fs.path.join(self.joltdir, self.relpath)
        self.refspecs = kwargs.get("refspecs", [])
        self.git = GitRepository(self.url, self.abspath, self.relpath, self.refspecs)

    @utils.cached.instance
    def _get_name(self):
        repo = fs.path.basename(self.url.get_value())
        name, _ = fs.path.splitext(repo)
        return name

    def _get_revision(self):
        if self._revision.value is not None:
            return self._revision.value
        if not self.sha.is_unset():
            return self.sha.get_value()
        return None

    def _get_diff(self):
        return self._diff.value

    def acquire(self, artifact, env, tools):
        if not self.git.is_cloned():
            self.git.clone()
        rev = self._get_revision()
        if rev is not None:
            raise_task_error_if(
                not self.sha.is_unset() and self.git.diff(), self,
                "explicit sha requested but git repo '{0}' has local changes", self.git.relpath)
            # Should be safe to do this now
            self.git.checkout(rev)
            self.git.clean()
            self.git.patch(self._get_diff())


TaskRegistry.get().add_task_class(GitSrc)


class Git(GitSrc, HashInfluenceProvider):
    """ Clones a Git repo.

    Also influences the hash of consuming tasks, causing tasks to
    be re-executed if the cloned repo is modified.

    """
    name = "git"
    url = Parameter(help="URL to the git repo to be cloned. Required.")
    sha = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    _revision = Export(value=lambda self: self._get_revision())
    _diff = Export(value=lambda self: self.git.diff(), encoded=True)

    def __init__(self, *args, **kwargs):
        super(Git, self).__init__(*args, **kwargs)
        self.influence.append(self)

    @utils.cached.instance
    def get_influence(self, task):
        if not self.git.is_cloned():
            self.git.clone()
        rev = self._get_revision()
        if rev is not None:
            return self.git.tree_hash(rev)
        return "{0}: {1}".format(
            self.git.relpath,
            self.git.tree_hash())

TaskRegistry.get().add_task_class(Git)
