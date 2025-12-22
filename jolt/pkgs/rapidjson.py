from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class RapidJSON(cmake.CMake):
    name = "rapidjson"
    version = Parameter("1.1.0", help="rapidjson version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/Tencent/rapidjson.git,rev=v{version}"]
    srcdir = "{git[rapidjson]}"


TaskRegistry.get().add_task_class(RapidJSON)
