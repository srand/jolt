from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import libudev_zero
from jolt.plugins import autotools, cxxinfo, fetch, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@attributes.requires("requires_udev")
@pkgconfig.requires()
@cxxinfo.publish(libraries=["usb-1.0"])
@attributes.requires("requires_compiler")
class Libusb(autotools.Autotools):
    """ Library for access to USB devices """

    name = "libusb"
    version = Parameter("1.0.30", help="libusb version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://github.com/libusb/libusb/releases/download/v{version}/libusb-{version}.tar.bz2"]
    requires_udev = ["libudev-zero"]
    srcdir = "{fetch[src]}/libusb-{version}"
    options = [
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "--enable-udev",
    ]

    def run(self, deps, tools):
        # libudev is looked for with header and library checks, which ignore pkg-config
        with tools.environ(
            CPPFLAGS=tools.run("pkg-config --cflags libudev").strip() + " " + tools.getenv("CPPFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs-only-L libudev").strip() + " " + tools.getenv("LDFLAGS", ""),
        ):
            super().run(deps, tools)
        # Let pkg-config find libudev, which is not installed on the system.
        # A static library is useless without it, also without --static.
        requires = "Requires.private" if self.shared else "Requires"
        with tools.cwd(tools.autotools().installdir, "jolt-prefix", "lib", "pkgconfig"):
            tools.replace_in_file("libusb-1.0.pc", "Libs.private: -ludev", requires + ": libudev\nLibs.private:")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libusb)
