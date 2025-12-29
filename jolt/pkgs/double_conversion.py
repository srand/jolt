from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class DoubleConversion(cmake.CMake):
    name = "double-conversion"
    version = Parameter("3.4.0", help="double_conversion version.")
    options = ["BUILD_SHARED_LIBS=ON"]
    requires_git = ["git:url=https://github.com/google/double-conversion.git,rev=v{version}"]
    srcdir = "{git[double-conversion]}"


TaskRegistry.get().add_task_class(DoubleConversion)
