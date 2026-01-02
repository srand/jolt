import os
from jolt import attributes, Parameter
from jolt.pkgs import b2
from jolt.plugins import git
from jolt.tasks import Task, TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_b2")
@attributes.requires("requires_git")
@attributes.system
class Boost(Task):
    name = "boost"
    version = Parameter("1.90.0", help="Boost version.")
    requires_b2 = ["b2"]
    requires_git = ["git:url=https://github.com/boostorg/boost.git,depth=1,rev=boost-{version},submodules=true"]

    def run(self, artifact, tools):
        self.builddir = tools.builddir("build", incremental=True)
        self.installdir = tools.builddir("install")
        with tools.cwd("{git[boost]}"):
            if self.system == "windows":
                tools.run("b2 install --prefix={installdir} --with=all --build-dir={builddir} -j{}", tools.cpu_count())
            else:
                tools.run("b2 install --prefix={installdir} --with=all --build-dir={builddir} -j{}", tools.cpu_count())

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")

        with tools.cwd(self.installdir + "/lib"):
            for lib in tools.glob("libboost_*.a"):
                name, _ = os.path.splitext(os.path.basename(lib))
                artifact.cxxinfo.libraries.append(name[3:])
            for lib in tools.glob("boost_*.lib"):
                name, _ = os.path.splitext(os.path.basename(lib))
                artifact.cxxinfo.libraries.append(name)


TaskRegistry.get().add_task_class(Boost)
