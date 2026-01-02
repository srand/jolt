from jolt import attributes, Alias, Parameter, Task
from jolt.pkgs import nasm, perl
from jolt.plugins import git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_perl_{system}")
@attributes.requires("requires_nasm")
@attributes.common_metadata()
@attributes.system
@pkgconfig.to_cxxinfo(["openssl"])
class OpenSSL(Task):
    name = "openssl"
    version = Parameter("3.6.0", help="openssl version.")

    requires_git = ["git:url=https://github.com/openssl/openssl.git,rev=openssl-{version}"]
    requires_perl_windows = ["perl"]
    requires_nasm = ["nasm"]

    def run(self, deps, tools):
        self.builddir = tools.builddir(incremental=True)
        self.installdir = tools.builddir("install")
        self.srcdir = tools.expand_path("{git[openssl]}")
        with tools.cwd(self.builddir):
            self.info("Configuring OpenSSL... {builddir}")
            
            if self.system == "windows":
                tools.run("perl {srcdir}/Configure --prefix={installdir} --openssldir=ssl no-tests ")
                tools.run("nmake")
                tools.run("nmake install")
            else:
                tools.run("{srcdir}/config --prefix={installdir} no-tests")
                tools.run("make -j{}", tools.cpu_count())
                tools.run("make install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)


class Libssl(Alias):
    name = "libssl"
    requires = ["openssl"]


TaskRegistry.get().add_task_class(OpenSSL)
