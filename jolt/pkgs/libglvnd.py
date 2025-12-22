from jolt import attributes, Parameter
from jolt.tasks import TaskRegistry
from jolt.plugins import autotools, git


@attributes.requires("requires_git")
class Libglvnd(autotools.Autotools):
    name = "libglvnd"
    version = Parameter("1.7.0", help="libglvnd version.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/glvnd/libglvnd.git,rev=v{version}"]
    srcdir = "{git[libglvnd]}"


TaskRegistry.get().add_task_class(Libglvnd)
