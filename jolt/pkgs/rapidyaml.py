from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
class RapidYAML(cmake.CMake):
    name = "rapidyaml"
    version = Parameter("0.7.0", help="RapidYAML version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_src = ["git:url=https://github.com/biojppm/rapidyaml.git,rev=v{version},submodules=true"]
    srcdir = "{git[rapidyaml]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "RYML_BUILD_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("ryml")
        artifact.cxxinfo.libraries.append("c4core")


TaskRegistry.get().add_task_class(RapidYAML)
