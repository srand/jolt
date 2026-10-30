from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class Brotli(cmake.CMake):
    name = "brotli"
    version = Parameter("1.2.1", help="Brotli version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/google/brotli.git,rev=v{version},submodules=true"]
    srcdir = "{git[brotli]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(Brotli)
