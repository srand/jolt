from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_abseil")
@attributes.requires("requires_git")
@cmake.requires()
class RE2(cmake.CMake):
    name = "re2"
    version = Parameter("2025-11-05", help="re2 version.")
    requires_abseil = ["abseil"]
    requires_git = ["git:url=https://github.com/google/re2.git,rev={version}"]
    srcdir = "{git[re2]}"


TaskRegistry.get().add_task_class(RE2)
