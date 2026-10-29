from jolt import attributes, Parameter
from jolt.pkgs import gmp
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_gmp")
@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["mpfr"])
@attributes.requires("requires_compiler")
class Mpfr(autotools.Autotools):
    """ GNU multiple precision floating-point library """

    name = "mpfr"
    version = Parameter("4.2.2", help="MPFR version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_gmp = ["gmp"]
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/mpfr/mpfr-{version}.tar.xz"]
    srcdir = "{fetch[src]}/mpfr-{version}"
    options = [
        "--disable-shared",
        "--enable-static",
        "--with-gmp={_gmp}",
        "--with-pic",
    ]

    @property
    def _gmp(self):
        return self.deps["gmp"].path


TaskRegistry.get().add_task_class(Mpfr)
