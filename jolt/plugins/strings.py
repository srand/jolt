from jolt.cache import *


class StringVariable(ArtifactStringAttribute):
    def __init__(self, name):
        super(StringVariable, self).__init__(name)
        self._old_value = None

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass


class StringVariableSet(ArtifactAttributeSet):
    def __init__(self):
        super(StringVariableSet, self).__init__()

    def create(self, name):
        return StringVariable(name)


@ArtifactAttributeSetProvider.Register
class StringVariableSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "strings", StringVariableSet())

    def parse(self, artifact, content):
        if "strings" not in content:
            return

        for key, value in content["strings"].items():
            setattr(artifact.strings, key, value)

    def format(self, artifact, content):
        if "strings" not in content:
            content["strings"] = {}

        for key, value in artifact.strings.items():
            content["strings"][key] = str(value)

    def apply(self, task, artifact):
        artifact.strings.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.strings.unapply(task, artifact)
