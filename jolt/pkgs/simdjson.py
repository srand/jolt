from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Simdjson(cmake.CMake):
    name = "simdjson"
    version = Parameter("4.2.4", help="simdjson version.")
    requires_git = ["git:url=https://github.com/simdjson/simdjson.git,rev=v{version}"]
    srcdir = "{git[simdjson]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("simdjson")


TaskRegistry.get().add_task_class(Simdjson)
