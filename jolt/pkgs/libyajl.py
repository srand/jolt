from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class Libyajl(cmake.CMake):
    name = "libyajl"
    version = Parameter("2.1.0", help="libyajl version.")
    requires_cmake = ["cmake:version=3.31.10"]
    requires_git = ["git:url=https://github.com/lloyd/yajl.git,rev={version}"]
    srcdir = "{git[yajl]}"


TaskRegistry.get().add_task_class(Libyajl)
