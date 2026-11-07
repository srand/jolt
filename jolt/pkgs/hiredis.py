from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, ssl
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ssl_{ssl[on,off]}")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["hiredis"])
@attributes.requires("requires_compiler")
class Hiredis(cmake.CMake):
    """ Minimalistic C client library for Redis """

    name = "hiredis"
    version = Parameter("1.5.0", help="hiredis version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    ssl = BooleanParameter(False, help="Enable SSL support.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/redis/hiredis.git,rev=v{version}"]
    requires_ssl_on = ["virtual/ssl:shared={shared}"]
    srcdir = "{git[hiredis]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "DISABLE_TESTS=ON",
        "ENABLE_NUGET=OFF",
        "ENABLE_SSL={ssl[ON,OFF]}",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        if self.ssl:
            # Let pkg-config find OpenSSL, which is not installed on the system.
            # A static library is useless without it, also without --static.
            requires = "Requires.private" if self.shared else "Requires"
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("hiredis_ssl.pc", "Libs.private: -lssl -lcrypto", requires + ": openssl")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.ssl:
            artifact.cxxinfo.libraries.append("hiredis_ssl")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Hiredis)
