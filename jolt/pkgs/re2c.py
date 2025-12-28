from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class Re2c(cmake.CMake):
    name = "re2c"
    version = Parameter("4.4", help="re2c version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/skvadrik/re2c.git,rev={version}"]
    srcdir = "{git[re2c]}"


TaskRegistry.get().add_task_class(Re2c)
