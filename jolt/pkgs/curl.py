from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Curl(cmake.CMake):
    name = "curl"
    version = Parameter("8.17.0", help="Curl version.")
    requires_git = ["git:url=https://github.com/curl/curl.git,rev=curl-{_version_tag},submodules=true"]
    options = ["CURL_USE_LIBPSL=OFF"]
    srcdir = "{git[curl]}"

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
