from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Fmt(cmake.CMake):
    name = "fmt"
    version = Parameter("12.1.0", help="Fmt version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/fmtlib/fmt.git,rev={version}"]
    srcdir = "{git[fmt]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "FMT_TEST=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("fmt")


TaskRegistry.get().add_task_class(Fmt)
