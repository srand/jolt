import json
from os import path

from jolt import *
from jolt.tasks import TaskRegistry
from jolt.error import raise_task_error_if


class ConanPkgs(Task):
    manifest = None

    packages = []

    def run(self, deps, tools):
        raise_task_error_if(not tools.which("conan"), self, "Conan is not installed in the PATH")

        manifest = tools.expand_path(self.manifest) if self.manifest else None

        with tools.cwd(tools.builddir()):
            if manifest is None or not path.exists(manifest):
                manifest = "conanfile.txt"
                self.info("Creating conanfile.txt")
                self.tools.write_file(manifest, "[requires]\n")
                for pkg in self.packages:
                    self.tools.append_file(manifest, pkg + "\n")

            self.info("Installing the manifest into the Conan cache")
            tools.run("conan install --build=missing -u -if . -g json {}", manifest)

            self.info("Parsing manifest")
            self._manifest = json.loads(tools.read_file("conanbuildinfo.json"))

            for dep in self._manifest["dependencies"]:
                self.info("Collecting '{}' files from: {}", dep["name"], dep["rootpath"])
                tools.copy(dep["rootpath"], dep["name"])


    def publish(self, artifact, tools):
        self.info("Publishing package files")
        with tools.cwd(tools.builddir()):
            artifact.collect("*")

        self.info("Publishing metadata")
        for dep in self._manifest["dependencies"]:
            for incpath in dep["include_paths"]:
                artifact.cxxinfo.incpaths.append(path.join(dep["name"], path.relpath(incpath, dep["rootpath"])))
            for libpath in dep["lib_paths"]:
                artifact.cxxinfo.libpaths.append(path.join(dep["name"], path.relpath(libpath, dep["rootpath"])))
            for binpath in dep["bin_paths"]:
                artifact.environ.PATH.append(path.join(dep["name"], path.relpath(binpath, dep["rootpath"])))
            artifact.cxxinfo.libraries.append(dep["libs"])
            artifact.cxxinfo.libraries.append(dep["system_libs"])
            artifact.cxxinfo.macros.append(dep["defines"])
            artifact.cxxinfo.cflags.append(dep["cflags"])
            artifact.cxxinfo.cxxflags.append(dep["cxxflags"])
            artifact.cxxinfo.ldflags.append(dep["exelinkflags"])
