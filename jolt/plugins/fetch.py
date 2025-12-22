import hashlib
from jolt import BooleanParameter, Parameter
from jolt.plugins.git import ErrorDict
from jolt.tasks import Resource, TaskRegistry
from jolt import filesystem as fs
from jolt import utils
from jolt.error import raise_error_if
from jolt.loader import JoltLoader
from jolt.tools import SUPPORTED_ARCHIVE_TYPES


class Fetch(Resource):
    name = "fetch"
    alias = Parameter(required=False, help="Name of the task used when referencing content. Defaults to the filename of the fetched file.")
    extract = BooleanParameter(default=True, help="Whether to extract the fetched file.")
    path = Parameter(required=False, help="Destination directory.")
    url = Parameter(help="URL to fetch from.")
    md5 = Parameter(required=False, help="Expected MD5 hash of the fetched file.")
    sha256 = Parameter(required=False, help="Expected SHA256 hash of the fetched file.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.joltdir = JoltLoader.get().joltdir

        # Set the path to the extraction directory
        if self.path.is_unset():
            self.abspath = self.tools.builddir(utils.canonical(self.short_qualified_name), incremental="always", unique=False)
            if not self._extract():
                # Join with filename if not extracting
                self.abspath = fs.path.join(self.abspath, self._get_filename())
        else:
            self.abspath = fs.path.join(self.joltdir, str(self.path) or self._get_name())

        self.relpath = fs.path.relpath(self.abspath, self.tools.wsroot)

    def _extract(self):
        """ Check if the fetched file should/can be extracted. """
        filename = self._get_filename()

        if not any([filename.endswith(ext) for ext in SUPPORTED_ARCHIVE_TYPES]):
            return False

        return bool(self.extract)

    def _acquire_ws(self):
        # Create the destination directory if it does not exist
        self.tools.mkdir(fs.path.dirname(self.abspath), recursively=True)

        if self._extract():
            with self.tools.tmpdir() as tmpdir, self.tools.cwd(tmpdir):
                filename = self._get_filename()
                self.tools.download(self.url, filename)
                self._verify_sha256(filename)
                self.tools.extract(filename, self.abspath)
        else:
            self.tools.download(self.url, self.abspath)
            self._verify_sha256(self.abspath)

    def acquire(self, artifact, deps, tools, owner):
        self._acquire_ws()
        self._assign_fetch(owner)
        artifact.worktree = fs.path.relpath(self.abspath, owner.joltdir)

    def _assign_fetch(self, task, none=False):
        if not hasattr(task, "fetch"):
            task.fetch = ErrorDict(self)
        if none:
            # None means the git repo is not cloned or checked out
            # and should not be included in the git dictionary
            # of the consuming task yet. If the consuming task
            # requires the git repo for its influence collection,
            # the dict will raise an error. The solution is to
            # assign hash=true to the git requirement which
            # will cause the git repo to be cloned and checked out
            # before the influence collection is performed.
            task.fetch[self._get_name()] = None
        else:
            # Assign the git repo to the consuming task.
            # The git repo is cloned and checked out before
            # any influence collection is performed.
            task.fetch[self._get_name()] = fs.path.relpath(self.abspath, task.joltdir)

    def _get_name(self):
        return str(self.alias) if self.alias.is_set() else self._get_filename()

    def _get_filename(self):
        return fs.path.basename(str(self.url))

    def _verify_sha256(self, filepath):
        if not self.sha256.is_set():
            return
        actual_hash = self.tools.checksum_file(filepath, hashfn=hashlib.sha256)
        expected_hash = str(self.sha256)
        raise_error_if(
            actual_hash != expected_hash,
            f"SHA256 hash mismatch for fetched file '{filepath}': expected {expected_hash}, got {actual_hash}"
        )


TaskRegistry.get().add_task_class(Fetch)
