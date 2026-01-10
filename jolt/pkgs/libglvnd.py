from jolt import attributes, Parameter
from jolt.pkgs import x11
from jolt.tasks import TaskRegistry
from jolt.plugins import meson, git, pkgconfig


@attributes.arch
@attributes.requires("requires_git")
@attributes.requires("requires_glproto")
@attributes.requires("requires_x11")
@attributes.requires("requires_xext")
@meson.requires()
@pkgconfig.requires()
class Libglvnd(meson.Meson):
    name = "libglvnd"
    version = Parameter("1.7.0", help="libglvnd version.")

    requires_git = ["git:url=https://github.com/NVIDIA/libglvnd.git,rev=v{version}"]
    requires_glproto = ["glproto"]
    requires_x11 = ["libx11"]
    requires_xext = ["libxext"]
    srcdir = "{git[libglvnd]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.environ.LD_LIBRARY_PATH.append("lib/{arch}-linux-gnu")


TaskRegistry.get().add_task_class(Libglvnd)
