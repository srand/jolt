from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import nasm, pkgconfig, xz, xorg
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_{system}_libx11")
@attributes.requires("requires_nasm")
@attributes.requires("requires_xz")
@attributes.system
@autotools.requires()
class FFmpeg(autotools.Autotools):
    name = "ffmpeg"
    version = Parameter("8.0.1", help="ffmpeg version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/FFmpeg/FFmpeg.git,rev=n{version}"]
    requires_linux_libx11 = ["libx11"]
    requires_nasm = ["nasm"]
    requires_xz = ["xz"]
    srcdir = "{git[FFmpeg]}"
    options = [
        "--{shared[enable,disable]}-shared",
        "--{shared[disable,enable]}-static",
    ]


TaskRegistry.get().add_task_class(FFmpeg)
