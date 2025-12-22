from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_cmake")
class SpirvTools(cmake.CMake):
    name = "spirv-tools"
    version = Parameter("2024.6", help="SPIRV-Tools version.")
    requires_git = ["git:url=https://github.com/KhronosGroup/SPIRV-Tools.git,rev=v{version}"]
    requires_cmake = ["cmake"]
    srcdir = "{git[spirv-tools]}"


TaskRegistry.get().add_task_class(SpirvTools)
