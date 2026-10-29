from jolt import attributes, Parameter
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
class Libffi(autotools.Autotools):
    name = "libffi"
    version = Parameter("3.8.0", help="libffi version.")
    requires_src = ["git:clean=true,url=https://github.com/libffi/libffi.git,rev=v{version}"]
    srcdir = "{git[libffi]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libffi)
