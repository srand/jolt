from jolt import attributes, Parameter
from jolt.pkgs import cmake, llvm, spirv_tools
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_llvm")
@attributes.requires("requires_spirv_tools")
@cmake.requires()
class SpirvLLVM(cmake.CMake):
    name = "spirv-llvm-translator"
    version = Parameter("21.1.3", help="SPIRV-LLVM version.")
    requires_git = ["git:url=https://github.com/KhronosGroup/SPIRV-LLVM-Translator.git,rev=v{version}"]
    requires_llvm = ["llvm"]
    requires_spirv_tools = ["spirv-tools"]
    srcdir = "{git[SPIRV-LLVM-Translator]}"


TaskRegistry.get().add_task_class(SpirvLLVM)
