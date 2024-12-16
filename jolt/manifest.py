from xml.dom import minidom
from xml.etree import ElementTree as ET
import os

from jolt.xmldom import Attribute, Composition, SubElement, Element, ElementTree
from jolt import filesystem as fs
from jolt import log


@Attribute('name')
@Attribute('value', child=True)
class _JoltAttribute(SubElement):
    def __init__(self, elem=None):
        super(_JoltAttribute, self).__init__('attribute', elem=elem)


@Attribute('path')
@Attribute('source', child=True, zlib=True)
class _JoltRecipe(SubElement):
    def __init__(self, elem=None):
        super(_JoltRecipe, self).__init__('recipe', elem=elem)


@Attribute('src')
@Attribute('dest')
class _JoltProjectLink(SubElement):
    def __init__(self, elem=None):
        super(_JoltProjectLink, self).__init__('link', elem=elem)


@Attribute('src')
@Attribute('joltdir')
class _JoltProjectRecipe(SubElement):
    def __init__(self, elem=None):
        super(_JoltProjectRecipe, self).__init__('recipe', elem=elem)


@Attribute('src')
class _JoltProjectModule(SubElement):
    def __init__(self, elem=None):
        super(_JoltProjectModule, self).__init__('module', elem=elem)

    @property
    def path(self):
        return self.src

    @path.setter
    def path(self, value):
        self.src = value


@Attribute('name')
class _JoltProjectResource(SubElement):
    def __init__(self, elem=None):
        super(_JoltProjectResource, self).__init__('resource', elem=elem)


@Attribute('name')
@Composition(_JoltProjectLink, "link")
@Composition(_JoltProjectModule, "module")
@Composition(_JoltProjectRecipe, "recipe")
@Composition(_JoltProjectResource, "resource")
class _JoltProject(SubElement):
    def __init__(self, elem=None):
        super(_JoltProject, self).__init__('project', elem=elem)


@Attribute('type', child=True)
@Attribute('location', child=True)
@Attribute('message', child=True)
@Attribute('details', child=True)
class _JoltTaskError(SubElement):
    def __init__(self, elem=None):
        super(_JoltTaskError, self).__init__('error', elem=elem)


@Attribute('name')
@Attribute('duration', child=True)
@Attribute('goal', child=True)
@Attribute('identity', child=True)
@Attribute('instance', child=True)
@Attribute('logstash', child=True)
@Attribute('result', child=True)
@Composition(_JoltAttribute, "attribute")
@Composition(_JoltTaskError, "error")
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


@Attribute("key")
@Attribute("value")
class _JoltNetworkParameter(SubElement):
    def __init__(self, elem=None):
        super(_JoltNetworkParameter, self).__init__('parameter', elem=elem)


@Attribute("config", child=True, zlib=True)
@Attribute("stdout", child=True, zlib=True)
@Attribute("stderr", child=True, zlib=True)
@Attribute("result", child=True)
@Attribute("duration", child=True)
@Attribute("name")
@Attribute("workspace")
@Attribute("build")
@Attribute("version")
@Composition(_JoltRecipe, "recipe")
@Composition(_JoltTask, "task")
@Composition(_JoltBuild, "build")
@Composition(_JoltNetworkParameter, "parameter")
@Composition(_JoltProject, "project")
class JoltManifest(ElementTree):
    def __init__(self):
        super(JoltManifest, self).__init__(element=Element('jolt-manifest'))
        self._identities = None
        self._elem = self.getroot()
        self.path = None

    def is_valid(self):
        return self.path is not None

    def get_workspace_path(self):
        if self.path is None:
            return None
        joltdir = fs.path.dirname(self.path)
        if self.workspace:
            joltdir = fs.path.normpath(fs.path.join(joltdir, self.workspace))
        return joltdir

    def get_workspace_name(self):
        if self.name:
            return self.name
        if self.path is None:
            return None
        return fs.path.basename(fs.path.dirname(self.path))

    @property
    def attrib(self):
        return self.getroot().attrib

    def append(self, element):
        SubElement(elem=self.getroot()).append(element)

    def get(self, key):
        return self.getroot().get(key)

    def set(self, key, value):
        self.getroot().set(key, value)

    def remove(self, child):
        self.getroot().remove(child)

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
            self.parsestring(f.read())
            log.verbose("Loaded: {0}", filepath)
            self.path = filepath
            return self
        raise Exception("failed to parse xml file")

    def parsestring(self, string):
        root = ET.fromstring(string)
        for elem in root.iter():
            if elem.text is not None:
                elem.text = elem.text.strip()
            if elem.tail is not None:
                elem.tail = elem.tail.strip()
        self._setroot(root)
        self._elem = root
        return self

    def format(self):
        return minidom.parseString(ET.tostring(self.getroot())).toprettyxml(indent="  ")

    def transform(self, xsltfile):
        from lxml import etree as lxmlET
        manifest = lxmlET.fromstring(self.format())
        xslt = lxmlET.parse(xsltfile)
        transform = lxmlET.XSLT(xslt)
        document = transform(manifest)
        return minidom.parseString(lxmlET.tostring(document)).toprettyxml(indent="  ")

    def write(self, filename):
        with open(filename, 'w') as f:
            f.write(self.format())

    def has_task(self, task):
        return self.find("./task[@identity='{}']".format(task.identity)) is not None

    def has_failure(self):
        if self.result and self.result == "FAILED":
            return True
        return self.find("./task[result='FAILED']") is not None

    def has_unstable(self):
        return self.find("./task[result='UNSTABLE']") is not None

    def has_tasks(self):
        return self.find("./task") is not None

    def find_task(self, task):
        match = self.find("./task[@name='{0}']".format(task))
        if match is None:
            return None
        return _JoltTask(elem=match)

    def get_parameter(self, key):
        match = self.find("./parameter[@key='{0}']".format(key))
        if match is None:
            return None
        return match.get("value")

    @property
    def task_identities(self):
        if self._identities is not None:
            return self._identities
        self._identities = {}
        for manifest_task in self.tasks:
            self._identities[manifest_task.name] = manifest_task.identity
        return self._identities
