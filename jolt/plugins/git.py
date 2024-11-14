import os
import pygit2
import re
import urllib.parse

from jolt.tasks import BooleanParameter, Export, Parameter, TaskRegistry, WorkspaceResource
from jolt.influence import FileInfluence, HashInfluenceRegistry
from jolt.tools import Tools
from jolt.loader import JoltLoader, workspace_locked
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

        # Get reference repository path
        refroot = config.get("git", "reference", None)
        refpath = None
        if refroot:
            # Append <host>/<path> to the reference root
            url = urllib.parse.urlparse(str(self.url))
            refpath = fs.path.join(refroot, url.hostname, url.path.lstrip("/"))
            refpath = fs.path.abspath(refpath)

        # If the directory exists, initialize the repository instead of cloning
        if fs.path.exists(self.path):
            with self.tools.cwd(self.path):
                self.tools.run("git init", output_on_error=True)

                # Set the reference repository if available
                if refpath:
                    # Check if the reference repository is a git repository
                    objpath = os.path.join(refpath, ".git", "objects")
                    objpath_bare = os.path.join(refpath, "objects")
                    if os.path.isdir(objpath):
                        refpath = objpath
                    elif os.path.isdir(objpath_bare):
                        refpath = objpath_bare
                    else:
                        refpath = None

                if refpath:
                    self.tools.mkdir(".git/objects/info")
                    self.tools.write_file(".git/objects/info/alternates", refpath)

                self.tools.run("git remote add origin {}", self.url, output_on_error=True)
                self.tools.run("git fetch origin", output_on_error=True)
                self.tools.run("git checkout -f FETCH_HEAD", output_on_error=True)
        else:
            if refpath and os.path.isdir(refpath):
                self.tools.run("git clone --reference-if-able {0} {1} {2}", refpath, self.url, self.path, output_on_error=True)
            else:
                self.tools.run("git clone  {0} {1}", self.url, self.path, output_on_error=True)

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
        dlim = config.getsize("git", "maxdiffsize", "1 MiB")
        raise_error_if(
            len(diff) > dlim,
            "Repository '{}' has uncommitted changes. Size of patch exceeds configured transfer limit ({} > {} bytes)."
            .format(self.relpath, len(diff), dlim))
        return diff

    def patch(self, patch):
        if not patch:
            return
        with self.tools.cwd(self.path), self.tools.tmpdir("git") as tmp:
            patchfile = fs.path.join(tmp, "jolt.diff")
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
    @workspace_locked
    def write_tree(self):
        tools = Tools()
        with tools.cwd(self._git_folder()):
            tools.copy("index", "jolt-index")
        with tools.environ(GIT_INDEX_FILE=self._git_jolt_index()), tools.cwd(self.path):
            tree = tools.run(
                "git -c core.safecrlf=false add -A && git write-tree",
                output_on_error=True)
        return tree

    def tree_hash(self, rev=None, path="/"):
        # When rev is None, the caller want the tree hash of the repository's
        # current workspace state. If no checkout has been made, that would be the
        # tree that was written upon initialization of the repository as it
        # includes any uncommitted changes. If a checkout has been made since
        # the repo was initialized, make this an explicit request for the current
        # head - there can be no local changes.
        if rev is None:
            if self.is_original_head():
                tree = self.repository.get(self.write_tree())
            else:
                rev = self.head()

        path = fs.path.normpath(path)
        full_path = fs.path.join(self.path, path) if path != "/" else self.path

        # Lookup tree hash value in cache
        value = self._tree_hash.get((full_path, rev))
        if value is not None:
            return value

        # Translate explicit rev to tree
        if rev is not None:
            commit = self.rev_parse(rev)
            obj = self.repository.get(commit)
            try:
                tree = obj.tree
            except AttributeError:
                tree = obj.get_object().tree

        # Traverse tree from root to requested path
        if path != "/":
            tree = tree[fs.as_posix(path)]

        # Update tree hash cache
        self._tree_hash[(full_path, rev)] = value = tree.id

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
                "git fetch --prune {url} {what}",
                url=self.url,
                what=commit or refspec or '',
                output_on_error=True)

    def checkout(self, rev, commit=None):
        if rev == self._last_rev:
            log.debug("Checkout skipped, already @ {}", rev)
            return False
        log.verbose("Checking out {0} in {1}", rev, self.path)
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


class ErrorDict(dict):
    """ A dict that raises an error if the value of a key is None. """

    def __init__(self, repo):
        self.repo = repo

    def __getitem__(self, key):
        value = super().__getitem__(key)
        raise_task_error_if(value is None, self.repo, "Git repository '{0}' referenced in influence collection before being cloned/checked out. Assign hash=true to the git requirement.", key)
        return value


