import atexit
import contextlib
from collections import namedtuple, OrderedDict
from datetime import datetime
import fasteners
import json
import os
import sqlite3
from threading import RLock
import uuid

from jolt import config
from jolt import expires
from jolt import filesystem as fs
from jolt import influence
from jolt import log
from jolt import tools
from jolt import utils
from jolt import tasks
from jolt.options import JoltOptions
from jolt.error import raise_error, raise_error_if
from jolt.error import raise_task_error, raise_task_error_if
from jolt.expires import ArtifactEvictionStrategyRegister


DEFAULT_ARCHIVE_TYPE = ".tar.zst"


def locked(func):
    def _f(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    return _f


class StorageProvider(object):
    def download(self, artifact, force=False):
        return False

    def download_enabled(self):
        return True

    def upload(self, artifact, force=False):
        return False

    def upload_enabled(self):
        return True

    def location(self, artifact):
        return ''  # URL

    def availability(self, artifacts):
        # Ensure artifacts is a list
        artifacts = utils.as_list(artifacts)

        present = set()
        missing = set()

        for artifact in artifacts:
            if self.location(artifact):
                present.add(artifact)
            else:
                missing.add(artifact)

        return list(present), list(missing)


class StorageProviderFactory(StorageProvider):
    def create(self):
        pass


def RegisterStorage(cls):
    ArtifactCache.storage_provider_factories.append(cls)


class ArtifactAttributeSet(object):
    def __init__(self):
        super(ArtifactAttributeSet, self).__setattr__("_attributes", {})

    def _get_attributes(self):
        return self._attributes

    def __getattr__(self, name):
        attributes = self._get_attributes()
        if name not in attributes:
            attributes[name] = self.create(name)
        return attributes[name]

    def __setattr__(self, name, value):
        attributes = self._get_attributes()
        if name not in attributes:
            attributes[name] = self.create(name)
        attributes[name].set_value(value)
        return attributes[name]

    def __dict__(self):
        return {key: str(value) for key, value in self.items()}

    def items(self):
        return self._get_attributes().items()

    def apply(self, task, artifact):
        for _, value in self.items():
            value.apply(task, artifact)

    def apply_deps(self, task, deps):
        pass

    def unapply(self, task, artifact):
        for _, value in self.items():
            value.unapply(task, artifact)

    def unapply_deps(self, task, deps):
        pass

    def visit(self, task, artifact, visitor):
        for _, value in self.items():
            value.visit(task, artifact, visitor)


class ArtifactAttributeSetRegistry(object):
    providers = []

    @staticmethod
    def create_all(artifact):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().create(artifact)

    @staticmethod
    def parse_all(artifact, content):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().parse(artifact, content)

    @staticmethod
    def format_all(artifact, content):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().format(artifact, content)

    @staticmethod
    def apply_all(task, artifact):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().apply(task, artifact)

    @staticmethod
    def apply_all_deps(task, deps):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().apply_deps(task, deps)

    @staticmethod
    def unapply_all(task, artifact):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().unapply(task, artifact)

    @staticmethod
    def unapply_all_deps(task, deps):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().unapply_deps(task, deps)

    @staticmethod
    def visit_all(task, artifact, visitor):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().visit(task, artifact, visitor)


def visit_artifact(task, artifact, visitor):
    ArtifactAttributeSetRegistry.visit_all(task, artifact, visitor)


class ArtifactAttributeSetProvider(object):
    @staticmethod
    def Register(cls):
        ArtifactAttributeSetRegistry.providers.append(cls)

    def create(self, artifact):
        raise NotImplementedError()

    def parse(self, artifact, content):
        raise NotImplementedError()

    def format(self, artifact, content):
        raise NotImplementedError()

    def apply(self, task, artifact):
        pass

    def apply_deps(self, task, deps):
        pass

    def unapply(self, task, artifact):
        pass

    def unapply_deps(self, task, deps):
        pass

    def visit(self, task, artifact, visitor):
        pass


class ArtifactAttribute(object):
    def __init__(self, name):
        self._name = name

    def get_name(self):
        return self._name

    def set_value(self, value, expand=True):
        raise NotImplementedError()

    def get_value(self):
        raise NotImplementedError()

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def __str__(self):
        raise NotImplementedError()


class ArtifactStringAttribute(ArtifactAttribute):
    def __init__(self, artifact, name):
        self._artifact = artifact
        self._name = name
        self._value = None

    def get_name(self):
        return self._name

    def set_value(self, value, expand=True):
        self._value = self._artifact.tools.expand(str(value)) if expand else str(value)

    def get_value(self):
        return self._value

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def __str__(self):
        return str(self._value)


class ArtifactListAttribute(ArtifactAttribute):
    def __init__(self, artifact, name):
        self._artifact = artifact
        self._name = name
        self._value = []

    def __getitem__(self, key):
        return self._value[key]

    def __getslice__(self, i, j):
        return self._value[i:j]

    def get_name(self):
        return self._name

    def set_value(self, value, expand=True):
        if type(value) is str:
            value = value.split(":")
        raise_error_if(type(value) is not list, "Illegal value assigned to artifact list attribute")
        self._value = self._artifact.tools.expand(value) if expand else value

    def get_value(self):
        return self._value

    def append(self, value):
        if type(value) is list:
            self._value.extend(self._artifact.tools.expand(value))
        else:
            self._value.append(self._artifact.tools.expand(value))

    def extend(self, value):
        raise_error_if(
            type(value) is not list,
            "Illegal type passed to {}.extend() - list expected".format(self._name))
        self._value.extend(self._artifact.tools.expand(value))

    def items(self):
        return list(self._value)

    def count(self):
        return len(self.items())

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass


class ArtifactFileAttribute(object):
    def __init__(self):
        self._files = []

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def append(self, src, dst):
        self._files.append((fs.as_posix(src), fs.as_posix(dst)))

    def assign(self, files):
        self._files = files

    def items(self):
        return self._files


@ArtifactAttributeSetProvider.Register
class ArtifactFileAttributeProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "files", ArtifactFileAttribute())

    def parse(self, artifact, content):
        if "files" not in content:
            return
        artifact.files.assign([])
        for record in content["files"]:
            artifact.files.append(record["src"], record["dst"])

    def format(self, artifact, content):
        content["files"] = [{"src": src, "dst": dst} for src, dst in artifact.files.items()]

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def visit(self, task, artifact, visitor):
        pass


def json_serializer(obj):
    if isinstance(obj, datetime):
        return dict(type="datetime", value=obj.strftime("%Y-%m-%d %H:%M:%S.%f"))


def json_deserializer(dct):
    if dct.get("type") == "datetime":
        return datetime.strptime(dct["value"], "%Y-%m-%d %H:%M:%S.%f")
    return dct


