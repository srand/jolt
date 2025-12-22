from jolt import attributes, Parameter, Task
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.common_metadata()
class OpenSSL(Task):
    name = "openssl"
    version = Parameter("3.6.0", help="openssl version.")

    requires_git = ["git:url=https://github.com/openssl/openssl.git,rev=openssl-{version}"]

    def run(self, deps, tools):
        self.builddir = tools.builddir(incremental=True)
        self.installdir = tools.builddir("install")
        self.srcdir = tools.expand_path("{git[openssl]}")
        with tools.cwd(self.builddir):
            self.info("Configuring OpenSSL... {builddir}")
            tools.run(
                "{srcdir}/config --prefix={installdir} no-tests",
            )
            tools.run("make -j{}", tools.cpu_count())
            tools.run("make install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(OpenSSL)
