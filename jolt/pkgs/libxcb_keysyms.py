from jolt import attributes, Parameter
from jolt.pkgs import cmake, libtool, libx11
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@attributes.requires("requires_libtool")
@attributes.requires("requires_x11")
class XCBKeysyms(autotools.Autotools):
    name = "libxcb-keysyms"
    version = Parameter("0.4.1", help="XCB Keysyms version.")

    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/lib/libxcb-keysyms.git,rev=xcb-util-keysyms-{version}"]
    requires_libtool = ["libtool"]
    requires_x11 = ["libx11"]
    src_dir = "{git[libxcb-keysyms]}"


TaskRegistry.get().add_task_class(XCBKeysyms)
