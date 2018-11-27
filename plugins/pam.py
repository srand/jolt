from tasks import *
from influence import *


import build.model
import toolchains.pam


class CXXExecutable(Task, HashInfluenceProvider):
    sources = []

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.influence.append(self)
        self.project = build.model.cxx_executable(
            self.name,
            sources=self.sources
        )
        self.toolchain = toolchains.pam.pam_gnu_toolchain("pam-gcc")
        self.cxx_project = self.toolchain.generate(self.project)

    def run(self, deps, tools):
        self.cxx_project.transform()

    def publish(self, artifact, tools):
        artifact.collect("output/pam-gcc/{0}/{0}".format(self.name), flatten=True)

    def get_influence(self, task):
        return self.cxx_project.job.get_hash()


TaskRegistry.get().add_task_class(CXXExecutable)
