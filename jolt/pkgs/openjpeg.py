from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["openjp2"])
@attributes.requires("requires_compiler")
class OpenJpeg(cmake.CMake):
    """ JPEG 2000 codec library """

    name = "openjpeg"
    version = Parameter("2.5.4", help="OpenJPEG version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/uclouvain/openjpeg.git,rev=v{version}"]
    srcdir = "{git[openjpeg]}"
    # The codec executables would use the image libraries of the build host.
    options = [
        "BUILD_CODEC=OFF",
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_STATIC_LIBS={shared[OFF,ON]}",
        "BUILD_TESTING=OFF",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        if not self.shared:
            # Without OPJ_STATIC, the headers declare the functions as imported
            # from a DLL on Windows, and the static library needs libm. Consumers
            # rarely pass --static to pkg-config.
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("libopenjp2.pc", "\nLibs.private:", "")
                tools.replace_in_file("libopenjp2.pc", "\nCflags.private: -DOPJ_STATIC", "")
                tools.replace_in_file("libopenjp2.pc", "Cflags: -I${{includedir}}", "Cflags: -I${{includedir}} -DOPJ_STATIC")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include/openjpeg-{_major_minor}")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
        else:
            artifact.cxxinfo.macros.append("OPJ_STATIC")

    @property
    def _major_minor(self):
        return ".".join(str(self.version).split(".")[:2])


TaskRegistry.get().add_task_class(OpenJpeg)
