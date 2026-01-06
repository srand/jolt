from jolt import attributes
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
@autotools.requires()
class Libffi(autotools.Autotools):
    name = "libffi"
    version = "3.5.2"
    requires_src = ["git:url=https://github.com/libffi/libffi.git,rev=v{version}"]
    srcdir = "{git[libffi]}"


TaskRegistry.get().add_task_class(Libffi)
