from jolt import attributes, Parameter
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
@attributes.requires("requires_compiler")
class GPerf(autotools.Autotools):
    name = "gperf"
    version = Parameter("3.3", help="gperf version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_src = ["fetch:alias=src,url=http://ftpmirror.gnu.org/gperf/gperf-{version}.tar.gz"]
    srcdir = "{fetch[src]}/gperf-{version}"


TaskRegistry.get().add_task_class(GPerf)
