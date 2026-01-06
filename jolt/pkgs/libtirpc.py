from jolt import attributes, Parameter
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
class Libtirpc(autotools.Autotools):
    """Libtirpc package"""
    name = "libtirpc"

    version = Parameter("1.3.7", help="libtirpc version.")
    requires_src = ["fetch:alias=src,url=https://downloads.sourceforge.net/project/libtirpc/libtirpc/1.3.7/libtirpc-1.3.7.tar.bz2"]
    srcdir = "{fetch[src]}/libtirpc-{version}"
    options = ["--disable-gssapi"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("tirpc")


TaskRegistry.get().add_task_class(Libtirpc)
