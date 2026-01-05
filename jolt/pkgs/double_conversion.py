from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class DoubleConversion(cmake.CMake):
    name = "double-conversion"
    version = Parameter("3.4.0", help="double_conversion version.")
    options = ["BUILD_SHARED_LIBS=ON"]
    requires_git = ["git:url=https://github.com/google/double-conversion.git,rev=v{version}"]
    srcdir = "{git[double-conversion]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("double-conversion")


TaskRegistry.get().add_task_class(DoubleConversion)
