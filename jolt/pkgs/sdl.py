from jolt import BooleanParameter, Parameter, attributes
from jolt.pkgs import alsa_lib, cmake, compiler, libglvnd, libusb, xorg
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_{system}")
@attributes.system
@cmake.requires()
@cmake.options("options_{system}")
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class SDL(cmake.CMake):
    name = "sdl"
    version = Parameter("3.4.18", help="SDL version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/libsdl-org/SDL.git,rev=release-{version}"]
    requires_linux = ["alsa-lib", "libglvnd", "libusb:shared={shared}", "xorg/libxrandr", "xorg/libxtst"]
    """ Libraries that SDL is built against on Linux. ALSA, OpenGL and the X11 libraries are loaded at runtime. """
    srcdir = "{git[SDL]}"
    options = [
        "SDL_HIDAPI_LIBUSB_SHARED={shared[ON,OFF]}",
        "SDL_SHARED={shared[ON,OFF]}",
        "SDL_STATIC={shared[OFF,ON]}",
        "SDL_TESTS=OFF",
    ]
    options_linux = [
        "SDL_X11_XCURSOR=OFF",
        "SDL_X11_XSCRNSAVER=OFF",
    ]
    """ Features of libraries that there are no packages for, which would come from the host. """

    def run(self, deps, tools):
        if self.system != "linux":
            return super().run(deps, tools)
        # SDL only uses the include directory of the X11 library, not those of extensions
        with tools.environ(
            CFLAGS=tools.run("pkg-config --cflags gl xrandr xtst").strip() + " " + tools.getenv("CFLAGS", ""),
        ):
            super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("SDL3{shared[,-static]}")
        else:
            artifact.cxxinfo.libraries.append("SDL3")


TaskRegistry.get().add_task_class(SDL)
