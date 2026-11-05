from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import bzip2, cmake, compiler, zlib
from jolt.plugins import cmake, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_bzip2")
@attributes.requires("requires_src")
@attributes.requires("requires_zlib")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
@attributes.system
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

    @property
    def _library_suffix(self):
        """ MSVC builds name the static libraries pcre2-8-static.lib and so on. """
        return "-static" if self.system == "windows" and not self.shared else ""

    def run(self, deps, tools):
        super().run(deps, tools)
        if self._library_suffix:
            # The pkg-config files name the libraries without the suffix
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                for lib in ["8", "16", "32", "posix"]:
                    tools.replace_in_file(
                        f"libpcre2-{lib}.pc",
                        rf"-lpcre2-{lib}(?![\w-])",
                        f"-lpcre2-{lib}{self._library_suffix}",
                        regex=True)
        # The prefix in pcre2-config must follow the artifact when it is relocated
        with tools.cwd(tools.cmake().installdir, "jolt-prefix", "bin"):
            tools.replace_in_file("pcre2-config", "prefix=/jolt-prefix", 'prefix="$(cd "$(dirname "$0")/.." && pwd)"')

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        for lib in ["posix", "8", "16", "32"]:
            artifact.cxxinfo.libraries.append(f"pcre2-{lib}{self._library_suffix}")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
        else:
            artifact.cxxinfo.macros.append("PCRE2_STATIC")


TaskRegistry.get().add_task_class(Pcre2)
