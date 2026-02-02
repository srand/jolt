from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["re2"])
class RE2(cmake.CMake):
    name = "re2"
    version = Parameter("2025-11-05", help="re2 version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_abseil = ["abseil:shared={shared}"]
    requires_git = ["git:url=https://github.com/google/re2.git,rev={version}"]
    srcdir = "{git[re2]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "RE2_BUILD_TESTING=OFF",
    ]


TaskRegistry.get().add_task_class(RE2)
