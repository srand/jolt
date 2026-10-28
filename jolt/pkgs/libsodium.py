from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["sodium"])
class Libsodium(autotools.Autotools):
    """ Library for encryption, decryption, signatures and password hashing, including Argon2 """

    name = "libsodium"
    version = Parameter("1.0.22", help="libsodium version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_src = ["fetch:alias=src,url=https://download.libsodium.org/libsodium/releases/libsodium-{version}.tar.gz"]
    srcdir = "{fetch[src]}/libsodium-{version}"
    options = [
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "--{pic[with,without]}-pic",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libsodium)
