from jolt import attributes, Parameter
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
class Texinfo(autotools.Autotools):
    name = "texinfo"
    version = Parameter("7.3", help="Texinfo version.")
    requires_src = ["fetch:alias=src,url=http://ftpmirror.gnu.org/texinfo/texinfo-{version}.tar.xz"]
    srcdir = "{fetch[src]}/texinfo-{version}"


TaskRegistry.get().add_task_class(Texinfo)
