from jolt import attributes, Parameter
from jolt.plugins import cmake, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
class Patchelf(cmake.CMake):
    name = "patchelf"
    version = Parameter("0.15.5", help="patchelf version.")
    requires_src = ["fetch:alias=src,url=https://github.com/NixOS/patchelf/archive/refs/tags/{version}.tar.gz"]
    srcdir = "{fetch[src]}/patchelf-{version}"


TaskRegistry.get().add_task_class(Patchelf)
