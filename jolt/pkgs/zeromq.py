from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, libsodium, openssl
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_sodium_{system}")
@attributes.system
@cmake.requires()
@cmake.options("options_{system}")
@cmake.use_ninja()
@cxxinfo.publish(libraries=["zmq"])
@attributes.requires("requires_compiler")
class Libzmq(cmake.CMake):
    name = "libzmq"
    version = Parameter("4.3.5", help="ZeroMQ version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/zeromq/libzmq.git,rev=v{version}"]
    requires_sodium_darwin = ["libsodium:pic=true,shared={shared}"]
    """ Library used for CURVE security. """
    requires_sodium_linux = requires_sodium_darwin
    srcdir = "{git[libzmq]}"
    options = [
        "BUILD_SHARED={shared[ON,OFF]}",
        "BUILD_STATIC={shared[OFF,ON]}",
        "BUILD_TESTS=OFF",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
        "ENABLE_CURVE=ON",
        # GnuTLS would be found on the build host
        "WITH_TLS=OFF",
    ]
    options_darwin = [
        "WITH_LIBSODIUM=ON",
        "WITH_LIBSODIUM_STATIC={shared[OFF,ON]}",
    ]
    options_linux = options_darwin
    options_windows = ["WITH_LIBSODIUM=OFF"]
    """ libsodium is built with Autotools, which doesn't work on Windows. CURVE uses the built-in TweetNaCl. """

    def run(self, deps, tools):
        super().run(deps, tools)
        if not self.shared and self.system != "windows":
            # A static library is useless without libsodium, also without --static
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("libzmq.pc", "Requires.private:  libsodium", "Requires: libsodium")


@attributes.requires("requires_git")
@attributes.requires("requires_libzmq")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class Cppzmq(cmake.CMake):
    name = "cppzmq"
    version = Parameter("4.11.0", help="cppzmq version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/zeromq/cppzmq.git,rev=v{version}"]
    requires_libzmq = ["libzmq"]
    srcdir = "{git[cppzmq]}"
    options = ["CPPZMQ_BUILD_TESTS=OFF"]


TaskRegistry.get().add_task_class(Libzmq)
TaskRegistry.get().add_task_class(Cppzmq)
