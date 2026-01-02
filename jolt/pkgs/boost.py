import os
from jolt import attributes, Alias, Download, IntParameter, Parameter
from jolt.plugins import git
from jolt.tasks import Task, TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_git")
@attributes.system
class BoostSrc(Task):
    name = "boost/src"
    version = Parameter("1.90.0", help="Boost version.")
    requires_git = ["git:url=https://github.com/boostorg/boost.git,depth=1,rev=boost-{version},submodules=true"]

    def run(self, artifact, tools):
        self.builddir = tools.builddir("build", incremental=True)
        self.installdir = tools.builddir("install")
        with tools.cwd("{git[boost]}"):
            if self.system == "windows":
                tools.run("bootstrap.bat msvc")
                tools.run("b2 install --prefix={installdir} --with=all --build-dir={builddir} -j{}", tools.cpu_count())
            else:
                tools.run("./bootstrap.sh")
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


class BoostBin(Download):
    """ Downloads official pre-built Boost binaries """
    name = "boost/bin/msvc"
    version = Parameter("1.90.0", help="Boost version.")
    url = "https://archives.boost.io/release/1.90.0/binaries/boost_1_90_0-bin-msvc-all-32-64.7z"
    collect = [
        {"files": "*", "dest": "lib/", "cwd": "boost_{version_dir}/lib{bits}-msvc-{msvcver}"},
        {"files": "boost", "dest": "include/", "cwd": "boost_{version_dir}"},
    ]
    msvcver = Parameter("14.3", help="MSVC version.")
    bits = IntParameter(64, values=[32, 64])

    @property
    def version_dir(self):
        return str(self.version).replace(".", "_")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.crt = "Dynamic"
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        with tools.cwd(artifact.path, "lib"):
            for lib in tools.glob("lib*-mt-x*.lib"):
                name, _ = os.path.splitext(lib)
                artifact.cxxinfo.libraries.append(name)


@attributes.system
@attributes.requires("requires_{system}")
class Boost(Alias):
    name = "boost"
    version = Parameter("1.90.0", help="Boost version.")
    requires_darwin = ["boost/src:version={version}"]
    requires_linux = requires_darwin
    requires_windows = ["boost/bin/msvc:version={version}"]


TaskRegistry.get().add_task_class(Boost)
TaskRegistry.get().add_task_class(BoostBin)
TaskRegistry.get().add_task_class(BoostSrc)
