from jolt import attributes as jolt_attributes
from jolt import Download
from jolt import Parameter
from jolt.tasks import TaskRegistry

import platform


@jolt_attributes.system
@jolt_attributes.attribute("bin", "bin_{system}")
@jolt_attributes.attribute("url", "url_{system}")
class NodeJS(Download):
    name = "nodejs"
    version = Parameter("16.15.1", help="NodeJS version.")
    url_linux = "https://nodejs.org/dist/v{version}/node-v{version}-linux-{arch}.tar.gz"
    url_windows = "https://nodejs.org/dist/v{version}/node-v{version}-win-{arch}.zip"
    bin_linux = "node-v{version}-linux-{arch}/bin"
    bin_windows = "node-v{version}-win-{arch}/bin"

    @property
    def arch(self):
        arch = platform.machine()
        if arch == "x86_64":
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
