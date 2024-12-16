from configparser import ConfigParser, NoOptionError, NoSectionError
from urllib.parse import urlparse
import os
import re

from jolt import common_pb2 as common_pb
from jolt import filesystem as fs
from jolt import utils
from jolt.error import raise_error_if


_workdir = os.getcwd()


if os.getenv("JOLT_CONFIG_PATH"):
    location = fs.path.join(os.getenv("JOLT_CONFIG_PATH"), "config")
    location_user = fs.path.join(os.getenv("JOLT_CONFIG_PATH"), "user")
    location_overlay = os.getenv("JOLT_CONFIG_OVERLAY")
    if location_overlay:
        location_overlay = fs.path.join(os.getenv("JOLT_CONFIG_PATH"), location_overlay)
elif os.name == "nt":
    appdata = os.getenv("APPDATA", fs.path.join(fs.userhome(), "AppData", "Roaming"))
    location = fs.path.join(appdata, "Jolt", "config")
    location_user = fs.path.join(appdata, "Jolt", "user")
    location_overlay = os.getenv("JOLT_CONFIG_OVERLAY")
else:
    location = fs.path.join(fs.userhome(), ".config", "jolt", "config")
    location_user = fs.path.join(fs.userhome(), ".config", "jolt", "user")
    location_overlay = os.getenv("JOLT_CONFIG_OVERLAY")


