import functools
import os
import platform
import shlex
import shutil
import subprocess
import tempfile

from jolt import Alias, Task, influence, utils
from jolt.error import raise_task_error_if
from jolt.tasks import TaskRegistry


@functools.lru_cache(maxsize=None)
def _run(*args):
    """ Returns the first line of the output of a command, or None if it fails. """
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    # cl prints its version to stderr, and fails without source files
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0].strip() if lines else None


def _command(variable, default):
    """ The compiler that builds use: the one in the environment variable,
    or the default. Returns None if it isn't installed. """
    command = shlex.split(os.environ.get(variable) or default)
    if not command or not shutil.which(command[0]):
        return None
    return command


def _is_msvc(command):
    return os.path.basename(command[0]).lower() in ("cl", "cl.exe")


def _describe(command):
    """ Describes a compiler by its version and target. """
    if command is None:
        return "<not found>"
    if _is_msvc(command):
        return _run(*command) or "<unknown>"
    version = _run(*command, "--version") or "<unknown>"
    target = _run(*command, "-dumpmachine")
    return "{} ({})".format(version, target) if target else version


# Macros that identify the C++ standard libraries, in the order they are
# reported. Those that a library doesn't define are left unexpanded.
_STDLIB_MACROS = {
    "libstdcxx": ["_GLIBCXX_RELEASE", "__GLIBCXX__"],
    "libcxx": ["_LIBCPP_VERSION"],
    "msvc": ["_MSVC_STL_VERSION", "_MSVC_STL_UPDATE"],
}
_STDLIB_NAMES = {"libstdcxx": "libstdc++", "libcxx": "libc++", "msvc": "msvc"}


@functools.lru_cache(maxsize=None)
def _stdlib(command):
    """
    Identifies the C++ standard library of a compiler by preprocessing one
    of its headers. Returns None if the headers aren't found.
    """
    source = "#include <cstddef>\n" + "".join(
        "jolt_stdlib {} {}\n".format(name, " ".join(macros))
        for name, macros in _STDLIB_MACROS.items())

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "stdlib.cpp")
        with open(path, "w") as f:
            f.write(source)
        args = ["/nologo", "/EP", path] if _is_msvc(command) else ["-E", "-P", "-x", "c++", path]
        try:
            result = subprocess.run(command + tuple(args), capture_output=True, text=True, timeout=60, cwd=tmpdir)
        except (OSError, subprocess.SubprocessError):
            return None
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        words = line.split()
        if len(words) < 2 or words[0] != "jolt_stdlib":
            continue
        name, values = words[1], words[2:]
        if values != _STDLIB_MACROS[name]:
            return "{} {}".format(_STDLIB_NAMES[name], " ".join(values))
    return "<unknown>"


def _host():
    system, arch = utils.platform_os_arch()
    info = {"os": system, "arch": arch}
    if system == "linux":
        libc, version = platform.libc_ver()
        info["libc"] = "{} {}".format(libc, version) if libc else "<unknown>"
    return info


def _c_command():
    return _command("CC", "cl" if utils.platform_os_arch()[0] == "windows" else "cc")


def _cxx_command():
    return _command("CXX", "cl" if utils.platform_os_arch()[0] == "windows" else "c++")


def host_c_compiler(task):
    """
    Describes the host and the C compiler that builds use on it, so that
    their artifacts are kept apart from those of other platforms and
    compilers.
    """
    info = _host()
    info["cc"] = _describe(_c_command())
    return info


def host_cxx_compiler(task):
    """
    Describes the host, the C++ compiler that builds use on it and its
    standard library.
    """
    info = _host()
    command = _cxx_command()
    info["cxx"] = _describe(command)
    info["stdlib"] = (_stdlib(tuple(command)) or "<not found>") if command else "<not found>"
    return info


def _hint():
    if utils.platform_os_arch()[0] == "windows":
        return ", or run Jolt from a Visual Studio developer prompt"
    return ""


@influence.function(host_c_compiler)
class HostCCompiler(Task):
    """
    The C compiler of the host.

    The identity of the task depends on the operating system and
    architecture of the host, and on the version and target of the C
    compiler that builds use, the one in ``CC`` or the default. Packages
    that require it are built separately for each platform and compiler.
    """

    name = "compiler/c"

    def run(self, deps, tools):
        raise_task_error_if(
            _c_command() is None, self,
            "No C compiler found: install one, or set CC to the one to use" + _hint())


@influence.function(host_cxx_compiler)
class HostCXXCompiler(Task):
    """
    The C++ compiler of the host and its standard library.

    The identity of the task depends on the operating system and
    architecture of the host, on the version and target of the C++
    compiler that builds use, the one in ``CXX`` or the default, and on
    the version of its standard library: libstdc++, libc++ or the one of
    MSVC.
    """

    name = "compiler/cxx"

    def run(self, deps, tools):
        command = _cxx_command()
        raise_task_error_if(
            command is None, self,
            "No C++ compiler found: install one, or set CXX to the one to use" + _hint())
        raise_task_error_if(
            _stdlib(tuple(command)) is None, self,
            "The headers of the C++ standard library of {} were not found: install "
            "the development package of the library", " ".join(command))


class CCompiler(Alias):
    """
    The C compiler that packages are built with.

    Packages require this alias rather than a specific compiler. It
    selects the compiler of the host, and can be overridden to build all
    packages with another compiler.
    """

    name = "virtual/compiler/c"
    requires = ["compiler/c"]


class CXXCompiler(Alias):
    """
    The C++ compiler that packages are built with.

    Packages written in C++ require this alias in addition to
    ``virtual/compiler/c``. It selects the compiler of the host, and can be
    overridden to build all packages with another compiler.
    """

    name = "virtual/compiler/cxx"
    requires = ["compiler/cxx"]


TaskRegistry.get().add_task_class(HostCCompiler)
TaskRegistry.get().add_task_class(HostCXXCompiler)
TaskRegistry.get().add_task_class(CCompiler)
TaskRegistry.get().add_task_class(CXXCompiler)
