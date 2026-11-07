from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, mbedtls
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_tls_{tls[on,off]}")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["nng"])
@attributes.requires("requires_compiler")
class Nng(cmake.CMake):
    """ Lightweight messaging library, the successor of nanomsg """

    name = "nng"
    version = Parameter("2.1.0", help="NNG version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    tls = BooleanParameter(False, help="Enable TLS support.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/nanomsg/nng.git,rev=v{version}"]
    requires_tls_on = ["mbedtls:pic={pic},shared={shared}"]
    srcdir = "{git[nng]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "NNG_ENABLE_TLS={tls[ON,OFF]}",
        "NNG_TESTS=OFF",
        "NNG_TLS_ENGINE={tls[mbed,none]}",
        "NNG_TOOLS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
        else:
            artifact.cxxinfo.macros.append("NNG_STATIC_LIB")


TaskRegistry.get().add_task_class(Nng)
