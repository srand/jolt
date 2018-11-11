import cache
import log
import config
import shutil
import requests
from requests.auth import HTTPBasicAuth
import filesystem as fs
import keyring
import getpass

NAME = "artifactory"


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

    def download(self, node, force=False):
        if not self._download and not force:
            return False
        with self._cache.get_artifact(node) as artifact:
            url = self._get_url(node, artifact)
            if node.tools.download(url, artifact.get_archive_path()):
                return True
        return False

    def upload(self, node, force=False):
        if not self._upload and not force:
            return True
        with self._cache.get_artifact(node) as artifact:
            url = self._get_url(node, artifact)
            archive = artifact.get_archive()
            return node.tools.upload(archive, url, auth=self._get_auth())
        return False

    def location(self, node):
        with self._cache.get_artifact(node) as artifact:
            url = self._get_url(node, artifact)
            response = requests.head(url, stream=True)
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
