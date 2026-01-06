from jolt import attributes, Parameter, Task
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class GoogleTest(cmake.CMake):
    name = "googletest"
    version = Parameter("1.12.1", help="GoogleTest version.")
    requires_git = ["git:url=https://github.com/google/googletest.git,rev=release-{version}"]
    srcdir = "{git[googletest]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("gmock")
        artifact.cxxinfo.libraries.append("gtest")


class GTestMain(Task):
    name = "gtest/main"
    extends = "googletest"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("gtest_main")


class GmockMain(Task):
    name = "gmock/main"
    extends = "googletest"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("gmock_main")


TaskRegistry.get().add_task_class(GoogleTest)
TaskRegistry.get().add_task_class(GTestMain)
TaskRegistry.get().add_task_class(GmockMain)
