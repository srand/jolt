import os
import pygit2
import re

from jolt.tasks import BooleanParameter, Export, Parameter, TaskRegistry, WorkspaceResource
from jolt.influence import FileInfluence, HashInfluenceRegistry
from jolt.tools import Tools
from jolt.loader import JoltLoader
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.error import JoltCommandError
from jolt.error import raise_error
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if


log.verbose("[Git] Loaded")


class GitRepository(object):
    def __init__(self, url, path, relpath, refspecs=None):
        self.path = path
        self.relpath = relpath
        self.gitpath = None
        self.tools = Tools()
        self.url = url
        self.default_refspecs = [
            '+refs/heads/*:refs/remotes/origin/*',
            '+refs/tags/*:refs/remotes/origin/*',
        ]
        self.refspecs = refspecs or []
        self._tree_hash = {}
        self._original_head = True
        self._last_rev = None
        self._init_repo()

    def _init_repo(self):
        gitpath = os.path.join(self.path, ".git")
        if os.path.isdir(os.path.join(self.path, ".git")):
            self.gitpath = gitpath
            self.repository = pygit2.Repository(self.gitpath)
        elif os.path.exists(gitpath):
            with self.tools.cwd(self.path):
                path = self.tools.run("git rev-parse --git-dir", output=False)
            self.gitpath = os.path.join(self.path, path)
            self.repository = pygit2.Repository(self.gitpath)
        else:
            self.repository = None

    @utils.cached.instance
    def _git_folder(self):
        return self.gitpath

    @utils.cached.instance
    def _git_index(self):
        return fs.path.join(self.gitpath, "index")

    @utils.cached.instance
    def _git_jolt_index(self):
        return fs.path.join(self.gitpath, "jolt-index")

    def is_cloned(self):
        return self.gitpath is not None

    def is_indexed(self):
        return self.is_cloned() and fs.path.exists(self._git_index())

    def clone(self):
        log.info("Cloning into {0}", self.path)
        if fs.path.exists(self.path):
            with self.tools.cwd(self.path):
                self.tools.run("git init && git remote add origin {} && git fetch",
                               self.url, output_on_error=True)
        else:
            self.tools.run("git clone {0} {1}", self.url, self.path, output_on_error=True)
        self._init_repo()
        raise_error_if(
            self.repository is None,
            "Failed to clone repository '{0}'", self.relpath)

    @utils.cached.instance
    def diff_unchecked(self):
        if not self.is_indexed():
            return ""

        # Build the jolt index file
        self.write_tree()

        # Diff against the jolt index
        with self.tools.environ(GIT_INDEX_FILE=self._git_jolt_index()), self.tools.cwd(self.path):
            return self.tools.run("git diff --binary --no-ext-diff HEAD ./",
                                  output_on_error=True,
                                  output_rstrip=False)

    def diff(self):
        diff = self.diff_unchecked()
        dlim = config.getsize("git", "maxdiffsize", "1M")
        raise_error_if(
            len(diff) > dlim,
            "Repository '{}' has uncommitted changes. Size of patch exceeds configured transfer limit ({} > {} bytes)."
            .format(self.relpath, len(diff), dlim))
        return diff

    def patch(self, patch):
        if not patch:
            return
        with self.tools.cwd(self.path), self.tools.tmpdir("git") as t:
            patchfile = fs.path.join(t.path, "jolt.diff")
            with open(patchfile, "wb") as f:
                f.write(patch.encode())
            log.info("Applying patch to {0}", self.path)
            self.tools.run("git apply --whitespace=nowarn {patchfile}", patchfile=patchfile)

    def head(self):
        if not self.is_cloned():
            return None
        return str(self.repository.head.target)

    def is_head(self, rev):
        return self.is_indexed() and self.head() == rev

    def is_original_head(self):
        return self._original_head

    def is_valid_sha(self, rev):
        return re.match(r"[0-9a-f]{40}", rev)

    def rev_parse(self, rev):
        if self.is_valid_sha(rev):
            return rev
        with self.tools.cwd(self.path):
            try:
                commit = self.repository.revparse_single(rev)
            except KeyError:
                self.fetch(commit=rev)
                try:
                    commit = self.repository.revparse_single(rev)
                except Exception:
                    raise_error("Invalid git reference: {}", rev)
            try:
                return str(commit.id)
            except Exception:
                return str(commit)

    @utils.cached.instance
    def write_tree(self):
        tools = Tools()
        with tools.cwd(self._git_folder()):
            tools.copy("index", "jolt-index")
        with tools.environ(GIT_INDEX_FILE=self._git_jolt_index()), tools.cwd(self.path):
            tree = tools.run(
                "git -c core.safecrlf=false add -A && git write-tree",
                output_on_error=True)
        return tree

    def tree_hash(self, sha=None, path="/"):
        # When sha is None, the caller want the tree hash of the repository's
        # current workspace state. If no checkout has been made, that would be the
        # tree that was written upon initialization of the repository as it
        # includes any uncommitted changes. If a checkout has been made since
        # the repo was initialized, make this an explicit request for the current
        # head - there can be no local changes.
        if sha is None:
            if self.is_original_head():
                tree = self.repository.get(self.write_tree())
            else:
                sha = self.head()

        path = fs.path.normpath(path)
        full_path = fs.path.join(self.path, path) if path != "/" else self.path

        # Lookup tree hash value in cache
        value = self._tree_hash.get((full_path, sha))
        if value is not None:
            return value

        # Translate explicit sha to tree
        if sha is not None:
            commit = self.rev_parse(sha)
            obj = self.repository.get(commit)
            try:
                tree = obj.tree
            except AttributeError:
                tree = obj.get_object().tree

        # Traverse tree from root to requested path
        if path != "/":
            tree = tree[fs.as_posix(path)]

        # Update tree hash cache
        self._tree_hash[(full_path, sha)] = value = tree.id

        return value

    def clean(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git clean -dfx", output_on_error=True)

    def reset(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git reset --hard", output_on_error=True)

    def fetch(self, commit=None):
        if commit and not self.is_valid_sha(commit):
            commit = None

        refspec = " ".join(self.default_refspecs + self.refspecs)
        with self.tools.cwd(self.path):
            log.info("Fetching {0} from {1}", commit or refspec or 'commits', self.url)
            self.tools.run(
                "git fetch {url} {what}",
                url=self.url,
                what=commit or refspec or '',
                output_on_error=True)

    def checkout(self, rev, commit=None):
        if rev == self._last_rev:
            log.debug("Checkout skipped, already @ {}", rev)
            return False
        log.info("Checking out {0} in {1}", rev, self.path)
        with self.tools.cwd(self.path):
            try:
                self.tools.run("git checkout -f {rev}", rev=rev, output=False)
            except Exception:
                self.fetch(commit=commit)
                try:
                    self.tools.run("git checkout -f {rev}", rev=rev, output_on_error=True)
                except Exception:
                    raise_error("Commit does not exist in remote for '{}': {}", self.relpath, rev)
        self._original_head = False
        self._last_rev = rev
        return True


_gits = {}


def new_git(url, path, relpath, refspecs=None):
    refspecs = utils.as_list(refspecs or [])
    try:
        git = _gits[path]
        raise_error_if(git.url != url, "Multiple git repositories required at {}", relpath)
        raise_error_if(git.refspecs != refspecs,
                       "Conflicting refspecs detected for git repository at  {}", relpath)
        return git
    except Exception:
        git = _gits[path] = GitRepository(url, path, relpath, refspecs)
        return git


class GitInfluenceProvider(FileInfluence):
    name = "Git"

    def __init__(self, path):
        super().__init__(path)
        self.path = path.rstrip(fs.sep)
        self.name = GitInfluenceProvider.name

    @property
    def joltdir(self):
        return JoltLoader.get().joltdir

    def _find_dotgit(self, path):
        ppath = None
        while path != ppath:
            if fs.path.exists(fs.path.join(path, ".git")):
                return path
            ppath = path
            path = fs.path.dirname(path)
        raise_error("No git repository found at '{}'", self.path)

    @utils.cached.instance
    def get_influence(self, task):
        tools = Tools(task, task.joltdir)
        path = tools.expand_path(self.path)
        git_abs = self._find_dotgit(path)
        git_rel = git_abs[len(self.joltdir) + 1:]
        relpath = path[len(git_abs) + 1:]
        relpath = fs.as_posix(relpath) if relpath else relpath

        if not fs.path.exists(path):
            return "{0}/{1}: N/A".format(git_rel, relpath)
        try:
            git = new_git(None, git_abs, git_rel)
            return "{0}/{1}: {2}".format(git_rel, relpath, git.tree_hash(path=relpath or "/"))
        except KeyError:
            return "{0}/{1}: N/A".format(git_rel, relpath)
        except JoltCommandError as e:
            stderr = "\n".join(e.stderr)
            if "exists on disk, but not in" in stderr:
                return "{0}/{1}: N/A".format(git_rel, relpath)
            raise e

    def is_influenced_by(self, task, path):
        tools = Tools(task, task.joltdir)
        gitpath = tools.expand_path(self.path)
        return fs.is_relative_to(path, gitpath)


def global_influence(path, cls=GitInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path))


def influence(path, git_cls=GitInfluenceProvider):
    def _decorate(cls):
        _old_influence = cls._influence

        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(git_cls(path=path))
            return influence

        cls._influence = _influence
        return cls
    return _decorate


class GitSrc(WorkspaceResource, FileInfluence):
    """ Clones a Git repo.
    """

    name = "git-src"
    url = Parameter(help="URL to the git repo to be cloned. Required.")
    sha = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    defer = BooleanParameter(False, help="Defer cloning until a consumer task must be built.")
    _revision = Export(value=lambda t: t._export_revision())
    _diff = Export(value=lambda t: t.git.diff(), encoded=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.joltdir = JoltLoader.get().joltdir
        self.relpath = str(self.path) or self._get_name()
        self.abspath = fs.path.join(self.joltdir, self.relpath)
        self.refspecs = kwargs.get("refspecs", [])
        self.git = new_git(self.url, self.abspath, self.relpath, self.refspecs)

    @utils.cached.instance
    def _get_name(self):
        repo = fs.path.basename(self.url.get_value())
        name, _ = fs.path.splitext(repo)
        return name

    def _export_revision(self):
        return self.sha.value or self.git.head()

    def _get_revision(self):
        if self._revision.is_imported:
            return self._revision.value
        if not self.sha.is_unset():
            return self.sha.get_value()
        return None

    def acquire(self, **kwargs):
        self._acquire_ws()

    def acquire_ws(self):
        if self.defer is None or self.defer.is_false:
            self._acquire_ws()

    def _acquire_ws(self):
        commit = None
        if not self.git.is_cloned():
            self.git.clone()
        if not self._revision.is_imported:
            self.git.diff_unchecked()
        else:
            commit = self._revision.value
        rev = self._get_revision()
        if rev is not None:
            raise_task_error_if(
                not self._revision.is_imported and not self.sha.is_unset() and self.git.diff(), self,
                "explicit sha requested but git repo '{0}' has local changes", self.git.relpath)
            # Should be safe to do this now
            rev = self.git.rev_parse(rev)
            if not self.git.is_head(rev) or self._revision.is_imported:
                if self.git.checkout(rev, commit=commit):
                    self.git.clean()
                    self.git.patch(self._diff.value)

    def get_influence(self, task):
        return None

    def is_influenced_by(self, task, path):
        return fs.is_relative_to(path, self.abspath) and self.sha.is_set()


TaskRegistry.get().add_task_class(GitSrc)


class Git(GitSrc):
    """ Clones a Git repo.

    Also influences the hash of consuming tasks, causing tasks to
    be re-executed if the cloned repo is modified.

    """
    name = "git"
    url = Parameter(help="URL to the git repo to be cloned. Required.")
    sha = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    defer = None
    _revision = Export(value=lambda t: t._export_revision())
    _diff = Export(value=lambda t: t.git.diff(), encoded=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.influence.append(self)

    @utils.cached.instance
    def get_influence(self, task):
        if not self.git.is_cloned():
            self.git.clone()
        if not self._revision.is_imported:
            self.git.diff_unchecked()
        rev = self._get_revision()

        try:
            if rev is not None:
                th = self.git.tree_hash(rev)
            else:
                th = self.git.tree_hash()
        except KeyError:
            th = "N/A"

        return "{0}: {1}".format(self.git.relpath, th)

    def is_influenced_by(self, task, path):
        return path.startswith(self.abspath + fs.sep)


TaskRegistry.get().add_task_class(Git)
