from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import autotools, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
@cxxinfo.publish(libraries=["socketcan"])
@attributes.requires("requires_compiler")
class Libsocketcan(autotools.Autotools):
    """ Library to control SocketCAN interfaces: bitrate, state and restart """

    name = "libsocketcan"
    version = Parameter("0.0.12", help="libsocketcan version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:clean=true,url=https://github.com/linux-can/libsocketcan.git,rev=v{version}"]
    srcdir = "{git[libsocketcan]}"
    options = [
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "{_pic_option}",
    ]

    @property
    def _pic_option(self):
        # Shared libraries are always position independent
        if self.shared:
            return ""
        return "--with-pic" if self.pic else "--without-pic"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libsocketcan)
