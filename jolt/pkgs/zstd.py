from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Zstd(cmake.CMake):
    name = "zstd"
    version = Parameter("ebc93b0", help="zstd version.")
    shared = BooleanParameter(False, "Enable shared libraries.")
    requires_git = ["git:url=https://github.com/facebook/zstd.git,rev={version}"]
    srcdir = "{git[zstd]}"
    options = [
        "ZSTD_BUILD_SHARED={shared[ON,OFF]}",
        "ZSTD_BUILD_STATIC={shared[OFF,ON]}",
        "ZSTD_BUILD_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("zstd_static")
        else:
            artifact.cxxinfo.libraries.append("zstd")


TaskRegistry.get().add_task_class(Zstd)
