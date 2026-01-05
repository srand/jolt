from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class RE2(cmake.CMake):
    name = "re2"
    version = Parameter("2025-11-05", help="re2 version.")
    requires_abseil = ["abseil"]
    requires_git = ["git:url=https://github.com/google/re2.git,rev={version}"]
    srcdir = "{git[re2]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("re2")


TaskRegistry.get().add_task_class(RE2)
