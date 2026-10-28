from jolt import attributes, Download, Parameter
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
class Sccache(Download):
    """ Shared compiler cache """

    name = "sccache"
    version = Parameter("0.19.0", help="sccache version.")
    url = "https://github.com/mozilla/sccache/releases/download/v{version}/sccache-v{version}-{_triple}.{_ext}"

    @property
    def _triple(self):
        arch = "aarch64" if self.arch in ["arm64", "aarch64"] else "x86_64"
        return {
            "darwin": "{}-apple-darwin",
            "linux": "{}-unknown-linux-musl",
            "windows": "{}-pc-windows-msvc",
        }[self.system].format(arch)

    @property
    def _ext(self):
        return "zip" if self.system == "windows" else "tar.gz"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append(tools.expand("sccache-v{version}-{_triple}"))


TaskRegistry.get().add_task_class(Sccache)
