from jolt import BooleanParameter, Parameter, attributes
from jolt.pkgs import alsa_lib, cmake, libusb, xorg
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_{system}")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class SDL(cmake.CMake):
    name = "sdl"
    version = Parameter("3.4.18", help="SDL version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/libsdl-org/SDL.git,rev=release-{version}"]
    requires_linux = ["alsa-lib", "libusb:shared={shared}", "xorg/libxtst"]
    """ Libraries that SDL is built against on Linux. ALSA and XTest are loaded at runtime. """
    srcdir = "{git[SDL]}"
    options = [
        "SDL_HIDAPI_LIBUSB_SHARED={shared[ON,OFF]}",
        "SDL_SHARED={shared[ON,OFF]}",
        "SDL_STATIC={shared[OFF,ON]}",
        "SDL_TESTS=OFF",
    ]

    def run(self, deps, tools):
        if self.system != "linux":
            return super().run(deps, tools)
        # SDL only uses the include directory of the X11 library, not those of extensions
        with tools.environ(
            CFLAGS=tools.run("pkg-config --cflags xtst").strip() + " " + tools.getenv("CFLAGS", ""),
        ):
            super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("SDL3{shared[,-static]}")
        else:
            artifact.cxxinfo.libraries.append("SDL3")


TaskRegistry.get().add_task_class(SDL)
