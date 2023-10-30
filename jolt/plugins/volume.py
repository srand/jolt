import os
import uuid
import errno

from jolt import utils
from jolt import cache
from jolt import log
from jolt import config
from jolt import filesystem as fs
from jolt.error import raise_error_if


NAME = "volume"
TIMEOUT = (3.5, 27)


class StaleFileHandleError(OSError):
    pass


class DiskVolume(cache.StorageProvider):
    def __init__(self, cache):
        super(DiskVolume, self).__init__()
        self._cache = cache
        self._path = config.get(NAME, "path")
        raise_error_if(not self._path, "volume path not configured")
        fs.makedirs(self._path)
        self._upload = config.getboolean(NAME, "upload", True)
        self._download = config.getboolean(NAME, "download", True)

    def _get_path(self, artifact):
        return artifact.tools.expand(
            "{path}/{name}/{file}",
            path=self._path,
            name=artifact.task.name,
            file=fs.path.basename(artifact.get_archive_path()))

    def _get_temp(self, artifact):
        return artifact.tools.expand(
            "{path}/{name}/{file}",
            path=self._path,
            file=uuid.uuid4())

    @utils.retried.on_exception(StaleFileHandleError)
    def download(self, artifact, force=False):
        if not self._download and not force:
            return False

        path = self._get_path(artifact)
        try:
            log.verbose("[VOLUME] Copying {}", path)
            fs.copy(path, artifact.get_archive_path())
            return True
        except OSError as e:
            if e.errno == errno.ESTALE:
                log.verbose("[VOLUME] got stale file handle, retrying...")
                raise StaleFileHandleError(e)
            else:
                log.exception()
        except Exception:
            log.exception()

        return False

    def download_enabled(self):
        return self._download

    def upload(self, artifact, force=False):
        if not self._upload and not force:
            return True
        path = self._get_path(artifact)
        temp = self._get_temp(artifact)
        try:
            log.verbose("[VOLUME] Copying {}", path)
            fs.copy(artifact.get_archive_path(), temp)
            # To avoid race-condition, make sure that the artifact still is
            # missing before moving it into place.
            if not fs.exists(path):
                fs.rename(temp, path)
            else:
                fs.unlink(temp)
            return True
        except OSError as e:
            if e.errno != errno.EEXIST:
                log.verbose("[VOLUME] Failed to copy artifact, errno={}", os.strerror(e.errno))
            return e.errno == errno.EEXIST
        except Exception:
            log.exception()
        finally:
            fs.unlink(temp, ignore_errors=True)
        return False

    def upload_enabled(self):
        return self._upload

    def location(self, artifact):
        path = self._get_path(artifact)
        avail = fs.path.exists(path)
        log.debug("[VOLUME] {} is{} present", path, "" if avail else " not")
        return avail


@cache.RegisterStorage
class DiskVolumeFactory(cache.StorageProviderFactory):
    @staticmethod
    def create(cache):
        log.verbose("[Volume] Loaded")
        return DiskVolume(cache)

# vim: et sw=4 ts=4
