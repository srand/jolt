from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["uv"])
class Libuv(cmake.CMake):
    """ Cross-platform asynchronous I/O """

    name = "libuv"
    version = Parameter("1.53.0", help="libuv version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/libuv/libuv.git,rev=v{version}"]
    srcdir = "{git[libuv]}"
    options = [
        "BUILD_TESTING=OFF",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "LIBUV_BUILD_BENCH=OFF",
        "LIBUV_BUILD_SHARED={shared[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Libuv)
