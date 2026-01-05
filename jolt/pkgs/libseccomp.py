from jolt import attributes, Parameter
from jolt.pkgs import gperf, libtool
from jolt.plugins import git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_gperf")
@attributes.requires("requires_libtool")
@pkgconfig.requires()
@pkgconfig.to_cxxinfo("libseccomp")
class Libseccomp(autotools.Autotools):
    name = "libseccomp"
    version = Parameter("2.5.6", help="libseccomp version.")
    requires_git = ["git:url=https://github.com/seccomp/libseccomp.git,rev=v{version}"]
    requires_gperf = ["gperf"]
    requires_libtool = ["libtool"]
    srcdir = "{git[libseccomp]}"


TaskRegistry.get().add_task_class(Libseccomp)
