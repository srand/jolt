import os
from jolt import attributes, Alias, BooleanParameter, Download, IntParameter, Parameter
from jolt.pkgs import cpython
from jolt.plugins import git
from jolt.tasks import Task, TaskRegistry
from jolt.error import raise_task_error_if


@attributes.common_metadata()
@attributes.requires("requires_git")
@attributes.requires("requires_python")
@attributes.system
class Boost(Task):
    name = "boost"
    version = Parameter("1.90.0", help="Boost version.")
    shared = BooleanParameter(False, "Build shared libraries")
    bits = IntParameter(64, values=[32, 64], help="Boost address-model")
    requires_git = ["git:url=https://github.com/boostorg/boost.git,path={buildroot}/git-boost,rev=boost-{version},submodules=true"]
    requires_python = ["cpython"]

    def run(self, artifact, tools):
        self.builddir = tools.builddir("build", incremental=True)
        self.installdir = tools.builddir("install")
        with tools.cwd("{git[boost]}"):
            if self.system == "windows":
                tools.run(".\\bootstrap.bat msvc")
                tools.run(".\\b2 install address-model={bits} link={shared[shared,static]} --prefix={installdir} --with=all --build-dir={builddir} -j{}", tools.cpu_count())
            else:
                tools.run("./bootstrap.sh")
                tools.run("./b2 install address-model={bits} link={shared[shared,static]} --prefix={installdir} --with=all --build-dir={builddir} -j{}", tools.cpu_count())

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")

        with tools.cwd(self.installdir, "lib"):
            for lib in tools.glob("libboost_*.a"):
                name, _ = os.path.splitext(os.path.basename(lib))
                artifact.cxxinfo.libraries.append(name[3:])

            arch = tools.getenv("VSCMD_ARG_TGT_ARCH", "x64")
            for lib in tools.glob(f"lib*-mt-{arch}-*.lib"):
                name, _ = os.path.splitext(lib)
                artifact.cxxinfo.libraries.append(name)


TaskRegistry.get().add_task_class(Boost)
