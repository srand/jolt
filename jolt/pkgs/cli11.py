from jolt import attributes, Parameter
from jolt.plugins import cmake, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
class CLI11(cmake.CMake):
    name = "cli11"
    version = Parameter("2.6.1", help="CLI11 version.")
    requires_src = ["fetch:alias=src,url=https://github.com/CLIUtils/CLI11/archive/refs/tags/v{version}.tar.gz"]
    srcdir = "{fetch[src]}/CLI11-{version}"
    options = [
        "CLI11_BUILD_EXAMPLES=OFF",
        "CLI11_BUILD_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(CLI11)
