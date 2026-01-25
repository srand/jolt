from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import brotli, ssl, zlib, zstd
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_brotli")
@attributes.requires("requires_git")
@attributes.requires("requires_ssl")
@attributes.requires("requires_zlib")
@attributes.requires("requires_zstd")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Curl(cmake.CMake):
    name = "curl"
    version = Parameter("8.17.0", help="Curl version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_brotli = ["brotli"]
    requires_git = ["git:url=https://github.com/curl/curl.git,rev=curl-{_version_tag},submodules=true"]
    requires_ssl = ["virtual/ssl"]
    requires_zlib = ["virtual/zlib"]
    requires_zstd = ["zstd"]
    srcdir = "{git[curl]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CURL_USE_LIBPSL=OFF",
        "USE_LIBIDN2=OFF",
    ]

    @property
    def _version_tag(self):
        return str(self.version).replace('.', '_')

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("libcurl_imp")
        else:
            artifact.cxxinfo.libraries.append("curl")


TaskRegistry.get().add_task_class(Curl)
