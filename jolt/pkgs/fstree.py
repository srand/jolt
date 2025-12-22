from jolt import attributes, Parameter, Task
from jolt.tasks import TaskRegistry


@attributes.system
class Fstree(Task):
    name = "fstree"
    version = Parameter("24.11.128")

    def publish(self, artifact, tools):
        with tools.cwd(tools.builddir()):
            tools.mkdir("jolt/bin")
            tools.download("https://github.com/srand/fstree/releases/download/{version}/fstree-{system}-x86_64", "jolt/bin/fstree-{system}-x86_64")
            tools.chmod("jolt/bin/fstree-{system}-x86_64", 0o755)
            artifact.collect("jolt/bin/fstree-{system}-x86_64", "bin/fstree")
            artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(Fstree)
