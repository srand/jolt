import platform

from jolt.tasks import *
from jolt import influence

import build
import build.model
import toolchains.pam


def verbose():
    build.verbose = True


@influence.attribute("features")
@influence.attribute("incpaths")
@influence.attribute("macros")
@influence.attribute("sources")
class CXXProject(Task):
    incpaths = []
    features = []
    macros = []
    sources = []
    source_influence = True

    def __init__(self, *args, **kwargs):
        super(CXXProject, self).__init__(*args, **kwargs)
        self._init_sources()
        self.macros = utils.as_list(utils.call_or_return(self, self.__class__.macros))
        self.incpaths = utils.as_list(utils.call_or_return(self, self.__class__.incpaths))
        self.features = utils.as_list(utils.call_or_return(self, self.__class__.features))
        if self.source_influence:
            for source in self.sources:
                self.influence.append(influence.FileInfluence(source))

    def _init_sources(self):
        sources = utils.as_list(utils.call_or_return(self, self.__class__.sources))
        self.sources = []
        for l in map(self.tools.glob, sources):
            self.sources += l
        self.sources.sort()
        assert self.sources, "no source files found for task {0}".format(self.name)

    def run(self, deps, tools):
        if hasattr(self, "project"):
            with tools.environ() as env:
                self.toolchain = toolchains.pam.pam_gnu_toolchain("pam-gcc", env=env)
                self.cxx_project = self.toolchain.generate(self.project)
                self.cxx_project.transform()

    def publish(self, artifact, tools):
        artifact.collect("output/pam-gcc/{0}/{0}".format(self.name), flatten=True)


@influence.attribute("shared")
class CXXLibrary(CXXProject):
    shared = False

    def __init__(self, *args, **kwargs):
        super(CXXLibrary, self).__init__(*args, **kwargs)

    def run(self, deps, tools):
        incpaths = []
        macros = []

        for name, artifact in deps.items():
            incpaths += artifact.cxxinfo.incpaths.items()
            macros += artifact.cxxinfo.macros.items()

        self.project = build.model.cxx_library(
            self.name,
            sources=self.sources,
            features=self.features,
            incpaths=self.incpaths + incpaths,
            macros=self.macros,
            shared=self.shared,
        )
        super(CXXLibrary, self).run(deps, tools)

    def publish(self, artifact, tools):
        with tools.cwd(self.cxx_project.output):
            artifact.collect("*.a", "lib/")
            artifact.collect("*.so", "lib/")
            artifact.collect("*.dll", "lib/")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append(self.name)


@influence.attribute("libpaths")
@influence.attribute("libraries")
class CXXExecutable(CXXProject):
    libpaths = []
    libraries = []

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.libpaths = utils.as_list(utils.call_or_return(self, self.__class__.libpaths))
        self.libraries = utils.as_list(utils.call_or_return(self, self.__class__.libraries))

    def run(self, deps, tools):
        incpaths = []
        libpaths = []
        libraries = []
        macros = []

        for name, artifact in deps.items():
            incpaths += [fs.path.join(artifact.path, path)
                         for path in artifact.cxxinfo.incpaths.items()]
            libpaths += [fs.path.join(artifact.path, path)
                         for path in artifact.cxxinfo.libpaths.items()]
            libraries += artifact.cxxinfo.libraries.items()
            macros += artifact.cxxinfo.macros.items()

        self.project = build.model.cxx_executable(
            self.name,
            sources=self.sources,
            features=self.features,
            incpaths=self.incpaths + incpaths,
            libpaths=self.libpaths + libpaths,
            libraries=self.libraries + libraries,
            macros=self.macros + macros,
        )
        super(CXXExecutable, self).run(deps, tools)

    def publish(self, artifact, tools):
        with tools.cwd(self.cxx_project.output):
            if platform.system() == "Windows":
                artifact.collect(self.name + '.exe', "bin/")
            else:
                artifact.collect(self.name, "bin/")
        artifact.environ.PATH.append("bin")
