from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["RapidJSON"])
@cmake.requires()
class RapidJSON(cmake.CMake):
    name = "rapidjson"
    version = Parameter("24b5e7a", help="rapidjson version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_git = ["git:url=https://github.com/Tencent/rapidjson.git,rev={version}"]
    srcdir = "{git[rapidjson]}"


TaskRegistry.get().add_task_class(RapidJSON)
