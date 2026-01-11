from jolt import attributes
from jolt import Download
from jolt import Parameter
from jolt.tasks import TaskRegistry

import platform


@attributes.system
class NodeJS(Download):
    name = "nodejs"
    version = Parameter("25.2.1", help="NodeJS version.")
    url = "https://nodejs.org/dist/v{version}/node-v{version}-{os}-{arch}.{ext}"
    bin = "node-v{version}-{os}-{arch}/bin"

    @property
    def os(self):
        if self.system == "windows":
            return "win"
        return self.system

    @property
    def ext(self):
        if self.system == "windows":
            return "zip"
        return "tar.gz"

    @property
    def arch(self):
        arch = platform.machine().lower()
        if arch in ["amd64", "x86_64"]:
            return "x64"
        if arch in ["i386", "i486", "i586", "i686"]:
            return "x86"
        if arch in ["arm", "armv7l"]:
            return "armv7l"
        if arch in ["arm64", "armv8l", "aarch64"]:
            return "arm64"
        return None

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append(self.bin)


TaskRegistry.get().add_task_class(NodeJS)
