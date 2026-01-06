from jolt import attributes, Parameter, Task
from jolt.pkgs import llvm
from jolt.tasks import TaskRegistry


@attributes.requires("requires_llvm")
class Clang(Task):
    name = "clang"
    version = Parameter(llvm.VERSION, help="Clang version.")

    requires_llvm = ["llvm:version={version}"]

    def publish(self, artifact, tools):
        artifact.environ.LLVM_TOOL_clang = "clang"
        artifact.environ.LLVM_TOOL_clangpp = "clang++"
        artifact.environ.AR = "llvm-ar"
        artifact.environ.CC = "clang"
        artifact.environ.CXX = "clang++"
        artifact.environ.LD = "clang++"
        artifact.environ.NM = "llvm-nm"
        artifact.environ.OBJCOPY = "llvm-objcopy"
        artifact.environ.OBJDUMP = "llvm-objdump"
        artifact.environ.PATH.append("bin")
        artifact.environ.RANLIB = "llvm-ranlib"
        artifact.environ.STRIP = "llvm-strip"


class ClangFormat(llvm.LLVMFromSrc):
    name = "clang-format"
    projects = ["clang", "clang-tools-extra"]
    targets = []
    install = ["install-clang-format"]


class ClangTidy(llvm.LLVMFromSrc):
    name = "clang-tidy"
    projects = ["clang", "clang-tools-extra"]
    targets = []
    install = ["install-clang-tidy"]


TaskRegistry.get().add_task_class(Clang)
TaskRegistry.get().add_task_class(ClangFormat)
TaskRegistry.get().add_task_class(ClangTidy)
