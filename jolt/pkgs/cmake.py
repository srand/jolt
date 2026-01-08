from jolt import attributes, Alias, Download, Parameter
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
@attributes.common_metadata()
class CMakeBin(Download):
    name = "cmake/bin"
    version = Parameter("4.2.1", help="CMake version.")
    url = ["https://github.com/Kitware/CMake/releases/download/v{version}/cmake-{version}-{cmake_system}-{cmake_arch}{cmake_ext}"]
    collect = [{"files": "*", "cwd": "cmake-{version}-{cmake_system}-{cmake_arch}{cmake_contents}"}]

    @property
    def cmake_arch(self):
        if self.system == "darwin":
            return "universal"
        if self.arch == "amd64":
            return "x86_64"
        return self.arch

    @property
    def cmake_ext(self):
        if self.system == "windows":
            return ".zip"
        return ".tar.gz"

    @property
    def cmake_system(self):
        if self.system == "darwin":
            return "macos"
        return self.system

    @property
    def cmake_contents(self):
        if self.system == "darwin":
            return "/CMake.app/Contents"
        return ""


class CMake(Alias):
    name = "cmake"
    version = Parameter("4.2.1", help="CMake version.")
    requires = ["cmake/bin:version={version}"]


TaskRegistry.get().add_task_class(CMake)
TaskRegistry.get().add_task_class(CMakeBin)
