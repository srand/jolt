from jolt import attributes, Parameter
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
@autotools.requires()
class Libffi(autotools.Autotools):
    name = "libffi"
    version = Parameter("3.8.0", help="libffi version.")
    requires_src = ["git:clean=true,url=https://github.com/libffi/libffi.git,rev=v{version}"]
    srcdir = "{git[libffi]}"


TaskRegistry.get().add_task_class(Libffi)
