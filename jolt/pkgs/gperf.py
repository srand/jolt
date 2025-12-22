from jolt import attributes
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
class GPerf(autotools.Autotools):
    name = "gperf"
    version = "3.3"
    requires_src = ["fetch:alias=src,url=http://ftpmirror.gnu.org/gperf/gperf-{version}.tar.gz"]
    srcdir = "{fetch[src]}/gperf-{version}"


TaskRegistry.get().add_task_class(GPerf)
