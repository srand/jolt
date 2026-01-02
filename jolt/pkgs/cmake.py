from jolt import attributes, Download, Parameter
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
@attributes.common_metadata()
class CMake(Download):
    name = "cmake"
    version = Parameter("4.2.1", help="CMake version.")
    url = ["https://github.com/Kitware/CMake/releases/download/v{version}/cmake-{version}-{system}-{cmake_arch}{cmake_ext}"]
    collect = [{"files": "*", "cwd": "cmake-{version}-{system}-{cmake_arch}"}]

    @property
    def cmake_arch(self):
        if self.system == "macos":
            return "universal"
        if self.arch == "amd64":
            return "x86_64"
        return self.arch

    @property
    def cmake_ext(self):
        if self.system == "windows":
            return ".zip"
        return ".tar.gz"


TaskRegistry.get().add_task_class(CMake)
