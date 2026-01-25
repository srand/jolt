from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["gmock", "gtest"])
class GoogleTest(cmake.CMake):
    name = "google/test"
    version = Parameter("1.12.1", help="GoogleTest version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/google/googletest.git,rev=release-{version}"]
    srcdir = "{git[googletest]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


class GTestMain(Task):
    name = "google/test/main"
    extends = "google/test"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("gtest_main")


class GmockMain(Task):
    name = "google/mock/main"
    extends = "google/test"

    def publish(self, artifact, tools):
        artifact.cxxinfo.libraries.append("gmock_main")


TaskRegistry.get().add_task_class(GoogleTest)
TaskRegistry.get().add_task_class(GTestMain)
TaskRegistry.get().add_task_class(GmockMain)
