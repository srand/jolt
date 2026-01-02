from jolt import attributes, Task, Parameter
from jolt.pkgs import libtool, meson
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libtool")
@attributes.requires("requires_meson")
class PkgConf(meson.Meson):
    """ Package that provides the 'pkgconf' binary, an alternative implementation of 'pkg-config'. """

    name = "pkgconf"
    version = Parameter("2.5.1", help="pkg-config version.")
    requires_git = ["git:url=https://github.com/pkgconf/pkgconf.git,rev=pkgconf-{version}"]
    #requires_libtool = ["libtool"]
    requires_meson = ["meson"]
    srcdir = "{git[pkgconf]}"
    options = [
        "default_library=static",
        "tests=disabled",
    ]


@attributes.common_metadata()
@attributes.system
class PkgConfig(Task):
    """ Package that provides the 'pkg-config' binary using 'pkgconf'. """

    name = "pkg-config"
    requires = ["pkgconf"]
    selfsustained = True

    def run(self, deps, tools):
        self.pkgconf = deps["pkgconf"]

    def publish(self, artifact, tools):
        with tools.cwd(self.pkgconf.path):
            artifact.collect("*", symlinks=True)
            artifact.environ.PKG_CONFIG = "pkgconf"

        if self.system == "windows":
            return

        # Create a pkg-config symlink
        with tools.cwd(artifact.path, "bin"):
            tools.symlink("pkgconf", "pkg-config")


TaskRegistry.get().add_task_class(PkgConf)
TaskRegistry.get().add_task_class(PkgConfig)
