from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["ng-log"])
class NgLog(cmake.CMake):
    name = "ng-log"
    version = Parameter("0.8.2", help="ng_log version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/ng-log/ng-log.git,rev=v{version}"]
    srcdir = "{git[ng-log]}"
    options = ["BUILD_SHARED_LIBS={shared[ON,OFF]}"]


TaskRegistry.get().add_task_class(NgLog)
