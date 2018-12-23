from jolt.cache import *


class EnvironmentVariable(ArtifactStringAttribute):
    def __init__(self, name):
        super(EnvironmentVariable, self).__init__(name)
        self._old_value = None

    def apply(self, task, artifact):
        self._old_value = task.tools.getenv(self.get_name())
        task.tools.setenv(self.get_name(), self.get_value())

    def unapply(self, task, artifact):
        if self._old_value:
            task.tools.setenv(self.get_name(), self._old_value)
        else:
            task.tools.setenv(self.get_name())
        self._old_value = None


class PathEnvironmentVariable(EnvironmentVariable):
    def __init__(self, name="PATH"):
        super(PathEnvironmentVariable, self).__init__(name)

    def append(self, value):
        if self.get_value():
            self.set_value(self.get_value() + fs.pathsep + value)
        else:
            self.set_value(value)

    def apply(self, task, artifact):
        self._old_value = task.tools.getenv(self.get_name())
        paths = self.get_value().split(fs.pathsep)
        paths = [fs.path.join(artifact.path, path) for path in paths]
        new_val = fs.pathsep.join(paths)
        if self._old_value:
            new_val = new_val + fs.pathsep + task.tools.getenv(self.get_name())
        task.tools.setenv(self.get_name(), new_val)


class EnvironmentVariableSet(ArtifactAttributeSet):
    def __init__(self):
        super(EnvironmentVariableSet, self).__init__()

    def create(self, name):
        if name == "PATH":
            return PathEnvironmentVariable(name)
        if name == "LD_LIBRARY_PATH":
            return PathEnvironmentVariable(name)
        if name == "PKG_CONFIG_PATH":
            return PathEnvironmentVariable(name)
        return EnvironmentVariable(name)


@ArtifactAttributeSetProvider.Register
class EnvironmentVariableSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "environ", EnvironmentVariableSet())

    def parse(self, artifact, content):
        if "environ" not in content:
            return

        for key, value in content["environ"].items():
            setattr(artifact.environ, key, value)

    def format(self, artifact, content):
        if "environ" not in content:
            content["environ"] = {}

        for key, value in artifact.environ.items():
            content["environ"][key] = str(value)

    def apply(self, task, artifact):
        artifact.environ.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.environ.unapply(task, artifact)
