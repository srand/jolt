from jolt import attributes, Parameter
from jolt.plugins import autotools, git, libtool, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires(libtool=False)
@libtool.relocate()
@libtool.requires()
@pkgconfig.requires()
@pkgconfig.to_cxxinfo("libfastjson")
class Libfastjson(autotools.Autotools):
    """ Builds and publishes liblibraries and headers. """

    name = "libfastjson"
    version = Parameter("1.2304.0", help="Libfastjson version.")
    requires_git = ["git:url=https://github.com/rsyslog/libfastjson.git,rev=v{version}"]
    srcdir = "{git[libfastjson]}"


TaskRegistry.get().add_task_class(Libfastjson)
