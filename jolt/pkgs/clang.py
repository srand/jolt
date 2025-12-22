from jolt import attributes, Parameter, Task
from jolt.tasks import TaskRegistry


@attributes.requires("requires_llvm")
class Clang(Task):
    name = "clang"
    version = Parameter("21.1.8", help="Clang version.")

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


TaskRegistry.get().add_task_class(Clang)
