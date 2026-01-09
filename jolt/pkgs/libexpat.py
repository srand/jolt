from jolt import attributes, Parameter
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
class Libexpat(cmake.CMake):
    name = "libexpat"
    version = Parameter("2.7.3", help="Expat version.")
    version_tag = property(lambda self: str(self.version).replace('.', '_'))
    requires_src = ["fetch:alias=src,url=https://github.com/libexpat/libexpat/releases/download/R_{version_tag}/expat-{version}.tar.gz"]
    srcdir = "{fetch[src]}/expat-{version}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("expat")


TaskRegistry.get().add_task_class(Libexpat)
