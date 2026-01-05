from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Spdlog(cmake.CMake):
    name = "spdlog"
    version = Parameter("1.16.0", help="spdlog version.")
    requires_git = ["git:url=https://github.com/gabime/spdlog.git,rev=v{version}"]
    srcdir = "{git[spdlog]}"
    options = [
        "SPDLOG_BUILD_TESTS=OFF",
        "SPDLOG_BUILD_BENCH=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("stdlog")


TaskRegistry.get().add_task_class(Spdlog)
