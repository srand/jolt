from jolt import attributes, Parameter
from jolt.pkgs import cmake, compiler
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class Re2c(cmake.CMake):
    name = "re2c"
    version = Parameter("4.6", help="re2c version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/skvadrik/re2c.git,rev={version}"]
    srcdir = "{git[re2c]}"


TaskRegistry.get().add_task_class(Re2c)
