from jolt import attributes, Parameter
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.cxxinfo(["liblzma"])
class Xz(cmake.CMake):
    name = "xz"
    version = Parameter("5.8.2", help="xz version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/tukaani-project/xz.git,rev=v{version}"]
    srcdir = "{git[xz]}"


TaskRegistry.get().add_task_class(Xz)
