from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Libogg(cmake.CMake):
    name = "libogg"
    version = Parameter("1.3.6", help="libogg version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_git = ["git:url=https://github.com/xiph/ogg.git,rev=v{version}"]
    srcdir = "{git[ogg]}"


TaskRegistry.get().add_task_class(Libogg)
