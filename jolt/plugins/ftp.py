import keyring
import getpass
from ftplib import FTP, FTP_TLS
from requests.exceptions import RequestException


from jolt import utils
from jolt import cache
from jolt import log
from jolt import config
from jolt import filesystem as fs
from jolt.tools import Tools
from jolt.error import raise_error_if


NAME = "ftp"
CONNECT_TIMEOUT = 3.5


def catch(func, *args, **kwargs):
    try:
        val = func(*args, **kwargs)
        return val if val is not None else True
    except Exception:
        log.exception()
        return False


class FtpStorage(cache.StorageProvider):
    def __init__(self, cache):
        super(FtpStorage, self).__init__()
        self._cache = cache
        self._uri = config.get(NAME, "host")
        raise_error_if(not self._uri, "ftp URI not configured")
        self._path = config.get(NAME, "path", "")
        self._upload = config.getboolean(NAME, "upload", True)
        self._download = config.getboolean(NAME, "download", True)
        self._tls = config.getboolean(NAME, "tls", False)
        self._disabled = False

    def _get_auth(self):
        service = config.get(NAME, "keyring.service")
        if not service:
            return None, None

        username = config.get(NAME, "keyring.username")
        if not username:
            username = input(NAME + " username: ")
            raise_error_if(not username, "no username configured for " + NAME)
            config.set(NAME, "keyring.username", username)
            config.save()

        password = config.get(NAME, "keyring.password") or keyring.get_password(NAME, username)
        if not password:
            password = getpass.getpass(NAME + " password: ")
            raise_error_if(not password, "no password in keyring for " + NAME)
            keyring.set_password(service, username, password)
        return username, password

    def _get_ftp(self):
        try:
            username, password = self._get_auth()
            if self._tls:
                ftp = FTP_TLS(self._uri, timeout=CONNECT_TIMEOUT)
            else:
                ftp = FTP(self._uri, timeout=CONNECT_TIMEOUT)
            ftp.login(username, password)
            if self._tls:
                ftp.prot_d()
            if not catch(ftp.cwd, self._path):
                if self._path.startswith("/"):
                    ftp.cwd("/")
                components = self._path.split("/")
                for component in components:
                    if not catch(ftp.cwd, component):
                        ftp.mkd(component)
                        ftp.cwd(component)
            return ftp
        except Exception:
            log.exception()
            log.warning("[FTP] failed to establish server connection, disabled")
            self._disabled = True
        return None

    @utils.retried.on_exception((RequestException))
    def download(self, node, force=False):
        if self._disabled:
            return False
        if not self._download and not force:
            return False
        with self._cache.get_artifact(node) as artifact:
            ftp = self._get_ftp()
            if ftp is None:
                return False
            pathname = artifact.get_archive_path()
            name = fs.path.basename(pathname)
            try:
                ftp.cwd(node.canonical_name)
                size = ftp.size(name)
            except Exception:
                return False
            with log.progress("Downloading {0}".format(name), size, "B") as pbar:
                with open(pathname, 'wb') as out_file:
                    def _write(block):
                        out_file.write(block)
                        pbar.update(len(block))
                    return catch(ftp.retrbinary,
                                 "RETR {filename}".format(filename=name),
                                 callback=_write)
        return False

    def download_enabled(self):
        return not self._disabled and self._download

    @utils.retried.on_exception((RequestException))
    def upload(self, node, force=False):
        if self._disabled:
            return True
        if not self._upload and not force:
            return True
        with self._cache.get_artifact(node) as artifact:
            ftp = self._get_ftp()
            if ftp is None:
                return False
            pathname = artifact.get_archive_path()
            name = fs.path.basename(pathname)
            size = Tools().file_size(pathname)
            with log.progress("Uploading {0}".format(name), size, "B") as pbar:
                with open(pathname, 'rb') as in_file:
                    if not catch(ftp.cwd, node.canonical_name):
                        if not catch(ftp.mkd, node.canonical_name):
                            return False
                        if not catch(ftp.cwd, node.canonical_name):
                            return False

                    catch(ftp.delete, name)

                    return catch(ftp.storbinary,
                                 "STOR {filename}".format(filename=name),
                                 in_file,
                                 callback=lambda b: pbar.update(len(b)))
        return False

    def upload_enabled(self):
        return not self._disabled and self._upload

    @utils.retried.on_exception((RequestException))
    def location(self, node):
        if self._disabled:
            return False
        with self._cache.get_artifact(node) as artifact:
            ftp = self._get_ftp()
            if ftp is None:
                return False
            username, _ = self._get_auth()
            username = username + "@" if username is not None else ""
            pathname = artifact.get_archive_path()
            name = fs.path.basename(pathname)
            if not catch(ftp.cwd, node.canonical_name):
                return False
            try:
                if ftp.size(name) is not None:
                    url = "ftp://{user}{uri}/{path}/{taskname}/{archive}".format(
                        user=username,
                        uri=self._uri,
                        path=self._path,
                        taskname=node.canonical_name,
                        archive=name)
                    log.debug("[FTP] {0}", url)
                    return url
            except Exception:
                return False
        return False


@cache.RegisterStorage
class FtpStorageFactory(cache.StorageProviderFactory):
    @staticmethod
    def create(cache):
        log.verbose("[Ftp] Loaded")
        return FtpStorage(cache)
