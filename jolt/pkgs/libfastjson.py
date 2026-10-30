from jolt import attributes, Parameter
from jolt.plugins import autotools, git, libtool, pkgconfig
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@attributes.requires("requires_git")
@autotools.requires(libtool=False)
@libtool.requires()
@pkgconfig.requires()
@pkgconfig.to_cxxinfo("libfastjson")
@attributes.requires("requires_compiler")
class Libfastjson(autotools.Autotools):
    """ Builds and publishes liblibraries and headers. """

    name = "libfastjson"
    version = Parameter("1.2609.0", help="libfastjson version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/rsyslog/libfastjson.git,rev=v{version}"]
    srcdir = "{git[libfastjson]}"


TaskRegistry.get().add_task_class(Libfastjson)
