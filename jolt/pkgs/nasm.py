from jolt import attributes, Parameter, Task
from jolt.pkgs import zlib
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_asciidoc")
@attributes.requires("requires_git")
@attributes.requires("requires_xmlto")
@attributes.requires("requires_zlib")
class NASM(Task):
    name = "nasm"
    version = Parameter("3.01", help="nasm version.")
    requires_git = ["git:url=https://github.com/netwide-assembler/nasm.git,rev=nasm-{version}"]
    requires_zlib = ["zlib"]
    srcdir = "{git[nasm]}"

    def run(self, deps, tools):
        self.srcdir = tools.expand_path(self.srcdir)
        self.builddir = tools.builddir()
        with tools.cwd(self.srcdir):
            tools.run("{srcdir}/autogen.sh")

        with tools.cwd(self.builddir):
            tools.run("{srcdir}/configure")
            tools.run("make -j{}", tools.thread_count())

    def publish(self, artifact, tools):
        with tools.cwd(self.builddir):
            artifact.collect("nasm", "bin/")
            artifact.collect("ndisasm", "bin/")
            artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(NASM)
