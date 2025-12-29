from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Catch2(cmake.CMake):
    name = "catch2"
    version = Parameter("3.11.0", help="catch2 version.")
    requires_git = ["git:url=https://github.com/catchorg/Catch2.git,rev=v{version}"]
    srcdir = "{git[Catch2]}"


TaskRegistry.get().add_task_class(Catch2)
