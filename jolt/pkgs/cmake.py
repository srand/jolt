from jolt import attributes, Download, Parameter
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
@attributes.common_metadata()
class CMake(Download):
    name = "cmake"
    version = Parameter("4.2.1", help="CMake version.")
    url = ["https://github.com/Kitware/CMake/releases/download/v{version}/cmake-{version}-{system}-{arch}.tar.gz"]
    collect = [{"files": "*", "cwd": "cmake-{version}-{system}-{arch}"}]


TaskRegistry.get().add_task_class(CMake)
