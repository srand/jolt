from jolt import attributes, Parameter, Task
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Abseil(cmake.CMake):
    """ Abseil C++ Common Libraries """

    name = "abseil"
    version = Parameter("20250814.1")
    requires_git = ["git:url=https://github.com/abseil/abseil-cpp.git,rev={version}"]
    srcdir = "{git[abseil-cpp]}"


TaskRegistry.get().add_task_class(Abseil)
