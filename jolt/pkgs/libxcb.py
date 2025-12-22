from jolt import attributes, Parameter
from jolt.pkgs import xorg_macros, libxcb_proto
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_xorg_macros")
@attributes.requires("requires_xcb_proto")
class Libxcb(autotools.Autotools):
    name = "libxcb"
    version = Parameter("1.17.0", help="Libxcb version.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/lib/libxcb.git,rev=libxcb-{version}"]
    requires_xorg_macros = ["xorg/macros"]
    requires_xcb_proto = ["libxcb-proto"]
    srcdir = "{git[libxcb]}"


TaskRegistry.get().add_task_class(Libxcb)
