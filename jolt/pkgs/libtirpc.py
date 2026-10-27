from jolt import attributes, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
@cxxinfo.publish(libraries=["tirpc"])
class Libtirpc(autotools.Autotools):
    """Libtirpc package"""
    name = "libtirpc"

    version = Parameter("1.3.8", help="libtirpc version.")
    requires_src = ["fetch:alias=src,url=https://downloads.sourceforge.net/project/libtirpc/libtirpc/{version}/libtirpc-{version}.tar.bz2"]
    srcdir = "{fetch[src]}/libtirpc-{version}"
    options = ["--disable-gssapi"]


TaskRegistry.get().add_task_class(Libtirpc)
