from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["yaml-cpp"])
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


TaskRegistry.get().add_task_class(YamlCPP)
