from jolt import attributes, Parameter
from jolt.pkgs import gmp, mpfr
from jolt.plugins import autotools, cxxinfo, fetch, libtool
from jolt.tasks import TaskRegistry


@attributes.requires("requires_libs")
@attributes.requires("requires_src")
@libtool.relocate()
@cxxinfo.publish(libraries=["mpc"])
class Mpc(autotools.Autotools):
    """ GNU multiple precision complex arithmetic library """

    name = "mpc"
    version = Parameter("1.4.1", help="GNU MPC version.")
    requires_libs = ["gmp", "mpfr"]
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/mpc/mpc-{version}.tar.xz"]
    srcdir = "{fetch[src]}/mpc-{version}"
    options = [
        "--disable-shared",
        "--enable-static",
        "--with-gmp={_gmp}",
        "--with-mpfr={_mpfr}",
        "--with-pic",
    ]

    @property
    def _gmp(self):
        return self.deps["gmp"].path

    @property
    def _mpfr(self):
        return self.deps["mpfr"].path


TaskRegistry.get().add_task_class(Mpc)
