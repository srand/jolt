from base64 import decodebytes as base64_decodebytes
from base64 import encodebytes as base64_encodebytes
import codecs
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import ElementTree


class SubElement(object):
    def __init__(self, tag='', elem=None):
        super(SubElement, self).__init__()
        self._elem = elem if elem is not None else Element(tag)

    def append(self, e, *args, **kwargs):
        return self._elem.append(e._elem, *args, **kwargs)

    @property
    def attrib(self):
        return self._elem.attrib

    @property
    def tag(self):
        return self._elem.tag

    @property
    def text(self):
        return self._elem.text

    @text.setter
    def text(self, value):
        self._elem.text = value

    @property
    def items(self):
        return self._elem.items

    @property
    def tail(self):
        return self._elem.tail

    def __len__(self):
        return len(self._elem)

    def get(self, *args, **kwargs):
        return self._elem.get(*args, **kwargs)

    def set(self, *args, **kwargs):
        return self._elem.set(*args, **kwargs)

    def iter(self, *args, **kwargs):
        return self._elem.iter(*args, **kwargs)

    def remove(self, *args, **kwargs):
        return self._elem.remove(*args, **kwargs)


class Attribute(object):
    def __init__(self, attribute, varname=None, child=False, values=None, base64=False, zlib=False):
        self.attribute = attribute
        self.varname = varname if varname is not None else attribute.lower()
        self.child = child
        self.values = values
        self.base64 = base64 or zlib
        self.zlib = zlib

    def __call__(self, cls):
        def decorate(cls, attribute, varname, child, values):
            base64 = self.base64
            zlib = self.zlib

            def _check_value(value, values):
                if values and value not in values:
                    raise ValueError('{0} is not one of {1}'.format(value, values))

            def attr_get(self):
                if attribute not in self.attrib:
                    return ''
                value = self.get(attribute)
                if base64:
                    value = base64_decodebytes(value.encode())
                    if zlib:
                        value = codecs.decode(value, "zlib")
                    value = value.decode()
                return value

            def attr_set(self, value):
                if value is None:
                    try:
                        self.attrib.pop(attribute)
                    except Exception:
                        pass
                    finally:
                        return
                _check_value(value, values)
                if base64:
                    value = value.encode()
                    if zlib:
                        value = codecs.encode(value, "zlib")
                    value = base64_encodebytes(value).decode()
                return self.set(attribute, value)

            def child_get(self):
                if not hasattr(self, '_' + varname):
                    e = SubElement(attribute, elem=self._elem.find(attribute))
                    setattr(self, '_' + varname, e)
                value = getattr(self, '_' + varname).text
                if value is None:
                    return None
                if base64:
                    try:
                        value = base64_decodebytes(value.encode())
                        if zlib:
                            value = codecs.decode(value, "zlib")
                        value = value.decode()
                    except Exception:
                        value = getattr(self, '_' + varname).text
                return str(value)

            def child_set(self, value):
                _check_value(value, values)
                if value is None:
                    return
                if not hasattr(self, '_' + varname):
                    e = SubElement(attribute)
                    self.append(e)
                    setattr(self, '_' + varname, e)
                if base64:
                    value = value.encode()
                    if zlib:
                        value = codecs.encode(value, "zlib")
                    value = base64_encodebytes(value).decode()
                getattr(self, '_' + varname).text = value

            if not child:
                setattr(cls, varname, property(attr_get, attr_set))
            else:
                setattr(cls, varname, property(child_get, child_set))
            return cls
        return decorate(cls, self.attribute, self.varname, self.child, self.values)


class Composition(object):
    def __init__(self, cls, name):
        self.cls = cls
        self.name = name if name is not None else cls.__name__.lower()

    def __call__(self, cls):
        def decorate(cls, comp_cls, name):
            def create(self, *args, **kwargs):
                child = comp_cls(*args, **kwargs)
                self.append(child)
                return child

            def remove(self, *args, **kwargs):
                self.remove(*args, **kwargs)

            @property
            def get(self):
                children = list(self.getroot()) if isinstance(self, ElementTree) else list(self._elem)
                children = [n for n in children if n.tag == name]
                return [comp_cls(elem=child) for child in children]

            def clear(self):
                children = list(self.getroot()) if isinstance(self, ElementTree) else list(self._elem)
                children = [n for n in children if n.tag == name]
                for child in children:
                    getattr(self, "remove_" + name)(child)

            setattr(cls, 'clear_' + name + "s", clear)
            setattr(cls, 'create_' + name, create)
            setattr(cls, 'remove_' + name, remove)
            setattr(cls, name + 's', get)
            return cls
        return decorate(cls, self.cls, self.name)
