from jolt import Alias, BooleanParameter, Download, ListParameter, Parameter, Task, attributes
from jolt.pkgs import cmake, ninja
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
class LLVMFromBin(Download):
    name = "llvm/bin"
    version = Parameter("21.1.0", help="LLVM version.")
    url = [
        "https://github.com/llvm/llvm-project/releases/download/llvmorg-{version}/LLVM-{version}-Linux-X64.tar.xz"
    ]

    collect = [{"files": "*", "cwd": "LLVM-{version}-Linux-X64"}]


@attributes.requires("requires_git")
@attributes.requires("requires_ninja")
@cmake.requires()
class LLVMFromSrc(cmake.CMake):
    name = "llvm/src"

    projects = ListParameter(
        ["clang", "clang-tools-extra", "lld", "libclc", ],
        values=[
            "clang",
            "clang-tools-extra",
            "lld",
            "libclc",
            "libcxx",
            "libcxxabi",
            "compiler-rt",
            "openmp",
            "polly",
        ],
        help="LLVM projects to build.",
    )
    release = BooleanParameter(True, help="Build a release version.")
    rtti = BooleanParameter(True, help="Enable RTTI support.")
    targets = ListParameter(
        ["X86", "ARM", "AArch64", "RISCV", "AMDGPU"],
        values=["X86", "AMDGPU", "ARM", "AArch64", "RISCV", "Mips", "PowerPC", "SystemZ"],
        help="LLVM targets to build.",
    )
    version = Parameter("21.1.8", help="LLVM version.")

    requires_ninja = ["ninja"]
    requires_git = [
        "git:url=https://github.com/llvm/llvm-project.git,depth=1,rev=llvmorg-{version}"
    ]

    options = [
        "CMAKE_BUILD_TYPE={release[Release,Debug]}",
        "LLVM_ENABLE_PROJECTS='{_projects_str}'",
        "LLVM_TARGETS_TO_BUILD='{_targets_str}'",
        "LLVM_ENABLE_RTTI={rtti[ON,OFF]}",
    ]

    srcdir = "{git[llvm-project]}/llvm"

    @property
    def _projects_str(self):
        return ";".join(self.projects)

    @property
    def _targets_str(self):
        return ";".join(self.targets)


class LLVM(Alias):
    name = "llvm"
    version = Parameter("21.1.8", help="LLVM version.")
    requires = ["llvm/src:version={version},release=true"]


TaskRegistry.get().add_task_class(LLVMFromBin)
TaskRegistry.get().add_task_class(LLVMFromSrc)
TaskRegistry.get().add_task_class(LLVM)
