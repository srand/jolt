import os
from jolt import attributes, Parameter
from jolt.plugins import git
from jolt.tasks import Task, TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_git")
@attributes.system
class B2(Task):
    name = "b2"
    version = Parameter("5.4.2", help="B2 version.")
    requires_git = ["git:url=https://github.com/bfgroup/b2.git"]

    def run(self, artifact, tools):
        self.builddir = tools.builddir("build", incremental=True)
        self.installdir = tools.builddir("install")
        with tools.cwd("{git[b2]}"):
            if self.system == "windows":
                tools.run(".\\bootstrap.bat")
                tools.run(".\\b2 install --prefix={installdir} --build-dir={builddir} -j{}", tools.cpu_count())
            else:
                tools.run("./bootstrap.sh")
                tools.run("./b2 install --prefix={installdir} --build-dir={builddir} -j{}", tools.cpu_count())

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(B2)
