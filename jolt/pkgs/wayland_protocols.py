from jolt import attributes, Parameter
from jolt.pkgs import compiler, wayland
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_wayland")
@meson.requires()
@attributes.requires("requires_compiler")
class WaylandProtocols(meson.Meson):
    name = "wayland-protocols"
    version = Parameter("1.49", help="wayland-protocols version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://gitlab.freedesktop.org/wayland/wayland-protocols.git,rev={version}"]
    requires_wayland = ["wayland"]
    srcdir = "{git[wayland-protocols]}"
    options = ["tests=false"]


TaskRegistry.get().add_task_class(WaylandProtocols)
