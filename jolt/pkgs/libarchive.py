from jolt import attributes, BooleanParameter, Parameter
from jolt.tasks import TaskRegistry
from jolt.plugins import cmake, git
from jolt.pkgs import bzip2, libexpat, lz4, openssl, xz, zlib, zstd


@attributes.requires("requires_bzip2")
@attributes.requires("requires_expat")
@attributes.requires("requires_lz4")
@attributes.requires("requires_openssl")
@attributes.requires("requires_xz")
@attributes.requires("requires_zlib")
@attributes.requires("requires_zstd")
@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Libarchive(cmake.CMake):
    name = "libarchive"
    version = Parameter("3.8.5", help="libarchive version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_bzip2 = ["libbzip2"]
    requires_git = ["git:url=https://github.com/libarchive/libarchive.git,rev=v{version}"]
    requires_expat = ["libexpat"]
    requires_lz4 = ["lz4"]
    requires_openssl = ["openssl"]
    requires_xz = ["xz"]
    requires_zlib = ["zlib"]
    requires_zstd = ["zstd"]
    srcdir = "{git[libarchive]}"
    options = [
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "ENABLE_TEST=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("archive")


TaskRegistry.get().add_task_class(Libarchive)
