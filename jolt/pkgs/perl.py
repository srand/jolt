from jolt import attributes, Alias, Download, Parameter
from jolt.tasks import TaskRegistry


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
@attributes.requires("requires_{system}")
class Perl(Alias):
    name = "virtual/perl"
    requires_windows = ["perl/strawberry"]


TaskRegistry.get().add_task_class(Perl)
TaskRegistry.get().add_task_class(StrawberryPerl)