class Git(WorkspaceResource, FileInfluence):
    """
    Resource that clones and monitors a Git repo.

    By default, the repo is cloned into a build directory named after
    the resource. The 'path' parameter can be used to specify a different
    location relative to the workspace root.

    The path of the cloned repo is made available to consuming tasks
    through their 'git' attribute. The 'git' attribute is a dictionary
    where the key is the name of the git repository and the value is
    the relative path to the repository from the consuming task's
    workspace.

    The resource influences the hash of consuming tasks, causing tasks
    to be re-executed if the cloned repo is modified.

    The plugin must be loaded before it can be used. This is done by
    importing the module, or by adding the following line to the
    configuration file:

    .. code-block:: ini

            [git]

    Example:

    .. code-block:: python

            from jolt.plugins import git

            class Example(Task):
                requires = ["git:url=https://github.com/user/repo.git"]

                def run(self, deps, tools):
                    self.info("The git repo is located at: {git[repo]}")
                    with tools.cwd(self.git["repo"]):
                        tools.run("make")

    """
    name = "git"

    url = Parameter(help="URL to the git repo to be cloned. Required.")
    """ URL to the git repo to be cloned. Required. """

    rev = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    """ Specific commit or tag to be checked out. Optional. """

    hash = BooleanParameter(required=False, help="Let repo content influence the hash of consuming tasks.")
    """ Let repo content influence the hash of consuming tasks. Default ``True``. Optional. """

    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    """ Alternative path where the repository should be cloned. Relative to ``joltdir``. Optional. """

    _revision = Export(value=lambda t: t._export_revision())
    """ To worker exported value of the revision to be checked out. """

    _diff = Export(value=lambda t: t.git.diff(), encoded=True)
    """ To worker exported value of the diff of the repo. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.joltdir = JoltLoader.get().joltdir

        # Set the path to the repo
        if self.path.is_unset():
            self.abspath = self.tools.builddir(utils.canonical(self.short_qualified_name), incremental="always", unique=False)
            self.relpath = fs.path.relpath(self.abspath, self.tools.wsroot)
        else:
            self.abspath = fs.path.join(self.joltdir, str(self.path) or self._get_name())
            self.relpath = fs.path.relpath(self.abspath, self.tools.wsroot)

        # Create the git repository
        self.refspecs = kwargs.get("refspecs", [])
        self.git = new_git(self.url, self.abspath, self.relpath, self.refspecs)

    @utils.cached.instance
    def _get_name(self):
        repo = fs.path.basename(self.url.get_value())
        name, _ = fs.path.splitext(repo)
        return name

    def _export_revision(self):
        return self.rev.value or self.git.head()

    def _get_revision(self):
        if self._revision.is_imported:
            return self._revision.value
        if not self.rev.is_unset():
            return self.rev.get_value()
        return None

    def _assign_git(self, task, none=False):
        if not hasattr(task, "git"):
            task.git = ErrorDict(self)
        if none:
            # None means the git repo is not cloned or checked out
            # and should not be included in the git dictionary
            # of the consuming task yet. If the consuming task
            # requires the git repo for its influence collection,
            # the dict will raise an error. The solution is to
            # assign hash=true to the git requirement which
            # will cause the git repo to be cloned and checked out
            # before the influence collection is performed.
            task.git[self._get_name()] = None
        else:
            # Assign the git repo to the consuming task.
            # The git repo is cloned and checked out before
            # any influence collection is performed.
            task.git[self._get_name()] = fs.path.relpath(self.abspath, task.joltdir)

    def acquire(self, artifact, deps, tools, owner):
        self._acquire_ws()
        self._assign_git(owner)
        artifact.worktree = fs.path.relpath(self.abspath, owner.joltdir)

    def prepare_ws_for(self, task):
        """ Prepare the workspace for the task.

        :param task: The task to prepare the workspace for.
        """
        if not self._must_influence():
            # The content of the git repo is not required to influence the hash of the
            # consumer task. The repo is therefore not cloned or checked out
            # until the consumer is executed. Raise an error if the git repo
            # is required for the influence collection of the consumer task.
            self._assign_git(task, none=True)
            return
        # The content of the git repo is required to influence the hash of the consumer task.
        self._assign_git(task)

    def acquire_ws(self, force=False):
        """ Clone and/or checkout the git repo if required """
        if force or self._must_influence() or self._revision.is_imported:
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
                not self._revision.is_imported and not self.rev.is_unset() and self.git.diff(), self,
                "Explicit revision requested but git repo '{0}' has local changes, refusing checkout", self.git.relpath)
            # Should be safe to do this now
            rev = self.git.rev_parse(rev)
            if not self.git.is_head(rev) or self._revision.is_imported:
                if self.git.checkout(rev, commit=commit):
                    self.git.clean()
                    self.git.patch(self._diff.value)

    def _must_influence(self):
        """ Check if the git repo must influence the hash of the consumer task."""

        # If the hash parameter is set, honor it
        if self.hash.is_set():
            return self.hash

        # If the revision parameter is not set, the git repo must influence the hash
        if self.rev.is_unset():
            return True

        # If the revision parameter is set, no influence is needed since the
        # revision is fixed and repository content will not change.
        return False

    def is_influenced_by(self, task, path):
        influencing = self._must_influence() or self.rev.is_set()
        return influencing and fs.is_relative_to(path, self.abspath)

    def _influence(self):
        influence = super()._influence()
        return influence + [self] if self._must_influence() else influence

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


TaskRegistry.get().add_task_class(Git)
