from jolt import attributes, Parameter
from jolt.pkgs import xorg_macros, libxcb_proto
from jolt.plugins import autotools, git, libtool, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_xorg_macros")
@attributes.requires("requires_xcb_proto")
@pkgconfig.cxxinfo(["xcb"]) 
@autotools.requires()
@libtool.relocate()
class Libxcb(autotools.Autotools):
    name = "libxcb"
    version = Parameter("1.17.0", help="Libxcb version.")

    requires_git = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libxcb-{version}.tar.gz"]
    requires_xorg_macros = ["xorg/macros"]
    requires_xcb_proto = ["libxcb-proto"]
    srcdir = "{fetch[src]}/libxcb-{version}"


TaskRegistry.get().add_task_class(Libxcb)
