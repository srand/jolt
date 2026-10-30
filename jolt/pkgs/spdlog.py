from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["spdlog"])
@attributes.requires("requires_compiler")
class Spdlog(cmake.CMake):
    name = "spdlog"
    version = Parameter("1.17.0", help="spdlog version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/gabime/spdlog.git,rev=v{version}"]
    srcdir = "{git[spdlog]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "SPDLOG_BUILD_BENCH=OFF",
        "SPDLOG_BUILD_TESTS=OFF",
    ]


TaskRegistry.get().add_task_class(Spdlog)
