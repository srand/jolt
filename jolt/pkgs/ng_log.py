from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class NgLog(cmake.CMake):
    name = "ng-log"
    version = Parameter("0.8.2", help="ng_log version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/ng-log/ng-log.git,rev=v{version}"]
    srcdir = "{git[ng-log]}"
    options = ["BUILD_SHARED_LIBS={shared[ON,OFF]}"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("ng-log")


TaskRegistry.get().add_task_class(NgLog)
