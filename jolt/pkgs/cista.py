from jolt import attributes, Parameter, Task
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
class Cista(Task):
    name = "cista"
    version = Parameter("0.16", help="Cista version.")
    requires_git = ["git:url=https://github.com/felixguendling/cista.git,rev=v{version}"]
    srcdir = "{git[cista]}"

    def publish(self, artifact, tools):
        with tools.cwd(self.srcdir):
            artifact.collect("include/")
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(Cista)
