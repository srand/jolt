import functools
import os
import platform
import shlex
import shutil
import subprocess

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


def _compiler(variable, default):
    """ Describes the compiler that builds use: the one in the environment
    variable, or the default. """
    command = shlex.split(os.environ.get(variable) or default)
    if not command or not shutil.which(command[0]):
        return "<not found>"
    if os.path.basename(command[0]).lower() in ("cl", "cl.exe"):
        return _run(*command) or "<unknown>"
    version = _run(*command, "--version") or "<unknown>"
    target = _run(*command, "-dumpmachine")
    return "{} ({})".format(version, target) if target else version


def host_compilers(task):
    """
    Describes the host and the C and C++ compilers that builds use on it,
    so that their artifacts are kept apart from those of other platforms
    and compilers.
    """
    system, arch = utils.platform_os_arch()
    info = {"os": system, "arch": arch}

    if system == "linux":
        libc, version = platform.libc_ver()
        info["libc"] = "{} {}".format(libc, version) if libc else "<unknown>"

    if system == "windows":
        info["cc"] = _compiler("CC", "cl")
        info["cxx"] = _compiler("CXX", "cl")
    else:
        info["cc"] = _compiler("CC", "cc")
        info["cxx"] = _compiler("CXX", "c++")

    return info


@influence.function(host_compilers)
class HostCompiler(Task):
    """
    The C and C++ compilers of the host.

    The identity of the task depends on the operating system and
    architecture of the host, and on the versions and targets of the
    compilers that builds use, those in ``CC`` and ``CXX`` or the defaults.
    Packages that require it are built separately for each platform and
    compiler.
    """

    name = "compiler/c"

    def run(self, deps, tools):
        info = host_compilers(self)
        hint = ", or run Jolt from a Visual Studio developer prompt" if info["os"] == "windows" else ""
        raise_task_error_if(
            info["cc"] == "<not found>", self,
            "No C compiler found: install one, or set CC to the one to use" + hint)


class CCompiler(Alias):
    """
    The C and C++ compilers that packages are built with.

    Packages require this alias rather than a specific compiler. It
    selects the compilers of the host, and can be overridden to build all
    packages with another compiler.
    """

    name = "virtual/compiler/c"
    requires = ["compiler/c"]


TaskRegistry.get().add_task_class(HostCompiler)
TaskRegistry.get().add_task_class(CCompiler)
