from jolt import attributes, Parameter
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
class CRun(autotools.Autotools):
    name = "crun"
    version = Parameter("1.26", help="crun version.")
    requires_git = ["git:url=https://github.com/containers/crun.git,rev={version},submodules=true"]
    srcdir = "{git[crun]}"
    options = [
        # Unable to get ./configure to pick these up from pkg-config
        "--enable-embedded-yajl",
        "--disable-seccomp",
    ]


TaskRegistry.get().add_task_class(CRun)
