from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Spdlog(cmake.CMake):
    name = "spdlog"
    version = Parameter("1.16.0", help="spdlog version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/gabime/spdlog.git,rev=v{version}"]
    srcdir = "{git[spdlog]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "SPDLOG_BUILD_BENCH=OFF",
        "SPDLOG_BUILD_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("spdlog")


TaskRegistry.get().add_task_class(Spdlog)
