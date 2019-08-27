import uuid

from jolt import utils
from jolt import cache
from jolt import log
from jolt import config
from jolt import filesystem as fs
from jolt.error import raise_error_if


NAME = "volume"
TIMEOUT = (3.5, 27)


class DiskVolume(cache.StorageProvider):
    def __init__(self, cache):
        super(DiskVolume, self).__init__()
        self._cache = cache
        self._path = config.get(NAME, "path")
        raise_error_if(not self._path, "volume path not configured")
        fs.makedirs(self._path)
        self._upload = config.getboolean(NAME, "upload", True)
        self._download = config.getboolean(NAME, "download", True)

    def _get_path(self, node, artifact):
        return "{path}/{name}/{file}".format(
            path=self._path,
            name=node.name,
            file=fs.path.basename(artifact.get_archive_path()))

    def _get_temp(self, node, artifact):
        return "{path}/{name}/{file}".format(
            path=self._path,
            name=node.name,
            file=uuid.uuid4())

    def download(self, node, force=False):
        if not self._download and not force:
            return False
        with self._cache.get_artifact(node) as artifact:
            path = self._get_path(node, artifact)
            try:
                log.verbose("[VOLUME] Copying {}", path)
                fs.copy(path, artifact.get_archive_path())
                return True
            except:
                log.exception()
        return False

    def download_enabled(self):
        return self._download

    def upload(self, node, force=False):
        if not self._upload and not force:
            return True
        with self._cache.get_artifact(node) as artifact:
            path = self._get_path(node, artifact)
            temp = self._get_temp(node, artifact)
            try:
                log.verbose("[VOLUME] Copying {}", path)
                fs.copy(artifact.get_archive_path(), temp)
                fs.rename(temp, path)
                return True
            except OSError as e:
                return e.errno == errno.EEXIST
            except:
                log.exception()
            finally:
                fs.unlink(temp, ignore_errors=True)
        return False

    def upload_enabled(self):
        return self._upload

    def location(self, node):
        with self._cache.get_artifact(node) as artifact:
            path = self._get_path(node, artifact)
            avail = fs.path.exists(path)
            log.debug("[VOLUME] {} is{} present", path, "" if avail else " not")
            return avail
        return False


@cache.RegisterStorage
class DiskVolumeFactory(cache.StorageProviderFactory):
    @staticmethod
    def create(cache):
        log.verbose("Volume cache loaded")
        return DiskVolume(cache)
