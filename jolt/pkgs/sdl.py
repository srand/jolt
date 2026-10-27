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
    version = Parameter("3.4.18", help="SDL version.")
    shared = BooleanParameter(False, help="Build shared library")
    requires_git = ["git:url=https://github.com/libsdl-org/SDL.git,rev=release-{version}"]
    srcdir = "{git[SDL]}"
    options = [
        "SDL_SHARED={shared[ON,OFF]}",
        "SDL_STATIC={shared[OFF,ON]}",
        "SDL_X11_XTEST=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("SDL3{shared[,-static]}")
        else:
            artifact.cxxinfo.libraries.append("SDL3")


TaskRegistry.get().add_task_class(SDL)
