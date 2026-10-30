from jolt import attributes, Parameter
from jolt.pkgs import cmake, compiler
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class GFlags(cmake.CMake):
    name = "gflags"
    version = Parameter("2.3.1", help="gflags version.")
    options = ["BUILD_SHARED_LIBS=ON"]
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/gflags/gflags.git,rev=v{version}"]
    srcdir = "{git[gflags]}"


TaskRegistry.get().add_task_class(GFlags)
