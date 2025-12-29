from jolt import Parameter, attributes
from jolt.pkgs import cmake
from jolt.plugins import cmake, git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["sdl2"])
@cmake.requires()
class SDL(cmake.CMake):
    name = "sdl"
    version = Parameter("3.2.28", help="SDL version.")
    requires_git = ["git:url=https://github.com/libsdl-org/SDL.git"]
    srcdir = "{git[SDL]}"


TaskRegistry.get().add_task_class(SDL)
