from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import ElementTree
from xml.dom import minidom

from jolt.utils import cached



class SubElement(object):
    def __init__(self, tag='', elem=None):
        super(SubElement, self).__init__()
        self._elem = elem if elem is not None else Element(tag)

    @property
    def attrib(self):
        return self._elem.attrib

    def get(self, *args, **kwargs):
        return self._elem.get(*args, **kwargs)

    def set(self, *args, **kwargs):
        return self._elem.set(*args, **kwargs)



class Attribute(object):
    def __init__(self, attribute, varname=None, child=False, values=None):
        self.attribute = attribute
        self.varname = varname if varname is not None else attribute.lower()
        self.child = child
        self.values = values

    def __call__(self, cls):
        def decorate(cls, attribute, varname, child, values):
            def _check_value(value, values):
                if values and value not in values:
                    raise ValueError('{0} is not one of {1}'.format(value, values))

            def attr_get(self):
                if attribute not in self.attrib:
                    return ''
                return self.get(attribute)

            def attr_set(self, value):
                if value is None:
                    try:
                        self.attrib.pop(attribute)
                    except:
                        pass
                    finally:
                        return
                _check_value(value, values)
                return self.set(attribute, value)

            def child_get(self):
                if not hasattr(self, '_'+varname):
                    return ''
                return getattr(self, '_'+varname).text

            def child_set(self, value):
                _check_value(value, values)
                if not value: return
                if not hasattr(self, '_'+varname):
                    e = SubElement(attribute)
                    self.append(e)
                    setattr(self, '_'+varname, e)
                getattr(self,'_'+varname).text = value

            if not child:
                setattr(cls, varname, property(attr_get, attr_set))
            else:
                setattr(cls, varname, property(child_get, child_set))
            return cls
        return decorate(cls, self.attribute, self.varname, self.child, self.values)


class Composition(object):
    def __init__(self, cls, name):
        self.cls = cls
        self.name = name if name is not None else attribute.lower()

    def __call__(self, cls):
        def decorate(cls, comp_cls, name):
            def create(self, *args, **kwargs):
                child = comp_cls(*args, **kwargs)
                self.append(child)
                return child

            @property
            @cached.instance
            def get(self):
                children = list(self.getroot()) if isinstance(self, ElementTree) else list(self)
                children = [n for n in children if n.tag == name]
                return [comp_cls(elem=child) for child in children]

            setattr(cls, 'create_' + name, create)
            setattr(cls, name + 's', get)
            return cls
        return decorate(cls, self.cls, self.name)
