from jolt import attributes, Alias, Parameter, Task
from jolt.plugins import autotools, git, pkgconfig
from jolt.tasks import TaskRegistry


def _unpack_adjust_scripts(artifact, tools):
    bindir = "Scripts" if artifact.strings.system == "windows" else "bin"

    with tools.cwd(artifact.path, bindir):
        # Adjust paths in scripts
        for script in tools.glob("*"):
            # Ignore python executables
            if script.startswith("python"):
                continue
            tools.replace_in_file(script, artifact.strings.install_prefix, artifact.final_path)

    artifact.strings.install_prefix = artifact.final_path


@attributes.requires("requires_git")
class CPythonPosix(autotools.Autotools):
    """ Builds and publishes CPython libraries and headers. """

    name = "cpython/posix"
    version = Parameter("3.14.2", help="CPython version.")
    requires_git = ["git:url=https://github.com/python/cpython.git,rev=v{version}"]
    srcdir = "{git[cpython]}"

    @property
    def version_major(self):
        ver = str(self.version).split(".")
        return f"{ver[0]}.{ver[1]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.strings.version = str(self.version)
        artifact.strings.version_major = str(self.version_major)

    def unpack(self, artifact, tools):
        super().unpack(artifact, tools)
        _unpack_adjust_scripts(artifact, tools)


@attributes.requires("requires_git")
@attributes.common_metadata()
class CPythonWin32(Task):
    """ Builds and publishes CPython libraries and headers. """

    name = "cpython/win32"
    version = Parameter("3.14.2", help="CPython version.")
    requires_git = ["git:url=https://github.com/python/cpython.git,rev=v{version}"]
    srcdir = "{git[cpython]}"

    @property
    def version_major(self):
        ver = str(self.version).split(".")
        return f"{ver[0]}.{ver[1]}"

    @property
    def version_major_compact(self):
        ver = str(self.version).split(".")
        return f"{ver[0]}{ver[1]}"

    def run(self, deps, tools):
        with tools.cwd(self.srcdir, "PCbuild"):
            tools.run("build.bat")

    def publish(self, artifact, tools):
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.strings.version = str(self.version)
        artifact.strings.version_major = str(self.version_major)
        with tools.cwd(self.srcdir):
            artifact.collect("Include", "include")
            artifact.collect("Lib", "lib")
        with tools.cwd(self.srcdir, "PCbuild", "amd64"):
            artifact.collect("python.exe", "bin/python3.exe")
            artifact.collect("python.exe", "bin/python{version_major}.exe")
            artifact.collect("*.dll", "bin/")
            artifact.collect("*.lib", "lib/")
        with tools.tmpdir() as tmp, tools.cwd(tmp):
            tools.write_file(
                "python3.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/lib
includedir=${{prefix}}/include

Name: Python
Description: Build a C extension for Python
Version: {version}-{identity}
Libs: -L${{libdir}} -lpython3
Cflags: -I${{includedir}}
""")
            tools.write_file(
                "python3-embed.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/lib
includedir=${{prefix}}/include

Name: Python
Description: Embed Python into an application
Version: {version}-{identity}
Libs: -L${{libdir}} -lpython{version_major_compact}
Cflags: -I${{includedir}}
""")
            artifact.collect("*.pc", "lib/pkgconfig/")

    def unpack(self, artifact, tools):
        super().unpack(artifact, tools)
        _unpack_adjust_scripts(artifact, tools)


@attributes.requires("requires_{system}")
@attributes.system
class CPython(Alias):
    """ Alias for CPython """
    name = "cpython"
    version = Parameter("3.14.2", help="CPython version.")
    requires_darwin = ["cpython/posix:version={version}"]
    requires_linux = requires_darwin
    requires_windows = ["cpython/win32:version={version}"]


@pkgconfig.to_cxxinfo("python3-embed")
@attributes.common_metadata()
@attributes.system
@pkgconfig.requires()
class CPythonEmbed(Task):
    name = "cpython/embed"
    requires = ["cpython"]
    selfsustained = True

    def run(self, deps, tools):
        name = "cpython/win32" if self.system == "windows" else "cpython/posix"
        self.cpython = deps[name]

    def publish(self, artifact, tools):
        with tools.cwd(self.cpython.path):
            artifact.collect("*", symlinks=True)


@pkgconfig.to_cxxinfo("python3")
@attributes.common_metadata()
@attributes.system
@pkgconfig.requires()
class CPythonExtend(Task):
    name = "cpython/extend"
    requires = ["cpython"]
    selfsustained = True

    def run(self, deps, tools):
        name = "cpython/win32" if self.system == "windows" else "cpython/posix"
        self.cpython = deps[name]

    def publish(self, artifact, tools):
        with tools.cwd(self.cpython.path):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(CPythonPosix)
TaskRegistry.get().add_task_class(CPythonWin32)
TaskRegistry.get().add_task_class(CPython)
TaskRegistry.get().add_task_class(CPythonEmbed)
TaskRegistry.get().add_task_class(CPythonExtend)
