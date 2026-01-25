from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["Catch2"])
class Catch2(cmake.CMake):
    name = "catch2"
    version = Parameter("3.11.0", help="catch2 version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/catchorg/Catch2.git,rev=v{version}"]
    srcdir = "{git[Catch2]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


class Catch2Main(Task):
    name = "catch2/main"
    extends = "catch2"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("Catch2Main")


TaskRegistry.get().add_task_class(Catch2)
TaskRegistry.get().add_task_class(Catch2Main)
