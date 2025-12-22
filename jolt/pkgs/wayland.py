from jolt import attributes, Parameter
from jolt.pkgs import meson
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_meson")
class Wayland(meson.Meson):
    name = "wayland"
    version = Parameter("1.24.0", help="Wayland version.")
    requires_git = ["git:url=https://gitlab.freedesktop.org/wayland/wayland.git,rev={version}"]
    requires_meson = ["meson"]
    srcdir = "{git[wayland]}"
    options = [
        "documentation=false",
        "tests=false",
    ]


TaskRegistry.get().add_task_class(Wayland)
