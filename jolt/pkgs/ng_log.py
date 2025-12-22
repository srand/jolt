from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class NgLog(cmake.CMake):
    name = "ng-log"
    version = Parameter("0.8.2", help="ng_log version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/ng-log/ng-log.git,rev=v{version}"]
    srcdir = "{git[ng-log]}"


TaskRegistry.get().add_task_class(NgLog)
