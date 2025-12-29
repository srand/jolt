from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Curl(cmake.CMake):
    name = "curl"
    version = Parameter("8.17.0", help="Curl version.")
    requires_git = ["git:url=https://github.com/curl/curl.git,rev=curl-{_version_tag},submodules=true"]
    options = ["CURL_USE_LIBPSL=OFF"]
    srcdir = "{git[curl]}"

    @property
    def _version_tag(self):
        return str(self.version).replace('.', '_')


TaskRegistry.get().add_task_class(Curl)
