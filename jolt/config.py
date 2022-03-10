from configparser import SafeConfigParser, NoOptionError, NoSectionError
import os

from jolt import filesystem as fs
from jolt import utils
from jolt.error import raise_error_if
from jolt.manifest import ManifestExtension, ManifestExtensionRegistry


_workdir = os.getcwd()


if os.getenv("JOLT_CONFIG_PATH"):
    location = fs.path.join(os.getenv("JOLT_CONFIG_PATH"), "config")
    location_user = fs.path.join(os.getenv("JOLT_CONFIG_PATH"), "user")
elif os.name == "nt":
    appdata = os.getenv("APPDATA", fs.path.join(fs.userhome(), "AppData", "Roaming"))
    location = fs.path.join(appdata, "Jolt", "config")
    location_user = fs.path.join(appdata, "Jolt", "user")
else:
    location = fs.path.join(fs.userhome(), ".config", "jolt", "config")
    location_user = fs.path.join(fs.userhome(), ".config", "jolt", "user")


class ConfigFile(SafeConfigParser):
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

    def save(self):
        if self._location is None:
            return
        with open(self._location, 'w') as configfile:
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

    def save(self):
        for config in self.configs():
            config.save()


_config = Config()
_config.add_file("global", location)
_config.add_file("user", location_user)
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
    return int(get(section, key, default=default, alias=alias))


def getsize(section, key, default=None, alias=None):
    units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    value = get(section, key, default=None, alias=alias)
    if value is None:
        if type(default) == int:
            return default
        else:
            value = str(default)
    value = value.strip()
    value = value.split()
    if len(value) == 1 and value[0][-1] in units:
        size, unit = value[0][:-1], value[0][-1]
    else:
        raise_error_if(
            len(value) != 2,
            "config: size '{2}' invalid for '{0}.{1}', expected '<size> <unit>'", value, section, key)
        size, unit = value[0], value[1]
    raise_error_if(
        unit not in units,
        "config: unit invalid for '{0}.{1}', expected [B,K,M,G,T]", section, key)
    return int(size) * units[unit]


def getfloat(section, key, default=None, alias=None):
    return float(get(section, key, default=default, alias=alias))


def getboolean(section, key, default=None, alias=None):
    value = get(section, key, default=default, alias=alias)
    return value is not None and str(value).lower() in ["true", "yes", "on", "1"]


def get_jolthome():
    if os.name == "nt":
        return fs.path.join(os.getenv("LOCALAPPDATA", fs.path.join(fs.userhome(), "AppData", "Local")), "Jolt")
    else:
        return fs.path.join(fs.userhome(), ".jolt")


def get_logpath():
    return get_jolthome()


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
        raise_error_if(len(key_value) <= 1, "syntax error in configuration: '{}'".format(file_or_str))
        section_key = key_value[0].split(".", 1)
        raise_error_if(len(section_key) <= 1, "syntax error in configuration: '{}'".format(file_or_str))
        _config.set(section_key[0], section_key[1], key_value[1], alias="cli")


def save():
    _config.save()


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


class ConfigExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        manifest.config = get("network", "config", "", expand=False)

        for key, value in options("params"):
            p = manifest.create_parameter()
            p.key = "config." + key
            p.value = value

    def import_manifest(self, manifest):
        if manifest.config:
            _manifest.read_string(manifest.config)
            from jolt.loader import JoltLoader
            JoltLoader.get().load_plugins()

        for param in manifest.parameters:
            if param.key.startswith("config."):
                set("params", param.key.split(".", 1)[1], param.value)


# High priority so that plugins are loaded before resources are acquired.
ManifestExtensionRegistry.add(ConfigExtension(), -10)
