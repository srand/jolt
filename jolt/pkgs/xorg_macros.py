from jolt import attributes, Parameter
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
class XorgMacros(autotools.Autotools):
    name = "xorg/macros"
    version = Parameter("1.20.2", help="Xorg Macros version.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/util/macros.git,rev=util-macros-{version}"]
    srcdir = "{git[macros]}"


TaskRegistry.get().add_task_class(XorgMacros)
