from xml.dom import minidom
import os

from jolt.xmldom import Attribute, Composition, SubElement, Element, ElementTree, ET
from jolt import filesystem as fs
from jolt import log


@Attribute('name')
@Attribute('value', child=True)
class _JoltAttribute(SubElement):
    def __init__(self, elem=None):
        super(_JoltAttribute, self).__init__('attribute', elem=elem)


@Attribute('path')
@Attribute('source', child=True)
class _JoltRecipe(SubElement):
    def __init__(self, elem=None):
        super(_JoltRecipe, self).__init__('recipe', elem=elem)


@Attribute('name')
@Attribute('identity', child=True)
@Composition(_JoltAttribute, "attribute")
class _JoltTask(SubElement):
    def __init__(self, elem=None):
        super(_JoltTask, self).__init__('task', elem=elem)


@Attribute('name')
class _JoltDefault(SubElement):
    def __init__(self, elem=None):
        super(_JoltDefault, self).__init__('default', elem=elem)


@Composition(_JoltDefault, "default")
@Composition(_JoltTask, "task")
class _JoltBuild(SubElement):
    def __init__(self, elem=None):
        super(_JoltBuild, self).__init__('build', elem=elem)


@Attribute("config", child=True)
@Composition(_JoltRecipe, "recipe")
@Composition(_JoltTask, "task")
@Composition(_JoltBuild, "build")
class JoltManifest(ElementTree):
    def __init__(self):
        super(JoltManifest, self).__init__(element=Element('jolt-manifest'))
        self._identities = None
        self._elem = self.getroot()

    def append(self, element):
        SubElement(elem=self.getroot()).append(element)

    def get(self, key):
        self.getroot().get(key)

    def set(self, key, value):
        self.getroot().set(key, value)

    def parse(self, filename="default.joltxmanifest"):
        path = os.getcwd()
        filepath = fs.path.join(path, filename)
        while not fs.path.exists(filepath):
            opath = path
            path = fs.path.dirname(path)
            if path == opath:
                break
            filepath = fs.path.join(path, filename)
        if path == fs.sep:
            raise Exception("couldn't find manifest file")
        with open(filepath) as f:
            data = f.read().replace("\n  ", "")
            data = data.replace("\n", "")
            root = ET.fromstring(data)
            self._setroot(root)
            self._elem = root
            log.verbose("Loaded: {0}", filepath)
            return self
        raise Exception("failed to parse xml file")

    def format(self):
        return minidom.parseString(ET.tostring(self.getroot())).toprettyxml(indent="  ")

    def write(self, filename):
        with open(filename, 'w') as f:
            f.write(self.format())

    def has_task(self, task):
        return self.find("./task[@identity='{}']".format(task.identity)) is not None

    def find_task(self, task):
        match = self.find("./task[@name='{0}']".format(task))
        if not match:
            return None
        return _JoltTask(elem=match)

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

    def process_import(self):
        ManifestExtensionRegistry.import_manifest(self)


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
            extension.import_manifest(manifest)


class ManifestExtension(object):
    def export_manifest(self, manifest, task):
        pass

    def import_manifest(self, manifest):
        pass
