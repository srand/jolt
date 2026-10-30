from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler, zlib
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_zlib")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class Libpng(cmake.CMake):
    name = "libpng"
    version = Parameter("1.6.59", help="libpng version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/pnggroup/libpng.git,rev=v{version}"]
    requires_zlib = ["virtual/zlib:pic={pic},shared={shared}"]
    srcdir = "{git[libpng]}"
    options = [
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "PNG_SHARED={shared[ON,OFF]}",
        "PNG_STATIC={shared[OFF,ON]}",
        "PNG_TESTS=OFF",
        "PNG_TOOLS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("libpng16{shared[,_static]}")
        else:
            artifact.cxxinfo.libraries.append("png16")


TaskRegistry.get().add_task_class(Libpng)
