from jolt import attributes, Parameter
from jolt.pkgs import boost
from jolt.plugins import cmake, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_boost")
@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["mstch"])
class MSTCH(cmake.CMake):
    name = "mstch"
    version = Parameter("1.0.2", help="MSTCH version.")
    requires_boost = ["boost"]
    requires_src = ["fetch:alias=src,url=https://github.com/no1msd/mstch/archive/refs/tags/{version}.tar.gz"]
    srcdir = "{fetch[src]}/mstch-{version}"
    options = [
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
    ]


TaskRegistry.get().add_task_class(MSTCH)
