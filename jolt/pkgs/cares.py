from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class CAres(cmake.CMake):
    name = "c-ares"
    version = Parameter("1.34.6", help="c-ares version.")
    requires_git = ["git:url=https://github.com/c-ares/c-ares.git,depth=1,rev=v{version}"]
    srcdir = "{git[c-ares]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("cares")


TaskRegistry.get().add_task_class(CAres)
