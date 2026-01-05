from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class GoogleTest(cmake.CMake):
    name = "googletest"
    version = Parameter("1.12.1", help="GoogleTest version.")
    requires_git = ["git:url=https://github.com/google/googletest.git,rev=release-{version}"]
    srcdir = "{git[googletest]}"


TaskRegistry.get().add_task_class(GoogleTest)
