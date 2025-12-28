from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.cxxinfo(["yaml-cpp"])
class YamlCPP(cmake.CMake):
    name = "yaml-cpp"
    version = Parameter("bbf8bdb", help="yaml-cpp version.")
    shared = BooleanParameter(True, help="Build shared libraries.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/jbeder/yaml-cpp.git,rev={version}"]
    srcdir = "{git[yaml-cpp]}"
    options = [
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
        "YAML_BUILD_SHARED_LIBS={shared[ON,OFF]}"
        "YAML_BUILD_TOOLS=OFF"
    ]


TaskRegistry.get().add_task_class(YamlCPP)
