import platform

from jolt import attributes, Parameter, Task
from jolt.plugins import fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@attributes.requires("requires_compiler")
class LinuxHeaders(Task):
    """ Linux kernel headers for user space, such as for building C libraries """

    name = "linux-headers"
    version = Parameter("7.3", help="Linux version.")
    target = Parameter(required=False, help="Target of the headers, such as aarch64-linux-gnu. The host if not set.")
    requires_compiler = ["compiler/c"]
    requires_src = ["fetch:alias=src,url=https://cdn.kernel.org/pub/linux/kernel/v{_major}.x/linux-{version}.tar.xz"]
    srcdir = "{fetch[src]}/linux-{version}"

    @property
    def _major(self):
        return str(self.version).split(".")[0]

    @property
    def _arch(self):
        """ Architecture of the kernel for the target. """
        machine = str(self.target).split("-")[0] if self.target.is_set() else platform.machine()
        if machine in ["amd64", "i386", "i486", "i586", "i686", "x86_64"]:
            return "x86"
        if machine in ["aarch64", "aarch64_be", "arm64"]:
            return "arm64"
        if machine.startswith("arm"):
            return "arm"
        if machine.startswith("riscv"):
            return "riscv"
        if machine.startswith("powerpc") or machine.startswith("ppc"):
            return "powerpc"
        if machine.startswith("mips"):
            return "mips"
        return machine

    def run(self, deps, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self.srcdir):
            tools.run("make ARCH={_arch} INSTALL_HDR_PATH={installdir}/usr headers_install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*")


TaskRegistry.get().add_task_class(LinuxHeaders)
