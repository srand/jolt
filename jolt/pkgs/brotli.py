from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Brotli(cmake.CMake):
    name = "brotli"
    version = Parameter("1.2.0", help="Brotli version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/google/brotli.git,rev=v{version},submodules=true"]
    srcdir = "{git[brotli]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(Brotli)
