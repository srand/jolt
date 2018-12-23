from configparser import SafeConfigParser, NoOptionError

from jolt import filesystem as fs
from jolt import utils


location = fs.path.join(fs.path.expanduser("~"), ".config", "jolt", "config")

_file = SafeConfigParser()
_file.read(location)
if not _file.has_section("jolt"):
    _file.add_section("jolt")

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
            assert len(value) == 2, "invalid size format for {0}.{1}, "\
                "expected '<size> <unit>'"\
                .format(section, key)
            size, unit = value[0], value[1]
        assert unit in units, "invalid unit requested for {0}.{1}"\
            .format(section, key)
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

def set(section, key, value):
    if not _file.has_section(section):
        _file.add_section(section)
    _file.set(section, key, value)

def load(file):
    _file.read(file)

def save():
    fs.makedirs(fs.path.dirname(location))
    with open(location, 'wb') as configfile:
        _file.write(configfile)

def sections():
    return _file.sections()
