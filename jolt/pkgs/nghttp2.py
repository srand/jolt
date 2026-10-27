from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["nghttp2"])
class Nghttp2(cmake.CMake):
    name = "nghttp2"
    version = Parameter("1.70.0", help="nghttp2 version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/nghttp2/nghttp2.git,rev=v{version}"]
    srcdir = "{git[nghttp2]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_STATIC_LIBS={shared[OFF,ON]}",
        "BUILD_TESTING=OFF",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "ENABLE_DOC=OFF",
        "ENABLE_LIB_ONLY=ON",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Nghttp2)
