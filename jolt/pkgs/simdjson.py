from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["simdjson"])
@cmake.requires()
class Simdjson(cmake.CMake):
    name = "simdjson"
    version = Parameter("4.2.4", help="simdjson version.")
    requires_git = ["git:url=https://github.com/simdjson/simdjson.git,rev=v{version}"]
    srcdir = "{git[simdjson]}"


TaskRegistry.get().add_task_class(Simdjson)
