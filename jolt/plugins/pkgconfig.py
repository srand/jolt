from jolt import attributes
from jolt import filesystem as fs
from jolt import utils


class PkgConfigHelper(object):

    TEMPLATE_PKGCONFIG = """
prefix={{ artifact.final_path }}

Name: {{ pkgname }}
Description: {{ pkgname }} package
Version: {{ artifact.identity }}

Cflags: {% for flag in cxxflags %}{{ flag }} {% endfor %}{% for inc in incpaths %}-I${prefix}/{{ inc }} {% endfor %}{% for macro in macros %}-D{{ macro }} {% endfor %}

Libs: {% for flag in ldflags %}{{ flag }} {% endfor %}{% for libpath in libpaths %}-L${prefix}/{{ libpath }} {% endfor %}{% for library in libraries %}-l{{ library }} {% endfor %}

"""

    def __init__(self, artifact, tools):
        self.artifact = artifact
        self.tools = tools

    def _mkpath(self, path):
        if fs.path.commonpath([path, self.artifact.path]) != self.artifact.path:
            return path
        return fs.path.relpath(path, self.artifact.path)

    def cflags(self, package):
        package = " ".join(utils.as_list(package))
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --cflags-only-other {}", self.pkgconfig, package, output=False)
                return output.strip().split()
        except Exception:
            return []

    def incpaths(self, package):
        package = " ".join(utils.as_list(package))
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --cflags-only-I {}", self.pkgconfig, package, output=False)
                return [self._mkpath(inc[2:]) for inc in output.strip().split()]
        except Exception:
            return []

    def linkflags(self, package):
        package = " ".join(utils.as_list(package))
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --libs-only-other {}", self.pkgconfig, package, output=False)
                return output.strip().split()
        except Exception:
            return []

    def libpaths(self, package):
        package = " ".join(utils.as_list(package))
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --libs-only-L {}", self.pkgconfig, package, output=False)
                return [self._mkpath(lib[2:]) for lib in output.strip().split()]
        except Exception:
            return []

    def libraries(self, package):
        package = " ".join(utils.as_list(package))
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --libs-only-l {}", self.pkgconfig, package, output=False)
                return [lib[2:] for lib in output.strip().split()]
        except Exception:
            return []

    def write_pc(self, package):
        with self.tools.tmpdir() as tmpdir, self.tools.cwd(tmpdir):
            content = self.tools.render(
                self.TEMPLATE_PKGCONFIG,
                artifact=self.artifact,
                pkgname=package,
                macros=list(self.artifact.cxxinfo.macros),
                incpaths=list(self.artifact.cxxinfo.incpaths),
                libpaths=list(self.artifact.cxxinfo.libpaths),
                libraries=list(self.artifact.cxxinfo.libraries),
            )
            print(content)
            self.tools.write_file(f"{package}.pc", content, expand=False)
            self.artifact.collect(f"{package}.pc", "lib/pkgconfig/")

    @property
    def pkgconfig(self):
        return self.tools.which(self.tools.getenv("PKG_CONFIG", "pkg-config"))

    @property
    def environ(self):
        path = self.artifact.environ.get("PKG_CONFIG_PATH")
        if path is None:
            self.tools._task.verbose("No PKG_CONFIG_PATH in artifact environment")

        # Path from the artifact environment
        path = str(path).split(fs.pathsep)
        path = ":".join(fs.path.join(self.artifact.path, p) for p in path)

        # Append existing PKG_CONFIG_PATH from the tools environment
        if self.tools.getenv("PKG_CONFIG_PATH"):
            path = path + ":" + self.tools.getenv("PKG_CONFIG_PATH")

        return {"PKG_CONFIG_PATH": path}


def to_cxxinfo(
    pkg: list | str,
    cflags: bool = True,
    cxxflags: bool = True,
    incpaths: bool = True,
    ldflags: bool = True,
    libpaths: bool = True,
    libraries: bool = True,
):
    """
    Decorator to add pkg-config information to cxxinfo metadata of an artifact.

    The decorator enables interoperability between libraries built with Jolt's
    Ninja plugin and external packages that provide pkg-config files.

    It uses the pkg-config tool to query for compiler and linker flags,
    include paths, library paths, and libraries associated with a given package.
    If the relevant flags are found, they are appended to the corresponding fields
    in the artifact's cxxinfo metadata.

    Args:
        pkg (str): The name of the pkg-config package to be added to cxxinfo.
        cflags (bool): Whether to add C compiler flags from pkg-config.
        cxxflags (bool): Whether to add C++ compiler flags from pkg-config.
        incpaths (bool): Whether to add include paths from pkg-config.
        ldflags (bool): Whether to add linker flags from pkg-config.
        libpaths (bool): Whether to add library paths from pkg-config.
        libraries (bool): Whether to add libraries from pkg-config.
    """

    def decorate(cls):
        original_publish = cls.publish

        def publish(self, artifact, tools):
            original_publish(self, artifact, tools)

            pc = PkgConfigHelper(artifact, tools)
            if not pc.environ:
                self.verbose("Skipping pkg-config cxxinfo addition due to missing PKG_CONFIG_PATH.")
                return

            if cflags:
                artifact.cxxinfo.cflags.extend(pc.cflags(pkg))
            if cxxflags:
                artifact.cxxinfo.cxxflags.extend(pc.cflags(pkg))
            if incpaths:
                artifact.cxxinfo.incpaths.extend(pc.incpaths(pkg))
            if ldflags:
                artifact.cxxinfo.ldflags.extend(pc.linkflags(pkg))
            if libpaths:
                artifact.cxxinfo.libpaths.extend(pc.libpaths(pkg))
            if libraries:
                artifact.cxxinfo.libraries.extend(pc.libraries(pkg))

        cls.publish = publish
        return cls

    return decorate


def from_cxxinfo(package):
    """
    Decorator to write a pkg-config file for the given package
    based on the cxxinfo metadata of the artifact.
    """

    def decorate(cls):
        original_publish = cls.publish
        original_unpack = cls.unpack

        def publish(self, artifact, tools):
            original_publish(self, artifact, tools)

            pc = PkgConfigHelper(artifact, tools)
            pc.write_pc(package)

        def unpack(self, artifact, tools):
            original_unpack(self, artifact, tools)

            pc = PkgConfigHelper(artifact, tools)
            pc.write_pc(package)

        cls.publish = publish
        cls.unpack = unpack
        return cls

    return decorate


def requires():
    """ Decorator to add pkg-config requirements to a task. """

    import jolt.pkgs.pkgconfig

    def decorate(cls):
        cls = attributes.requires("requires_pkgconf")(cls)
        cls.requires_pkgconf = ["pkg-config"]
        return cls

    return decorate
