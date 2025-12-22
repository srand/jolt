from jolt import attributes, Parameter
from jolt.pkgs import meson
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requries_meson")
class Libpciaccess(meson.Meson):
    name = "libpciaccess"
    version = Parameter("0.18.1", help="pciaccess version.")
    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/lib/libpciaccess.git,rev=libpciaccess-{version}"]
    requires_meson = ["meson"]
    srcdir = "{git[libpciaccess]}"


TaskRegistry.get().add_task_class(Libpciaccess)
