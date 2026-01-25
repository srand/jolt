from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["ogg"])
class Libogg(cmake.CMake):
    name = "libogg"
    version = Parameter("1.3.6", help="libogg version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/xiph/ogg.git,rev=v{version}"]
    srcdir = "{git[ogg]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
    ]


TaskRegistry.get().add_task_class(Libogg)
