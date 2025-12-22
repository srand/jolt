from jolt import attributes, Parameter
from jolt.pkgs import nasm
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_nasm")
class FFmpeg(autotools.Autotools):
    name = "ffmpeg"
    version = Parameter("8.0.1", help="ffmpeg version.")
    requires_git = ["git:url=https://github.com/FFmpeg/FFmpeg.git,rev=n{version}"]
    requires_nasm = ["nasm"]
    srcdir = "{git[FFmpeg]}"


TaskRegistry.get().add_task_class(FFmpeg)
