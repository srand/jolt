from jolt import attributes, Parameter, Task
from jolt.pkgs import autoconf, automake, perl, zlib
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_autotools_{system}")
@attributes.requires("requires_git")
@attributes.requires("requires_perl")
@attributes.requires("requires_zlib")
@attributes.system
class NASM(Task):
    name = "nasm"
    version = Parameter("3.01", help="nasm version.")
    requires_autotools_linux = ["autoconf", "automake"]
    requires_git = ["git:url=https://github.com/netwide-assembler/nasm.git,rev=nasm-{version}"]
    requires_zlib = ["zlib"]
    requires_perl = ["virtual/perl"]
    srcdir = "{git[nasm]}"

    def run(self, deps, tools):
        self.srcdir = tools.expand_path(self.srcdir)
        self.builddir = tools.builddir()

        if self.system != "windows":
            with tools.cwd(self.srcdir):
                tools.run("{srcdir}/autogen.sh")

            with tools.cwd(self.builddir):
                tools.run("{srcdir}/configure")
                tools.run("make -j{}", tools.thread_count())
        else:
            with tools.cwd(self.srcdir):
                tools.run("nmake -f Mkfiles/msvc.mak")


    def publish(self, artifact, tools):
        if self.system == "windows":
            with tools.cwd(self.srcdir):
                artifact.collect("nasm.exe", "bin/")
                artifact.collect("ndisasm.exe", "bin/")
        else:
            with tools.cwd(self.builddir):
                artifact.collect("nasm", "bin/")
                artifact.collect("ndisasm", "bin/")
        artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(NASM)
