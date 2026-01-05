from jolt import attributes, Parameter, Task
from jolt.pkgs import abseil, cares, cmake, nasm, openssl, protobuf, re2, zlib
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_cares")
@attributes.requires("requires_git")
@attributes.requires("requires_nasm_{system}")
@attributes.requires("requires_protobuf")
@attributes.requires("requires_re2")
@attributes.requires("requires_ssl")
@attributes.requires("requires_zlib")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Grpc(cmake.CMake):
    name = "grpc"
    version = Parameter("1.76.0", help="Grpc version.")
    generator = "Ninja"
    requires_abseil = ["abseil"]
    requires_cares = ["c-ares"]
    requires_git = ["git:url=https://github.com/grpc/grpc.git,depth=1,path={buildroot}/git_grpc,rev=v{version},submodules=true"]
    requires_nasm_windows = ["nasm"]
    requires_protobuf = ["protobuf"]
    requires_re2 = ["re2"]
    requires_ssl = ["virtual/ssl"]
    requires_zlib = ["zlib"]
    srcdir = "{git[grpc]}"
    options = [
        "CMAKE_CXX_STANDARD=17",
        "gRPC_ABSL_PROVIDER=package",
        "gRPC_BUILD_TESTS=OFF",
        "gRPC_CARES_PROVIDER=package",
        "gRPC_MSVC_STATIC_RUNTIME=OFF",
        "gRPC_PROTOBUF_PROVIDER=package",
        "gRPC_RE2_PROVIDER=package",
        "gRPC_SSL_PROVIDER=package",
        "gRPC_ZLIB_PROVIDER=package",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.crt = "Dynamic"
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")


class GrpcC(Task):
    name = "grpc/c"
    extends = "grpc"

    def publish(self, artifact, tools):
        artifact.cxxinfo.crt = "Dynamic"
        artifact.cxxinfo.libraries.append("grpc")


class GrpcCXX(Task):
    name = "grpc/c++"
    extends = "grpc"

    def publish(self, artifact, tools):
        artifact.cxxinfo.crt = "Dynamic"
        artifact.cxxinfo.libraries.append("grpc++")


TaskRegistry.get().add_task_class(Grpc)
TaskRegistry.get().add_task_class(GrpcC)
TaskRegistry.get().add_task_class(GrpcCXX)