class Artifact(object):
    """
    An artifact is a collection of files and metadata produced by a task.

    Task implementors call artifact methods to collect files to be published.
    In addition to files, other metadata can be provided as well, such as
    variables that should be set in the environment of consumer tasks.

    """

    cxxinfo = {}
    """ Artifact C/C++ build metadata.

    A task can add compilation metadata to an artifact. Such metadata
    will be automatically applied when consumer compilation tasks
    are executed. A common use-case is to add preprocessor definitions,
    link libraries, etc. These string fields are supported:

    - ``asflags`` - assembler flags (string)
    - ``cflags`` - compiler flags (string)
    - ``cxxflags`` - compiler flags (string)
    - ``ldflags`` - linker flags (string)
    - ``libraries`` - libraries to link with (list, use append())
    - ``macros`` - preprocessor macros to set (list, use append())
    - ``sources`` - source files to compile (list, use append())

    Values appended to PATH-type metadata fields are relative to the artifact
    root. They will be automatically expanded to absolute paths. These
    PATH-type fields are supported:

    - ``incpaths`` - preprocessor include paths (list, use append())
    - ``libpaths`` - linker library search paths (list, use append())

    Example:

        .. code-block:: python

            def publish(self, artifact, tools):
                artifact.collect("*.h", "include/")
                artifact.cxxinfo.incpaths.append("include")
                artifact.cxxinfo.macros.append("PACKAGE_VERSION=1.0")
    """

    environ = {}
    """ Artifact environment variables.

    A task can add environment variables to an artifact. Such a
    variable will automatically be set in the environment when
    consumer tasks are executed. A common use-case is to add
    programs to the PATH.

    Values appended to PATH variables are relative to the artifact
    root. They will be automatically expanded to absolute paths.
    This applies to all variables with ``PATH`` in the name.

    Example:

        .. code-block:: python

            def publish(self, artifact, tools):
                artifact.environ.PATH.append("bin")
                artifact.environ.JAVA_HOME = artifact.final_path
    """

    paths = {}
    """ Artifact paths.

    A task can add paths to files and directories inside an artifact.
    Paths are relative to the root of the artifact when created, but
    are expanded to absolute paths when the artifact is consumed by
    a task.

    This is useful as an abstraction when directories or filenames
    have varying names.

    Example:

        .. code-block:: python

            def publish(self, artifact, tools):
                artifact.paths.file = "{date}.txt"

    The ``file`` path is then expanded to a full path for consumers:

        .. code-block:: python

            requires = ["dep"]

            def run(self, deps, tools):
                filedata = tools.read_file(deps["dep"].paths.file)

    """

    python = {}
    """ Artifact Python configuration.

    A task can add Python configuration to an artifact. Such configuration
    will automatically be set in the environment when consumer tasks are
    executed. A common use-case is to add Python modules to the PATH so that
    they can be easily imported by a consumer.

    Values appended to PATH-type variables are relative to the artifact
    root. They will be automatically expanded to absolute paths.

    Example:

        .. code-block:: python

            def publish(self, artifact, tools):
                artifact.python.PATH.append("my_module")
    """

    strings = {}
    """ Artifact strings.

    A task can add arbitrary string values to an artifact. Such a
    string will be available for consumer tasks to read.

    Example:

        .. code-block:: python

            def publish(self, artifact, tools):
                artifact.strings.version = "1.2"
    """

    def __init__(self, cache, node, name=None, identity=None, tools=None, session=False):
        self._cache = cache
        if identity:
            self._identity = identity
        else:
            self._identity = node.identity if not session else node.instance
        if name:
            self._identity = name + "@" + self._identity
        self._main = name == "main"
        self._name = name or "main"
        self._full_name = f"{self._name}@{node.short_qualified_name}" if node else self._name
        self._log_name = f"{self._full_name} {node.identity[:8]}" if node else self._full_name
        self._node = node
        self._session = session
        self._task = node.task if node else None
        self._tools = tools or self._node.tools
        self._path = cache._fs_get_artifact_path(self._identity, node.canonical_name if node else name)
        self._temp = cache._fs_get_artifact_tmppath(self._identity, node.canonical_name if node else name)
        self._archive = cache._fs_get_artifact_archivepath(self._identity, node.canonical_name if node else name)
        self._lock_path = cache._fs_get_artifact_lockpath(self._identity)
        ArtifactAttributeSetRegistry.create_all(self)
        self.reload()

    def _info(self, fmt, *args, **kwargs):
        log.info(fmt + f" ({self._log_name})", *args, **kwargs)

    def _debug(self, fmt, *args, **kwargs):
        log.debug(fmt + f" ({self._log_name})", *args, **kwargs)

    def _warning(self, fmt, *args, **kwargs):
        log.warning(fmt + f" ({self._log_name})", *args, **kwargs)

    def _error(self, fmt, *args, **kwargs):
        log.error(fmt + f" ({self._log_name})", *args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        pass

    def __getattr__(self, name):
        raise_task_error(self._node, "Attempt to access invalid artifact attribute '{0}'", name)

    def _write_manifest(self, temporary=False):
        content = {}
        content["size"] = self._get_size()
        content["unpacked"] = self._unpacked
        content["uploadable"] = self._uploadable
        if self._node:
            content["task"] = self._node.name
            content["identity"] = self._node.identity
            content["requires"] = self._node.task.requires
            content["parameters"] = self._node.task._get_parameters()

        if self._influence is not None:
            content["influence"] = self._influence
        elif self._node:
            content["influence"] = influence.HashInfluenceRegistry.get().get_strings(self._node.task)
        else:
            content["influence"] = []
        content["created"] = self._created
        content["modified"] = datetime.now()
        content["expires"] = self._expires.value
        self._created = content.get("created", datetime.now())
        self._modified = content.get("modified", datetime.now())

        ArtifactAttributeSetRegistry.format_all(self, content)

        if temporary:
            manifest = fs.path.join(self.temporary_path, ".manifest.json")
        else:
            manifest = fs.path.join(self.final_path, ".manifest.json")
        with open(manifest, "wb") as f:
            f.write(json.dumps(content, indent=2, default=json_serializer).encode())

    def _read_manifest(self, temporary=False):
        try:
            if temporary:
                manifest_path = fs.path.join(self.temporary_path, ".manifest.json")
            else:
                manifest_path = fs.path.join(self.final_path, ".manifest.json")
            with open(manifest_path) as manifest_file:
                content = json.load(manifest_file, object_hook=json_deserializer)
            self._valid = True
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            self._valid = False
            return
        self._size = content["size"]
        self._unpacked = content["unpacked"]
        self._uploadable = content.get("uploadable", True)
        self._created = content.get("created", datetime.now())
        self._modified = content.get("modified", datetime.now())
        self._influence = content.get("influence", [])
        self._expires = ArtifactEvictionStrategyRegister.get().find(
            content.get("expires", "immediately"))
        ArtifactAttributeSetRegistry.parse_all(self, content)
        return content

    def _get_size(self):
        counted_inodes = {}
        size = 0
        for path, dirs, files in os.walk(self.path):
            for file in files:
                fp = os.path.join(path, file)
                try:
                    stat = os.lstat(fp)
                except OSError:
                    continue

                try:
                    counted_inodes[stat.st_ino]
                except KeyError:
                    counted_inodes[stat.st_ino] = True
                else:
                    continue

                size += stat.st_size

            for dir in dirs:
                fp = os.path.join(path, dir)
                try:
                    stat = os.lstat(fp)
                except OSError:
                    continue

                size += stat.st_size

        self._size = size
        return size

    def apply(self):
        pass

    def unapply(self):
        pass

    def is_main(self):
        return self._main

    def is_session(self):
        return self._session

    def is_valid(self):
        return self._valid

    def reload(self):
        self._unpacked = False
        self._uploadable = True
        self._created = datetime.now()
        self._modified = datetime.now()
        self._expires = self._task.expires if not self._session else expires.Immediately()
        self._size = 0
        self._influence = None
        self._valid = False
        self._temporary = False
        self._read_manifest()
        self._temporary = not self._valid

    def reset(self):
        self._unpacked = False
        self._uploadable = True
        self._created = datetime.now()
        self._modified = datetime.now()
        self._expires = self._task.expires if not self._session else expires.Immediately()
        self._size = 0
        self._influence = None
        self._valid = False
        self._temporary = True

    @property
    def name(self):
        """ str: The name of the artifact. Default: 'main'. """
        return self._name

    @property
    def path(self):
        """ str: The current location of the artifact in the local cache. """
        return self._temp if self._temporary else self._path

    @property
    def final_path(self):
        """ str: The final location of the artifact in the local cache. """
        return self._path

    @property
    def stable_path(self):
        """ Deprecated. Use final_path. """
        return self._path

    @property
    def temporary_path(self):
        return self._temp

    @property
    def tools(self):
        return self._tools

    def collect(self, files, dest=None, flatten=False, symlinks=False, cwd=None):
        """ Collect files to be included in the artifact.

        Args:
            files (str): A filename pattern matching the files to be included
                in the artifact. The pattern may contain simple shell-style
                wildcards such as '*' and '?'. Note: files starting with a
                dot are not matched by these wildcards.
            dest (str, optional): Destination path within the artifact. If
                the string ends with a path separator a new directory will
                be created and all matched source files will be copied into
                the new directory. A destination without trailing path
                separator can be used to rename single files, one at a time.
            flatten (boolean, optional): If True, the directory tree structure
                of matched source files will flattened, i.e. all files will
                be copied into the root of the destination path. The default
                is False, which retains the directory tree structure
                relative to the current working directory.
            symlinks (boolean, optional): If True, symlinks are copied.
                The default is False, i.e. the symlink target is copied.
            cwd (str, optional): Change current working directory before
                starting collection.

        """
        if cwd:
            with self.tools.cwd(cwd):
                return self.collect(files, dest, flatten, symlinks)

        raise_task_error_if(
            not self.is_temporary(),
            self._node,
            "Can't collect files into an already published task artifact ({})", self._log_name)

        files = self.tools.expand_path(files)
        files = self.tools.glob(files)
        dest = self.tools.expand_relpath(dest, self.tools.getcwd()) if dest is not None else ""

        # Special case for renaming files
        safe_dest = dest or fs.sep
        if len(files) == 1 and safe_dest[-1] != fs.sep and safe_dest[-1] != '.':
            src = files[0]
            self.files.append(self.tools.expand_relpath(src), dest)
            self.tools.copy(src, fs.path.join(self._temp, dest), symlinks=symlinks)
            log.verbose("Collected {0} -> {2}/{1}", src, dest, self._temp)
            return [dest]

        # Expand directories into full file list if flatting a tree
        # Determine relative artifact destination paths
        if flatten:
            files = [q
                     for f in files
                     for q in ([p for p in fs.scandir(fs.path.join(self.tools.getcwd(), f))]
                               if fs.path.isdir(fs.path.join(self.tools.getcwd(), f)) else [f])]
            reldestfiles = [fs.path.join(dest, fs.path.basename(f)) for f in files]
        else:
            reldestfiles = [fs.path.join(dest, self.tools.expand_relpath(f, self.tools.getcwd()))
                            for f in files]

        # General case
        for srcpath, reldstpath in zip(files, reldestfiles):
            relsrcpath = self.tools.expand_relpath(srcpath, self.tools.getcwd())
            dstpath = fs.path.join(self._temp, reldstpath)

            if symlinks or fs.path.exists(srcpath):
                self.files.append(self.tools.expand_relpath(srcpath), reldstpath)
                self.tools.copy(srcpath, dstpath, symlinks=symlinks)
                log.verbose("Collected {0} -> {1}", relsrcpath, reldstpath)

        return reldestfiles

    def copy(self, files, dest, flatten=False, symlinks=False, cwd=None):
        """ Copy files from the artifact.

        Args:
            files (str): A filename pattern matching the files to be copied
                from the artifact. The filepath is relative to the artifact
                root and may contain simple shell-style wildcards such as
                '*' and '?'. Note: files starting with a dot are not matched
                by these wildcards.
            dest (str, optional): Destination path, relative to the current
                working directory. If the string ends with a path separator
                a new directory will be created and all matched source files
                will be copied into the new directory. A destination without
                trailing path separator can be used to rename single files,
                one at a time.
            flatten (boolean, optional): If True, the directory tree structure
                of matched source files will flattened, i.e. all files will
                be copied into the root of the destination path. The default
                is False, which retains the directory tree structure.
            symlinks (boolean, optional): If True, symlinks are copied.
                The default is False, i.e. the symlink target is copied.
            cwd (str, optional): Change destination working directory before
                starting copy.

        """
        if cwd:
            with self.tools.cwd(cwd):
                return self.copy(files, dest, flatten, symlinks)

        raise_task_error_if(
            self.is_temporary(),
            self._node,
            "Can't copy files from an unpublished task artifact ({})", self._log_name)

        files = fs.path.join(self._path, files)
        files = self.tools.expand_path(files)
        files = self.tools.glob(files)
        dest = self.tools.expand_relpath(dest, self.tools.getcwd()) if dest is not None else ""

        # Special case for renaming files
        safe_dest = dest or fs.sep
        if len(files) == 1 and safe_dest[-1] != fs.sep and safe_dest[-1] != '.':
            src = files[0]
            self.tools.copy(src, dest, symlinks=symlinks)
            log.verbose("Copied {0} -> {1}",
                        self.tools.expand_relpath(src, self._path), dest)
            return

        # Expand directories into full file list if flatting a tree
        # Determine relative artifact destination paths
        if flatten:
            files = [q
                     for f in files
                     for q in ([p for p in fs.scandir(f)] if fs.path.isdir(f) else [f])]
            reldestfiles = [fs.path.join(dest, fs.path.basename(f)) for f in files]
        else:
            reldestfiles = [fs.path.join(dest, self.tools.expand_relpath(f, self._path))
                            for f in files]

        # General case
        for srcpath, reldstpath in zip(files, reldestfiles):
            relsrcpath = self.tools.expand_relpath(srcpath, self._path)
            dstpath = fs.path.join(self.tools.getcwd(), reldstpath)

            if symlinks or fs.path.exists(srcpath):
                self.tools.copy(srcpath, dstpath, symlinks=symlinks)
                log.verbose("Copied {0} -> {1}", relsrcpath, reldstpath)

    def _set_uploadable(self, uploadable):
        self._uploadable = uploadable

    def _set_unpacked(self, unpacked=True):
        self._unpacked = unpacked

    def get_archive(self):
        return self._archive if fs.path.exists(self._archive) else None

    def get_archive_path(self):
        return self._archive

    def get_lock_path(self):
        return self._lock_path

    def get_temporary_path(self):
        return self._temp

    def get_size(self):
        return self._size

    def get_cache(self):
        return self._cache

    def get_task(self):
        return self._node.task

    def get_node(self):
        return self._node

    def is_temporary(self) -> bool:
        return self._temporary

    def is_unpackable(self) -> bool:
        if not self._node:
            return True
        if self.name == "main":
            return self._task.unpack.__func__ is not tasks.Task.unpack
        return getattr(self._task, "unpack_" + self.name, tasks.Task.unpack) is not tasks.Task.unpack

    def is_unpacked(self):
        return self._unpacked

    def is_uploadable(self):
        return self._uploadable

    def is_cacheable(self):
        if not self._node:
            return True
        if self.is_session():
            return True
        return self.task.is_cacheable()

    @property
    def identity(self):
        return self._identity

    @property
    def task(self):
        if not self._node:
            Task = namedtuple('Point', ['name'])
            return Task(name=self.name)
        return self._node.task


class Context(object):
    """
    Execution context and dependency wrapper.

    A ``Context`` gathers dependencies and initializes the environment
    for an executing task. It is passed as an argument to the
    Task's :func:`~jolt.Task.run` method.

    A task implementor can use the context as a dictionary of dependencies where
    the key is the name of a dependency and the value is the dependency's
    :class:`~jolt.Artifact`.

    """

    def __init__(self, cache, node):
        self._cache = cache
        self._node = node
        self._artifacts = OrderedDict()
        self._artifacts_index = OrderedDict()

    def __enter__(self):
        try:
            for dep in reversed(self._node.children):
                for artifact in dep.artifacts:
                    # Create clone with tools from this task
                    artifact = self._cache.get_artifact(
                        dep,
                        name=artifact.name,
                        session=artifact.is_session(),
                        tools=self._node.tools,
                    )

                    # Don't include session artifacts that don't exist,
                    # i.e. where no build has taken place due to presence
                    # of the persistent artifacts.
                    if artifact.is_session() and not self._cache.is_available_locally(artifact):
                        continue

                    self._cache.unpack(artifact)

                    if artifact.name == "main":
                        self._artifacts_index[dep.qualified_name] = artifact
                        self._artifacts_index[dep.short_qualified_name] = artifact
                    self._artifacts[artifact.name + "@" + dep.qualified_name] = artifact
                    self._artifacts_index[artifact.name + "@" + dep.qualified_name] = artifact
                    self._artifacts_index[artifact.name + "@" + dep.short_qualified_name] = artifact
                    artifact.apply()
                    ArtifactAttributeSetRegistry.apply_all(self._node.task, artifact)
            ArtifactAttributeSetRegistry.apply_all_deps(self._node.task, self)
        except (Exception, KeyboardInterrupt) as e:
            # Rollback all attributes/resources except the last failing one
            ArtifactAttributeSetRegistry.unapply_all_deps(self._node.task, self)
            for name, artifact in reversed(list(self._artifacts.items())[:-1]):
                with utils.ignore_exception():
                    ArtifactAttributeSetRegistry.unapply_all(self._node.task, artifact)
                    artifact.unapply()
            raise e
        return self

    def __exit__(self, type, value, tb):
        ArtifactAttributeSetRegistry.unapply_all_deps(self._node.task, self)
        for name, artifact in reversed(self._artifacts.items()):
            ArtifactAttributeSetRegistry.unapply_all(self._node.task, artifact)
            artifact.unapply()

    def __getitem__(self, key):
        """ Get artifact for a task listed as a requirement.

        Args:
            key (str): Name of the task listed as a requirement.

        Returns:
            The :class:`~jolt.Artifact` associated with the task.

        Example:
            .. code-block:: python

                requires = "dependency"

                def run(self, deps, tools):
                    dependency_artifact = deps["dependency"]

        """

        key = self._node.tools.expand(key)

        alias, artifact, task, params = utils.parse_aliased_task_name(key)
        raise_task_error_if(alias, self._node, "Cannot define alias when indexing dependencies: {}", alias)
        task_name = utils.format_task_name(task, params)
        task_artifact_name = utils.format_task_name(task, params, artifact)

        if task_name not in self._artifacts_index and \
           task_artifact_name not in self._artifacts_index and not params:
            key = self._node.resolve_requirement_alias(task_name)
            if key:
                _, _, task, params = utils.parse_aliased_task_name(key)
                task_name = utils.format_task_name(task, params)
                task_artifact_name = utils.format_task_name(task, params, artifact)

        # Parameters may be overspecified, resolve task
        if task_artifact_name not in self._artifacts_index:
            from jolt.tasks import TaskRegistry
            task_obj = TaskRegistry.get().get_task(task_name)
            task_name = task_obj.short_qualified_name if task_obj is not None else task
            task_artifact_name = task_name if not artifact else f"{artifact}@{task_name}"

        if task_artifact_name not in self._artifacts_index:
            raise KeyError("No such artifact dependency '{0}' ({1})".format(
                task_artifact_name, self._node.short_qualified_name))
        return self._artifacts_index[task_artifact_name]

    def items(self):
        """ List all requirements and their artifacts.

        Returns:
            Requirement dictionary items. Each item is a tuple with the
            requirement name and the artifact.
        """
        return reversed(self._artifacts.items())


class PidProvider(object):
    def __call__(self):
        pid = str(uuid.uuid4())
        log.debug("New cache lock file: {0}", pid)
        return pid


@utils.Singleton
class ArtifactCache(StorageProvider):
    """
    Manages the local artifact cache and exchanges artifacts with
    external caches using configured storage provider plugins.

    Artifacts are directories containing files published by tasks.
    They are normally stored uncompressed in the filesystem for
    fast access during builds. They are exchanged with external
    caches as gzip compressed tarballs.

    Unused artifacts can be evicted when new artifacts are committed
    to the cache if the configured cache size is exceeded. Selection
    follows LRU order, but deviations are possible through artifact
    eviction policies. For example, an important large artifact could
    declare that it shouldn't be evicted unless unused for two weeks.
    It would then not be considered for eviction until later.

    Artifacts in the cache can be accessed by multiple processes in
    parallel. Critical sections are enforced using a combination of
    file locks and database record keeping.

    Each locally available artifact is recorded in an Sqlite database
    (table: artifacts).

    If an artifact is required during a build, an artifact reference
    is recorded in the database table ``artifact_refs``. This prevents
    the artifact from being evicted while the process is alive. The
    reference is garbage collected by other processes if the owner
    process should terminate abnormally.

    If an artifact is not present in the cache and either has to be
    built or downloaded, the artifact will be interprocess locked,
    i.e. it cannot be built or downloaded by any other process.
    Artifacts are also locked when the Task.unpack() method is run.

    Each process that wishes to lock an artifact records their
    interest in the database table ``artifact_lockrefs``. Actual
    interprocess concurrency is prevented by using a file lock
    in <cache_directory>/locks/<artifact_identity>.lock.
    This lock file is deleted by the last process holding lock reference
    in the database, or when garbage collected.

    Each process also owns a pid lock file in
    <cache_directory>/locks/<pid>.lock. The purpose of this file is
    to allow other processes to detect termination of the owner
    process. If a read lock cannot be obtained on this file then the
    process is still alive. Otherwise, any artifact references created
    by the owner process may be garbage collected.

    A global cache lock is always acquired when creating or deleting
    artifact or process lock files. It's also used when performing
    database transactions for simplicity.
    """

    storage_provider_factories = []

    def __init__(self, options=None, pidprovider=None):
        self._options = options or JoltOptions()
        self._storage_providers = [
            factory.create(self)
            for factory in ArtifactCache.storage_provider_factories]

        # If no storage providers supports the availability method,
        # we will not only use the local presence cache.
        self._remote_presence_cache = set()
        self._presence_cache_only = self.has_availability()

        # Read configuration
        self._max_size = config.getsize(
            "jolt", "cachesize", os.environ.get("JOLT_CACHESIZE", 1 * 1024 ** 3))

        # Create cache directory
        self._fs_create_cachedir()

        # Create global cache lock file
        self._cache_locked = False
        self._lock_file = fasteners.InterProcessLock(self._fs_get_lock_file())
        self._thread_lock = RLock()

        # Create process lock file
        with self._cache_lock():
            self._pid_provider = pidprovider or PidProvider()
            self._pid = self._pid_provider()
            self._pid_file = fasteners.InterProcessLock(self._fs_get_pid_file(self._pid))
            self._pid_file.acquire()

        # Setup database and garbage collect stale refs
        self._db_path = self._fs_get_db_path()
        with self._cache_lock(), self._db() as db:
            self._db_create_tables(db)
            self._db_invalidate_locks(db)
            self._db_invalidate_references(db)
            self._fs_invalidate_pids(db)
            size = self._db_select_sum_artifact_size(db)
            count = self._db_select_artifact_count(db)
            in_use = self._db_select_artifact_count_in_use(db)
            cur_size = utils.as_human_size(size)
            max_size = utils.as_human_size(self._max_size)
            log.verbose("Cache size is {} (max {}, {} artifacts, {} in use)",
                        cur_size, max_size, count, in_use)
        atexit.register(self.close)

    ############################################################################
    # Internal API
    ############################################################################

    def _assert_cache_locked(self):
        assert self._cache_locked, "illegal function call, cache lock is not held"

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self._db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        try:
            db.execute("PRAGMA journal_mode=OFF")
            # db.set_trace_callback(log.warning)
            yield db
        finally:
            db.close()

    def _db_create_tables(self, db):
        cur = db.cursor()

        # All artifacts currently residing in the cache
        cur.execute("CREATE TABLE IF NOT EXISTS artifacts "
                    "(identity text PRIMARY KEY, name text, size integer, last_used timestamp)")

        # All process references to artifacts in the cache. No eviction allowed while rows exist here.
        cur.execute("CREATE TABLE IF NOT EXISTS artifact_refs (identity text, pid text)")

        # All process references to artifict locks.
        # A lock may exist before the artifact, for example during building or downloading.
        # A lock file may be safely deleted if the global cache lock is held and there are
        # no rows present.
        cur.execute("CREATE TABLE IF NOT EXISTS artifact_lockrefs (identity text, pid text)")
        db.commit()

    def _db_insert_artifact(self, db, identity, task_name, size):
        cur = db.cursor()
        cur.execute("INSERT INTO artifacts VALUES (?,?,?,?)", (identity, task_name, size, datetime.now()))
        db.commit()

    def _db_update_artifact_size(self, db, identity, size):
        cur = db.cursor()
        cur.execute("UPDATE artifacts SET size = ? WHERE identity = ?", (size, identity))
        db.commit()

    def _db_delete_artifact(self, db, identity, and_refs=True):
        cur = db.cursor()
        if and_refs:
            cur.execute("DELETE FROM artifact_refs WHERE identity = ?", (identity,))
        cur.execute("DELETE FROM artifacts WHERE identity = ?", (identity,))
        db.commit()

    def _db_insert_reference(self, db, identity):
        cur = db.cursor()
        cur.execute("INSERT INTO artifact_refs VALUES (?,?)", (identity, self._pid))
        cur.execute("UPDATE artifacts SET last_used = ? WHERE identity = ?", (datetime.now(), identity))
        db.commit()

    def _db_delete_reference(self, db, identity):
        cur = db.cursor()
        cur.execute("DELETE FROM artifact_refs WHERE identity = ? AND pid = ?", (identity, self._pid))
        db.commit()

    def _db_select_reference(self, db, identity):
        cur = db.cursor()
        return list(cur.execute("SELECT * FROM artifact_refs WHERE identity = ? AND pid = ?", (identity, self._pid)))

    def _db_insert_lock(self, db, identity):
        cur = db.cursor()
        cur.execute("INSERT INTO artifact_lockrefs VALUES (?,?)", (identity, self._pid))
        db.commit()

    def _db_delete_lock(self, db, identity):
        cur = db.cursor()
        cur.execute("DELETE FROM artifact_lockrefs WHERE identity = ? AND pid = ?", (identity, self._pid))
        db.commit()

    def _db_delete_locks_by_pid(self, db, pid):
        cur = db.cursor()
        cur.execute("DELETE FROM artifact_lockrefs WHERE pid = ?", (pid,))
        db.commit()

    def _db_select_locks(self, db):
        cur = db.cursor()
        return [n[0] for n in cur.execute("SELECT DISTINCT identity FROM artifact_lockrefs")]

    def _db_select_lock_count(self, db, identity):
        cur = db.cursor()
        record = cur.execute("SELECT COUNT(*) FROM artifact_lockrefs WHERE identity = ?",
                             (identity,)).fetchone()
        return record[0]

    def _db_delete_references_by_pid(self, db, pid):
        cur = db.cursor()
        cur.execute("DELETE FROM artifact_refs WHERE pid = ?", (pid,))
        db.commit()

    def _db_select_artifact(self, db, identity):
        cur = db.cursor()
        return list(cur.execute("SELECT * FROM artifacts WHERE identity = ?", (identity,)))

    def _db_select_artifacts(self, db):
        cur = db.cursor()
        return list(cur.execute("SELECT * FROM artifacts"))

    def _db_select_lock_pids(self, db):
        cur = db.cursor()
        return [n[0] for n in cur.execute("SELECT DISTINCT pid FROM artifact_lockrefs")]

    def _db_select_artifact_lock_pids(self, db, identity):
        cur = db.cursor()
        return [n[0] for n in cur.execute("SELECT DISTINCT pid FROM artifact_lockrefs WHERE identity = ?", (identity,))]

    def _db_select_reference_pids(self, db):
        cur = db.cursor()
        return [n[0] for n in cur.execute("SELECT DISTINCT pid FROM artifact_refs")]

    def _db_select_artifact_reference_pids(self, db, identity):
        cur = db.cursor()
        return [n[0] for n in cur.execute("SELECT DISTINCT pid FROM artifact_refs WHERE identity = ?", (identity,))]

    def _db_select_artifact_not_in_use(self, db, identity):
        cur = db.cursor()
        return list(
            cur.execute("SELECT * FROM artifacts WHERE identity = ? AND identity NOT IN "
                        "(SELECT identity FROM artifact_refs) "
                        "ORDER BY last_used", (identity,)))

    def _db_select_artifacts_not_in_use(self, db):
        cur = db.cursor()
        return list(
            cur.execute("SELECT * FROM artifacts WHERE identity NOT IN "
                        "(SELECT identity FROM artifact_refs) "
                        "ORDER BY last_used"))

    def _db_select_sum_artifact_size(self, db):
        cur = db.cursor()
        return list(cur.execute("SELECT SUM(size) FROM artifacts"))[0][0] or 0

    def _db_select_artifact_count(self, db):
        cur = db.cursor()
        return list(cur.execute("SELECT COUNT(identity) FROM artifacts"))[0][0] or 0

    def _db_select_artifact_count_in_use(self, db):
        cur = db.cursor()
        return list(cur.execute("SELECT COUNT(DISTINCT artifact_refs.identity) FROM artifact_refs"))[0][0] or 0

    def _db_invalidate_locks(self, db, try_all=False):
        """ Removes any stale artifact lock references and lock files """
        self._assert_cache_locked()
        locks = self._db_select_locks(db)
        for pid in self._db_select_lock_pids(db):
            if not try_all and pid == self._pid:
                continue
            try:
                # Throws exception if lock is held
                with self._pid_lock(pid):
                    self._db_delete_locks_by_pid(db, pid)
            except KeyboardInterrupt as e:
                raise e
            except Exception:
                pass

        for lock in locks:
            if self._db_select_lock_count(db, lock) == 0:
                fs.unlink(self._fs_get_artifact_lockpath(lock), ignore_errors=True)

    def _db_invalidate_references(self, db, try_all=False):
        """ Removes any stale artifact references """
        self._assert_cache_locked()
        for pid in self._db_select_reference_pids(db):
            if not try_all and pid == self._pid:
                continue
            try:
                # Throws exception if lock is held
                with self._pid_lock(pid):
                    self._db_delete_references_by_pid(db, pid)
            except KeyboardInterrupt as e:
                raise e
            except Exception:
                pass

    def _fs_invalidate_pids(self, db, try_all=False):
        """ Removes any stale pid files """
        self._assert_cache_locked()
        for pid in fs.scandir(fs.path.join(self.root, "pids")):
            if not try_all and fs.path.basename(pid) == self._pid:
                continue
            try:
                # Throws exception if lock is held
                with self._pid_lock(pid):
                    pass
                fs.unlink(pid, ignore_errors=True)
            except KeyboardInterrupt as e:
                raise e
            except Exception:
                pass

    def _fs_create_cachedir(self):
        self.root = config.get_cachedir()
        log.verbose("Jolt cache path: {}", self.root)
        try:
            fs.makedirs(self.root)
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            raise_error("Failed to create cache directory '{0}'", self.root)

    def _fs_get_artifact(self, node, name, tools=None, session=False):
        return Artifact(self, node, name=name, tools=tools, session=session)

    def _fs_commit_artifact(self, artifact: Artifact, uploadable: bool, temporary: bool):
        artifact._set_uploadable(uploadable)
        if not artifact.is_unpackable():
            artifact._set_unpacked()
        if temporary:
            artifact._write_manifest(temporary=True)
            fs.rmtree(artifact.final_path, ignore_errors=True)
            fs.rename(artifact.temporary_path, artifact.final_path)
        else:
            artifact._write_manifest(temporary=False)

    @contextlib.contextmanager
    def _fs_compress_artifact(self, artifact):
        task = artifact.task
        archive = artifact.get_archive_path()

        raise_task_error_if(
            artifact.is_temporary(), task,
            "Can't compress an unpublished task artifact ({})", artifact._log_name)

        try:
            artifact.tools.archive(artifact.path, archive)
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            raise_task_error(task, "Failed to compress task artifact ({})", artifact._log_name)
        try:
            yield
        finally:
            fs.unlink(archive, ignore_errors=True)

    def _fs_decompress_artifact(self, artifact):
        task = artifact.task
        archive = artifact.get_archive_path()
        try:
            task.tools.extract(archive, artifact.temporary_path, ignore_owner=True)
            artifact._read_manifest(temporary=True)
        except KeyboardInterrupt as e:
            fs.rmtree(artifact.temporary_path, ignore_errors=True)
            raise e
        except Exception:
            fs.rmtree(artifact.temporary_path, ignore_errors=True)
            raise_task_error(task, "Failed to extract task artifact archive ({})", artifact._log_name)
        finally:
            fs.unlink(archive, ignore_errors=True)

    def _fs_delete_artifact(self, identity, task_name, onerror=None):
        fs.rmtree(self._fs_get_artifact_path(identity, task_name), ignore_errors=True, onerror=onerror)
        fs.rmtree(self._fs_get_artifact_tmppath(identity, task_name), ignore_errors=True, onerror=onerror)
        fs.rmtree(self._fs_get_artifact_path_legacy(identity, task_name), ignore_errors=True, onerror=onerror)
        fs.rmtree(self._fs_get_artifact_tmppath_legacy(identity, task_name), ignore_errors=True, onerror=onerror)
        fs.unlink(fs.path.join(self.root, task_name), ignore_errors=True)

    def _fs_identity(self, identity):
        parts = identity.split("@", 1)
        if len(parts) <= 1:
            parts = ["main"] + parts
        return parts[1] + "-" + utils.canonical(parts[0])

    def _fs_identity_legacy(self, identity):
        parts = identity.split("@", 1)
        if len(parts) <= 1:
            parts = ["main"] + parts
        return parts[0] + "@" + utils.canonical(parts[1])

    def _fs_get_artifact_archivepath(self, identity, task_name):
        identity = self._fs_identity(identity)
        return fs.path.join(self.root, task_name, identity) + DEFAULT_ARCHIVE_TYPE

    def _fs_get_artifact_lockpath(self, identity):
        identity = self._fs_identity(identity)
        return fs.path.join(self.root, "locks", identity + ".lock")

    def _fs_get_artifact_tmppath(self, identity, task_name):
        identity = self._fs_identity(identity)
        return fs.path.join(self.root, task_name, "." + identity)

    def _fs_get_artifact_path(self, identity, task_name):
        identity = self._fs_identity(identity)
        return fs.path.join(self.root, task_name, identity)

    def _fs_get_artifact_tmppath_legacy(self, identity, task_name):
        identity = self._fs_identity_legacy(identity)
        return fs.path.join(self.root, task_name, "." + identity)

    def _fs_get_artifact_path_legacy(self, identity, task_name):
        identity = self._fs_identity_legacy(identity)
        return fs.path.join(self.root, task_name, identity)

    def _fs_get_artifact_manifest_path(self, identity, task_name):
        return fs.path.join(self._fs_get_artifact_path(identity, task_name), ".manifest.json")

    def _fs_get_artifact_manifest(self, identity, task_name):
        path = self._fs_get_artifact_manifest_path(identity, task_name)
        with open(path) as manifest_file:
            return json.load(manifest_file, object_hook=json_deserializer)

    def _fs_get_db_path(self):
        return fs.path.join(self.root, "cache.db")

    def _fs_get_lock_file(self):
        return fs.path.join(self.root, "lock")

    def _fs_get_pid_file(self, pid):
        return fs.path.join(self.root, "pids", pid)

    def _fs_is_artifact_expired(self, identity, task_name, last_used):
        try:
            manifest = self._fs_get_artifact_manifest(identity, task_name)
            manifest["used"] = last_used
            strategy = ArtifactEvictionStrategyRegister.get().find(
                manifest.get("expires", "immediately"))
            return strategy.is_evictable(manifest)
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            return True

    def close(self):
        with self._cache_lock(), self._db() as db:
            self._db_invalidate_locks(db, try_all=True)
            self._db_invalidate_references(db, try_all=True)
            self._fs_invalidate_pids(db, try_all=True)

    @contextlib.contextmanager
    def _cache_lock(self):
        with self._thread_lock:
            self._lock_file.acquire()
            self._cache_locked = True
            try:
                yield
            finally:
                self._cache_locked = False
                self._lock_file.release()

    @contextlib.contextmanager
    def _pid_lock(self, pid, wait=False, timeout=None):
        """
        Process specific lock.

        Indicator of process liveness. Throws exception if process is alive.
        """
        if not wait:
            self._assert_cache_locked()
        with self._thread_lock:
            lock_file = self._fs_get_pid_file(pid)
            lock = fasteners.InterProcessLock(lock_file)
            if not lock.acquire(blocking=wait, timeout=timeout):
                raise RuntimeError()
            try:
                yield
            finally:
                lock.release()

    def _discard(self, db, artifacts, if_expired, onerror=None):
        """ Discard list of artifacts. Cache lock must be held. """
        self._assert_cache_locked()
        evicted = 0
        for identity, task_name, _, used in artifacts:
            if not if_expired or self._fs_is_artifact_expired(identity, task_name, used):
                with utils.delayed_interrupt():
                    self._db_delete_artifact(db, identity)
                    self._fs_delete_artifact(identity, task_name, onerror=onerror)
                    evicted += 1
                    log.debug("Evicted {}: {}", identity, task_name)
        return evicted == len(artifacts)

    ############################################################################
    # Public API
    ############################################################################

    def release(self):
        """
        Release references to artifacts held by the current process.

        Effectively, a new pid lock file is created and the old one is deleted. This
        allows other processes to detect termination of the current process and
        garbage collect any references owned by the process.
        """
        with self._cache_lock(), self._db() as db:
            self._db_invalidate_locks(db, try_all=True)
            self._db_invalidate_references(db, try_all=True)
            self._fs_invalidate_pids(db, try_all=True)
            self._pid_file.release()

            self._pid = self._pid_provider()
            self._pid_file = fasteners.InterProcessLock(self._fs_get_pid_file(self._pid))
            self._pid_file.acquire()

    @utils.delay_interrupt
    def is_available_locally(self, artifact):
        """
        Check presence of task artifact in cache.

        If the artifact is present, an artifact reference is automatically
        recorded for the running process to prevent eviction by other
        processes.
        """
        if not artifact.is_cacheable():
            return False

        with self._cache_lock(), self._db() as db:
            if self._db_select_artifact(db, artifact.identity) or self._db_select_reference(db, artifact.identity):
                artifact.reload()
                if artifact.is_temporary():
                    self._db_delete_artifact(db, artifact.identity, and_refs=False)
                    return False
                self._db_insert_reference(db, artifact.identity)
                return True
        return False

    def is_available_remotely(self, artifact, cache=True):
        """
        Check presence of task artifact in external remote caches.
        """
        if cache:
            if artifact.identity in self._remote_presence_cache:
                return True
            if self._presence_cache_only:
                return False
        for provider in self._storage_providers:
            present, _ = provider.availability([artifact])
            if present:
                self._remote_presence_cache.add(artifact.identity)
                return True
        return False

    def is_available(self, artifact):
        """ Check presence of task artifact in any cache, local or remote """
        return self.is_available_locally(artifact) or self.is_available_remotely(artifact)

    def has_availability(self):
        # Returns true if all storage providers implement the availability method
        return all([provider.availability.__func__ != StorageProvider.availability for provider in self._storage_providers])

    def availability(self, artifacts, remote=True):
        """ Check presence of task artifacts in any cache, local or remote """
        present = set()
        missing = set()

        # Make sure artifacts is a list
        artifacts = utils.as_list(artifacts)

        # Check presence of all artifacts in the local cache
        for artifact in artifacts:
            if self.is_available_locally(artifact):
                present.add(artifact)
            else:
                missing.add(artifact)

        if not remote:
            return list(present), list(missing)

        # Check presence of all artifacts in the remote caches
        missing_remotely = artifacts

        for provider in self._storage_providers:
            present_in_provider, missing_in_provider = provider.availability(missing_remotely)
            for artifact in present_in_provider:
                self._remote_presence_cache.add(artifact.identity)
            present.update(present_in_provider)
            missing_remotely = missing_in_provider
            if not missing_in_provider:
                break

        missing.update(missing_remotely)
        missing = missing - present

        return list(present), list(missing)

    def download_enabled(self):
        return self._options.download and \
            any([provider.download_enabled() for provider in self._storage_providers])

    def download_session_enabled(self):
        return self._options.download_session and \
            any([provider.download_enabled() for provider in self._storage_providers])

    def upload_enabled(self):
        return self._options.upload and \
            any([provider.upload_enabled() for provider in self._storage_providers])

    def download(self, artifact, force=False):
        """
        Downloads an artifact from a remote cache to the local cache.

        The artifact is interprocess locked during the operation.
        """
        if not force:
            if not artifact.is_session() and not self.download_enabled():
                return False
            if artifact.is_session() and not self.download_session_enabled():
                return False
        if not artifact.is_cacheable():
            return False
        with self.lock_artifact(artifact, why="download") as artifact:
            if self.is_available_locally(artifact):
                artifact._info("Download skipped, already in local cache")
                return True
            for provider in self._storage_providers:
                if provider.download(artifact, force):
                    self._fs_decompress_artifact(artifact)
                    self.commit(artifact, temporary=True)
                    return True
        return len(self._storage_providers) == 0

    def upload(self, artifact, force=False, locked=True):
        """
        Uploads an artifact from the local cache to all configured remote caches.

        The artifact is interprocess locked during the operation.
        """
        if not force and not self.upload_enabled():
            return False
        if not artifact.is_cacheable():
            return True
        raise_task_error_if(
            not self.is_available_locally(artifact), artifact.task,
            "Can't upload task artifact, no artifact present in the local cache ({})", artifact._log_name)
        with self.lock_artifact(artifact, why="upload") if locked else artifact as artifact:
            raise_task_error_if(
                not artifact.is_uploadable(), artifact.task,
                "Artifact was modified locally by another process and can no longer be uploaded, try again ({})", artifact._log_name)
            if self._storage_providers:
                with self._fs_compress_artifact(artifact):
                    return all([provider.upload(artifact, force) for provider in self._storage_providers])
        return len(self._storage_providers) == 0

    def location(self, artifact):
        for provider in self._storage_providers:
            url = provider.location(artifact)
            if url:
                return url
        return ''

    def unpack(self, artifact):
        """
        Unpacks/relocates the task artifact to the local cache.

        A temporary backup of the artifact is first created in the
        filesystem. The task's unpack() method is then executed with
        original artifact path as argument (to allow relocation to
        the final artifact path). If unpack() succeeds, the temporary
        backup is discarded. Otherwise the backup is restored.

        The artifact is interprocess locked during the operation.
        """
        if not artifact.is_unpackable():
            return True
        with self._thread_lock, self.lock_artifact(artifact, why="unpack") as artifact:
            raise_task_error_if(
                not self.is_available_locally(artifact),
                artifact.task,
                "Locked artifact is missing in cache (forcibly removed?) ({})", artifact._log_name)

            raise_task_error_if(
                artifact.is_temporary(),
                artifact.task,
                "Can't unpack an unpublished task artifact ({})", artifact._log_name)

            if artifact.is_unpacked():
                return True

            # Keep a temporary copy of the artifact if the task
            # unpack() method fails. The copy is removed in
            # get_locked_artifact() if left unused.
            fs.copy(artifact.final_path, artifact.temporary_path, symlinks=True)

            task = artifact.task
            with tools.Tools(task) as t:
                try:
                    # Note: unpack() will run on the original
                    # artifact, not in the temporary copy.
                    if task.unpack.__func__ is not tasks.Task.unpack:
                        artifact._info("Unpack started")
                    artifact._set_unpacked()
                    if artifact.name == "main":
                        task.unpack(artifact, t)
                    else:
                        unpack = getattr(task, "unpack_" + artifact.name, None)
                        raise_task_error_if(
                            unpack is None, task,
                            "Artifact unpack method not found: unpack_{}", artifact.name)
                        unpack(artifact, t)

                    self.commit(artifact, uploadable=False, temporary=False)

                except NotImplementedError:
                    self.commit(artifact, temporary=False)

                except (Exception, KeyboardInterrupt) as e:
                    # Restore the temporary copy
                    fs.rmtree(artifact.final_path, ignore_errors=True)
                    fs.rename(artifact.temporary_path, artifact.final_path)
                    artifact._error("Unpack failed")
                    raise e
        return True

    @utils.delay_interrupt
    def commit(self, artifact, uploadable=True, temporary=True):
        """
        Commits a task artifact to the cache.

        Committing includes renaming the artifact in the filesystem,
        adding an artifact database record as well as a process reference
        record.

        Once the artifact is committed, eviction of other artifacts will
        take place if the resulting cache size exceeds the configured
        limit.
        """
        if not artifact.is_cacheable():
            return

        with self._cache_lock(), self._db() as db:
            self._fs_commit_artifact(artifact, uploadable, temporary)
            with utils.ignore_exception():  # Possibly already exists in DB, e.g. unpacked
                self._db_insert_artifact(db, artifact.identity, artifact.task.canonical_name, artifact.get_size())
            self._db_update_artifact_size(db, artifact.identity, artifact.get_size())
            self._db_insert_reference(db, artifact.identity)
            artifact.reload()

            evict_size = self._db_select_sum_artifact_size(db) - self._max_size
            if evict_size < 0:
                return

            unused = self._db_select_artifacts_not_in_use(db)
            while evict_size > 0 and unused:
                candidate, unused = unused[0], unused[1:]
                if self._discard(db, [candidate], True):
                    evict_size -= candidate[2]

    @utils.delay_interrupt
    def discard(self, artifact, if_expired=False, onerror=None):
        with self._cache_lock(), self._db() as db:
            self._db_invalidate_locks(db)
            self._db_invalidate_references(db)
            self._fs_invalidate_pids(db)
            return self._discard(
                db,
                self._db_select_artifact_not_in_use(db, artifact.identity),
                if_expired,
                onerror=onerror)

    def _discard_wait(self, artifact):
        """
        Discards an artifact without expiration consideration.

        The artifact must be locked prior to calling this function.

        If the artifact is in use, the function waits for all references to be dropped.
        The artifact is also unregistered from the database to prevent new references,
        but it remains available in the filesystem.
        """
        with self._cache_lock(), self._db() as db:
            self._db_invalidate_locks(db)
            self._db_invalidate_references(db)
            self._fs_invalidate_pids(db)
            artifacts = self._db_select_artifact(db, artifact.identity)
            self._db_delete_artifact(db, artifact.identity, and_refs=False)
            refpids = self._db_select_artifact_reference_pids(db, artifact.identity)
            refpids = list(filter(lambda pid: pid != self._pid, refpids))
            lockpids = self._db_select_artifact_lock_pids(db, artifact.identity)

        if len(refpids) > 0:
            artifact._info("Artifact is temporarily in use, forced discard on hold")
            for pid in refpids:
                # Loop waiting for other processes to surrender the artifact
                while True:
                    try:
                        # No need to wait for self, nor for processes waiting
                        # for the artifact lock we are already holding.
                        if pid == self._pid or pid in lockpids:
                            break
                        # Throws exception after 1s if lock is not acquired.
                        # We then we check if there are any new lock references,
                        # which allows us to a break deadlock condition.
                        with self._pid_lock(pid, wait=True, timeout=1):
                            break
                    except RuntimeError:
                        with self._cache_lock(), self._db() as db:
                            lockpids = self._db_select_artifact_lock_pids(db, artifact.identity)

        with self._cache_lock(), self._db() as db:
            assert self._discard(db, artifacts, False), "Failed to discard artifact"
            artifact.reset()
        return artifact

    def discard_all(self, if_expired=False, onerror=None):
        with self._cache_lock(), self._db() as db:
            self._db_invalidate_locks(db)
            self._db_invalidate_references(db)
            self._fs_invalidate_pids(db)
            return self._discard(
                db,
                self._db_select_artifacts_not_in_use(db),
                if_expired,
                onerror=onerror)

    def get_context(self, node):
        return Context(self, node)

    def get_artifact(self, node, name, tools=None, session=False):
        artifact = self._fs_get_artifact(node, name=name, tools=tools, session=session)
        if not artifact.is_temporary():
            with self._cache_lock(), self._db() as db:
                if not self._db_select_artifact(db, artifact.identity) and not self._db_select_reference(db, artifact.identity):
                    log.verbose("Artifact not present in db, discarding archive ({} )", artifact.task.short_qualified_name, artifact.identity)
                    fs.rmtree(artifact.final_path, ignore_errors=True)
                    artifact.reload()
        return artifact

    @contextlib.contextmanager
    def lock_artifact(self, artifact: Artifact, discard: bool = False, why: str = "publish"):
        """
        Locks the task artifact.

        First records interest in artifact lock file and then attempts
        to acquire the lock. Deletes the file upon releasing the lock
        if there are no other references to the lock from other processes.
        """
        with self._cache_lock():
            with self._db() as db:
                self._db_insert_lock(db, artifact.identity)
                self._db_insert_reference(db, artifact.identity)
            lock_path = self._fs_get_artifact_lockpath(artifact.identity)
            lock = fasteners.InterProcessLock(lock_path)
            is_locked = lock.acquire(blocking=False)
        if not is_locked:
            artifact._info("Artifact is temporarily locked by another process")
            lock.acquire()

        artifact._debug("Artifact locked for {}", why)

        try:
            if discard:
                artifact = self._discard_wait(artifact)
            else:
                artifact.reload()

            if artifact.is_temporary():
                fs.rmtree(artifact.temporary_path, ignore_errors=True)
                fs.makedirs(artifact.temporary_path)

            yield artifact
        finally:
            artifact._debug("Artifact unlocked for {}", why)
            fs.rmtree(artifact.temporary_path, ignore_errors=True)
            with self._cache_lock():
                with self._db() as db:
                    self._db_delete_lock(db, artifact.identity)
                lock.release()
                with self._db() as db:
                    if self._db_select_lock_count(db, artifact.identity) == 0:
                        fs.unlink(lock_path, ignore_errors=True)

    def precheck(self, artifacts, remote=True):
        """ Precheck artifacts for availability and cache status. """
        if not self.has_availability():
            return
        present, missing = self.availability(artifacts, remote=remote)
        log.verbose("Cache: {}/{} artifacts present", len(present), len(artifacts))
