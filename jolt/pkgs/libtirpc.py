from jolt import attributes, Parameter
from jolt.plugins import autotools, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
@cxxinfo.publish(libraries=["tirpc"])
@attributes.requires("requires_compiler")
class Libtirpc(autotools.Autotools):
    """Libtirpc package"""
    name = "libtirpc"

    version = Parameter("1.3.8", help="libtirpc version.")
    # Release tarballs contain a link to an absolute path, which Python refuses to extract
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:clean=true,url=git://git.linux-nfs.org/projects/steved/libtirpc.git,rev=libtirpc-{_version}"]
    srcdir = "{git[libtirpc]}"
    options = ["--disable-gssapi"]

    @property
    def _version(self):
        return str(self.version).replace(".", "-")


TaskRegistry.get().add_task_class(Libtirpc)
