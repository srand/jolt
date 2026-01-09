import os
from jolt import attributes, Alias, Task, Parameter
from jolt.plugins import autotools, git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
class PkgConfPosix(autotools.Autotools):
    """ Package that provides the 'pkgconf' binary, an alternative implementation of 'pkg-config'. """

    name = "pkgconf/posix"
    version = Parameter("2.5.1", help="pkg-config version.")
    requires_git = ["git:url=https://github.com/pkgconf/pkgconf.git,rev=pkgconf-{version}"]
    srcdir = "{git[pkgconf]}"
    options = ["--enable-static", "--disable-shared"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PKG_CONFIG = "pkgconf"

        # Install pkg-config symlink
        with tools.cwd(artifact.path, "bin"):
            tools.symlink("pkgconf", "pkg-config")
        


@attributes.requires("requires_git")
@meson.requires()
class PkgConfWin32(meson.Meson):
    """ Package that provides the 'pkgconf' binary, an alternative implementation of 'pkg-config'. """

    name = "pkgconf/win32"
    version = Parameter("2.5.1", help="pkg-config version.")
    requires_git = ["git:url=https://github.com/pkgconf/pkgconf.git,rev=pkgconf-{version}"]
    srcdir = "{git[pkgconf]}"
    options = [
        "default_library=static",
        "tests=disabled",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PKG_CONFIG = "pkgconf"

        # Install pkg-config copy
        with tools.cwd(artifact.path, "bin"):
            tools.copy("pkgconf", "pkg-config")


@attributes.requires("requires_{system}")
@attributes.system
class PkgConf(Alias):
    """ Alias for pkgconf package. """

    name = "pkgconf"
    version = Parameter("2.5.1", help="pkg-config version.")
    requires_darwin = ["pkgconf/posix:version={version}"]
    requires_linux = requires_darwin
    requires_windows = ["pkgconf/win32:version={version}"]


TaskRegistry.get().add_task_class(PkgConf)
TaskRegistry.get().add_task_class(PkgConfPosix)
TaskRegistry.get().add_task_class(PkgConfWin32)
