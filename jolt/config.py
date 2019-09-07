import base64
from configparser import SafeConfigParser, NoOptionError
try:
    from StringIO import StringIO
except:
    from io import StringIO

from jolt import filesystem as fs
from jolt import utils
from jolt.error import raise_error_if
from jolt.manifest import ManifestExtension, ManifestExtensionRegistry


location = fs.path.join(fs.path.expanduser("~"), ".config", "jolt", "config")
location_user = fs.path.join(fs.path.expanduser("~"), ".config", "jolt", "user")

_file = SafeConfigParser()
_file.read(location)
_file.read(location_user)

if not _file.has_section("jolt"):
    _file.add_section("jolt")
if not _file.has_section("cxxinfo"):
    _file.add_section("cxxinfo")
if not _file.has_section("environ"):
    _file.add_section("environ")
if not _file.has_section("strings"):
    _file.add_section("strings")

def get(section, key, default=None, expand=True):
    try:
        value = _file.get(section, key)
        return utils.expand(value) if expand else value
    except NoOptionError:
        return default

def getint(section, key, default=None):
    try:
        return _file.getint(section, key)
    except NoOptionError:
        return default

def getsize(section, key, default=None):
    units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    try:
        value = _file.get(section, key)
        value = value.strip()
        value = value.split()
        if len(value) == 1 and value[0][-1] in units:
            size, unit = value[0][:-1], value[0][-1]
        else:
            raise_error_if(
                len(value) != 2,
                "config: size invalid for '{0}.{1}', expected '<size> <unit>'", section, key)
            size, unit = value[0], value[1]
        raise_error_if(
            unit not in units,
            "config: unit invalid for '{0}.{1}', expected [B,K,M,G,T]", section, key)
        return int(size)*units[unit]
    except NoOptionError:
        return default

def getfloat(section, key, default=None):
    try:
        return _file.getfloat(section, key)
    except NoOptionError:
        return default

def getboolean(section, key, default=None):
    try:
        return _file.getboolean(section, key)
    except NoOptionError:
        return default

def get_jolthome():
    return fs.path.join(fs.path.expanduser("~"), ".jolt")

def get_logpath():
    return get_jolthome()

def set(section, key, value):
    if not _file.has_section(section):
        _file.add_section(section)
    _file.set(section, key, value)

def load(file):
    _file.read(file)

def load_or_set(file_or_str):
    if fs.path.exists(file_or_str):
        _file.read(file_or_str)
    else:
        key_value = file_or_str.split("=", 1)
        raise_error_if(len(key_value) <= 1, "syntax error in configuration: '{}'".format(file_or_str))
        section_key = key_value[0].split(".", 1)
        raise_error_if(len(section_key) <= 1, "syntax error in configuration: '{}'".format(file_or_str))
        set(section_key[0], section_key[1], key_value[1])

def save():
    fs.makedirs(fs.path.dirname(location))
    config = StringIO()
    _file.write(config)
    with open(location, 'wb') as configfile:
        configfile.write(config.getvalue().encode())

def sections():
    return _file.sections()


class ConfigExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        manifest.config = base64.encodestring(
            get("network", "config", "", expand=False).encode()).decode()

    def import_manifest(self, manifest):
        _file.read_string(base64.decodestring(manifest.config.encode()).decode())


ManifestExtensionRegistry.add(ConfigExtension())
