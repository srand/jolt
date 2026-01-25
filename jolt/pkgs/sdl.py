from jolt import BooleanParameter, Parameter, attributes
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
class SDL(cmake.CMake):
    name = "sdl"
    version = Parameter("3.2.28", help="SDL version.")
    shared = BooleanParameter(False, help="Build shared library")
    requires_git = ["git:url=https://github.com/libsdl-org/SDL.git"]
    srcdir = "{git[SDL]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("SDL2{shared[,-static]}")
        else:
            artifact.cxxinfo.libraries.append("SDL2")


TaskRegistry.get().add_task_class(SDL)
