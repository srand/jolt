from collections import OrderedDict
import json
import os
from tempfile import mkdtemp
from threading import RLock
from datetime import datetime

from jolt import config
from jolt import filesystem as fs
from jolt import influence
from jolt import log
from jolt import tools
from jolt import utils
from jolt.options import JoltOptions
from jolt.error import raise_error
from jolt.error import raise_task_error, raise_task_error_if
from jolt.expires import ArtifactEvictionStrategyRegister


DEFAULT_ARCHIVE_TYPE = ".tar.gz"


def locked(func):
    def _f(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    return _f


class StorageProvider(object):
    def download(self, node, force=False):
        return False

    def download_enabled(self):
        return True

    def upload(self, node, force=False):
        return False

    def upload_enabled(self):
        return True

    def location(self, node):
        return ''  # URL


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

    def unapply(self, task, artifact):
        for _, value in self.items():
            value.unapply(task, artifact)


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
    def unapply_all(task, artifact):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().unapply(task, artifact)


class ArtifactAttributeSetProvider(object):
    @staticmethod
    def Register(cls):
        ArtifactAttributeSetRegistry.providers.append(cls)

    def create(self, artifact):
        raise NotImplemented()

    def parse(self, artifact, content):
        raise NotImplemented()

    def format(self, artifact, content):
        raise NotImplemented()

    def apply(self, task, artifact):
        raise NotImplemented()

    def unapply(self, task, artifact):
        raise NotImplemented()


class ArtifactAttribute(object):
    def __init__(self, name):
        self._name = name

    def get_name(self):
        return self._name

    def set_value(self, value):
        raise NotImplemented()

    def get_value(self):
        raise NotImplemented()

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def __str__(self):
        raise NotImplemented()


class ArtifactStringAttribute(ArtifactAttribute):
    def __init__(self, name):
        self._name = name
        self._value = None

    def get_name(self):
        return self._name

    def set_value(self, value):
        self._value = value

    def get_value(self):
        return self._value

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def __str__(self):
        return str(self._value)


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

    Values appended to PATH-type variables are relative to the artifact
    root. They will be automatically expanded to absolute paths. These
    PATH-type variables are supported:

    - ``PATH``
    - ``LD_LIBRARY_PATH``
    - ``PKG_CONFIG_PATH``

    Example:

        .. code-block:: python

            def publish(self, artifact, tools):
                artifact.environ.PATH.append("bin")
                artifact.environ.JAVA_HOME = artifact.final_path
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

    def __init__(self, cache, node):
        self._cache = cache
        self._node = node
        self._path = cache.get_path(node)
        self._stable_path = cache.get_stable_path(node)
        self._temp = cache.create_path(node) \
                     if not fs.path.exists(cache.get_path(node)) \
                     else None
        self._archive = None
        self._unpacked = False
        self._uploadable = True
        self._created = datetime.now()
        self._modified = datetime.now()
        self._expires = node.task.expires
        self._size = 0
        self._influence = None
        ArtifactAttributeSetRegistry.create_all(self)
        try:
            self._read_manifest()
        except:
            log.exception()
            self.discard()
            raise_task_error(node, "unable to read task artifact manifest")

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        if self._archive:
            fs.unlink(self._archive)
        if self._temp:
            fs.rmtree(self._temp, ignore_errors=True)

    def __getattr__(self, name):
        raise_task_error(self._node, "attempt to access invalid artifact attribute '{0}'", name)

    def _write_manifest(self):
        content = {}
        content["task"] = self._node.name
        content["size"] = self._get_size()
        content["unpacked"] = self._unpacked
        content["uploadable"] = self._uploadable
        content["identity"] = self._node.identity
        content["requires"] = self._node.task.requires
        content["parameters"] = self._node.task._get_parameters()
        if self._influence is not None:
            content["influence"] = self._influence
        else:
            content["influence"] = influence.HashInfluenceRegistry.get().get_strings(self._node.task)
        content["created"] = self._created
        content["modified"] = datetime.now()
        content["expires"] = self._expires.value
        self._created = content.get("created", datetime.now())
        self._modified = content.get("modified", datetime.now())

        ArtifactAttributeSetRegistry.format_all(self, content)

        manifest = fs.path.join(self._temp or self._path, ".manifest.json")
        with open(manifest, "wb") as f:
            f.write(json.dumps(content, indent=2, default=json_serializer).encode())

    @staticmethod
    def load_manifest(path):
        manifest = fs.path.join(path, ".manifest.json")
        with open(manifest, "rb") as f:
            data = utils.decode_str(f.read())
            content = json.loads(data, object_hook=json_deserializer)
        return content

    def _read_manifest(self):
        if self._temp:
            return
        content = Artifact.load_manifest(self._path)
        self._size = content["size"]
        self._unpacked = content["unpacked"]
        self._uploadable = content.get("uploadable", True)
        self._created = content.get("created", datetime.now())
        self._modified = content.get("modified", datetime.now())
        self._evictable = content.get("evictable", True)
        self._influence = content.get("influence", [])
        self._expires = ArtifactEvictionStrategyRegister.get().find(
            content.get("expires", "immediately"))
        ArtifactAttributeSetRegistry.parse_all(self, content)

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
        return size

    def apply(self):
        fs.unlink(self._stable_path, ignore_errors=True)
        if fs.path.exists(self._path):
            fs.symlink(self._path, self._stable_path)

    def unapply(self):
        fs.unlink(self._stable_path, ignore_errors=True)

    def commit(self, uploadable=True):
        if not self._node.task.is_cacheable():
            return
        if self._temp:
            self._uploadable = uploadable
            self._size = self._get_size()
            self._write_manifest()
            fs.rename(self._temp, self._path)
            self._temp = None
            self._cache.commit(self)

    def discard(self):
        if self._archive:
            fs.unlink(self._archive)
        if self._temp:
            fs.rmtree(self._temp, ignore_errors=True)
        if self._path:
            fs.rmtree(self._path)

    def modify(self):
        raise_task_error_if(
            self._temp,
            self._node,
            "attempting to unpack missing task artifact")
        self._temp = self._path
        self._unpacked = True

    @property
    def path(self):
        """ str: The current location of the artifact in the local cache. """
        return self._temp or self._path

    @property
    def final_path(self):
        """ str: The final location of the artifact in the local cache. """
        return self._path

    @property
    def stable_path(self):
        """ str: A stable location of the artifact in the local cache. """
        return self._stable_path

    @property
    def tools(self):
        return self._node.tools

    def collect(self, files, dest=None, flatten=False, symlinks=False):
        """ Collect files to be included in the artifact.

        Args:
            files (str): A filename pattern matching the files to be include
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

        """

        raise_task_error_if(
            not self._temp,
            self._node,
            "can't collect files into an already published task artifact")

        files = self._node.task.expand(files)
        files = self.tools.glob(files)

        dest = self._node.task.expand(dest) if dest is not None else None

        # Special case for renaming files
        safe_dest = dest or fs.sep
        if len(files) == 1 and safe_dest[-1] != fs.sep:
            src = files[0]
            self.tools.copy(src, fs.path.join(self._temp, dest), symlinks=symlinks)
            log.verbose("Collected {0} -> {2}/{1}", src, dest, self._temp)
            return

        # General case
        dirname = fs.path.join(self._temp, dest) if dest else self._temp + fs.sep
        for src in files:
            srcs = fs.scandir(src) if fs.path.isdir(src) and flatten else [src]
            for src in srcs:
                dest = fs.path.join(dirname, src) \
                       if not flatten else \
                          fs.path.join(dirname, fs.path.basename(src))
                if symlinks or fs.path.exists(self.tools.expand_path(src)):
                    self.tools.copy(src, dest, symlinks=symlinks)
                    log.verbose("Collected {0} -> {1}", src, dest[len(self._temp):])

    def copy(self, pathname, dest, flatten=False, symlinks=False):
        """ Copy files from the artifact.

        Args:
            pathname (str): A pathname pattern, relative to the root, matching
                the files to be copied from the artifact.
                The pattern may contain simple shell-style
                wildcards such as '*' and '?'. Note: files starting with a
                dot are not matched by these wildcards.
            dest (str, optional): Destination path. If the string ends with a
                path separator a new directory will
                be created and all matched source files will be copied into
                the new directory. A destination without trailing path
                separator can be used to rename single files, one at a time.
            flatten (boolean, optional): If True, the directory tree structure
                of matched source files will flattened, i.e. all files will
                be copied into the root of the destination path. The default
                is False, which retains the directory tree structure.
            symlinks (boolean, optional): If True, symlinks are copied.
                The default is False, i.e. the symlink target is copied.

        """

        raise_task_error_if(
            self._temp,
            self._node,
            "can't copy files from an unpublished task artifact")

        pathname = self._node.task.expand(pathname)
        dest = self._node.task.expand(dest)

        files = []
        with self.tools.cwd(self._path):
            files = self.tools.glob(pathname)
        for src in files:
            with self.tools.cwd(self._path):
                srcs = self.tools.glob(src) \
                    if fs.path.isdir(fs.path.join(self._path, src)) and flatten else [src]
            for src in srcs:
                destfile = fs.path.join(dest, src) \
                           if not flatten else \
                              fs.path.join(dest, fs.path.basename(src))
                self.tools.copy(fs.path.join(self._path, src), destfile, symlinks=symlinks)
                log.verbose("Copied {0} -> {1}", src, destfile)

    def compress(self):
        raise_task_error_if(
            self._temp,
            self._node,
            "can't compress an unpublished task artifact")

        if not self.get_archive():
            self._archive = self.tools.archive(
                self._path, self._path + DEFAULT_ARCHIVE_TYPE)

    def decompress(self):
        archive = self._path + DEFAULT_ARCHIVE_TYPE
        try:
            self.tools.extract(archive, self._path)
        except:
            self.discard()
            raise_task_error(
                self._node,
                "failed to extract task artifact archive")

        self.tools.unlink(archive)
        if self._temp:
            fs.rmtree(self._temp)
            self._temp = None
        self._read_manifest()

    def get_archive(self):
        path = fs.get_archive(self._path)
        return path if fs.path.exists(path) else None

    def get_archive_path(self):
        return fs.get_archive(self._path)

    def get_size(self):
        return self._size

    def get_task(self):
        return self._node.task

    def get_name(self):
        return self._node.qualified_name

    def get_cache(self):
        return self._cache

    def get_identity(self):
        return self._node.identity

    def is_temporary(self):
        return self._temp is not None

    def is_unpacked(self):
        return self._unpacked

    def is_uploadable(self):
        return self._uploadable


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
        for dep in self._node.children:
            self._cache.unpack(dep)
            with self._cache.get_artifact(dep) as artifact:
                self._artifacts[dep.qualified_name] = artifact
                self._artifacts_index[dep.qualified_name] = artifact
                self._artifacts_index[dep.short_qualified_name] = artifact
                artifact.apply()
                ArtifactAttributeSetRegistry.apply_all(self._node.task, artifact)
        return self

    def __exit__(self, type, value, tb):
        for name, artifact in self._artifacts.items():
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

        key = self._node.task.expand(key)
        raise_task_error_if(
            key not in self._artifacts_index,
            self._node,
            "no such dependency '{0}'", key)
        return self._artifacts_index[key]

    def items(self):
        """ List all requirements and their artifacts.

        Returns:
            Requirement dictionary items. Each item is a tuple with the
            requirement name and the artifact.
        """
        return self._artifacts.items()


class CacheStats(object):
    def __init__(self, cache):
        self.lock = RLock()
        self.cache = cache
        self.path = fs.path.join(cache.root, "stats.json")
        try:
            self.load()
        except:
            self.stats = {}
        self.active = set()
        log.verbose("Cache size is {0}", utils.as_human_size(self.get_size()))

    def load(self):
        with open(self.path) as f:
            data = utils.decode_str(f.read())
            self.stats = json.loads(data, object_hook=json_deserializer)

        deleted = []
        for artifact, stats in self.stats.items():
            path = fs.path.join(self.cache.root, stats["name"], artifact)
            if not os.path.exists(path):
                deleted.append(artifact)
        for deleted in deleted:
            del self.stats[deleted]

        self.save()

    @locked
    def save(self):
        with open(self.path, "wb") as f:
            f.write(json.dumps(self.stats, indent=2, default=json_serializer).encode())

    @locked
    def update(self, artifact, save=True):
        if artifact.is_temporary():
            return
        stats = {}
        stats["name"] = artifact.get_task().canonical_name
        stats["used"] = datetime.now()
        stats["size"] = artifact.get_size()
        self.stats[artifact.get_identity()] = stats
        self.active.add(artifact.get_identity())
        if save:
            self.save()

    @locked
    def remove(self, artifact):
        try:
            del self.stats[artifact["identity"]]
        except KeyError as e:
            log.verbose("Eviction from artifact DB failed: {}", e)
        else:
            self.save()

    def is_expired(self, artifact):
        if not self.stats:
            return False
        stats = self.stats.get(artifact.get_identity())
        if not stats:
            return False
        content = Artifact.load_manifest(artifact.path)
        content["used"] = stats["used"]
        strategy = ArtifactEvictionStrategyRegister.get().find(
            content.get("expires", "immediately"))
        return strategy.is_evictable(content)

    @locked
    def get_size(self):
        size = 0
        for artifact, stats in self.stats.items():
            size += stats["size"]
        return size

    @locked
    def get_lru(self):
        nt = [dict(identity=artifact, **stats) for artifact, stats in self.stats.items()]
        # Don't evict artifacts in the current active working set
        nt = list(filter(lambda x: x["identity"] not in self.active, nt))
        nt = sorted(nt, key=lambda x: x["used"])

        for target in nt:
            path = fs.path.join(self.cache.root, target["name"], target["identity"])
            try:
                content = Artifact.load_manifest(path)
            except FileNotFoundError as e:
                continue
            content["used"] = target["used"]
            strategy = ArtifactEvictionStrategyRegister.get().find(
                content.get("expires", "immediately"))
            if strategy.is_evictable(content):
                return target

        return None


@utils.Singleton
class ArtifactCache(StorageProvider):
    storage_provider_factories = []

    def __init__(self, options=None):
        self.root = config.get_cachedir()

        try:
            fs.makedirs(self.root)
        except:
            raise_error("failed to create cache directory '{0}'", self.root)

        self.max_size = config.getsize(
            "jolt", "cachesize", os.environ.get("JOLT_CACHESIZE", 1*1024**3))
        self.stats = CacheStats(self)
        self.storage_providers = [
            factory.create(self)
            for factory in ArtifactCache.storage_provider_factories]
        self._options = options or JoltOptions()
        self._remote_identity_cache = set()
        self._lockfile = utils.LockFile(
            fs.path.join(self.root),
            log.info, "Another instance of Jolt is already running, waiting for it to complete...")

    def get_path(self, node):
        return fs.path.join(self.root, node.canonical_name, node.identity)

    def get_stable_path(self, node):
        identity = utils.sha1(node.qualified_name)
        return fs.path.join(self.root, node.canonical_name, identity)


    def evict(self):
        while self.stats.get_size() > self.max_size:
            artifact = self.stats.get_lru()
            if artifact is None:
                return
            log.verbose("Evicting artifact '{name}:{identity}'".format(**artifact))
            path = fs.path.join(self.root, artifact["name"], artifact["identity"])
            self.stats.remove(artifact)
            fs.rmtree(path, ignore_errors=True)

    def create_path(self, node):
        path = None
        try:
            dirname = fs.path.join(self.root, node.canonical_name)
            fs.makedirs(dirname)
            path = mkdtemp(prefix=node.identity, dir=dirname)
        except:
            pass
        raise_task_error_if(
            not path, node,
            "couldn't create temporary task artifact directory")
        return path

    def is_available_locally(self, node):
        if not node.task.is_cacheable():
            return False
        if fs.path.exists(self.get_path(node)):
            with self.get_artifact(node) as a:
                self.stats.update(a)
            return True
        return False

    def is_available_remotely(self, node):
        if not self.upload_enabled() and not self.download_enabled():
            return True
        if not node.task.is_cacheable():
            return False
        if node.identity in self._remote_identity_cache:
            return True
        for provider in self.storage_providers:
            if provider.location(node):
                self._remote_identity_cache.add(node.identity)
                return True
        return False

    def is_available(self, node):
        return self.is_available_locally(node) or self.is_available_remotely(node)

    def is_uploadable(self, node):
        with self.get_artifact(node) as artifact:
            return artifact.is_uploadable()

    def download_enabled(self):
        return self._options.download and \
            any([provider.download_enabled() for provider in self.storage_providers])

    def download(self, node, force=False):
        if not force and not self.download_enabled():
            return False
        if not node.task.is_cacheable():
            return False
        if self.is_available_locally(node):
            node.info("Download skipped, already in local cache")
            return True
        if not node.is_downloadable():
            return True
        for provider in self.storage_providers:
            if provider.download(node, force):
                with self.get_artifact(node) as artifact:
                    artifact.decompress()
                    self.commit(artifact)
                return True
        return len(self.storage_providers) == 0

    def upload_enabled(self):
        return self._options.upload and \
            any([provider.upload_enabled() for provider in self.storage_providers])

    def upload(self, node, force=False):
        if not force and not self.upload_enabled():
            return False
        if not node.task.is_cacheable():
            return True
        raise_task_error_if(
            not self.is_available_locally(node), node,
            "can't upload task artifact, no artifact present in the local cache")
        if self.storage_providers:
            with self.get_artifact(node) as artifact:
                artifact.compress()
                return all([provider.upload(node, force) for provider in self.storage_providers])
        return len(self.storage_providers) == 0

    def location(self, node):
        if not node.task.is_cacheable():
            return ''
        for provider in self.storage_providers:
            url = provider.location(node)
            if url:
                return url
        return ''

    def unpack(self, node):
        if not node.task.is_cacheable():
            return False
        with self.get_artifact(node) as artifact:
            if artifact.is_unpacked():
                return True
            artifact.modify()
            task = artifact.get_task()
            with tools.Tools(task) as t:
                try:
                    task.unpack(artifact, t)
                    artifact.commit(uploadable=False)
                except NotImplementedError:
                    artifact.commit()
        return True

    def commit(self, artifact):
        self.stats.update(artifact)
        self.evict()

    def discard(self, node, if_expired=False):
        if not self.is_available_locally(node):
            return False
        with self.get_artifact(node) as artifact:
            if if_expired and not self.stats.is_expired(artifact):
                return False
            self.stats.remove(dict(identity=node.identity))
            artifact.discard()
        return True

    def discard_all(self, if_expired=False):
        if if_expired:
            artifact = self.stats.get_lru()
            while artifact is not None:
                log.verbose("Discarded: {name} ({})".format(
                    artifact["identity"][:8], **artifact))
                path = fs.path.join(self.root, artifact["name"], artifact["identity"])
                self.stats.remove(artifact)
                fs.rmtree(path, ignore_errors=True)
                artifact = self.stats.get_lru()
        else:
            with tools.Tools() as t:
                artifacts = t.glob(fs.path.join(self.root, "*"))
                for artifact in artifacts:
                    fs.rmtree(artifact, ignore_errors=True)

    def get_context(self, node):
        return Context(self, node)

    def get_artifact(self, node):
        return Artifact(self, node)

    def get_archive_path(self, node):
        return fs.get_archive(self.get_path(node))

    def advise(self, node_list):
        """ Advise the cache about what artifacts to retain in the cache. """
        for node in node_list:
            if not node.task.is_cacheable():
                continue
            if fs.path.exists(self.get_path(node)):
                with Artifact(self, node) as artifact:
                    self.stats.update(artifact, save=False)
        self.stats.save()
