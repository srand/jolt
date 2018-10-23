import filesystem as fs
from ConfigParser import SafeConfigParser, NoOptionError


location = fs.path.join(fs.path.expanduser("~"), ".config", "jolt", "config")

_file = SafeConfigParser()
_file.read(location)

def get(section, key, default=None):
    try:
        return _file.get(section, key)
    except NoOptionError:
        return default

def getint(section, key, default=None):
    try:
        return _file.getint(section, key)
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
