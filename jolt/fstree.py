from contextlib import contextmanager
import fasteners
import fnmatch
import json
import os
import platform
import struct
import subprocess
import threading

from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import tools
from jolt import utils
from jolt.error import raise_error_if


_MAGIC = 0x3ee3
_VERSION = 1

# Fields are written in native byte order without padding, and lengths
# are written as size_t.
_HEADER = struct.Struct("=HH")
_SIZE = struct.Struct("=Q" if struct.calcsize("@N") == 8 else "=I")
_STATUS_MTIME = struct.Struct("=Iq")

_TYPE_REGULAR = 1 << 24
_TYPE_DIRECTORY = 2 << 24
_TYPE_SYMLINK = 4 << 24
_TYPE_MASK = 7 << 24

_MAGIC_CHARS = frozenset("*?[")


def find_executable():
    """
    Returns the path to the fstree executable, or None if it can't be found.

    The executable is first searched for in PATH and then among the
    binaries bundled with Jolt.
    """
    executable = tools.Tools().which("fstree")
    if not executable:
        host = platform.system().lower()
        arch = platform.machine().lower()
        executable = os.path.join(os.path.dirname(__file__), "bin", f"fstree-{host}-{arch}")
    if not os.path.exists(executable):
        return None
    return executable


class IndexEntry(object):
    """ A file, directory or symlink in an fstree index. """

    __slots__ = ("path", "hash", "status", "mtime", "target")

    def __init__(self, path, hash, status, mtime, target):
        self.path = path
        self.hash = hash
        self.status = status
        self.mtime = mtime
        self.target = target

    @property
    def is_file(self):
        return self.status & _TYPE_MASK == _TYPE_REGULAR

    @property
    def is_dir(self):
        return self.status & _TYPE_MASK == _TYPE_DIRECTORY

    @property
    def is_symlink(self):
        return self.status & _TYPE_MASK == _TYPE_SYMLINK

    @property
    def hexdigest(self):
        """ The digest without the algorithm prefix, e.g. 'blake3:'. """
        return self.hash.partition(":")[2]


