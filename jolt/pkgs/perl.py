from jolt import attributes, influence
from jolt import Alias, Download, Parameter, Task
from jolt.tasks import TaskRegistry
from jolt.error import raise_task_error_if


class StrawberryPerl(Download):
    name = "perl/strawberry"
    version = Parameter("5.42.0.1", help="poco version.")
    url = "https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_{version_compact}_64bit/strawberry-perl-{version}-64bit-portable.zip"

    @property
    def version_compact(self):
        return str(self.version).replace(".", "")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("perl/bin")


@attributes.system
@influence.string("{system}")
class HostPerl(Task):
    name = "perl/host"

    def run(self, deps, tools):
        raise_task_error_if(not tools.which("perl"), "Perl is not installed on the host system.")


@attributes.system
@attributes.requires("requires_{system}")
class Perl(Alias):
    name = "virtual/perl"

    requires_darwin = ["perl/host"]
    requires_linux = ["perl/host"]
    requires_windows = ["perl/strawberry"]


TaskRegistry.get().add_task_class(Perl)
TaskRegistry.get().add_task_class(HostPerl)
TaskRegistry.get().add_task_class(StrawberryPerl)
