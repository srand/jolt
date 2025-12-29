from jolt import attributes, Parameter
from jolt.plugins import git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.arch
@attributes.system
@autotools.requires()
@pkgconfig.to_cxxinfo(["libunwind", "libunwind-generic", "libunwind-coredump", "libunwind-ptrace", "libunwind-setjmp"])
class LibUnwind(autotools.Autotools):
    name = "libunwind"
    version = Parameter("1.8.3", help="libunwind version.")
    options = ["--disable-tests"]
    requires_git = ["git:url=https://github.com/libunwind/libunwind.git,rev=v{version}"]
    srcdir = "{git[libunwind]}"

    def run(self, deps, tools):
        with tools.environ(TARGET="{target}"):
            super().run(deps, tools)

    @property
    def target(self):
        platform = self.tools.expand("{system}-{arch}")
        if platform == "linux-x86_64":
            return "x86_64-linux-gnu"
        elif platform == "linux-aarch64":
            return "aarch64-linux-gnu"
        elif platform == "linux-arm":
            return "arm-linux-gnueabihf"
        else:
            self.error(f"Unsupported platform: {platform}")


TaskRegistry.get().add_task_class(LibUnwind)