class Index(object):
    """
    Pure Python reader of fstree index files.

    The index lists every file, directory and symlink in a tree, with
    paths relative to the root of the tree and '/' as separator.
    """

    def __init__(self, root, entries):
        self.root = os.path.normpath(root)
        self._entries = {entry.path: entry for entry in entries}
        self._children = None
        self.excluded = []

    @staticmethod
    def load(root, indexfile):
        with open(indexfile, "rb") as f:
            data = f.read()

        try:
            magic, version = _HEADER.unpack_from(data, 0)
        except struct.error:
            raise_error_if(True, "Failed reading index: {}: truncated", indexfile)
        raise_error_if(magic != _MAGIC, "Failed reading index: {}: invalid magic", indexfile)
        raise_error_if(version != _VERSION, "Failed reading index: {}: invalid version", indexfile)

        entries = []
        offset = _HEADER.size
        size_size = _SIZE.size
        end = len(data)

        try:
            while offset < end:
                length, = _SIZE.unpack_from(data, offset)
                offset += size_size
                path = data[offset:offset + length].decode("utf-8", errors="surrogateescape")
                offset += length

                length, = _SIZE.unpack_from(data, offset)
                offset += size_size
                hash = data[offset:offset + length].decode()
                offset += length

                status, mtime = _STATUS_MTIME.unpack_from(data, offset)
                offset += _STATUS_MTIME.size

                target = None
                if status & _TYPE_MASK == _TYPE_SYMLINK:
                    length, = _SIZE.unpack_from(data, offset)
                    offset += size_size
                    target = data[offset:offset + length].decode("utf-8", errors="surrogateescape")
                    offset += length

                if offset > end:
                    raise struct.error("truncated")

                entries.append(IndexEntry(path, hash, status, mtime, target))
        except struct.error:
            raise_error_if(True, "Failed reading index: {}: truncated", indexfile)

        return Index(root, entries)

    def __len__(self):
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries.values())

    def relpath(self, path):
        """
        Returns the path relative to the root of the index, with '/' as
        separator, or None if the path is outside of the tree.
        """
        path = os.path.normpath(path)
        if path == self.root:
            return ""
        prefix = self.root.rstrip(os.sep) + os.sep
        if not path.startswith(prefix):
            return None
        return path[len(prefix):].replace(os.sep, "/")

    def abspath(self, relpath):
        if not relpath:
            return self.root
        return os.path.join(self.root, relpath.replace("/", os.sep))

    def get(self, path):
        """ Returns the entry at the absolute path, or None. """
        relpath = self.relpath(path)
        if relpath is None:
            return None
        return self._entries.get(relpath)

    def isdir(self, path):
        relpath = self.relpath(path)
        if relpath == "":
            return True
        entry = self._entries.get(relpath) if relpath else None
        return entry is not None and entry.is_dir

    def resolve(self, entry, depth=40):
        """
        Follows a symlink entry to the entry it points to.

        Returns a tuple of the final entry, or None if the target isn't
        in the index, and the absolute path of the final target.
        """
        path = self.abspath(entry.path)
        while entry is not None and entry.is_symlink and depth > 0:
            path = os.path.normpath(os.path.join(os.path.dirname(path), entry.target))
            entry = self.get(path)
            depth -= 1
        return entry, path

    def glob(self, pattern):
        """
        Returns the sorted absolute paths of entries matching the pattern.

        The pattern is an absolute path that may contain shell-style
        wildcards and recursive '**' wildcards, with the same semantics
        as :func:`glob.glob` with ``recursive=True``. Files starting with
        a dot are not matched by wildcards. Symlinks to directories are
        not followed.
        """
        relpattern = self.relpath(pattern)
        if relpattern is None:
            return []

        if not _MAGIC_CHARS.intersection(relpattern):
            if relpattern == "" or relpattern in self._entries:
                return [self.abspath(relpattern)]
            return []

        if self._children is None:
            self._children = self._build_children()

        segments = relpattern.split("/") if relpattern else []
        result = set()
        self._glob(segments, "", result)
        return sorted(self.abspath(path) for path in result)

    def _build_children(self):
        children = {"": []}
        for path, entry in self._entries.items():
            parent, _, name = path.rpartition("/")
            children.setdefault(parent, []).append(name)
            if entry.is_dir:
                children.setdefault(path, [])
        return children

    def _join(self, dirpath, name):
        return dirpath + "/" + name if dirpath else name

    def _is_dir(self, path):
        if path == "":
            return True
        entry = self._entries.get(path)
        return entry is not None and entry.is_dir

    def _descendants(self, dirpath):
        """ Yields all non-hidden descendants of a directory, recursively. """
        for name in self._children.get(dirpath, []):
            if name.startswith("."):
                continue
            path = self._join(dirpath, name)
            yield path
            if self._is_dir(path):
                yield from self._descendants(path)

    def _glob(self, segments, dirpath, result):
        if not segments:
            result.add(dirpath)
            return

        segment, rest = segments[0], segments[1:]

        if segment == "**":
            if not rest:
                result.add(dirpath)
                result.update(self._descendants(dirpath))
                return
            self._glob(rest, dirpath, result)
            for path in self._descendants(dirpath):
                if self._is_dir(path):
                    self._glob(rest, path, result)
            return

        if not _MAGIC_CHARS.intersection(segment):
            path = self._join(dirpath, segment)
            if path not in self._entries:
                return
            if rest and not self._is_dir(path):
                return
            self._glob(rest, path, result)
            return

        hidden = segment.startswith(".")
        for name in self._children.get(dirpath, []):
            if name.startswith(".") and not hidden:
                continue
            if not fnmatch.fnmatch(name, segment):
                continue
            path = self._join(dirpath, name)
            if rest and not self._is_dir(path):
                continue
            self._glob(rest, path, result)


_workspace_index = None
_workspace_index_lock = threading.Lock()


def get_workspace_index():
    """
    Returns an up-to-date index of the workspace.

    The index is refreshed with fstree the first time this function is
    called in a process and is then reused. Files ignored by .joltignore,
    files in the build and cache directories and files in directories
    added with :func:`add_ignored_path` are not indexed.
    """
    global _workspace_index
    with _workspace_index_lock:
        if _workspace_index is None:
            _workspace_index = _refresh_workspace_index()
        return _workspace_index


