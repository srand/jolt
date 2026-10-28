from contextlib import contextmanager
import functools
import os
import pygit2
import re
from threading import RLock
import urllib.parse

from jolt.tasks import BooleanParameter, Export, IntParameter, Parameter, TaskRegistry, WorkspaceResource
from jolt.influence import FileInfluence, HashInfluenceRegistry
from jolt.tools import Tools
from jolt.loader import JoltLoader, workspace_locked
from jolt import config
from jolt import fstree
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.error import JoltCommandError
from jolt.error import raise_error
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if


log.verbose("[Git] Loaded")


def locked(func):
    def _f(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)
    return _f


def _changes_workspace(func):
    """ Discards the workspace index after the decorated method has run. """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            fstree.invalidate_workspace_index(args[0].path)
    return wrapper


class GitProgress(object):
    """ Shows the progress that git writes to stderr as a progress bar. """

    # For example "Receiving objects:  45% (4500/10000), 12.30 MiB | 4.10 MiB/s"
    _pattern = re.compile(r"^(?:remote: )?([A-Za-z ]+):\s+\d+% \((\d+)/(\d+)\)")

    def __init__(self, desc):
        self._desc = desc
        self._bar = None
        self._phase = None
        self._completed = 0
        self._total = 0

    def __enter__(self):
        self._bar = log.progress(self._desc, None, " objects", estimates=False).__enter__()
        return self

    def __exit__(self, *args):
        return self._bar.__exit__(*args)

    def __call__(self, line):
        """ Updates the bar from a line of git output. Returns True if it was progress. """
        match = self._pattern.match(line)
        if not match:
            return False
        phase, completed, total = match.group(1), int(match.group(2)), int(match.group(3))
        # Each phase, and each submodule, counts from zero again
        if phase != self._phase or total != self._total or completed < self._completed:
            self._phase, self._completed, self._total = phase, 0, total
            self._bar.reset(total=total)
            self._bar.set_description("{}: {}".format(self._desc, phase.lower()))
        self._bar.update(completed - self._completed)
        self._completed = completed
        return True


