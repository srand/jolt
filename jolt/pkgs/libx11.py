from jolt import attributes, Parameter, Task
from jolt.pkgs import xorg_macros, libxcb, libx11
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_xorg_macros")
class Libx11(autotools.Autotools):
    name = "libx11"
    version = Parameter("1.8.12", help="Libx11 version.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/lib/libx11.git,rev=libX11-{version}"]
    requires_xorg_macros = ["xorg/macros"]
    srcdir = "{git[libx11]}"


@attributes.requires("requires_libx11")
@attributes.requires("requires_libxcb")
@attributes.common_metadata()
class LibX11Xcb(Task):
    """
    Republishes libx11 and libxcb as libx11-xcb for compatibility.

    Mainly, prefix must be shared in order to build mesa.
    """
    name = "libx11-xcb"
    requires_libx11 = ["libx11"]
    requires_libxcb = ["libxcb"]
    selfsustained = True

    def run(self, deps, tools):
        self.x11 = deps["libx11"]
        self.xcb = deps["libxcb"]

    def publish(self, artifact, tools):
        with tools.cwd(self.x11.path):
            artifact.collect("*", symlinks=True)
        with tools.cwd(self.xcb.path):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(Libx11)
TaskRegistry.get().add_task_class(LibX11Xcb)
