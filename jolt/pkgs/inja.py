from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, nlohmann_json
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@attributes.requires("requires_json")
class Inja(cmake.CMake):
    name = "inja"
    version = Parameter("3.5.0", help="Inja version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/pantor/inja.git,rev=v{version}"]
    requires_json = ["nlohmann/json"]
    srcdir = "{git[inja]}"
    options = [
        "BUILD_TESTING={tests[ON,OFF]}",
        "INJA_USE_EMBEDDED_JSON=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(Inja)
