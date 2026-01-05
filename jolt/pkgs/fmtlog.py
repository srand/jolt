from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class FmtLog(cmake.CMake):
    name = "fmtlog"
    version = Parameter("2.3.0", help="FmtLog version.")
    requires_git = ["git:url=https://github.com/MengRao/fmtlog.git,rev=v{version},submodules=true"]
    srcdir = "{git[fmtlog]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("fmtlog-static")


TaskRegistry.get().add_task_class(FmtLog)