def invalidate_workspace_index(path=None):
    """
    Discards the index of the workspace so that it is refreshed again
    when next requested.

    Call this after files in the workspace have been changed, for
    example by cloning a repository. If a path is given, the index is
    only discarded if the path is indexed.
    """
    global _workspace_index
    with _workspace_index_lock:
        if path is not None and _workspace_index is not None:
            if _workspace_index.relpath(path) is None:
                return
            if any(fs.is_relative_to(path, excluded) for excluded in _workspace_index.excluded):
                return
        _workspace_index = None


_ignored_paths = []


def add_ignored_path(path):
    """
    Exclude a directory from the workspace index.

    Args:
        path (str or callable): Absolute path of the directory, or a
            function returning the path when the index is refreshed.
    """
    _ignored_paths.append(path)


def _excluded_paths(loader):
    """ Directories that are never indexed. """
    paths = [loader.build_path, config.get_cachedir()]
    paths += [path() if callable(path) else path for path in _ignored_paths]
    return [os.path.normpath(path) for path in paths]


def _ignore_patterns(root, paths):
    patterns = []
    joltignore = os.path.join(root, ".joltignore")
    if os.path.exists(joltignore):
        with open(joltignore) as f:
            patterns = f.read().splitlines()
    for path in paths:
        relpath = os.path.relpath(path, root)
        if relpath != os.curdir and not relpath.startswith(os.pardir):
            patterns.append("/" + relpath.replace(os.sep, "/") + "/")
    return "\n".join(patterns) + "\n"


@contextmanager
def workspace_index_files():
    """
    Locks the index of the workspace and yields the paths of the index
    file and the ignore file to pass to fstree.

    The ignore file contains the patterns of .joltignore, the build and
    cache directories and directories added with :func:`add_ignored_path`.
    """
    from jolt.loader import JoltLoader

    loader = JoltLoader.get()
    root = loader.workspace_path
    raise_error_if(not root, "No workspace present")

    cachedir = config.get_cachedir()
    roothash = utils.hashstring(root)
    indexdir = os.path.join(cachedir, "indexes", roothash[:2])
    indexfile = os.path.join(indexdir, roothash[2:])
    ignorefile = indexfile + ".ignore"
    fs.makedirs(indexdir)

    ignores = _ignore_patterns(root, _excluded_paths(loader))

    with fasteners.InterProcessLock(indexfile + ".lock"):
        try:
            with open(ignorefile) as f:
                stale = f.read() != ignores
        except FileNotFoundError:
            stale = True
        if stale:
            with open(ignorefile, "w") as f:
                f.write(ignores)

        yield indexfile, ignorefile


def _refresh_workspace_index():
    from jolt.loader import JoltLoader

    loader = JoltLoader.get()
    root = loader.workspace_path

    executable = find_executable()
    raise_error_if(not executable, "fstree executable not found, it is required to calculate file influence")

    t = tools.Tools()
    cachedir = config.get_cachedir()

    jobserver_path = os.getenv("JOLT_JOBSERVER_PATH")
    jobserver_args = ["--jobserver-path", jobserver_path] if jobserver_path else []

    with workspace_index_files() as (indexfile, ignorefile):
        process = None
        try:
            with log.progress("Indexing workspace", count=None, unit="objects", estimates=False) as progress:
                process = subprocess.Popen(
                    [executable, "write-tree", "--json", "--cache", cachedir, "--ignore", ignorefile,
                     "--index", indexfile, "--threads", str(t.thread_count())] + jobserver_args + [root],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    cwd=root)

                for line in iter(process.stderr.readline, b''):
                    try:
                        event = json.loads(line.decode())
                    except json.JSONDecodeError as exc:
                        log.error("Failed to decode fstree event: {}", line.decode())
                        raise exc

                    if event.get("type") in ["cache::add"]:
                        progress.update(1)

        except Exception as exc:
            if process:
                process.terminate()
            raise exc
        finally:
            if process:
                process.wait()
                process.stderr.close()
                raise_error_if(process.returncode != 0, "Failed to index workspace")

        index = Index.load(root, indexfile)
        index.excluded = _excluded_paths(loader)
        return index
