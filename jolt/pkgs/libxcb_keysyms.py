from jolt import attributes, Parameter
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
class XCBKeysyms(autotools.Autotools):
    name = "libxcb-keysyms"
    version = Parameter("0.4.1", help="XCB Keysyms version.")

    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/xcb-util-keysyms-{version}.tar.xz"]
    srcdir = "{fetch[src]}/xcb-util-keysyms-{version}"


TaskRegistry.get().add_task_class(XCBKeysyms)
