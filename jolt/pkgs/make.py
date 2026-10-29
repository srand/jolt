from jolt import attributes, Parameter
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_texinfo")
@autotools.requires(automake=False, libtool=False)
@attributes.requires("requires_compiler")
class GnuMake(autotools.Autotools):
    name = "make"
    version = Parameter("4.4.1", help="GNU Make version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/make/make-{version}.tar.gz"]
    requires_texinfo = ["texinfo"]
    srcdir = "{fetch[src]}/make-{version}"


TaskRegistry.get().add_task_class(GnuMake)
