from jolt import attributes, Download, Parameter
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
class Zig(Download):
    """ Zig compiler and C/C++ cross compiler """

    name = "zig"
    version = Parameter("0.17.0", help="Zig version.")
    url = "https://ziglang.org/download/{version}/zig-{_arch}-{_os}-{version}.{_ext}"

    @property
    def _arch(self):
        if self.arch in ["amd64", "x86_64"]:
            return "x86_64"
        if self.arch in ["arm64", "aarch64"]:
            return "aarch64"
        return self.arch

    @property
    def _os(self):
        return {"darwin": "macos"}.get(self.system, self.system)

    @property
    def _ext(self):
        return "zip" if self.system == "windows" else "tar.xz"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append(tools.expand("zig-{_arch}-{_os}-{version}"))


TaskRegistry.get().add_task_class(Zig)
