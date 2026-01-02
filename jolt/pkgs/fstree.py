from jolt import attributes, Parameter, Task
from jolt.tasks import TaskRegistry


@attributes.system
class Fstree(Task):
    name = "fstree"
    version = Parameter("24.11.128")

    def publish(self, artifact, tools):
        self.ext = ".exe" if self.system == "windows" else ""
        with tools.cwd(tools.builddir()):
            tools.mkdir("jolt/bin")
            tools.download("https://github.com/srand/fstree/releases/download/{version}/fstree-{system}-x86_64{ext}", "jolt/bin/fstree-{system}-x86_64{ext}")
            tools.chmod("jolt/bin/fstree-{system}-x86_64{ext}", 0o755)
            artifact.collect("jolt/bin/fstree-{system}-x86_64{ext}", "bin/fstree{ext}")
            artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(Fstree)
