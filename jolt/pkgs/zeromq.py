from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import openssl
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Libzmq(cmake.CMake):
    name = "libzmq"
    version = Parameter("4.3.5", help="ZeroMQ version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/zeromq/libzmq.git,rev=v{version}"]
    srcdir = "{git[libzmq]}"
    options = [
        "BUILD_SHARED={shared[ON,OFF]}",
        "BUILD_TESTS=OFF",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("zmq")


@attributes.requires("requires_git")
@attributes.requires("requires_libzmq")
@cmake.requires()
@cmake.use_ninja()
class Cppzmq(cmake.CMake):
    name = "cppzmq"
    version = Parameter("4.11.0", help="cppzmq version.")
    requires_git = ["git:url=https://github.com/zeromq/cppzmq.git,rev=v{version}"]
    requires_libzmq = ["libzmq"]
    srcdir = "{git[cppzmq]}"
    options = ["CPPZMQ_BUILD_TESTS=OFF"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(Libzmq)
TaskRegistry.get().add_task_class(Cppzmq)
