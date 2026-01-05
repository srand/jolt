from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class NlohmannJson(cmake.CMake):
    name = "nlohmann/json"
    version = Parameter("3.12.0", help="nlohmann/json version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_git = ["git:url=https://github.com/nlohmann/json.git,rev=v{version}"]
    srcdir = "{git[json]}"
    options = [
        "JSON_BuildTests={tests[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(NlohmannJson)
