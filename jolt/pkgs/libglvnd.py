from jolt import attributes, Parameter
from jolt.pkgs import libx11
from jolt.tasks import TaskRegistry
from jolt.plugins import autotools, git, libtool, pkgconfig


@attributes.requires("requires_git")
@attributes.requires("requires_glproto")
@attributes.requires("requires_x11")
@attributes.requires("requires_xext")
@autotools.requires()
@pkgconfig.requires()
@libtool.relocate()
class Libglvnd(autotools.Autotools):
    name = "libglvnd"
    version = Parameter("1.7.0", help="libglvnd version.")

    requires_git = ["git:url=https://github.com/NVIDIA/libglvnd.git,rev=v{version}"]
    requires_glproto = ["glproto"]
    requires_x11 = ["libx11"]
    requires_xext = ["libxext"]
    srcdir = "{git[libglvnd]}"


TaskRegistry.get().add_task_class(Libglvnd)
