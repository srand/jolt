from jolt.xmldom import *
from jolt import filesystem as fs


@Attribute('path')
@Attribute('source', child=True)
class _JoltRecipe(SubElement):
    def __init__(self, elem=None):
        super(_JoltRecipe, self).__init__('recipe', elem=elem)


@Attribute('name')
@Attribute('identity')
class _JoltTask(SubElement):
    def __init__(self, elem=None):
        super(_JoltTask, self).__init__('task', elem=elem)


@Composition(_JoltRecipe, "recipe")
@Composition(_JoltTask, "task")
class JoltManifest(ElementTree):
    def __init__(self):
        super(JoltManifest, self).__init__(element=Element('jolt-manifest'))
        self._identities = None

    def append(self, element):
        self.getroot().append(element)

    def get(self, key):
        self.getroot().get(key)

    def set(self, key, value):
        self.getroot().set(key, value)

    def parse(self, filename="default.joltxmanifest"):
        with open(filename) as f:
            data = f.read().replace("\n  ", "")
            data = data.replace("\n", "")
            root = ET.fromstring(data)
            self._setroot(root)
            return self
        raise Exception("failed to parse xml file")

    def format(self):
        return minidom.parseString(ET.tostring(self.getroot())).toprettyxml(indent="  ")

    def write(self, filename):
        with open(filename, 'w') as f:
            f.write(self.format())

    def has_task(self, task):
        return len(self.getroot().findall(".//task[@identity='{}']".format(task.identity))) != 0

    @property
    def task_identities(self):
        if self._identities is not None:
            return self._identities
        self._identities = {}
        for manifest_task in self.tasks:
            self._identities[manifest_task.name] = manifest_task.identity
        return self._identities

    @staticmethod
    def export(task):
        manifest = JoltManifest()
        ManifestExtensionRegistry.export_manifest(manifest, task)
        return manifest


class ManifestExtensionRegistry(object):
    extensions = []

    @staticmethod
    def add(extension):
        ManifestExtensionRegistry.extensions.append(extension)

    @staticmethod
    def export_manifest(manifest, task):
        for extension in ManifestExtensionRegistry.extensions:
            extension.export_manifest(manifest, task)

    @staticmethod
    def import_manifest(manifest):
        for extension in ManifestExtensionRegistry.extensions:
            extension.omport_manifest(manifest)


class ManifestExtension(object):
    def export_manifest(self, manifest, task):
        pass

    def import_manifest(self, manifest):
        pass
