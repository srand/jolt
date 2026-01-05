from jolt import attributes, Parameter
from jolt.pkgs import cmake, openssl
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ssl")
@cmake.requires()
@cmake.use_ninja()
@pkgconfig.requires()
class LibEvent(cmake.CMake):
    name = "libevent"
    version = Parameter("2.1.12", help="libevent version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_git = ["git:url=https://github.com/libevent/libevent.git,rev=release-{version}-stable"]
    requires_ssl = ["openssl"]
    srcdir = "{git[libevent]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        with tools.cwd(artifact.path, "lib/cmake/libevent"):
            for file in tools.glob("*.cmake"):
                tools.replace_in_file(
                    file,
                    artifact.strings.install_prefix,
                    "${{CMAKE_CURRENT_LIST_DIR}}/../../..",
                )


TaskRegistry.get().add_task_class(LibEvent)
