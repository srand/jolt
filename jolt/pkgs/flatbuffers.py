from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Flatbuffers(cmake.CMake):
    name = "flatbuffers"
    version = Parameter("25.9.23", help="Flatbuffers version.")
    requires_git = ["git:url=https://github.com/google/flatbuffers.git,rev=v{version}"]
    srcdir = "{git[flatbuffers]}"
    options = ["FLATBUFFERS_BUILD_TESTS=OFF"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("flatbuffers")


TaskRegistry.get().add_task_class(Flatbuffers)
