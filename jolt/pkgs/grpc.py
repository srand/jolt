from jolt import attributes, Parameter
from jolt.pkgs import abseil, cares, cmake, protobuf, re2, zlib
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_cares")
@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@attributes.requires("requires_protobuf")
@attributes.requires("requires_re2")
@attributes.requires("requires_zlib")
class Grpc(cmake.CMake):
    name = "grpc"
    version = Parameter("1.76.0", help="Grpc version.")
    requires_abseil = ["abseil"]
    requires_cares = ["c-ares"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/grpc/grpc.git,depth=1,rev=v{version},submodules=true"]
    requires_protobuf = ["protobuf"]
    requires_re2 = ["re2"]
    requires_zlib = ["zlib"]
    srcdir = "{git[grpc]}"
    options = [
        "gRPC_BUILD_TESTS=OFF",
        "gRPC_ABSL_PROVIDER=package",
        "gRPC_CARES_PROVIDER=package",
        "gRPC_PROTOBUF_PROVIDER=package",
        "gRPC_RE2_PROVIDER=package",
        "gRPC_ZLIB_PROVIDER=package",
    ]


TaskRegistry.get().add_task_class(Grpc)
