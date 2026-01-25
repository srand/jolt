from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["flatbuffers"])
class Flatbuffers(cmake.CMake):
    name = "flatbuffers"
    version = Parameter("25.9.23", help="Flatbuffers version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/google/flatbuffers.git,rev=v{version}"]
    srcdir = "{git[flatbuffers]}"
    options = [
        "FLATBUFFERS_BUILD_FLATLIB={shared[OFF,ON]}",
        "FLATBUFFERS_BUILD_SHAREDLIB={shared[ON,OFF]}",
        "FLATBUFFERS_BUILD_TESTS=OFF",
    ]


TaskRegistry.get().add_task_class(Flatbuffers)
