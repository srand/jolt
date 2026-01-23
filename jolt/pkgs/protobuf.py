from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Protobuf(cmake.CMake):
    """
    Protocol buffers main package.

    For linking, require protobuf/lib and friends.
    """

    name = "protobuf"
    version = Parameter("33.2", help="Protobuf version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_abseil = ["abseil:shared={shared}"]
    requires_git = ["git:url=https://github.com/protocolbuffers/protobuf.git,rev=v{version}"]
    srcdir = "{git[protobuf]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_CXX_STANDARD=17",
        "protobuf_BUILD_TESTS=OFF",
        "protobuf_MSVC_STATIC_RUNTIME=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.msvcrt = "Dynamic"
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")


class ProtobufLib(Task):
    """ Protobuf library """

    name = "protobuf/lib"
    version = Parameter("33.2", help="Protobuf version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    extends = "protobuf:version={version},shared={shared}"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("protobuf")


class ProtobufLite(Task):
    """ Protobuf Lite library """

    name = "protobuf/lib-lite"
    version = Parameter("33.2", help="Protobuf version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    extends = "protobuf:version={version},shared={shared}"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("protobuf-lite")


class ProtobufLibProtoc(Task):
    """ Protobuf compiler library (libprotoc) """

    name = "protobuf/lib-compiler"
    version = Parameter("33.2", help="Protobuf version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    extends = "protobuf:version={version},shared={shared}"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("protoc")


TaskRegistry.get().add_task_class(Protobuf)
TaskRegistry.get().add_task_class(ProtobufLib)
TaskRegistry.get().add_task_class(ProtobufLite)
TaskRegistry.get().add_task_class(ProtobufLibProtoc)
