from jolt import attributes, Alias, Parameter
from jolt.pkgs import nasm
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_nasm_{system}")
@attributes.common_metadata()
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class LibreSSL(cmake.CMake):
    name = "libressl"
    version = Parameter("4.2.1", help="libressl version.")
    requires_git = ["git:url=https://github.com/libressl/portable.git,rev=v{version}"]
    requires_nasm_windows = ["nasm"]
    srcdir = "{git[portable]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("ssl")
        artifact.cxxinfo.libraries.append("crypto")        


TaskRegistry.get().add_task_class(LibreSSL)
