from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider
from jolt.cache import ArtifactStringAttribute


class StringVariable(ArtifactStringAttribute):
    def __init__(self, artifact, name):
        super(StringVariable, self).__init__(artifact, name)
        self._old_value = None

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass


class StringVariableSet(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(StringVariableSet, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        return StringVariable(self._artifact, name)


@ArtifactAttributeSetProvider.Register
class StringVariableSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "strings", StringVariableSet(artifact))

    def parse(self, artifact, content):
        if "strings" not in content:
            return

        for key, value in content["strings"].items():
            getattr(artifact.strings, key).set_value(value, expand=False)

    def format(self, artifact, content):
        if "strings" not in content:
            content["strings"] = {}

        for key, value in artifact.strings.items():
            content["strings"][key] = str(value)

    def apply(self, task, artifact):
        artifact.strings.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.strings.unapply(task, artifact)
