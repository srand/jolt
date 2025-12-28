from jolt import attributes, Parameter
from jolt.pkgs import libx11, xorg_macros
from jolt.plugins import autotools, git, libtool, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_xproto")
@attributes.requires("requires_xorg_macros")
@pkgconfig.cxxinfo(["xshmfence"])
@pkgconfig.requires()
@autotools.requires()
@libtool.relocate()
class Libxshmfence(autotools.Autotools):
    name = "libxshmfence"
    version = Parameter("1.3.3", help="Libxshmfence version.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/lib/libxshmfence.git,rev=libxshmfence-{version}"]
    requires_xproto = ["xproto"]
    requires_xorg_macros = ["xorg/macros"]
    srcdir = "{git[libxshmfence]}"


TaskRegistry.get().add_task_class(Libxshmfence)
