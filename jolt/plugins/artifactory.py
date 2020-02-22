from jolt import config
from jolt import log
from jolt.plugins import http


NAME = "artifactory"


class Artifactory(http.Http):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._uri = config.get(NAME, "uri")
        self._repository = config.get(NAME, "repository", "jolt")
        raise_error_if(not self._uri, "HTTP URI not configured")
        if self._uri[-1] != "/":
            self._uri += "/"
        self._upload = config.getboolean(NAME, "upload", True)
        self._download = config.getboolean(NAME, "download", True)
        self._disabled = False

    def _get_url(self, node, artifact):
        return "{uri}{repository}/{name}/{file}".format(
            uri=self._uri,
            repository=self._repository,
            name=node.name,
            file=fs.path.basename(artifact.get_archive_path()))

log.warning("[Artifactory] Deprecated plugin loaded. Use HTTP instead.")
