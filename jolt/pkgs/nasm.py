from jolt import attributes, Parameter, Task
from jolt.pkgs import autoconf, automake, compiler, perl, zlib
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_autotools_{system}")
@attributes.requires("requires_source_{system}")
@attributes.system
class NASM(Task):
    name = "nasm"
    version = Parameter("3.02", help="NASM version.")
    requires_autotools_darwin = ["autoconf", "automake"]
    requires_autotools_linux = requires_autotools_darwin
    requires_source_darwin = [
        "git:url=https://github.com/netwide-assembler/nasm.git,rev=nasm-{version}",
        "virtual/compiler/c",
        "virtual/perl",
        "zlib",
    ]
    """ Requirements of the source build. On Windows, the official build is downloaded instead. """
    requires_source_linux = requires_source_darwin
    srcdir = "{git[nasm]}"
    """ Source directory. """
    url = "https://www.nasm.us/pub/nasm/releasebuilds/{version}/win64/nasm-{version}-win64.zip"
    """ Official Windows build. """

    def run(self, deps, tools):
        self.builddir = tools.builddir()

        if self.system != "windows":
            self.srcdir = tools.expand_path(self.srcdir)
            with tools.cwd(self.srcdir):
                tools.run("{srcdir}/autogen.sh")

            with tools.cwd(self.builddir):
                tools.run("{srcdir}/configure")
                tools.run("make {}", tools.make_jobs())
        else:
            # The MSVC makefile fails with "No Target Architecture" in winnt.h
            with tools.cwd(self.builddir):
                tools.download(self.url, "nasm.zip")
                tools.extract("nasm.zip", ".")

    def publish(self, artifact, tools):
        if self.system == "windows":
            with tools.cwd(self.builddir, "nasm-{version}"):
                artifact.collect("nasm.exe", "bin/")
                artifact.collect("ndisasm.exe", "bin/")
        else:
            with tools.cwd(self.builddir):
                artifact.collect("nasm", "bin/")
                artifact.collect("ndisasm", "bin/")
        artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(NASM)
