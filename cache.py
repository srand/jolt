import filesystem as fs
import glob
import log
import tasks
import json
import copy
import os
from tempfile import mkdtemp
import tools
import influence
import config
import time


DEFAULT_ARCHIVE_TYPE = ".tar.gz"


class StorageProvider(object):
    def download(self, node, force=False):
        return False

    def upload(self, node, force=False):
        return False

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


class Artifact(object):
    def __init__(self, cache, node):
        self._cache = cache
        self._node = node
        self._path = cache.get_path(node)
        self._temp = cache.create_path(node) \
                     if not fs.path.exists(cache.get_path(node)) \
                     else None
        self._archive = None
        self._unpacked = False
        self._size = 0
        ArtifactAttributeSetRegistry.create_all(self)
        self._read_manifest()

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        if self._archive:
            fs.unlink(self._archive)
        if self._temp:
            fs.rmtree(self._temp)

    def __getattr__(self, name):
        assert False, "no attribute '{0}' in artifact for '{1}'".format(
            name, self._node.qualified_name)

    def _write_manifest(self):
        content = {}
        content["task"] = self._node.name
        content["size"] = self._get_size()
        content["unpacked"] = self._unpacked
        content["identity"] = self._node.identity
        content["requires"] = self._node.task._get_requires()
        content["parameters"] = self._node.task._get_parameters()
        content["influence"] = influence.HashInfluenceRegistry.get().get_strings(self._node.task)
        ArtifactAttributeSetRegistry.format_all(self, content)

        manifest = fs.path.join(self._temp, ".manifest.json")
        with open(manifest, "wb") as f:
            f.write(json.dumps(content, indent=3).encode())

    def _read_manifest(self):
        if self._temp:
            return
        manifest = fs.path.join(self._path, ".manifest.json")
        with open(manifest, "rb") as f:
            content = json.loads(f.read().decode())
            self._size = content["size"]
            self._unpacked = content["unpacked"]
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

    def commit(self):
        if not self._node.task.is_cacheable():
            return
        if self._temp:
            self.size = self._get_size()
            self._write_manifest()
            fs.rename(self._temp, self._path)
            self._temp = None
            self._cache.commit(self)

    def discard(self):
        if self._archive:
            fs.unlink(self._archive)
        if self._temp:
            fs.rmtree(self._temp)
        if self._path:
            fs.rmtree(self._path)

    def modify(self):
        assert not self._temp, "artifact is not published"
        #self._temp = self._cache.get_path(self._node) + ".unpack"
        #fs.move(self._path, self._temp)
        self._temp = self._path
        self._unpacked = True

    @property
    def path(self):
        return self._temp or self._path

    @property
    def tools(self):
        return self._node.tools

    def collect(self, files, dest=None, flatten=False):
        assert self._temp, "artifact is already published"
        files = self._node.task._get_expansion(files)
        dest = self._node.task._get_expansion(dest) if dest is not None else None

        files = self.tools.glob(files)
        dirname = fs.path.join(self._temp, dest) if dest else self._temp + fs.sep
        for src in files:
            srcs = fs.scandir(src) if fs.path.isdir(src) and flatten else [src]
            for src in srcs:
                dest = fs.path.join(dirname, src) \
                       if not flatten else \
                          fs.path.join(dirname, fs.path.basename(src))
                self.tools.copy(src, dest)
                log.verbose("Collected {0} -> {1}", src, dest[len(self._temp):])

    def copy(self, pattern, dest, flatten=False):
        assert not self._temp, "artifact is not published"
        pattern = self._node.task._get_expansion(pattern)
        dest = self._node.task._get_expansion(dest)

        files = []
        with self.tools.cwd(self._path):
            files = self.tools.glob(pattern)
        for src in files:
            srcs = fs.scandir(src) if fs.path.isdir(src) and flatten else [src]
            for src in srcs:
                destfile = fs.path.join(dest, src) \
                           if not flatten else \
                              fs.path.join(dest, fs.path.basename(src))
                self.tools.copy(fs.path.join(self._path, src), destfile)
                log.verbose("Copied {0} -> {1}", src, destfile)

    def compress(self):
        assert not self._temp, "artifact is not published, can't compress"
        if not self.get_archive():
            self._archive = self.tools.archive(
                self._path, self._path + DEFAULT_ARCHIVE_TYPE)

    def decompress(self):
        archive = self._path + DEFAULT_ARCHIVE_TYPE
        self.tools.extract(archive, self._path)
        self.tools.unlink(archive)
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

    def get_cache(self):
        return self._cache

    def get_identity(self):
        return self._node.identity

    def is_temporary(self):
        return self._temp is not None

    def is_unpacked(self):
        return self._unpacked


