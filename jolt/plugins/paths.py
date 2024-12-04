from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider
from jolt.cache import ArtifactStringAttribute

from jolt import filesystem as fs


class PathVariable(ArtifactStringAttribute):
    def __init__(self, artifact, name):
        super(PathVariable, self).__init__(artifact, name)
        self._old_value = None

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass

    def __bool__(self):
        return bool(str(self))

    def __eq__(self, value: str) -> bool:
        return str(self) == str(value)

    def __str__(self):
        if self._value is None:
            return ""
        return fs.path.join(self._artifact.path, self._value)


class PathVariableSet(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(PathVariableSet, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        return PathVariable(self._artifact, name)

    def __getattr__(self, name):
        attributes = self._get_attributes()
        return attributes.get(name, None)


@ArtifactAttributeSetProvider.Register
class PathVariableSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "paths", PathVariableSet(artifact))

    def parse(self, artifact, content):
        if "paths" not in content:
            return

        for key, value in content["paths"].items():
            setattr(artifact.paths, key, value)

    def format(self, artifact, content):
        if "paths" not in content:
            content["paths"] = {}

        for key, value in artifact.paths.items():
            content["paths"][key] = value.get_value()

    def apply(self, task, artifact):
        artifact.paths.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.paths.unapply(task, artifact)
