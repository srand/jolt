from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class YamlCPP(cmake.CMake):
    name = "yaml-cpp"
    version = Parameter("0.8.0", help="yaml-cpp version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/jbeder/yaml-cpp.git,rev={version}"]
    srcdir = "{git[yaml-cpp]}"


TaskRegistry.get().add_task_class(YamlCPP)
