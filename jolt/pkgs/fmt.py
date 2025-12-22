from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class Fmt(cmake.CMake):
    name = "fmt"
    version = Parameter("12.1.0", help="Fmt version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/fmtlib/fmt.git,rev={version}"]
    srcdir = "{git[fmt]}"


TaskRegistry.get().add_task_class(Fmt)
