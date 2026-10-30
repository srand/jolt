from jolt import attributes, Parameter
from jolt.pkgs import compiler, m4
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_m4")
@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["gmp"])
@attributes.requires("requires_compiler")
class Gmp(autotools.Autotools):
    """ GNU multiple precision arithmetic library """

    name = "gmp"
    version = Parameter("6.3.0", help="GMP version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_m4 = ["m4"]
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/gmp/gmp-{version}.tar.xz"]
    srcdir = "{fetch[src]}/gmp-{version}"
    options = [
        # C23 rejects old-style declarations in configure tests
        "CFLAGS='-O2 -std=gnu17'",
        "--disable-shared",
        "--enable-static",
        "--with-pic",
    ]


TaskRegistry.get().add_task_class(Gmp)
