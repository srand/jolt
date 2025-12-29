from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import boost, cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_boost")
@attributes.requires("requires_git")
@cmake.requires()
class Cereal(cmake.CMake):
    name = "cereal"
    version = Parameter("1.3.2", help="Cereal version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_boost = ["boost"]
    requires_git = ["git:url=https://github.com/USCiLab/cereal.git,rev=v{version}"]
    srcdir = "{git[cereal]}"
    options = [
        "BUILD_TESTS={tests[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(Cereal)
