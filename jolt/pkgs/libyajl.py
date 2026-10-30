from jolt import attributes, Parameter
from jolt.pkgs import cmake, compiler
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires(version="3.31.1")
@attributes.requires("requires_compiler")
class Libyajl(cmake.CMake):
    name = "libyajl"
    version = Parameter("2.1.0", help="YAJL version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/lloyd/yajl.git,rev={version}"]
    srcdir = "{git[yajl]}"


TaskRegistry.get().add_task_class(Libyajl)
