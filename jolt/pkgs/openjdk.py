from jolt import attributes
from jolt import Download
from jolt import Parameter
from jolt.tasks import TaskRegistry


@attributes.attribute("collect", "collect_{system}")
@attributes.attribute("url", "url_{system}")
@attributes.system
class OpenJDK(Download):
    name = "openjdk"
    version = Parameter("25.0.1", const=True, help="OpenJDK version.")

    collect_darwin = [{"files": "*", "cwd": f"jdk-{version}.jdk/Contents/Home"}]
    """ File publication instructions on macOS. See ``collect``. """
    collect_linux = [{"files": "*", "cwd": f"jdk-{version}"}]
    """ File publication instructions on Linux. See ``collect``. """
    collect_windows = collect_linux
    """ File publication instructions on Windows. See ``collect``. """
    url_darwin = "https://download.java.net/java/GA/jdk25.0.1/2fbf10d8c78e40bd87641c434705079d/8/GPL/openjdk-25.0.1_macos-x64_bin.tar.gz"
    """ URL of the file to download on macOS. """
    url_linux = "https://download.java.net/java/GA/jdk25.0.1/2fbf10d8c78e40bd87641c434705079d/8/GPL/openjdk-25.0.1_linux-x64_bin.tar.gz"
    """ URL of the file to download on Linux. """
    url_windows = "https://download.java.net/java/GA/jdk25.0.1/2fbf10d8c78e40bd87641c434705079d/8/GPL/openjdk-25.0.1_windows-x64_bin.zip"
    """ URL of the file to download on Windows. """

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(OpenJDK)
