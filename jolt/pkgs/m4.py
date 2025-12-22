from jolt import attributes
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
class M4(autotools.Autotools):
    name = "m4"
    version = "1.4.20"
    requires_src = ["fetch:alias=src,url=http://ftpmirror.gnu.org/m4/m4-{version}.tar.xz"]
    srcdir = "{fetch[src]}/m4-{version}"


TaskRegistry.get().add_task_class(M4)
