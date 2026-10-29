from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class Cxxopts(cmake.CMake):
    """ Command line option parser for C++ """

    name = "cxxopts"
    version = Parameter("3.3.1", help="cxxopts version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/jarro2783/cxxopts.git,rev=v{version}"]
    srcdir = "{git[cxxopts]}"
    options = [
        "CXXOPTS_BUILD_EXAMPLES=OFF",
        "CXXOPTS_BUILD_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Cxxopts)
