from jolt import attributes, Parameter
from jolt.pkgs import xorg_macros
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_xorg_macros")
class LibxcbProto(autotools.Autotools):
    name = "libxcb-proto"
    version = Parameter("1.17.0", help="Libxcb_proto version.")
    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/proto/xcbproto.git,rev=xcb-proto-{version}"]
    requires_xorg_macros = ["xorg/macros"]
    srcdir = "{git[xcbproto]}"
    options = ["--with-xorg-macros={deps[xorg/macros]}"]


TaskRegistry.get().add_task_class(LibxcbProto)
