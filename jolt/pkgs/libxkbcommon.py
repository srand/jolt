from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import bison, compiler, xorg
from jolt.plugins import cxxinfo, git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_bison")
@attributes.requires("requires_git")
@attributes.requires("requires_x11_{x11[on,off]}")
@meson.requires()
@cxxinfo.publish(libraries=["xkbcommon"])
@attributes.requires("requires_compiler")
class Libxkbcommon(meson.Meson):
    name = "libxkbcommon"
    version = Parameter("1.13.2", help="libxkbcommon version.")
    x11 = BooleanParameter(False, help="Build the libxkbcommon-x11 library.")
    requires_compiler = ["virtual/compiler/c"]
    requires_bison = ["bison"]
    requires_git = ["git:url=https://github.com/xkbcommon/libxkbcommon.git,rev=xkbcommon-{version}"]
    requires_x11_on = ["xorg/libxcb"]
    srcdir = "{git[libxkbcommon]}"
    options = [
        "enable-docs=false",
        "enable-tools=false",
        "enable-wayland=false",
        "enable-x11={x11[true,false]}",
        "enable-xkbregistry=false",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.x11:
            artifact.cxxinfo.libraries.append("xkbcommon-x11")


TaskRegistry.get().add_task_class(Libxkbcommon)
