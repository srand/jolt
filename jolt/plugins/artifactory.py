import shutil
import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import ConnectionError, ConnectTimeout, ReadTimeout
import keyring
import getpass

from jolt import utils
from jolt import cache
from jolt import log
from jolt import config
from jolt import filesystem as fs

NAME = "artifactory"
CONNECT_TIMEOUT = 3.5


class Artifactory(cache.StorageProvider):
    def __init__(self, cache):
        super(Artifactory, self).__init__()
        self._cache = cache
        self._uri = config.get(NAME, "uri")
        assert self._uri, "artifactory URI not configured"
        if self._uri[-1] != "/":
            self._uri += "/"
        self._repository = config.get(NAME, "repository", "jolt")
        self._upload = config.getboolean(NAME, "upload", False)
        self._download = config.getboolean(NAME, "download", True)
        self._disabled = False

    def _get_auth(self):
        service = config.get(NAME, "keyring.service")
        if not service:
            service = raw_input(NAME + " keyring service name (artifactory): ")
            if not service:
                service = NAME
            config.set(NAME, "keyring.service", service)
            config.save()

        username = config.get(NAME, "keyring.username")
        if not username:
            username = raw_input(NAME + " username: ")
            assert username, "no username configured for " + NAME
            config.set(NAME, "keyring.username", username)
            config.save()

        password = config.get(NAME, "keyring.password") or \
                   keyring.get_password(NAME, username)
        if not password:
            password = getpass.getpass(NAME + " password: ")
            assert password, "no password in keyring for " + NAME
            keyring.set_password(service, username, password)
        return HTTPBasicAuth(username, password)

    def _get_url(self, node, artifact):
        return "{uri}{repository}/{name}/{file}".format(
            uri=self._uri,
            repository=self._repository,
            name=node.name,
            file=fs.path.basename(artifact.get_archive_path()))

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def download(self, node, force=False):
        if self._disabled:
            return False
        if not self._download and not force:
            return False
        with self._cache.get_artifact(node) as artifact:
            url = self._get_url(node, artifact)
            if node.tools.download(url, artifact.get_archive_path()):
                return True
        return False

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def upload(self, node, force=False):
        if self._disabled:
            return True
        if not self._upload and not force:
            return True
        with self._cache.get_artifact(node) as artifact:
            url = self._get_url(node, artifact)
            archive = artifact.get_archive()
            return node.tools.upload(archive, url, auth=self._get_auth())
        return False

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def location(self, node):
        if self._disabled:
            return False
        with self._cache.get_artifact(node) as artifact:
            url = self._get_url(node, artifact)
            try:
                response = requests.head(url, stream=True, timeout=CONNECT_TIMEOUT)
            except ConnectTimeout as e:
                self._disabled = True
                log.warn("[ARTIFACTORY] failed to establish server connection, disabled")
                return False

            log.hysterical("[ARTIFACTORY] Head: {0}", url)
            log.hysterical("[ARTIFACTORY] Response: {0}", response.status_code)
            return url if response.status_code == 200 else ''
        return False


@cache.RegisterStorage
class ArtifactoryFactory(cache.StorageProviderFactory):
    @staticmethod
    def create(cache):
        log.verbose("Artifactory loaded")
        return Artifactory(cache)
