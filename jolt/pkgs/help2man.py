from jolt import attributes, Parameter
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
class Help2Man(autotools.Autotools):
    name = "help2man"
    version = Parameter("1.49.3", help="help2man version.")
    requires_src = ["fetch:alias=src,url=http://ftpmirror.gnu.org/help2man/help2man-{version}.tar.xz"]
    srcdir = "{fetch[src]}/help2man-{version}"


TaskRegistry.get().add_task_class(Help2Man)
