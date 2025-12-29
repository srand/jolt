from jolt import attributes, Parameter
from jolt.pkgs import cmake, gflags
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_gflags")
@attributes.requires("requires_git")
@cmake.requires()
class Glog(cmake.CMake):
    name = "glog"
    version = Parameter("0.7.1", help="glog version.")
    options = ["BUILD_SHARED_LIBS=ON"]
    requires_gflags = ["gflags"]
    requires_git = ["git:url=https://github.com/google/glog.git,rev=v{version}"]
    srcdir = "{git[glog]}"

    def run(self, deps, tools):
        self.warning("GLog is deprecated and unmaintained. Consider using ng-log instead.")
        super().run(deps, tools)


TaskRegistry.get().add_task_class(Glog)
