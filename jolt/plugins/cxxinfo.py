from jolt.cache import ArtifactListAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider


class CppInfoListVariable(ArtifactListAttribute):
    pass


class CppInfoDictVariable(ArtifactListAttribute):
    def __init__(self, artifact, name):
        super(CppInfoDictVariable, self).__init__(artifact, name)

    def __setitem__(self, key, value=None):
        item = "{0}={1}".format(key, value) if value is not None else key
        self.append(item)


class CppInfo(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(CppInfo, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        if name == "asflags":
            return CppInfoListVariable(self._artifact, "asflags")
        if name == "cflags":
            return CppInfoListVariable(self._artifact, "cflags")
        if name == "cxxflags":
            return CppInfoListVariable(self._artifact, "cxxflags")
        if name == "incpaths":
            return CppInfoListVariable(self._artifact, "incpaths")
        if name == "ldflags":
            return CppInfoListVariable(self._artifact, "ldflags")
        if name == "libpaths":
            return CppInfoListVariable(self._artifact, "libpaths")
        if name == "libraries":
            return CppInfoListVariable(self._artifact, "libraries")
        if name == "macros":
            return CppInfoDictVariable(self._artifact, "macros")
        if name == "sources":
            return CppInfoListVariable(self._artifact, "sources")
        assert False, "No such cxxinfo attribute: {0}".format(name)


@ArtifactAttributeSetProvider.Register
class CppInfoProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "cxxinfo", CppInfo(artifact))

    def parse(self, artifact, content):
        if "cxxinfo" not in content:
            return
        for key, value in content["cxxinfo"].items():
            getattr(artifact.cxxinfo, key).set_value(value, expand=False)

    def format(self, artifact, content):
        if "cxxinfo" not in content:
            content["cxxinfo"] = {}
        for key, attrib in artifact.cxxinfo.items():
            content["cxxinfo"][key] = attrib.get_value()

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass
