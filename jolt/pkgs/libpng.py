from jolt import attributes, BooleanParameter, Parameter
from jolt import filesystem as fs
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

    def run(self, deps, tools):
        super().run(deps, tools)
        if self.system == "windows":
            # libpng only installs libpng.pc on Unix-like systems, but
            # freetype2.pc requires it
            pcdir = tools.expand_path(fs.path.join(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"))
            tools.mkdir(pcdir)
            tools.write_file(
                fs.path.join(pcdir, "libpng.pc"),
                """
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}
libdir=${{prefix}}/lib
includedir=${{prefix}}/include/libpng16

Name: libpng
Description: Loads and saves PNG files
Version: {version}
Requires: zlib
Libs: -L${{libdir}} -llibpng16{shared[,_static]}
Cflags: -I${{includedir}}
""")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("libpng16{shared[,_static]}")
        else:
            artifact.cxxinfo.libraries.append("png16")


TaskRegistry.get().add_task_class(Libpng)
