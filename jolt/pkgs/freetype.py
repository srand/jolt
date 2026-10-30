from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler, libpng, zlib
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libs")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(incpaths=["include/freetype2"], libraries=["freetype"])
@attributes.requires("requires_compiler")
class Freetype(cmake.CMake):
    """ Font rendering library """

    name = "freetype"
    version = Parameter("2.15.0", help="FreeType version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://gitlab.freedesktop.org/freetype/freetype.git,rev=VER-{_version}"]
    requires_libs = [
        "libpng:pic={pic},shared={shared}",
        "virtual/zlib:pic={pic},shared={shared}",
    ]
    """ Libraries for PNG glyphs and compressed fonts. """
    srcdir = "{git[freetype]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "FT_DISABLE_BROTLI=ON",
        "FT_DISABLE_BZIP2=ON",
        "FT_DISABLE_HARFBUZZ=ON",
        "FT_REQUIRE_PNG=ON",
        "FT_REQUIRE_ZLIB=ON",
    ]

    @property
    def _version(self):
        return str(self.version).replace(".", "-")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Freetype)
