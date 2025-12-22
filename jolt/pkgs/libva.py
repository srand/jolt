from jolt import attributes, Parameter
from jolt.pkgs import libdrm, meson
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libdrm")
@attributes.requires("requires_meson")
class Libva(meson.Meson):
    name = "libva"
    version = Parameter("2.16.0", help="Libva version.")
    requires_git = ["git:url=https://github.com/intel/libva.git,rev={version}"]
    requires_libdrm = ["libdrm"]
    requires_meson = ["meson"]
    srcdir = "{git[libva]}"


TaskRegistry.get().add_task_class(Libva)
