from jolt import attributes, Parameter
from jolt.pkgs import blake3, cmake, compiler, fmt, zstd
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libs")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class Ccache(cmake.CMake):
    """ Compiler cache """

    name = "ccache"
    version = Parameter("4.14.2", help="ccache version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/ccache/ccache.git,rev=v{version}"]
    requires_libs = ["blake3", "fmt", "zstd"]
    """ Libraries used by ccache. Others are downloaded while configuring. """
    srcdir = "{git[ccache]}"
    options = [
        "ENABLE_DOCUMENTATION=OFF",
        "ENABLE_TESTING=OFF",
        "REDIS_STORAGE_BACKEND=OFF",
    ]


TaskRegistry.get().add_task_class(Ccache)
