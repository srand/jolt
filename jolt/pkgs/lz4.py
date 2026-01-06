from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Lz4(cmake.CMake):
    name = "lz4"
    version = Parameter("1.10.0", help="LZ4 version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/lz4/lz4.git,rev=v{version}"]
    srcdir = "{git[lz4]}/build/cmake"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("lz4")


TaskRegistry.get().add_task_class(Lz4)
