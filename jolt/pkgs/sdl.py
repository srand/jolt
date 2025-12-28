from jolt import Parameter, attributes
from jolt.pkgs import cmake
from jolt.plugins import cmake, git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.cxxinfo(["sdl2"])
class SDL(cmake.CMake):
    name = "sdl"
    version = Parameter("3.2.28", help="SDL version.")
    requires_git = ["git:url=https://github.com/libsdl-org/SDL.git"]
    requires_cmake = ["cmake"]
    srcdir = "{git[SDL]}"


TaskRegistry.get().add_task_class(SDL)
