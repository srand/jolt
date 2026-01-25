from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cmake.options("options_pic_{pic[on,off]}")
@cxxinfo.publish(libraries=["lzma"])
class Xz(cmake.CMake):
    name = "xz"
    version = Parameter("5.8.2", help="xz version.")
    pic = BooleanParameter(True, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/tukaani-project/xz.git,rev=v{version}"]
    srcdir = "{git[xz]}"
    options_pic_on = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE=ON",
    ]


TaskRegistry.get().add_task_class(Xz)
