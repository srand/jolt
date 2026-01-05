from jolt import attributes, Parameter
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Xz(cmake.CMake):
    name = "xz"
    version = Parameter("5.8.2", help="xz version.")
    requires_git = ["git:url=https://github.com/tukaani-project/xz.git,rev=v{version}"]
    srcdir = "{git[xz]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("lzma")


TaskRegistry.get().add_task_class(Xz)
