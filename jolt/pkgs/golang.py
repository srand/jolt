from jolt import attributes as jolt_attributes
from jolt import Download
from jolt import Parameter
from jolt.tasks import TaskRegistry

import platform


@jolt_attributes.arch
@jolt_attributes.system
@jolt_attributes.attribute("url", "url_{system}")
class Golang(Download):
    name = "golang"
    version = Parameter("1.25.5", help="Go version.")
    url_linux = "https://go.dev/dl/go{version}.linux-{go_arch}.tar.gz"
    url_windows = "https://go.dev/dl/go{version}.windows-{go_arch}.zip"

    @property
    def go_arch(self):
        if self.arch in ["amd64", "x86_64"]:
            return "amd64"
        if self.arch in ["i386", "i486", "i586", "i686"]:
            return "i386"
        if self.arch in ["arm", "armv6l", "armv7l"]:
            return "armv6l"
        if self.arch in ["arm64", "armv8l", "aarch64"]:
            return "arm64"
        return None

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.paths.goroot = "go"
        artifact.environ.GOROOT = str(artifact.paths.goroot)
        artifact.environ.PATH.append("go/bin")

    def unpack(self, artifact, tools):
        artifact.environ.GOROOT = str(artifact.paths.goroot)


TaskRegistry.get().add_task_class(Golang)