class GitRepository(object):
    # Local ref used to anchor a shallowly fetched revision. FETCH_HEAD is not
    # one of the reachability roots that git uses (refs, HEAD, the reflogs and
    # the index), so a real ref is required to keep the fetched objects alive
    # through repack/gc until the revision has been checked out.
    fetchref = "refs/jolt/head"

    def __init__(self, url, path, relpath, refspecs=None):
        self.path = path
        self.relpath = relpath
        self.gitpath = None
        self.tools = Tools()
        self.url = url
        self.default_refspecs = [
            '+refs/heads/*:refs/remotes/origin/*',
            '+refs/tags/*:refs/tags/*',
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
                path = self.tools.run("git rev-parse --git-dir", output=False, new_session=True)
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

    def _get_reference_path(self):
        """ Return the configured reference repository root path, or None. """
        refroot = config.get("git", "reference", None)
        if not refroot:
            return None
        url = urllib.parse.urlparse(str(self.url))
        refpath = fs.path.join(refroot, url.hostname, url.path.lstrip("/"))
        return fs.path.abspath(refpath)

    def _configure_alternates(self, refpath):
        """ Point the local repo at a reference repository via git alternates. """
        objpath = os.path.join(refpath, ".git", "objects")
        objpath_bare = os.path.join(refpath, "objects")
        if os.path.isdir(objpath):
            objects_path = objpath
        elif os.path.isdir(objpath_bare):
            objects_path = objpath_bare
        else:
            return
        self.tools.mkdir(".git/objects/info")
        self.tools.write_file(".git/objects/info/alternates", objects_path)

    @property
    def _name(self):
        """ Short name of the repository, for display. """
        name, _ = fs.path.splitext(fs.path.basename(str(self.url).rstrip("/")))
        return name

    @contextmanager
    def _progress(self, desc):
        """ Progress bar for a git command, and the option that enables its progress output.

        Git only reports progress to a terminal unless asked to. The output
        is parsed, so it must not be translated.
        """
        if not log.is_progress_enabled():
            yield "", None
            return
        with GitProgress(desc) as progress, self.tools.environ(LC_ALL="C", GIT_PROGRESS_DELAY="0"):
            yield "--progress", progress

    def _revision_refspec(self, rev=None):
        """ Refspec fetching a single revision into a local ref.

        An unspecified revision means the remote's default branch.
        """
        return "+{0}:{1}".format(rev or "HEAD", self.fetchref)

    def _fetch_reference(self, refpath, shallow=False, rev=None, depth=1):
        """ Copy objects from a reference repository into the local repository.

        In contrast to git alternates, the objects become owned by the local
        repository, so the workspace stays intact when the reference repository
        is later pruned, repacked or removed. The reference repository is only
        a cache: whatever it cannot provide is fetched from the remote in the
        next step, which is why a failure here is not an error.
        """
        if not os.path.isdir(refpath):
            return

        if shallow:
            # Tag auto-following would fetch tags pointing at the revision, and
            # the objects behind them, which is more than was asked for.
            what = rev or "HEAD"
            refspec = self._revision_refspec(rev)
            notags = "--no-tags"
        else:
            # The default refspecs already fetch every tag explicitly
            what = "commits"
            refspec = " ".join(self.default_refspecs + self.refspecs)
            notags = ""

        with self.tools.cwd(self.path):
            log.info("Fetching {0} from {1}", what, refpath)
            try:
                with self._progress("Fetching " + self._name) as (progress_option, progress):
                    self.tools.run(
                        "git fetch --force {progress_option} {notags} {depth} {refpath} {refspec}",
                        progress_option=progress_option,
                        notags=notags,
                        depth="--depth={0}".format(depth) if shallow else "",
                        refpath=refpath,
                        refspec=refspec,
                        output=False,
                        progress=progress,
                        new_session=True)
            except JoltCommandError as e:
                # A cache miss is routine, don't alarm the user about it
                log.verbose(
                    "Reference repository '{0}' could not provide {1}: {2}",
                    refpath, what, "\n".join(e.stderr))

    @_changes_workspace
    def clone(self, submodules=False, rev=None, shallow=False):
        """ Clone the repository.

        :param submodules: Initialize and update submodules after cloning.
        :param rev: Revision (tag or commit) to fetch and check out. Only used
            when ``shallow`` is True, where it defaults to the remote's default
            branch.
        :param shallow: Clone the repository without its full history.
            When True, only a single revision is fetched (shallow, depth 1)
            and checked out, avoiding the cost of a full clone.
        """
        refpath = self._get_reference_path()
        dissociate = config.getboolean("git", "dissociate", False)

        if shallow or fs.path.exists(self.path):
            # Only a single revision is wanted, or the directory already
            # exists: initialize and fetch instead of cloning.
            if shallow:
                log.info("Fetching {0} into {1}", rev or "HEAD", self.path)
            else:
                log.info("Cloning into {0}", self.path)
            self.tools.mkdir(self.path)
            with self.tools.cwd(self.path):
                self.tools.run("git init", output_on_error=True, new_session=True)
                if refpath:
                    if dissociate:
                        # Copy the objects out of the reference repository
                        # rather than borrowing them, so that the workspace
                        # never depends on it again and there is nothing to
                        # dissociate from afterwards.
                        self._fetch_reference(refpath, shallow=shallow, rev=rev)
                    else:
                        self._configure_alternates(refpath)
                if shallow:
                    self._fetch_revision(rev)
                else:
                    self.fetch()
                self.tools.run("git checkout -f FETCH_HEAD", output_on_error=True, new_session=True)
                if shallow and rev and not self.is_valid_sha(rev):
                    # Create a local tag so that the revision can later be
                    # resolved (e.g. by rev_parse) without re-contacting the
                    # remote.
                    self.tools.run("git tag -f {rev} FETCH_HEAD", rev=rev, output_on_error=True, new_session=True)
        else:
            log.info("Cloning into {0}", self.path)
            extra_clone_options = config.get("git", "clone_options", "")
            with self._progress("Cloning " + self._name) as (progress_option, progress):
                if refpath and os.path.isdir(refpath):
                    # git clones with --reference are dissociated by git itself
                    self.tools.run("git clone {0} --reference-if-able {1} {2} {3} {4} {5}", progress_option, refpath, "--dissociate" if dissociate else "", extra_clone_options, self.url, self.path, output_on_error=True, progress=progress, new_session=True)
                else:
                    self.tools.run("git clone {0} {1} {2} {3}", progress_option, extra_clone_options, self.url, self.path, output_on_error=True, progress=progress, new_session=True)

        self._init_repo()
        raise_error_if(
            self.repository is None,
            "Failed to clone repository '{0}'", self.relpath)
        if submodules:
            self._update_submodules()

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
                                  output_rstrip=False,
                                  new_session=True)

    def diff(self):
        diff = self.diff_unchecked()
        dlim = config.getsize("git", "maxdiffsize", "1 MiB")
        raise_error_if(
            len(diff) > dlim,
            "Repository '{}' has uncommitted changes. Size of patch exceeds configured transfer limit ({} > {} bytes)."
            .format(self.relpath, len(diff), dlim))
        return diff

    @_changes_workspace
    def patch(self, patch):
        if not patch:
            return
        with self.tools.cwd(self.path), self.tools.tmpdir("git") as tmp:
            patchfile = fs.path.join(tmp, "jolt.diff")
            with open(patchfile, "wb") as f:
                f.write(patch.encode())
            log.info("Applying patch to {0}", self.path)
            self.tools.run("git apply --whitespace=nowarn {patchfile}", patchfile=patchfile, new_session=True)

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
                output_on_error=True,
                new_session=True)
        return tree

    def tree_hash(self, rev=None, path="/"):
        path = fs.path.normpath(path)
        full_path = fs.path.join(self.path, path) if path != "/" else self.path

        # When a checkout has been made, there can be no local changes, so treat
        # an unspecified rev as an explicit request for the current head commit.
        if rev is None and not self.is_original_head():
            rev = self.head()

        value = self._tree_hash.get((full_path, rev))
        if value is not None:
            return value

        if rev is None:
            # Original head: capture current workspace state including uncommitted changes.
            tree = self.repository.get(self.write_tree())
        else:
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

    @_changes_workspace
    def clean(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git clean -dfx", output_on_error=True, new_session=True)

    @_changes_workspace
    def reset(self):
        with self.tools.cwd(self.path):
            return self.tools.run("git reset --hard", output_on_error=True, new_session=True)

    @utils.retried.on_exception(JoltCommandError, pattern="Command failed: git fetch", count=6, backoff=[2, 5, 10, 15, 20, 30])
    def fetch(self, commit=None):
        if commit and not self.is_valid_sha(commit):
            commit = None

        extra_fetch_options = config.get("git", "fetch_options", "")

        refspec = " ".join(self.default_refspecs + self.refspecs)
        with self.tools.cwd(self.path):
            log.info("Fetching {0} from {1}", commit or refspec or 'commits', self.url)
            with self._progress("Fetching " + self._name) as (progress_option, progress):
                self.tools.run(
                    "git fetch --force --prune {progress_option} {extra_fetch_options} {url} {what}",
                    progress_option=progress_option,
                    extra_fetch_options=extra_fetch_options,
                    url=self.url,
                    what=commit or refspec or '',
                    output_on_error=True,
                    progress=progress,
                    new_session=True)

    @utils.retried.on_exception(JoltCommandError, pattern="Command failed: git fetch", count=6, backoff=[2, 5, 10, 15, 20, 30])
    def _fetch_revision(self, rev=None, depth=1):
        """ Fetch a single revision (tag or commit) without its history.

        An unspecified revision fetches the remote's default branch.
        """
        extra_fetch_options = config.get("git", "fetch_options", "")
        with self.tools.cwd(self.path):
            log.info("Fetching {0} from {1}", rev or "HEAD", self.url)
            # The revision is fetched into a local ref, not just FETCH_HEAD, so
            # that its objects are reachable for git. Tag auto-following is
            # disabled to keep the fetch down to the requested revision.
            with self._progress("Fetching " + self._name) as (progress_option, progress):
                self.tools.run(
                    "git fetch --force --no-tags --depth={depth} {progress_option} {extra_fetch_options} {url} {refspec}",
                    depth=depth,
                    progress_option=progress_option,
                    extra_fetch_options=extra_fetch_options,
                    url=self.url,
                    refspec=self._revision_refspec(rev),
                    output_on_error=True,
                    progress=progress,
                    new_session=True)

    @_changes_workspace
    def checkout(self, rev, commit=None, submodules=False):
        if rev == self._last_rev:
            log.debug("Checkout skipped, already @ {}", rev)
            if submodules:
                self._update_submodules()
            return False
        log.verbose("Checking out {0} in {1}", rev, self.path)
        with self.tools.cwd(self.path):
            try:
                self.tools.run("git checkout -f {rev}", rev=rev, output=False, new_session=True)
                if submodules:
                    self._update_submodules()
            except Exception:
                self.fetch(commit=commit)
                try:
                    self.tools.run("git checkout -f {rev}", rev=rev, output_on_error=True, new_session=True)
                    if submodules:
                        self._update_submodules()
                except Exception:
                    raise_error("Commit does not exist in remote for '{}': {}", self.relpath, rev)
        self._original_head = False
        self._last_rev = rev
        return True

    def _update_submodules(self):
        with self.tools.cwd(self.path), self._progress("Updating submodules of " + self._name) as (progress_option, progress):
            # Relative submodule URLs are resolved against the URL of the origin
            # remote, which repositories initialized and fetched by URL don't have
            self.tools.run("git config remote.origin.url {0}", self.url, output_on_error=True, new_session=True)
            self.tools.run("git submodule sync --recursive", output_on_error=True, new_session=True)
            self.tools.run("git submodule update --init --recursive {0}", progress_option, output_on_error=True, progress=progress, new_session=True)


_gits = {}


def new_git(url, path, relpath, refspecs=None):
    refspecs = utils.as_list(refspecs or [])
    try:
        git = _gits[path]
        raise_error_if(git.url != url, "Multiple git repositories required at {}", relpath)
        raise_error_if(git.refspecs != refspecs,
                       "Conflicting refspecs detected for git repository at {}", relpath)
        return git
    except Exception:
        git = _gits[path] = GitRepository(url, path, relpath, refspecs)
        return git


class GitInfluenceProvider(FileInfluence):
    """
    Influence of a file or directory tree in the workspace.

    The fstree hash of the path in the workspace index is used as
    influence. Files ignored by the index don't influence the hash.
    """

    name = "Git"

    def __init__(self, path):
        super().__init__(path)
        self.name = GitInfluenceProvider.name

    def get_influence(self, task):
        index = fstree.get_workspace_index()
        path = task.tools.expand_path(self.path)
        relpath = index.relpath(path)
        tree = index.tree_hash(path)
        return "{0}: {1}".format(relpath or self.path, tree or "N/A")

    def is_influenced_by(self, task, path):
        gitpath = task.tools.expand_path(self.path)
        return fs.is_relative_to(task.tools.expand_path(path), gitpath)


def global_influence(path, cls=GitInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path))


