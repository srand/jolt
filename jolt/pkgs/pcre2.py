from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import bzip2, cmake, zlib
from jolt.plugins import cmake, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_bzip2")
@attributes.requires("requires_src")
@attributes.requires("requires_zlib")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["pcre2-posix", "pcre2-8", "pcre2-16", "pcre2-32"])
@attributes.requires("requires_compiler")
class Pcre2(cmake.CMake):
    """ Perl compatible regular expressions, for 8, 16 and 32-bit code units """

    name = "pcre2"
    version = Parameter("10.49", help="PCRE2 version.")
    jit = BooleanParameter(True, help="Enable just-in-time compilation.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_bzip2 = ["libbzip2"]
    """ Compression library used by pcre2grep. """
    requires_src = ["fetch:alias=src,url=https://github.com/PCRE2Project/pcre2/releases/download/pcre2-{version}/pcre2-{version}.tar.bz2"]
    requires_zlib = ["zlib"]
    """ Compression library used by pcre2grep. """
    srcdir = "{fetch[src]}/pcre2-{version}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_STATIC_LIBS={shared[OFF,ON]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "PCRE2_BUILD_PCRE2_16=ON",
        "PCRE2_BUILD_PCRE2_32=ON",
        "PCRE2_BUILD_TESTS=OFF",
        "PCRE2_SUPPORT_JIT={jit[ON,OFF]}",
        "PCRE2_SUPPORT_LIBBZ2=ON",
        "PCRE2_SUPPORT_LIBZ=ON",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        # The prefix in pcre2-config must follow the artifact when it is relocated
        with tools.cwd(tools.cmake().installdir, "jolt-prefix", "bin"):
            tools.replace_in_file("pcre2-config", "prefix=/jolt-prefix", 'prefix="$(cd "$(dirname "$0")/.." && pwd)"')

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
        else:
            artifact.cxxinfo.macros.append("PCRE2_STATIC")


TaskRegistry.get().add_task_class(Pcre2)
