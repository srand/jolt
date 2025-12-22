from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class LibEvent(cmake.CMake):
    name = "libevent"
    version = Parameter("2.1.12", help="libevent version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/libevent/libevent.git,rev=release-{version}-stable"]
    srcdir = "{git[libevent]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        with tools.cwd(artifact.path):
            tools.replace_in_file(
                "lib/cmake/libevent/LibeventTargets-shared.cmake",
                artifact.strings.install_prefix,
                "${{CMAKE_CURRENT_LIST_DIR}}/../../..",
            )
            tools.replace_in_file(
                "lib/cmake/libevent/LibeventTargets-static.cmake",
                artifact.strings.install_prefix,
                "${{CMAKE_CURRENT_LIST_DIR}}/../../..",
            )


TaskRegistry.get().add_task_class(LibEvent)
