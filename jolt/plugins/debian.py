from jolt import BooleanParameter, Parameter, Task
from jolt import attributes, filesystem as fs, loader
from jolt.tasks import TaskRegistry

from jolt.cache import ArtifactListAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider

import contextlib
import os
import platform


class DebianListVariable(ArtifactListAttribute):
    pass


class DebianAttributeSet(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(DebianAttributeSet, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        if name == "chroot":
            return DebianListVariable(self._artifact, "chroot")
        assert False, "No such debian attribute: {0}".format(name)


@ArtifactAttributeSetProvider.Register
class DebianAttributeProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "debian", DebianAttributeSet(artifact))

    def parse(self, artifact, content):
        if "debian" not in content:
            return
        for key, value in content["debian"].items():
            getattr(artifact.debian, key).set_value(value, expand=False)

    def format(self, artifact, content):
        if "debian" not in content:
            content["debian"] = {}
        for key, attrib in artifact.debian.items():
            content["debian"][key] = attrib.get_value()

    def apply_deps(self, task, deps):
        lowerdirs = []
        for _, artifact in deps.items():
            lowerdirs += [
                fs.path.join(artifact.path, item)
                for item in artifact.debian.chroot.items()
            ]
        if lowerdirs:
            task.__chroot = task.tools.builddir("chroot")
            with task.tools.cwd(task.__chroot):
                task.tools.mkdir("work")
                task.tools.mkdir("uppr")
                task.tools.mkdir("root")
                task.tools.run("fuse-overlayfs -o lowerdir={},upperdir=uppr,workdir=work root",
                               ":".join(lowerdirs))
            task.__unshare = contextlib.ExitStack()
            task.__unshare.enter_context(
                task.tools.chroot(chroot=fs.path.join(task.__chroot, "root")))

    def unapply_deps(self, task, deps):
        try:
            task.__unshare.close()
            with task.tools.cwd(task.__chroot):
                task.tools.run("fusermount -u root")
        except Exception:
            pass


class Debian(Task):
    abstract = False

    packages = []
    """ List of packages to install, in addition to those included by variant. """

    mode = "unshare"
    """
    Mode of operation when creating Debian chroot.

    Valid modes are:

      - fakeroot
      - proot
      - unshare

    The default mode is fakeroot. See mmdebstrap documentation
    for details. Note that Jolt does not permit any mode that requires
    root privileges.
    """

    mirrors = []
    """ List of mirrors """

    suite = "bullseye"
    """
    Debian release codename.

    The suite may be a valid release code name (eg, sid, stretch, jessie)
    or a symbolic name (eg, unstable, testing, stable, oldstable).
    Any suite name that works with apt on the given mirror will work.
    """

    target = "rootfs.tar"
    """ Target """

    variant = "extract"
    """
    Choose which package set to install.

    Valid variant names are:
      - extract
      - custom
      - essential
      - apt
      - required
      - minbase
      - buildd
      - important
      - debootstrap
      - standard

    The default variant is extract where only packages listed in ``packages``
    are downloaded and extracted, but not installed.

    See mmdebstrab documentation for details.
    """

    def run(self, deps, tools):
        with tools.cwd(tools.builddir()):
            packages = "--include={}".format(",".join(self.packages)) if self.packages else ""
            tools.run(
                "mmdebstrap {} --mode={mode} --variant={variant} {suite} {target}",
                packages,
            )

    def publish(self, artifact, tools):
        with tools.cwd(tools.builddir()):
            artifact.collect("*", symlinks=True)


class DebianPkgBase(Debian):
    abstract = True

    include = ["."]
    exclude = []

    def run(self, deps, tools):
        super().run(deps, tools)
        with tools.cwd(tools.builddir()):
            include = " ".join(self.include)
            exclude = " ".join(["--exclude=" + i for i in self.exclude])
            tools.run("tar --exclude=./dev {} -xf {target} {}", exclude, include)
            tools.unlink(self.target)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)

        with tools.cwd(artifact.path):
            for bindir in ["bin", "sbin", "usr/bin", "usr/sbin"]:
                if os.path.exists(tools.expand_path(bindir)):
                    artifact.environ.PATH.append(bindir)

            for incdir in ["usr/include"]:
                if os.path.exists(tools.expand_path(incdir)):
                    pass  # artifact.cxxinfo.incpaths.append(incdir)

            for libdir in ["lib", "usr/lib"]:
                if os.path.exists(tools.expand_path(libdir)):
                    pass  # artifact.cxxinfo.libpaths.append(libdir)
                    artifact.environ.LD_LIBRARY_PATH.append(libdir)

            for pkgdir in ["usr/share/pkgconfig"]:
                if os.path.exists(tools.expand_path(pkgdir)):
                    artifact.environ.PKG_CONFIG_PATH.append(pkgdir)


