from jolt import attributes, Alias, Download, Parameter
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
@attributes.common_metadata()
class NinjaBin(Download):
    name = "ninja/bin"
    version = Parameter("1.13.2", help="Ninja version.")
    url = ["https://github.com/ninja-build/ninja/releases/download/v{version}/ninja-{system}.zip"]
    collect = [{"files": "*", "dest": "bin/"}]


class Ninja(Alias):
    name = "ninja"
    version = Parameter("1.13.2", help="Ninja version.")
    requires = ["ninja/bin:version={version}"]


TaskRegistry.get().add_task_class(Ninja)
TaskRegistry.get().add_task_class(NinjaBin)
