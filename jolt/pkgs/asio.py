from jolt import attributes, Parameter
from jolt.plugins import cmake, git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo("asio")
@autotools.requires()
class Asio(autotools.Autotools):
    name = "asio"
    version = Parameter("1.36.0", help="asio version.")
    requires_git = ["git:url=https://github.com/chriskohlhoff/asio.git,rev=asio-{_version}"]
    srcdir = "{git[asio]}/asio"

    @property
    def _version(self):
        return str(self.version).replace(".", "-")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Asio)
