import os
from jolt import attributes, Parameter
from jolt.pkgs import cmake, openssl
from jolt.plugins import cxxinfo, git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ssl")
@cmake.requires()
@cmake.use_ninja()
@pkgconfig.requires()
@cxxinfo.publish(libraries=["event"])
class LibEvent(cmake.CMake):
    name = "libevent"
    version = Parameter("2.1.12", help="libevent version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_git = ["git:url=https://github.com/libevent/libevent.git,rev=release-{version}-stable"]
    requires_ssl = ["openssl"]
    srcdir = "{git[libevent]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)

        for libdir in ["lib", "lib32", "lib64"]:
            if os.path.isdir(os.path.join(artifact.path, libdir)):
                self.libdir = libdir
                break

        with tools.cwd(artifact.path, "{libdir}/cmake/libevent"):
            for file in tools.glob("*.cmake"):
                tools.replace_in_file(
                    file,
                    artifact.strings.install_prefix,
                    "${{CMAKE_CURRENT_LIST_DIR}}/../../..",
                )


TaskRegistry.get().add_task_class(LibEvent)
