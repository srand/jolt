from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class NlohmannJson(cmake.CMake):
    name = "nlohmann/json"
    version = Parameter("3.12.0", help="nlohmann/json version.")

    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/nlohmann/json.git,rev=v{version}"]
    srcdir = "{git[json]}"


TaskRegistry.get().add_task_class(NlohmannJson)
