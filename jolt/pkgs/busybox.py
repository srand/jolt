from jolt import attributes, influence, Parameter, Task
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
class BusyBox(Task):
    name = "busybox"
    defconfig = Parameter(required=False, help="BusyBox defconfig file.")
    version = Parameter("1.37.0", help="BusyBox version.")
    requires_git = ["git:url=git://busybox.net/busybox.git,rev={version_tag}"]
    srcdir = "{git[busybox]}"

    @property
    def version_tag(self):
        return str(self.version).replace(".", "_")

    @property
    def defconfig_arg(self):
        if self.defconfig:
            return f"{self.defconfig}_defconfig"
        return "defconfig"

    def run(self, deps, tools):
        self.outdir = tools.builddir()
        self.installdir = tools.builddir("install")

        with tools.cwd(self.srcdir):
            tools.run("make O={outdir} {defconfig_arg}")
            tools.run("make O={outdir} -j{}", tools.cpu_count())
            tools.run("make O={outdir} install DESTDIR={installdir}")

    def publish(self, artifact, tools):
        artifact.environ.PATH.append("bin")
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(BusyBox)
