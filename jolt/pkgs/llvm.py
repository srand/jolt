from jolt import Alias, BooleanParameter, Download, ListParameter, Parameter, Task, attributes
from jolt.error import raise_task_error_if
from jolt.pkgs import cmake, ninja
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


VERSION = "23.1.4"

# Target triples that libclc is built for, by LLVM target
LIBCLC_TRIPLES = {
    "AMDGPU": "amdgcn-amd-amdhsa-llvm",
}


@attributes.common_metadata()
class LLVMFromBin(Download):
    name = "llvm/bin"
    version = Parameter("23.1.4", help="LLVM version.")
    url = [
        "https://github.com/llvm/llvm-project/releases/download/llvmorg-{version}/LLVM-{version}-Linux-X64.tar.xz"
    ]

    collect = [{"files": "*", "cwd": "LLVM-{version}-Linux-X64"}]


@attributes.requires("requires_git")
@attributes.requires("requires_ninja")
@cmake.options("_libclc_options")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class LLVMFromSrc(cmake.CMake):
    name = "llvm/src"

    projects = ListParameter(
        ["clang", "clang-tools-extra", "lld", "libclc"],
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
    version = Parameter(VERSION, help="LLVM version.")

    requires_compiler = ["compiler/c", "compiler/cxx"]
    requires_ninja = ["ninja"]
    requires_git = ["git:url=https://github.com/llvm/llvm-project.git,rev=llvmorg-{version}"]

    options = [
        "CMAKE_BUILD_TYPE={release[Release,Debug]}",
        "LLVM_ENABLE_PROJECTS='{_projects_str}'",
        "LLVM_TARGETS_TO_BUILD='{_targets_str}'",
        "LLVM_ENABLE_RTTI={rtti[ON,OFF]}",
    ]

    srcdir = "{git[llvm-project]}/llvm"

    @property
    def _libclc_runtime(self):
        """ Since LLVM 23, libclc is built as a runtime for GPU targets. """
        return "libclc" in self.projects and int(str(self.version).split(".")[0]) >= 23

    @property
    def _libclc_options(self):
        if not self._libclc_runtime:
            return []
        triples = [LIBCLC_TRIPLES[target] for target in self.targets if target in LIBCLC_TRIPLES]
        raise_task_error_if(
            not triples, self,
            "libclc requires one of these targets: {}", ", ".join(LIBCLC_TRIPLES))
        return ["LLVM_RUNTIME_TARGETS='{}'".format(";".join(triples))] + [
            "RUNTIMES_{}_LLVM_ENABLE_RUNTIMES=libclc".format(triple) for triple in triples]

    @property
    def _projects_str(self):
        if self._libclc_runtime:
            return ";".join(project for project in self.projects if project != "libclc")
        return ";".join(self.projects)

    @property
    def _targets_str(self):
        return ";".join(self.targets)


class LLVM(Alias):
    name = "llvm"
    version = Parameter(VERSION, help="LLVM version.")
    requires = ["llvm/src:version={version},release=true"]


TaskRegistry.get().add_task_class(LLVMFromBin)
TaskRegistry.get().add_task_class(LLVMFromSrc)
TaskRegistry.get().add_task_class(LLVM)
