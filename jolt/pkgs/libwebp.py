from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["webpdemux", "webpmux", "webp", "sharpyuv"])
@attributes.requires("requires_compiler")
class Libwebp(cmake.CMake):
    """ WebP image codec """

    name = "libwebp"
    version = Parameter("1.6.0", help="libwebp version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/webmproject/libwebp.git,rev=v{version}"]
    srcdir = "{git[libwebp]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "WEBP_BUILD_ANIM_UTILS=OFF",
        "WEBP_BUILD_CWEBP=OFF",
        "WEBP_BUILD_DWEBP=OFF",
        "WEBP_BUILD_EXTRAS=OFF",
        "WEBP_BUILD_GIF2WEBP=OFF",
        "WEBP_BUILD_IMG2WEBP=OFF",
        "WEBP_BUILD_VWEBP=OFF",
        "WEBP_BUILD_WEBPINFO=OFF",
        "WEBP_BUILD_WEBPMUX=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Libwebp)
