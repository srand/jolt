from jolt import attributes as jolt_attributes
from jolt import Download
from jolt import Parameter
from jolt.tasks import TaskRegistry

import platform


@jolt_attributes.system
@jolt_attributes.attribute("url", "url_{system}")
class Golang(Download):
    name = "golang"
    version = Parameter("1.18.3", help="Go version.")
    url_linux = "https://go.dev/dl/go{version}.linux-{arch}.tar.gz"
    url_windows = "https://go.dev/dl/go{version}.windows-{arch}.zip"

    @property
    def arch(self):
        arch = platform.machine()
        if arch == "x86_64":
            return "amd64"
        if arch in ["i386", "i486", "i586", "i686"]:
            return "i386"
        if arch in ["arm", "armv6l", "armv7l"]:
            return "armv6l"
        if arch in ["arm64", "armv8l", "aarch64"]:
            return "arm64"
        return None

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("go/bin")
        artifact.paths.goroot = "go"

    def unpack(self, artifact, tools):
        artifact.environ.GOROOT = str(artifact.paths.goroot)


TaskRegistry.get().add_task_class(Golang)
