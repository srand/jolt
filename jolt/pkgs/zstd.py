from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class Zstd(cmake.CMake):
    name = "zstd"
    version = Parameter("ebc93b0", help="zstd version.")

    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/facebook/zstd.git,rev={version}"]
    srcdir = "{git[zstd]}"


TaskRegistry.get().add_task_class(Zstd)
