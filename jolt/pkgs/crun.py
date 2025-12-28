from jolt import attributes, Parameter
from jolt.plugins import git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
@pkgconfig.requires()
class CRun(autotools.Autotools):
    name = "crun"
    version = Parameter("1.26", help="crun version.")
    requires_git = ["git:url=https://github.com/containers/crun.git,rev={version},submodules=true"]
    srcdir = "{git[crun]}"
    options = [
        # Unable to get ./configure to pick these up from pkg-config
        "--disable-criu",
        "--disable-seccomp",
        "--enable-embedded-yajl",
    ]


TaskRegistry.get().add_task_class(CRun)
