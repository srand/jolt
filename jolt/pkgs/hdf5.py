from jolt import attributes, Parameter
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@attributes.requires("requires_git")
@cmake.requires()
@attributes.requires("requires_compiler")
class HDF5(cmake.CMake):
    name = "hdf5"
    version = Parameter("2.2.0", help="HDF5 version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/HDFGroup/hdf5.git,rev={version}"]
    srcdir = "{git[hdf5]}"
    options = [
        "BUILD_SHARED_LIBS=ON",
        "HDF5_BUILD_EXAMPLES=OFF",
    ]


TaskRegistry.get().add_task_class(HDF5)
