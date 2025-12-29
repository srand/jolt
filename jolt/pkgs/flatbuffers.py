from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["flatbuffers"])
class Flatbuffers(cmake.CMake):
    name = "flatbuffers"
    version = Parameter("25.9.23", help="Flatbuffers version.")

    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/google/flatbuffers.git,rev=v{version}"]
    srcdir = "{git[flatbuffers]}"


TaskRegistry.get().add_task_class(Flatbuffers)
