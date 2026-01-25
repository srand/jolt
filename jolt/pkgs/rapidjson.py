from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
class RapidJSON(cmake.CMake):
    name = "rapidjson"
    version = Parameter("24b5e7a", help="rapidjson version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_git = ["git:url=https://github.com/Tencent/rapidjson.git,rev={version}"]
    srcdir = "{git[rapidjson]}"
    options = [
        "RAPIDJSON_BUILD_EXAMPLES=OFF",
        "RAPIDJSON_BUILD_TESTS=OFF",
    ]


TaskRegistry.get().add_task_class(RapidJSON)
