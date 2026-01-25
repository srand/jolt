from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["simdjson"])
class Simdjson(cmake.CMake):
    name = "simdjson"
    version = Parameter("4.2.4", help="simdjson version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/simdjson/simdjson.git,rev=v{version}"]
    srcdir = "{git[simdjson]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(Simdjson)
