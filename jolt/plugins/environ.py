from jolt import filesystem as fs
from jolt import utils
from jolt.cache import ArtifactStringAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider


class EnvironmentVariable(ArtifactStringAttribute):
    def __init__(self, artifact, name):
        super(EnvironmentVariable, self).__init__(artifact, name)
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
    def __init__(self, artifact, name="PATH"):
        super(PathEnvironmentVariable, self).__init__(artifact, name)

    def set_value(self, value, expand=True):
        values = utils.as_list(value)
        super(PathEnvironmentVariable, self).set_value(fs.pathsep.join(values), expand)

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
    def __init__(self, artifact):
        super(EnvironmentVariableSet, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        if name == "PATH":
            return PathEnvironmentVariable(self._artifact, name)
        if name == "PYTHONPATH":
            return PathEnvironmentVariable(self._artifact, name)
        if name == "LD_LIBRARY_PATH":
            return PathEnvironmentVariable(self._artifact, name)
        if name == "PKG_CONFIG_PATH":
            return PathEnvironmentVariable(self._artifact, name)
        return EnvironmentVariable(self._artifact, name)


@ArtifactAttributeSetProvider.Register
class EnvironmentVariableSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "environ", EnvironmentVariableSet(artifact))

    def parse(self, artifact, content):
        if "environ" not in content:
            return

        for key, value in content["environ"].items():
            getattr(artifact.environ, key).set_value(value, expand=False)

    def format(self, artifact, content):
        if "environ" not in content:
            content["environ"] = {}

        for key, attrib in artifact.environ.items():
            content["environ"][key] = attrib.get_value()

    def apply(self, task, artifact):
        artifact.environ.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.environ.unapply(task, artifact)
