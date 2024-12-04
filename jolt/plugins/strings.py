from jolt.cache import ArtifactAttributeSetProvider


class StringVariableSet(object):
    def __init__(self, artifact):
        super(StringVariableSet, self).__setattr__("_attributes", {})
        super(StringVariableSet, self).__setattr__("_artifact", artifact)

    def _get_attributes(self):
        return self._attributes

    def __getattr__(self, name):
        attributes = self._get_attributes()
        if name not in attributes:
            return None
        return attributes[name]

    def __setattr__(self, name, value):
        if not isinstance(value, str):
            raise ValueError(f"Value assigned to artifact.strings.{name} must be a string, got {type(value)}")
        attributes = self._get_attributes()
        attributes[name] = self._artifact.tools.expand(value)
        return value

    def __dict__(self):
        return {key: str(value) for key, value in self.items()}

    def items(self):
        return self._get_attributes().items()


@ArtifactAttributeSetProvider.Register
class StringVariableSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "strings", StringVariableSet(artifact))

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
        pass

    def unapply(self, task, artifact):
        pass
