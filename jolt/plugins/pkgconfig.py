from jolt import filesystem as fs


class PkgConfigHelper(object):
    def __init__(self, artifact, tools):
        self.artifact = artifact
        self.tools = tools

    def _mkpath(self, path):
        if fs.path.commonpath([path, self.artifact.path]) != self.artifact.path:
            return path
        return fs.path.relpath(path, self.artifact.path)

    def cflags(self, package):
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --cflags-only-other {}", self.pkgconfig, package, output=False)
                return output.strip().split()
        except Exception:
            return []

    def incpaths(self, package):
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --cflags-only-I {}", self.pkgconfig, package, output=False)
                return [self._mkpath(inc[2:]) for inc in output.strip().split()]
        except Exception:
            return []

    def linkflags(self, package):
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --libs-only-other {}", self.pkgconfig, package, output=False)
                return output.strip().split()
        except Exception:
            return []

    def libpaths(self, package):
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --libs-only-L {}", self.pkgconfig, package, output=False)
                return [self._mkpath(lib[2:]) for lib in output.strip().split()]
        except Exception:
            return []

    def libraries(self, package):
        try:
            with self.tools.environ(**self.environ):
                output = self.tools.run("{} --libs-only-l {}", self.pkgconfig, package, output=False)
                return [lib[2:] for lib in output.strip().split()]
        except Exception:
            return []

    @property
    def pkgconfig(self):
        return self.tools.which(self.tools.getenv("PKG_CONFIG", "pkg-config"))

    @property
    def environ(self):
        path = self.artifact.environ.get("PKG_CONFIG_PATH")
        if path is None:
            self.verbose("No PKG_CONFIG_PATH in artifact environment; skipping pkg-config.")
            return {}

        # Path from the artifact environment
        path = str(path).split(fs.pathsep)
        path = ":".join(fs.path.join(self.artifact.path, p) for p in path)

        return {"PKG_CONFIG_PATH": path}


def cxxinfo(
    pkg: str,
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
