from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["wolfssl"])
@attributes.requires("requires_compiler")
class WolfSsl(cmake.CMake):
    """ Embedded TLS library """

    name = "wolfssl"
    version = Parameter("5.9.4", help="wolfSSL version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/wolfSSL/wolfssl.git,rev=v{version}-stable"]
    srcdir = "{git[wolfssl]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "WOLFSSL_CRYPT_TESTS=no",
        "WOLFSSL_EXAMPLES=no",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        if not self.shared:
            # The static library needs libm, also without --static
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("wolfssl.pc", "\nLibs.private:", "")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(WolfSsl)
