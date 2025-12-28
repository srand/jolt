from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.cxxinfo(["protobuf"])
class Protobuf(cmake.CMake):
    name = "protobuf"
    version = Parameter("33.2", help="Protobuf version.")

    requires_abseil = ["abseil"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/protocolbuffers/protobuf.git,rev=v{version},submodules=true"]
    srcdir = "{git[protobuf]}"
    options = ["protobuf_BUILD_TESTS=OFF"]


TaskRegistry.get().add_task_class(Protobuf)
