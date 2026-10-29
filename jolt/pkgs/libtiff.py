from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, libjpeg_turbo, libwebp, xz, zlib, zstd
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libs")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["tiff"])
@attributes.requires("requires_compiler")
class Libtiff(cmake.CMake):
    """ TIFF image library """

    name = "libtiff"
    version = Parameter("4.7.2", help="LibTIFF version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://gitlab.com/libtiff/libtiff.git,rev=v{version}"]
    requires_libs = [
        "libjpeg-turbo:pic={pic},shared={shared}",
        "libwebp:pic={pic},shared={shared}",
        "virtual/zlib:pic={pic},shared={shared}",
        "xz:shared={shared}",
        "zstd:pic={pic},shared={shared}",
    ]
    """ Libraries of the supported compression methods. """
    srcdir = "{git[libtiff]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "jbig=OFF",
        "jpeg=ON",
        "lerc=OFF",
        "libdeflate=OFF",
        "lzma=ON",
        "tiff-contrib=OFF",
        "tiff-docs=OFF",
        "tiff-tests=OFF",
        "tiff-tools=OFF",
        "webp=ON",
        "zlib=ON",
        "zstd=ON",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Libtiff)
