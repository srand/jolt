import os
import platform

from jolt import filesystem as fs
from jolt.cache import ArtifactAttributeSetProvider
from jolt.cache import ArtifactListAttribute


class RpathAttribute(ArtifactListAttribute):
    """
    Folders in an artifact with shared libraries that are loaded at runtime.

    The folders are relative to the artifact root. Consumers that relocate
    their binaries (see :func:`jolt.attributes.relocate_binaries`) link with
    rpaths to these folders on Linux and macOS, and find DLLs in them through
    ``PATH`` on Windows.

    Example:

    .. code-block:: python

        artifact.rpath.append("lib")

    """

    def __init__(self, artifact):
        super().__init__(artifact, "rpath")
        self._old_env = None

    def _set(self, task, key, value):
        self._old_env.append((key, task.tools.getenv(key)))
        task.tools.setenv(key, value)

    def apply(self, task, artifact):
        self._old_env = []
        if not self._value or not getattr(task, "relocate_binaries", False):
            return

        paths = [fs.path.join(artifact.path, folder) for folder in self._value]
        system = platform.system()

        if system == "Windows":
            old = task.tools.getenv("PATH")
            self._set(task, "PATH", os.pathsep.join(paths + ([old] if old else [])))
            return

        flags = task.tools.getenv("LDFLAGS", "").split()
        flags += ["-Wl,-rpath," + path for path in paths]
        if system == "Darwin" and "-Wl,-headerpad_max_install_names" not in flags:
            flags.append("-Wl,-headerpad_max_install_names")
        self._set(task, "LDFLAGS", " ".join(flags))

    def unapply(self, task, artifact):
        for key, value in reversed(self._old_env or []):
            task.tools.setenv(key, value)
        self._old_env = None


class RpathProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "rpath", RpathAttribute(artifact))

    def parse(self, artifact, content):
        if "rpath" not in content:
            return
        artifact.rpath.set_value(content["rpath"], expand=False)

    def format(self, artifact, content):
        content["rpath"] = list(artifact.rpath)

    def apply(self, task, artifact):
        artifact.rpath.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.rpath.unapply(task, artifact)


# Register() returns None, keep the class name usable
ArtifactAttributeSetProvider.Register(RpathProvider)