def influence(path, git_cls=GitInfluenceProvider):
    def _decorate(cls):
        _old_influence = cls._influence

        def _influence(self, *args, **kwargs):
            influence = _old_influence(self, *args, **kwargs)
            influence.append(git_cls(path))
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

    rev = Parameter(required=False, help="Specific commit or tag to be checked out.")
    """ Specific commit or tag to be checked out.

    When ``shallow`` is True and the repository has not already been cloned,
    an unset revision fetches the remote's default branch. Optional. """

    hash = BooleanParameter(required=False, help="Let repo content influence the hash of consuming tasks.")
    """ Let repo content influence the hash of consuming tasks. Default ``True``. Optional. """

    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    """ Alternative path where the repository should be cloned. Relative to ``joltdir``. Optional. """

    shallow = BooleanParameter(default=False, help="Clone the repository without its full history.")
    """ Clone the repository without its full history. Default ``False``. Optional. """

    submodules = BooleanParameter(default=False, help="Initialize and update git submodules after cloning.")
    """ Initialize and update git submodules after cloning. Default ``False``. Optional. """

    clean = BooleanParameter(default=False, help="Clean repository after it has been used")
    """ Removes untracked files from the repository. """

    _revision = Export(value=lambda t: t._export_revision())
    """ To worker exported value of the revision to be checked out. """

    _diff = Export(value=lambda t: t.git.diff(), encoded=True)
    """ To worker exported value of the diff of the repo. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = RLock()
        self.joltdir = JoltLoader.get().joltdir

        # Set the path to the repo
        if self.path.is_unset():
            self.abspath = self.tools.builddir(utils.canonical(self.short_qualified_name), incremental="always", unique=False)
            self.relpath = fs.path.relpath(self.abspath, self.tools.wsroot)
        else:
            self.abspath = fs.path.join(self.joltdir, str(self.path) or self._get_name())
            self.relpath = fs.path.relpath(self.abspath, self.tools.wsroot)

        self.abspath = fs.path.normpath(self.abspath)
        self.relpath = fs.path.normpath(self.relpath)

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
            # Placeholder; the dict raises an error if accessed before the repo is cloned.
            # Set hash=true on the requirement to force cloning before influence collection.
            task.git[self._get_name()] = None
        else:
            task.git[self._get_name()] = fs.path.relpath(self.abspath, task.joltdir)

    def acquire(self, artifact, deps, tools, owner):
        self._acquire_ws()
        self._assign_git(owner)
        artifact.worktree = fs.path.relpath(self.abspath, owner.joltdir)

    def release(self, artifact, deps, tools, owner):
        if self.clean:
            self.git.clean()
            self.git.reset()

    def prepare_ws_for(self, task):
        """ Prepare the workspace for the task.

        :param task: The task to prepare the workspace for.
        """
        if not self._must_influence():
            # Repo is not cloned until the consumer executes.
            self._assign_git(task, none=True)
            return
        self._assign_git(task)

    def acquire_ws(self, force=False):
        """ Clone and/or checkout the git repo if required """
        if force or self._must_influence() or self._revision.is_imported:
            self._acquire_ws()

    @locked
    def _acquire_ws(self):
        commit = None
        if not self.git.is_cloned():
            self.git.clone(submodules=bool(self.submodules), rev=self._get_revision(), shallow=bool(self.shallow))
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
                if self.git.checkout(rev, commit=commit, submodules=bool(self.submodules)):
                    self.git.clean()
                    self.git.patch(self._diff.value)

    def _must_influence(self):
        """ Check if the git repo must influence the hash of the consumer task."""
        if self.hash.is_set():
            return self.hash
        # A fixed revision doesn't need content-based influence.
        return self.rev.is_unset()

    def is_influenced_by(self, task, path):
        influencing = self._must_influence() or self.rev.is_set()
        return influencing and fs.is_relative_to(path, self.abspath)

    def _influence(self):
        influence = super()._influence()
        return influence + [self] if self._must_influence() else influence

    @locked
    @utils.cached.instance
    def get_influence(self, task):
        if not self.git.is_cloned():
            self.git.clone(submodules=bool(self.submodules), rev=self._get_revision(), shallow=bool(self.shallow))
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
