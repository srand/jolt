from jolt import attributes, Parameter
from jolt.pkgs import libexpat, libffi, libxml2
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_expat")
@attributes.requires("requires_git")
@attributes.requires("requires_libffi")
@attributes.requires("requires_libxml2")
@meson.requires()
@attributes.requires("requires_compiler")
class Wayland(meson.Meson):
    name = "wayland"
    version = Parameter("1.26.0", help="Wayland version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_expat = ["libexpat:pic=true"]
    requires_git = ["git:url=https://gitlab.freedesktop.org/wayland/wayland.git,rev={version}"]
    requires_libffi = ["libffi"]
    requires_libxml2 = ["libxml2"]
    srcdir = "{git[wayland]}"
    options = [
        "documentation=false",
        "tests=false",
    ]


TaskRegistry.get().add_task_class(Wayland)
