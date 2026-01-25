from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["cares"])
class CAres(cmake.CMake):
    name = "c-ares"
    version = Parameter("1.34.6", help="c-ares version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/c-ares/c-ares.git,rev=v{version}"]
    srcdir = "{git[c-ares]}"
    options = [
        "CARES_SHARED={shared[ON,OFF]}",
        "CARES_STATIC={shared[OFF,ON]}",
        "CARES_BUILD_TESTS=OFF",
    ]


TaskRegistry.get().add_task_class(CAres)
