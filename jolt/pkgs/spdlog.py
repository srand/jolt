from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["spdlog"])
class Spdlog(cmake.CMake):
    name = "spdlog"
    version = Parameter("1.16.0", help="spdlog version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/gabime/spdlog.git,rev=v{version}"]
    srcdir = "{git[spdlog]}"
    options = [
        "SPDLOG_BUILD_TESTS=OFF",
        "SPDLOG_BUILD_BENCH=OFF",
    ]


TaskRegistry.get().add_task_class(Spdlog)
