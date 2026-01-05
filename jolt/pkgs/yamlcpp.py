from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class YamlCPP(cmake.CMake):
    name = "yaml-cpp"
    version = Parameter("bbf8bdb", help="yaml-cpp version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/jbeder/yaml-cpp.git,rev={version}"]
    srcdir = "{git[yaml-cpp]}"
    options = [
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
        "YAML_BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "YAML_BUILD_TOOLS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("yaml-cpp")


TaskRegistry.get().add_task_class(YamlCPP)
