from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.cxxinfo(["fmtlog"])
class FmtLog(cmake.CMake):
    name = "fmtlog"
    version = Parameter("2.3.0", help="FmtLog version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/MengRao/fmtlog.git,rev=v{version},submodules=true"]
    srcdir = "{git[fmtlog]}"


TaskRegistry.get().add_task_class(FmtLog)
