from jolt import attributes, Parameter, Task
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Catch2(cmake.CMake):
    name = "catch2"
    version = Parameter("3.11.0", help="catch2 version.")
    requires_git = ["git:url=https://github.com/catchorg/Catch2.git,rev=v{version}"]
    srcdir = "{git[Catch2]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("Catch2")


class Catch2Main(Task):
    name = "catch2/main"
    extends = "catch2"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("Catch2Main")


TaskRegistry.get().add_task_class(Catch2)
TaskRegistry.get().add_task_class(Catch2Main)
