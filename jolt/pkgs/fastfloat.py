from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class FastFloat(cmake.CMake):
    name = "fastfloat"
    version = Parameter("8.1.0", help="fastfloat version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/fastfloat/fast_float.git,rev=v{version}"]
    srcdir = "{git[fast_float]}"


TaskRegistry.get().add_task_class(FastFloat)
