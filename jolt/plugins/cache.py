from requests.exceptions import ConnectTimeout, RequestException
from urllib.parse import urlparse, urlunparse

from jolt import utils
from jolt import cache
from jolt import log
from jolt import config
from jolt import filesystem as fs
from jolt import tools
from jolt.error import raise_error_if, JoltError


NAME = "cache"
NAME_LOG = "Cache Service"
TIMEOUT = (3.5, 27)
TIMEOUT_HEAD = (27, 27)


class Cache(cache.StorageProvider):
    def __init__(self, cache):
        super().__init__()
        self._cache = cache
        self._uri = config.get(NAME, "uri", "http://cache")
        self._uri = self._uri.rstrip("/")
        raise_error_if(not self._uri, "Cache Service URI not configured")
        self._file_uri = self._uri + "/files"
        self._upload = config.getboolean(NAME, "upload", True)
        self._download = config.getboolean(NAME, "download", True)
        self._disabled = False

    def _get_path(self, artifact):
        return artifact.tools.expand(
            "{name}/{file}",
            name=artifact.task.name,
            file=fs.path.basename(artifact.get_archive_path()))

    def _get_url(self, artifact):
        return artifact.tools.expand(
            "{uri}/{name}/{file}",
            uri=self._file_uri,
            name=artifact.task.name,
            file=fs.path.basename(artifact.get_archive_path()))

    @utils.retried.on_exception((RequestException, JoltError))
    def download(self, artifact, force=False):
        if self._disabled:
            return False
        if not self._download and not force:
            return False
        url = self._get_url(artifact)
        return artifact.tools.download(
            url,
            artifact.get_archive_path(),
            exceptions=False,
            timeout=TIMEOUT)

    def download_enabled(self):
        return not self._disabled and self._download

    @utils.retried.on_exception((RequestException))
    def upload(self, artifact, force=False):
        if self._disabled:
            return True
        if not self._upload and not force:
            return True
        url = self._get_url(artifact)
        archive = artifact.get_archive()
        return artifact.tools.upload(
            archive, url,
            exceptions=False,
            timeout=TIMEOUT)

    def upload_enabled(self):
        return not self._disabled and self._upload

    @utils.retried.on_exception((RequestException))
    def availability(self, artifacts):
        if self._disabled:
            return [], artifacts

        file_map = {self._get_path(artifact): artifact for artifact in artifacts}
        try:
            data = {"files": list(file_map.keys())}
            response = tools.http_session.post(self._file_uri, json=data, stream=True, timeout=TIMEOUT_HEAD)
        except ConnectTimeout:
            self._disabled = True
            log.warning(NAME_LOG + " failed to establish server connection, disabled")
            return [], []

        if response.status_code != 200:
            log.debug(NAME_LOG + " POST ({}): {}", response.status_code, self._file_uri)
            return [], artifacts

        present = []
        missing = []
        data = response.json()

        for file in data.get("present", []):
            present.append(file_map[file])

        for file in data.get("missing", []):
            missing.append(file_map[file])

        return present, missing

    @utils.retried.on_exception((RequestException))
    def location(self, artifact):
        if self._disabled:
            return False

        url = self._get_url(artifact)
        try:
            response = tools.http_session.head(url, stream=True, timeout=TIMEOUT_HEAD)

        except ConnectTimeout:
            self._disabled = True
            log.warning(NAME_LOG + " failed to establish server connection, disabled")
            return False

        if response.status_code != 200:
            log.debug(NAME_LOG + " HEAD ({}): {}", response.status_code, url)
            return None

        url = urlunparse(urlparse(url))
        return url


@cache.RegisterStorage
class HttpFactory(cache.StorageProviderFactory):
    @staticmethod
    def create(cache):
        log.verbose(NAME_LOG + " Loaded")
        return Cache(cache)
