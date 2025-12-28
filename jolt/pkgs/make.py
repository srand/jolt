from jolt import attributes, Parameter, Task
from jolt.pkgs import makeinfo, autoconf
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_autoconf")
@attributes.requires("requires_git")
@attributes.requires("requires_texinfo")
class GnuMake(autotools.Autotools):
    name = "make"
    version = Parameter("4.4.1", help="Automake version.")
    requires_autoconf = ["autoconf"]
    requires_git = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/make/make-{version}.tar.gz"]
    requires_texinfo = ["texinfo"]
    srcdir = "{fetch[src]}/make-{version}"


TaskRegistry.get().add_task_class(GnuMake)
