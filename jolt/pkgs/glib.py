from jolt import attributes, Parameter
from jolt.pkgs import meson, zlib
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_meson")
@attributes.requires("requires_zlib")
class GLib(meson.Meson):
    name = "glib"
    version = Parameter("2.86.3", help="glib version.")
    requires_git = ["git:url=https://gitlab.gnome.org/GNOME/glib.git,rev={version},submodules=true"]
    requires_meson = ["meson"]
    requires_zlib = ["zlib"]
    srcdir = "{git[glib]}"


TaskRegistry.get().add_task_class(GLib)
