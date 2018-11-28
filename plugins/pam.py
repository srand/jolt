from tasks import *
from influence import *


import build.model
import toolchains.pam


class CXXExecutable(Task, HashInfluenceProvider):
    sources = []
    macros = []
    incpaths = []
    libpaths = []
    features = []
    libraries = []

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.influence.append(self)
        self.sources = utils.as_list(utils.call_or_return(self, self.__class__.sources))
        sources = []
        for l in map(self.tools.glob, self.sources):
            sources += l
        self.sources = sources
        self.project = build.model.cxx_executable(
            self.name,
            sources=self.sources,
            macros=self.macros,
            incpaths=self.incpaths,
            libpaths=self.libpaths,
            features=self.features,
            libraries=self.libraries
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