@attributes.method("run", "run_{download[download,build]}")
class MMDebstrap(DebianPkgBase):
    """
    Provides the tools required to build Debian tools and filesystems.
    """

    name = "debian/mmdebstrap"
    packages = [
        "bash",
        "bubblewrap",
        "coreutils",
        "dash",
        "fakechroot",
        "fakeroot",
        "fuse-overlayfs",
        "mmdebstrap",
        "proot",
        "qemu-user",
        "util-linux",
    ]
    mode = "unshare"
    suite = "bullseye"
    variant = "essential"

    download = BooleanParameter(True, help="Download files from Github, or build from scratch.")
    url = "https://github.com/srand/jolt/releases/download/v0.9.35/mmdebstrap.tgz"

    @property
    def joltdir(self):
        return loader.JoltLoader.get().joltdir

    def run_build(self, deps, tools):
        super().run(deps, tools)

    def run_download(self, deps, tools):
        with tools.cwd(tools.builddir()):
            assert tools.download(self.url, "debstrap.tgz"), "Failed to download mmdebstrap"
            tools.extract("debstrap.tgz", ".")
            tools.unlink("debstrap.tgz")


TaskRegistry.get().add_task_class(MMDebstrap)


class DebianPkg(DebianPkgBase):
    abstract = True
    requires = ["debian/mmdebstrap"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.debian.chroot.append(".")


class DebianEssential(DebianPkg):
    name = "debian/essential"
    variant = "essential"

    @property
    def joltdir(self):
        return loader.JoltLoader.get().joltdir


TaskRegistry.get().add_task_class(DebianEssential)


def _host():
    m = platform.machine()
    if m == "x86_64":
        return "amd64"
    return m


@attributes.attribute("packages", "packages_{host}_{arch}")
@attributes.method("publish", "publish_{host}_{arch}")
class GCC(DebianPkg):
    name = "debian/gcc"

    host = Parameter(_host(), values=["amd64"], const=True)
    arch = Parameter(_host(), values=["amd64", "armel", "armhf", "arm64"], help="Target architecture.")

    packages_amd64_amd64 = ["gcc", "g++"]
    packages_amd64_armhf = ["crossbuild-essential-armhf"]
    packages_amd64_armel = ["crossbuild-essential-armel"]
    packages_amd64_arm64 = ["crossbuild-essential-arm64"]

    @property
    def joltdir(self):
        return loader.JoltLoader.get().joltdir

    def publish_amd64_amd64(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.AR = "ar"
        artifact.environ.CC = "gcc"
        artifact.environ.CONFIGURE_FLAGS = ""
        artifact.environ.CPP = "cpp"
        artifact.environ.CROSS_COMPILE = ""
        artifact.environ.CXX = "g++"
        artifact.environ.LD = "ld"
        artifact.environ.OBJCOPY = "objcopy"
        artifact.environ.OBJDUMP = "objdump"
        artifact.environ.PKG_CONFIG = "pkg-config"
        artifact.environ.RANLIB = "ranlib"
        artifact.environ.STRIP = "strip"
        artifact.environ.TARGET_PREFIX = ""

    def publish_amd64_armel(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.AR = "arm-linux-gnueabi-ar"
        artifact.environ.CC = "arm-linux-gnueabi-gcc"
        artifact.environ.CONFIGURE_FLAGS = "--target arm-linux-gnueabi --host arm-linux-gnueabi --build x86_64-linux-gnu"
        artifact.environ.CPP = "arm-linux-gnueabi-cpp"
        artifact.environ.CROSS_COMPILE = "arm-linux-gnueabi-"
        artifact.environ.CXX = "arm-linux-gnueabi-g++"
        artifact.environ.LD = "arm-linux-gnueabi-ld"
        artifact.environ.NM = "arm-linux-gnueabi-nm"
        artifact.environ.OBJCOPY = "arm-linux-gnueabi-objcopy"
        artifact.environ.OBJDUMP = "arm-linux-gnueabi-objdump"
        artifact.environ.PKG_CONFIG = "arm-linux-gnueabi-pkg-config"
        artifact.environ.RANLIB = "arm-linux-gnueabi-ranlib"
        artifact.environ.STRIP = "arm-linux-gnueabi-strip"
        artifact.environ.TARGET_PREFIX = "arm-linux-gnueabi-"

    def publish_amd64_armhf(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.AR = "arm-linux-gnueabihf-ar"
        artifact.environ.CC = "arm-linux-gnueabihf-gcc"
        artifact.environ.CONFIGURE_FLAGS = "--target arm-linux-gnueabihf --host arm-linux-gnueabihf --build x86_64-linux-gnu"
        artifact.environ.CPP = "arm-linux-gnueabihf-cpp"
        artifact.environ.CROSS_COMPILE = "arm-linux-gnueabihf-"
        artifact.environ.CXX = "arm-linux-gnueabihf-g++"
        artifact.environ.LD = "arm-linux-gnueabihf-ld"
        artifact.environ.NM = "arm-linux-gnueabihf-nm"
        artifact.environ.OBJCOPY = "arm-linux-gnueabihf-objcopy"
        artifact.environ.OBJDUMP = "arm-linux-gnueabihf-objdump"
        artifact.environ.PKG_CONFIG = "arm-linux-gnueabihf-pkg-config"
        artifact.environ.RANLIB = "arm-linux-gnueabihf-ranlib"
        artifact.environ.STRIP = "arm-linux-gnueabihf-strip"
        artifact.environ.TARGET_PREFIX = "arm-linux-gnueabihf-"

    def publish_amd64_arm64(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.AR = "aarch64-linux-gnu-ar"
        artifact.environ.CC = "aarch64-linux-gnu-gcc"
        artifact.environ.CONFIGURE_FLAGS = "--target aarch64-linux-gnu --host aarch64-linux-gnu --build x86_64-linux-gnu"
        artifact.environ.CPP = "aarch64-linux-gnu-cpp"
        artifact.environ.CROSS_COMPILE = "aarch64-linux-gnu-"
        artifact.environ.CXX = "aarch64-linux-gnu-g++"
        artifact.environ.LD = "aarch64-linux-gnu-ld"
        artifact.environ.NM = "aarch64-linux-gnu-nm"
        artifact.environ.OBJCOPY = "aarch64-linux-gnu-objcopy"
        artifact.environ.OBJDUMP = "aarch64-linux-gnu-objdump"
        artifact.environ.PKG_CONFIG = "aarch64-linux-gnu-pkg-config"
        artifact.environ.RANLIB = "aarch64-linux-gnu-ranlib"
        artifact.environ.STRIP = "aarch64-linux-gnu-strip"
        artifact.environ.TARGET_PREFIX = "aarch64-linux-gnu-"


TaskRegistry.get().add_task_class(GCC)
