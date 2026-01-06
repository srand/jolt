from jolt import attributes
from jolt import Download
from jolt import Parameter
from jolt.tasks import TaskRegistry


@attributes.attribute("url", "url_{system}")
@attributes.system
class OpenJDK(Download):
    name = "openjdk"
    version = Parameter("25.0.1", const=True, help="OpenJDK version.")

    collect = [{"files": "*", "cwd": f"jdk-{version}"}]
    url_darwin = "https://download.java.net/java/GA/jdk25.0.1/2fbf10d8c78e40bd87641c434705079d/8/GPL/openjdk-25.0.1_macos-x64_bin.tar.gz"
    url_linux = "https://download.java.net/java/GA/jdk25.0.1/2fbf10d8c78e40bd87641c434705079d/8/GPL/openjdk-25.0.1_linux-x64_bin.tar.gz"
    url_windows = "https://download.java.net/java/GA/jdk25.0.1/2fbf10d8c78e40bd87641c434705079d/8/GPL/openjdk-25.0.1_windows-x64_bin.zip"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(OpenJDK)
