from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["numa"])
@attributes.requires("requires_compiler")
class Numactl(autotools.Autotools):
    """ NUMA policy library and tools """

    name = "numactl"
    version = Parameter("2.0.19", help="numactl version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://github.com/numactl/numactl/releases/download/v{version}/numactl-{version}.tar.gz"]
    srcdir = "{fetch[src]}/numactl-{version}"
    options = [
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Numactl)