class ConfigFile(ConfigParser):
    def __init__(self, location, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._location = location
        if location is not None:
            dirname = fs.path.dirname(location)
            if dirname:
                fs.makedirs(dirname)

    def load(self):
        if self._location:
            super().read(self._location)
            if not self.has_section("jolt"):
                self.add_section("jolt")

    def save(self, path=None):
        if self._location is None and path is None:
            return
        with open(path or self._location, 'w') as configfile:
            super().write(configfile)

    def delete(self, section, key):
        if key is None:
            return self.remove_section(section)
        try:
            success = self.remove_option(section, key)
            if success and len(self[section].items()) <= 0:
                self.remove_section(section)
            return success
        except NoSectionError:
            return False

    def set(self, section, key, value):
        if not self.has_section(section):
            self.add_section(section)
        super().set(section, key, value)


class Config(object):
    def __init__(self):
        self._configs = []

    def configs(self, alias=None):
        return [config for name, config in self._configs if not alias or name == alias]

    def add_file(self, alias, location):
        file = ConfigFile(location)
        if alias == "cli":
            self._configs.insert(-1, (alias, file))
        else:
            self._configs.append((alias, file))
        return file

    def get(self, section, key, default, alias=None):
        for config in reversed(self.configs(alias)):
            try:
                return config.get(section, key)
            except (NoOptionError, NoSectionError):
                continue
        return default

    def set(self, section, key, value, alias=None):
        count = 0
        for config in self.configs(alias):
            config.set(section, key, value)
            count += 1
        return count

    def delete(self, section, key, alias=None):
        count = 0
        for config in self.configs(alias):
            count += int(config.delete(section, key))
        return count

    def sections(self, alias=None):
        s = []
        for config in self.configs(alias):
            s += config.sections()
        return sorted(s)

    def options(self, section, alias=None):
        s = []
        for config in self.configs(alias):
            if config.has_section(section):
                s += config[section].items()
        return sorted(s)

    def items(self, alias=None):
        o = {}
        for section in self.sections(alias):
            for option, value in self.options(section):
                o[(section, option)] = value
            if not o:
                o[(section, None)] = None
        return [(section, option, value) for (section, option), value in o.items()]

    def load(self):
        for config in self.configs():
            config.load()

    def save(self, path=None):
        for name, config in self._configs:
            config.save(os.path.join(path, f"{name}.conf") if path else None)


_config = Config()
_config.add_file("global", location)
_config.add_file("user", location_user)
if location_overlay:
    _config.add_file("overlay", location_overlay)
_manifest = _config.add_file("manifest", None)
# Note: cli configs are added next to last in the chain,
# before manifest, and can therefore not override the
# imported manifest config.
_config.add_file("cli", None)
_config.load()


def get(section, key, default=None, expand=True, alias=None):
    val = _config.get(section, key, default, alias)
    return utils.expand(val) if expand and val is not None else val


def getint(section, key, default=None, alias=None):
    value = get(section, key, default=default, alias=alias)
    if value is not None:
        try:
            return int(value)
        except ValueError:
            raise_error_if(True, "Config: value '{0}' invalid for '{1}.{2}', expected integer", value, section, key)
    return None


def getsize(section, key, default=None, alias=None):
    units = {
        None: 1,
        "B": 1,

        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
        "P": 1000**5,
        "E": 1000**6,

        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "Ei": 1024**6,
    }

    value = get(section, key, default=None, alias=alias)
    if value is None:
        if type(default) is int:
            return default
        else:
            value = str(default)

    m = re.search(r"^(0|[1-9][0-9]*) ?([KMGTPE]i?)?B?$", value)
    raise_error_if(
        not m,
        "Config: size '{0}' invalid for '{1}.{2}', expected '<size> <unit>'", value, section, key)
    raise_error_if(
        m[2] not in units,
        "Config: unit invalid for '{0}.{1}', expected [B,K,M,G,T,P,E,Mi,Gi,Ti,Pi,Ei]", section, key)

    return int(m[1]) * units.get(m[2], 1)


def getfloat(section, key, default=None, alias=None):
    return float(get(section, key, default=default, alias=alias))


def getboolean(section, key, default=None, alias=None):
    value = get(section, key, default=default, alias=alias)
    return value is not None and str(value).lower() in ["true", "yes", "on", "1"]


def geturi(section, key, default=None, alias=None):
    value = get(section, key, default=default, alias=alias)
    if value is None:
        return None
    return urlparse(value)


def get_jolthome():
    if os.name == "nt":
        return fs.path.join(os.getenv("LOCALAPPDATA", fs.path.join(fs.userhome(), "AppData", "Local")), "Jolt")
    else:
        return fs.path.join(fs.userhome(), ".jolt")


def get_logpath():
    return get("jolt", "logpath", get_jolthome())


def get_cachedir():
    if os.name == "nt":
        default = fs.path.join(get_jolthome(), "Cache")
    else:
        default = fs.path.join(fs.userhome(), ".cache", "jolt")
    return get("jolt", "cachedir", default)


def get_workdir():
    return _workdir


def get_shell():
    cmd = os.getenv("SHELL", "bash")
    if "bash" in cmd:
        cmd = cmd + " --norc"
    return get("jolt", "shell", cmd)


def get_keep_going():
    return getboolean("params", "keep_going", False)


def is_incremental_build():
    """
    Whether to enable incremental builds.

    If disabled, all build directories are deleted upon completion of tasks.
    """
    return getboolean("jolt", "incremental_dirs", True)


def set_keep_going(value=False):
    return set("params", "keep_going", str(value).lower())


def set(section, key, value, alias=None):
    _config.set(section, key, value, alias or "user")


def load(file):
    _config.load()


def load_or_set(file_or_str):
    if fs.path.exists(file_or_str):
        _config.add_file("cli", file_or_str)
        _config.load()
    else:
        key_value = file_or_str.split("=", 1)
        raise_error_if(len(key_value) <= 1, "Syntax error in configuration: '{}'".format(file_or_str))
        section_key = key_value[0].split(".", 1)
        raise_error_if(len(section_key) <= 1, "Syntax error in configuration: '{}'".format(file_or_str))
        _config.set(section_key[0], section_key[1], key_value[1], alias="cli")


def save(path=None):
    _config.save(path)


def delete(key, alias=None):
    section, option = split(key)
    return _config.delete(section, option, alias)


def sections(alias=None):
    return _config.sections(alias)


def plugins():
    automatic = ["cxxinfo", "environ", "paths", "python", "strings"]
    return sections() + automatic


def items(alias=None):
    return _config.items(alias)


def options(section, alias=None):
    return _config.options(section, alias)


def split(string):
    try:
        section, key = string.split(".", 1)
    except ValueError:
        section, key = string, None
    return section, key


def import_config(snippet: str):
    """ Apply extra configuration for the worker, provided by the client. """
    _manifest.read_string(snippet)
    from jolt.loader import JoltLoader
    JoltLoader.get().load_plugins()


def export_config():
    """ Get extra configuration for the worker. """
    return get("network", "config", "", expand=False)


def import_params(params: dict):
    """ Apply user-defined parameters (-c params.key=value). """
    for key, value in params.items():
        if key.startswith("config."):
            set("params", key.split(".", 1)[1], value)


def export_params():
    """ Get user-defined parameters (-c params.key=value). """
    parameters = []
    for key, value in options("params"):
        parameters.append(common_pb.Property(key="config." + key, value=value))
    return parameters