class Context(object):
    def __init__(self, cache, node):
        self._cache = cache
        self._node = node
        self._artifacts = {}

    def __enter__(self):
        for dep in self._node.children:
            self._cache.unpack(dep)
            with self._cache.get_artifact(dep) as artifact:
                self._artifacts[dep.qualified_name] = artifact
                ArtifactAttributeSetRegistry.apply_all(self._node.task, artifact)
        return self

    def __exit__(self, type, value, tb):
        for name, artifact in self._artifacts.items():
            ArtifactAttributeSetRegistry.unapply_all(self._node.task, artifact)

    def __getitem__(self, key):
        key = self._node.task._get_expansion(key)
        assert key in self._artifacts, "no such dependency: {0}".format(key)
        return self._artifacts[key]

    def items(self):
        return self._artifacts.items()


class CacheStats(object):
    def __init__(self, cache):
        self.cache = cache
        self.path = fs.path.join(cache.root, ".stats.json")
        try:
            self.load()
        except:
            self.stats = {}
        self.active = set()
        log.verbose("Cache size is {0} bytes", self.get_size())

    def load(self):
        with open(self.path) as f:
            self.stats = json.loads(f.read().decode())

        deleted = []
        for artifact, stats in self.stats.items():
            path = fs.path.join(self.cache.root, stats["name"], artifact)
            if not os.path.exists(path):
                deleted.append(artifact)
        for deleted in deleted:
            del self.stats[deleted]

        self.save()

    def save(self):
        with open(self.path, "wb") as f:
            f.write(json.dumps(self.stats, indent=3).encode())

    def update(self, artifact):
        if artifact.is_temporary():
            return
        stats = {}
        stats["name"] = artifact.get_task().name
        stats["used"] = time.time()
        stats["size"] = artifact.get_size()
        self.stats[artifact.get_identity()] = stats
        self.active.add(artifact.get_identity())
        self.save()

    def remove(self, artifact):
        del self.stats[artifact["identity"]]
        self.save()

    def get_size(self):
        size = 0
        for artifact, stats in self.stats.items():
            size += stats["size"]
        return size

    def get_lru(self):
        assert self.stats, "no artifacts in cache"
        nt = [dict(identity=artifact, **stats) for artifact, stats in self.stats.items()]
        nt = sorted(nt, key=lambda x: x["used"])
        # Don't evict artifacts in the current working set
        nt = list(filter(lambda x: x["identity"] not in self.active, nt))
        return nt[0] if len(nt) > 0 else None


class ArtifactCache(StorageProvider):
    root = fs.path.join(fs.path.expanduser("~"), ".cache", "jolt")
    storage_provider_factories = []

    def __init__(self):
        try:
            self.root = config.get("jolt", "cachedir") or ArtifactCache.root
            fs.makedirs(self.root)
        except:
            assert False, "failed to create cache directory"

        self.max_size = config.getsize("jolt", "cachesize", 0)
        self.stats = CacheStats(self)
        self.storage_providers = [
            factory.create(self)
            for factory in ArtifactCache.storage_provider_factories]

    def get_path(self, node):
        return fs.path.join(self.root, node.canonical_name, node.identity)

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
        assert path, "couldn't create temporary directory"
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
        if not node.task.is_cacheable():
            return False
        for provider in self.storage_providers:
            if provider.location(node):
                return True
        return False

    def is_available(self, node):
        return self.is_available_locally(node) or self.is_available_remotely(node)

    def is_available(self, node, on_network):
        return \
            (not on_network and self.is_available_locally(node)) or \
            (on_network and self.is_available_remotely(node))

    def download_enabled(self):
        return config.getboolean("jolt", "download", True)

    def download(self, node, force=False):
        if not force and not self.download_enabled():
            return False
        if not node.task.is_cacheable():
            return False
        if self.is_available_locally(node):
            node.info("Download skipped, already in local cache")
            return True
        for provider in self.storage_providers:
            if provider.download(node, force):
                with self.get_artifact(node) as artifact:
                    artifact.decompress()
                self.evict()
                return True
        return len(self.storage_providers) == 0

    def upload_enabled(self):
        return config.getboolean("jolt", "upload", True)

    def upload(self, node, force=False):
        if not force and not self.upload_enabled():
            return False
        if not node.task.is_cacheable():
            return True
        assert self.is_available_locally(node), "can't upload task, not in the local cache"
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
                task.unpack(artifact, t)
            artifact.commit()
        return True

    def commit(self, artifact):
        self.stats.update(artifact)
        self.evict()

    def discard(self, node):
        if not self.is_available_locally(node):
            return False
        with self.get_artifact(node) as artifact:
            self.stats.remove(dict(identity=node.identity))
            artifact.discard()
        return True

    def get_context(self, node):
        return Context(self, node)

    def get_artifact(self, node):
        artifact = Artifact(self, node)
        self.stats.update(artifact)
        return artifact

    def get_archive_path(self, node):
        return fs.get_archive(self.get_path(node))
