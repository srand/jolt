from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["zlib"])
@cmake.requires()
class Zlib(cmake.CMake):
    name = "zlib"
    version = Parameter("1.3.1", help="Zlib version.")
    requires_git = ["git:url=https://github.com/madler/zlib.git,rev=v{version}"]
    srcdir = "{git[zlib]}"


TaskRegistry.get().add_task_class(Zlib)
