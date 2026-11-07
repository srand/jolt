from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, ssl, zlib
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ssl_{ssl[on,off]}")
@attributes.requires("requires_zlib_{zlib[on,off]}")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["capnp-rpc", "capnp", "kj-async", "kj"])
@attributes.requires("requires_compiler")
class CapnProto(cmake.CMake):
    """ Data interchange format and capability-based RPC system """

    name = "capnproto"
    version = Parameter("1.5.0", help="Cap'n Proto version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    ssl = BooleanParameter(False, help="Enable OpenSSL support.")
    zlib = BooleanParameter(False, help="Enable zlib support.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/capnproto/capnproto.git,rev=v{version}"]
    requires_ssl_on = ["virtual/ssl:pic={pic},shared={shared}"]
    requires_zlib_on = ["zlib:pic={pic},shared={shared}"]
    srcdir = "{git[capnproto]}/c++"
    # OpenSSL and zlib are used if found on the build host unless disabled.
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_TESTING=OFF",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "WITH_OPENSSL={ssl[ON,OFF]}",
        "WITH_ZLIB={zlib[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(CapnProto)
