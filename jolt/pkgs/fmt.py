from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Fmt(cmake.CMake):
    name = "fmt"
    version = Parameter("12.1.0", help="Fmt version.")
    requires_git = ["git:url=https://github.com/fmtlib/fmt.git,rev={version}"]
    srcdir = "{git[fmt]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("fmt")


TaskRegistry.get().add_task_class(Fmt)
