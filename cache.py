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
        return {key: str(value) for key, value in self.iteritems()}

    def iteritems(self):
        return self._get_attributes().iteritems()

    def apply(self, artifact):
        for _, value in self.iteritems():
            value.apply(artifact)

    def unapply(self, artifact):
        for _, value in self.iteritems():
            value.unapply(artifact)


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
    def apply_all(artifact):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().apply(artifact)

    @staticmethod
    def unapply_all(artifact):
        for provider in ArtifactAttributeSetRegistry.providers:
            provider().unapply(artifact)

            
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

    def apply(self, artifact):
        raise NotImplemented()

    def unapply(self, artifact):
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

    def apply(self, artifact):
        pass
        
    def unapply(self, artifact):
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

    def apply(self, artifact):
        pass
        
    def unapply(self, artifact):
        pass

    def __str__(self):
        return str(self._value)

        
class Artifact(object):
    def __init__(self, cache, node):
        self._cache = cache
        self._node = node
        self._path = cache.get_path(node)
        self._temp = cache.create_path(node) \
                     if not cache.is_available_locally(node) \
                     else None
        self._archive = None
        ArtifactAttributeSetRegistry.create_all(self)

    def __enter__(self):
        self._read_manifest()
        return self

    def __exit__(self, type, value, tb):
        self.discard()
        
    def __getattr__(self, name):
        assert False, "no attribute '{}' in artifact for '{}'".format(
            name, self._node.qualified_name)

    def _write_manifest(self):
        content = {}
        content["task"] = self._node.name
        content["attributes"] = self._node.task.attributes
        content["identity"] = self._node.identity
        content["requires"] = self._node.task._get_requires()
        content["parameters"] = self._node.task._get_parameters()
        content["influence"] = influence.HashInfluenceRegistry.get().get_strings(self._node.task)
        ArtifactAttributeSetRegistry.format_all(self, content)

        manifest = fs.path.join(self._temp, ".manifest.json")
        with open(manifest, "wb") as f:
            f.write(json.dumps(content, indent=3))

    def _read_manifest(self):
        if self._temp:
            return
        manifest = fs.path.join(self._path, ".manifest.json")
        with open(manifest, "rb") as f:
            content = json.loads(f.read())
            ArtifactAttributeSetRegistry.parse_all(self, content)

    def commit(self):
        if not self._node.task.is_cacheable():
            return
        if self._temp:
            self._write_manifest()
            fs.rename(self._temp, self._path)
            self._temp = None

    def discard(self):
        if self._archive:
            fs.unlink(self._archive)
        if self._temp:
            fs.rmtree(self._temp)

    @property
    def path(self):
        return self._temp or self._path

    def collect(self, files, dest=None, flatten=False):
        assert self._temp, "artifact is already published"
        files = self._node.task._get_expansion(files)
        dest = self._node.task._get_expansion(dest) if dest is not None else None

        files = glob.glob(files)
        dirname = fs.path.join(self._temp, dest) if dest else self._temp + fs.sep
        for src in files:
            srcs = fs.scandir(src) if fs.path.isdir(src) and flatten else [src]
            for src in srcs:
                dest = fs.path.join(dirname, src) \
                       if not flatten else \
                          fs.path.join(dirname, fs.path.basename(src))
                fs.copy(src, dest)
                log.verbose("Collected {} -> {}", src, dest[len(self._temp):])

    def copy(self, pattern, dest, flatten=False):
        assert not self._temp, "artifact is not published"
        pattern = self._node.task._get_expansion(pattern)
        dest = self._node.task._get_expansion(dest)

        files = []
        with tools.cwd(self._path):
            files = glob.glob(pattern)
        for src in files:
            srcs = fs.scandir(src) if fs.path.isdir(src) and flatten else [src]
            for src in srcs:
                destfile = fs.path.join(dest, src) \
                           if not flatten else \
                              fs.path.join(dest, fs.path.basename(src))
                fs.copy(fs.path.join(self._path, src), destfile)
                log.verbose("Copied {} -> {}", src, destfile)

    def compress(self):
        assert not self._temp, "artifact is not published, can't compress"
        if not self.get_archive():
            self._archive = fs.make_archive(self._path, self._path, remove=False)

    def decompress(self):
        fs.extract_archive(self._path, self._path, remove=True)
        self._read_manifest()

    def get_archive(self):
        path = fs.get_archive(self._path)
        return path if fs.path.exists(path) else None

    def get_archive_path(self):
        return fs.get_archive(self._path)

    def get_task(self):
        return self._node.task


class Context(object):
    def __init__(self, cache, node):
        self._cache = cache
        self._node = node
        self._artifacts = {}

    def __enter__(self):
        for dep in self._node.children:
            with self._cache.get_artifact(dep) as artifact:
                self._artifacts[dep.qualified_name] = artifact
                ArtifactAttributeSetRegistry.apply_all(artifact)
        return self

    def __exit__(self, type, value, tb):
        for name, artifact in self._artifacts.iteritems():
            ArtifactAttributeSetRegistry.unapply_all(artifact)

    def __getitem__(self, key):
        key = self._node.task._get_expansion(key)
        assert key in self._artifacts, "no such dependency: {}".format(key)
        return self._artifacts[key]

    def iteritems(self):
        return self._artifacts.iteritems()


class ArtifactCache(StorageProvider):
    root = fs.path.join(fs.path.expanduser("~"), ".cache", "jolt")
    storage_provider_factories = []

    def __init__(self):
        try:
            fs.makedirs(self.root)
        except:
            pass

        self.storage_providers = [
            factory.create(self)
            for factory in ArtifactCache.storage_provider_factories]

    def get_path(self, node):
        return fs.path.join(self.root, node.canonical_name, node.identity)

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
        return fs.path.exists(self.get_path(node))

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
    
    def download(self, node, force=False):
        if not config.getboolean("jolt", "download", True):
            return True
        if not node.task.is_cacheable():
            return True
        assert not self.is_available_locally(node), "can't download task, exists in the local cache"
        for provider in self.storage_providers:
            if provider.download(node, force):
                return True
        return len(self.storage_providers) == 0

    def upload(self, node, force=False):
        if not config.getboolean("jolt", "upload", True):
            return True
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
            return False
        for provider in self.storage_providers:
            url = provider.location(node)
            if url:
                return url
        return ''

    def get_context(self, node):
        return Context(self, node)

    def get_artifact(self, node):
        return Artifact(self, node)

    def get_archive_path(self, node):
        return fs.get_archive(self.get_path(node))
