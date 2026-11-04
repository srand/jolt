"""
Reading and changing the shared library references of binaries.

A thin layer over LIEF for ELF (Linux), Mach-O (macOS) and PE (Windows)
files, used to relocate artifacts (see :mod:`jolt.relocate`).
"""

import os
import platform
import subprocess
import tempfile

import lief

from jolt import log
from jolt.error import raise_error


lief.logging.disable()


_ELF_MAGIC = b"\x7fELF"
_MACHO_MAGICS = (
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",  # 32-bit
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",  # 64-bit
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",  # universal
)
_PE_MAGIC = b"MZ"

_MACHO_LIBRARY_COMMANDS = (
    lief.MachO.LoadCommand.TYPE.LOAD_DYLIB,
    lief.MachO.LoadCommand.TYPE.LOAD_WEAK_DYLIB,
    lief.MachO.LoadCommand.TYPE.REEXPORT_DYLIB,
    lief.MachO.LoadCommand.TYPE.LAZY_LOAD_DYLIB,
    lief.MachO.LoadCommand.TYPE.LOAD_UPWARD_DYLIB,
)


class Binary(object):
    """ An executable or shared library. """

    format = None
    """ Binary format: ``"elf"``, ``"macho"`` or ``"pe"``. """

    def __init__(self, path):
        self.path = path
        self.modified = False

    @property
    def is_library(self):
        """ True for shared objects, dylibs, bundles and DLLs. """
        raise NotImplementedError()

    @property
    def install_name(self):
        """ The install name of a Mach-O dylib (``LC_ID_DYLIB``), otherwise None. """
        return None

    @property
    def needed(self):
        """ Names or paths of the shared libraries the binary links to. """
        raise NotImplementedError()

    @property
    def rpaths(self):
        """ Runtime search paths recorded in the binary. """
        return []

    @property
    def interpreter(self):
        """ The dynamic loader of an ELF executable, otherwise None. """
        return None

    def set_install_name(self, name):
        raise_error("Can't set the install name of {}", self.path)

    def change_needed(self, old, new):
        raise_error("Can't change the libraries of {}", self.path)

    def set_rpaths(self, rpaths):
        if rpaths:
            raise_error("Can't set rpaths in {}", self.path)

    def _write(self, path):
        raise NotImplementedError()

    def save(self):
        """
        Writes the binary back to its file if it was changed.

        The file mode is kept and, on macOS, the file is signed again with
        an ad-hoc signature.

        Returns:
            True if the file was written.
        """
        if not self.modified:
            return False

        mode = os.stat(self.path).st_mode
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".relocate-")
        os.close(fd)
        try:
            self._write(tmp)
            os.chmod(tmp, mode | 0o200)
            if self.format == "macho" and platform.system() == "Darwin":
                subprocess.run(["codesign", "-s", "-", "-f", tmp], check=True, capture_output=True)
            os.chmod(tmp, mode)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        self.modified = False
        return True


class ElfBinary(Binary):
    format = "elf"

    def __init__(self, path, binary):
        super().__init__(path)
        self._binary = binary

    @property
    def is_library(self):
        TAG = lief.ELF.DynamicEntry.TAG
        if self._binary.has(TAG.SONAME):
            return True
        return self._binary.header.file_type == lief.ELF.Header.FILE_TYPE.DYN \
            and not self._binary.has_interpreter

    @property
    def needed(self):
        return list(self._binary.libraries)

    @property
    def rpaths(self):
        TAG = lief.ELF.DynamicEntry.TAG
        for tag in (TAG.RUNPATH, TAG.RPATH):
            entry = self._binary.get(tag)
            if entry is not None:
                return list(entry.paths)
        return []

    @property
    def interpreter(self):
        return self._binary.interpreter if self._binary.has_interpreter else None

    def set_rpaths(self, rpaths):
        TAG = lief.ELF.DynamicEntry.TAG
        rpaths = list(rpaths)
        if rpaths == self.rpaths:
            return
        old_size = len(":".join(self.rpaths))
        for tag in (TAG.RUNPATH, TAG.RPATH):
            while self._binary.has(tag):
                self._binary.remove(tag)
        if rpaths:
            self._binary.add(lief.ELF.DynamicEntryRunPath(rpaths))
        if len(":".join(rpaths)) > old_size:
            log.warning(
                "[Relocate] {0}: the runpath doesn't fit in place, the file may break when stripped",
                self.path)
        self.modified = True

    def _write(self, path):
        self._binary.write(path)


class MachOBinary(Binary):
    """ A thin or universal Mach-O file. Edits apply to every slice. """

    format = "macho"

    def __init__(self, path, fat):
        super().__init__(path)
        self._fat = fat
        self._slices = [fat.at(i) for i in range(fat.size)]
        self._grow = [0] * len(self._slices)

    @property
    def _first(self):
        return self._slices[0]

    @property
    def is_library(self):
        TYPE = lief.MachO.Header.FILE_TYPE
        return self._first.header.file_type in (TYPE.DYLIB, TYPE.BUNDLE)

    @staticmethod
    def _id_command(binary):
        for command in binary.commands:
            if command.command == lief.MachO.LoadCommand.TYPE.ID_DYLIB:
                return command
        return None

    @staticmethod
    def _library_commands(binary):
        return [c for c in binary.commands if c.command in _MACHO_LIBRARY_COMMANDS]

    @property
    def install_name(self):
        command = self._id_command(self._first)
        return command.name if command is not None else None

    @property
    def needed(self):
        return [c.name for c in self._library_commands(self._first)]

    @property
    def rpaths(self):
        return [c.path for c in self._first.rpaths]

    @staticmethod
    def _command_size(string):
        # Load command strings are NUL terminated and padded to 8 bytes
        return (len(string) + 1 + 7) // 8 * 8

    def _check_space(self, index, grow):
        self._grow[index] += grow
        binary = self._slices[index]
        if self._grow[index] > binary.available_command_space:
            raise_error(
                "Not enough space for load commands in {}, link it with -headerpad_max_install_names",
                self.path)

    def set_install_name(self, name):
        if name == self.install_name:
            return
        for index, binary in enumerate(self._slices):
            command = self._id_command(binary)
            if command is None:
                raise_error("{} has no install name", self.path)
            self._check_space(index, self._command_size(name) - self._command_size(command.name))
            command.name = name
        self.modified = True

    def change_needed(self, old, new):
        for index, binary in enumerate(self._slices):
            for command in self._library_commands(binary):
                if command.name == old:
                    self._check_space(index, self._command_size(new) - self._command_size(old))
                    command.name = new
                    self.modified = True

    def set_rpaths(self, rpaths):
        rpaths = list(rpaths)
        if rpaths == self.rpaths:
            return
        for index, binary in enumerate(self._slices):
            old = list(binary.rpaths)
            grow = sum(16 + self._command_size(p) for p in rpaths) - \
                sum(16 + self._command_size(c.path) for c in old)
            self._check_space(index, grow)
            for command in old:
                binary.remove(command)
            for path in rpaths:
                binary.add(lief.MachO.RPathCommand.create(path))
        self.modified = True

    def _write(self, path):
        self._fat.write(path)


class PeBinary(Binary):
    format = "pe"

    def __init__(self, path, binary):
        super().__init__(path)
        self._binary = binary

    @property
    def is_library(self):
        return self._binary.header.has_characteristic(lief.PE.Header.CHARACTERISTICS.DLL)

    @property
    def needed(self):
        names = [imp.name for imp in self._binary.imports]
        names += [imp.name for imp in self._binary.delay_imports]
        return names


def _magic(path):
    try:
        with open(path, "rb") as f:
            return f.read(4)
    except OSError:
        return b""


def binary_format(path):
    """ ``"elf"``, ``"macho"`` or ``"pe"`` for regular files that start like such files, otherwise None. """
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    magic = _magic(path)
    if magic == _ELF_MAGIC:
        return "elf"
    if magic in _MACHO_MAGICS:
        return "macho"
    if magic[:2] == _PE_MAGIC:
        return "pe"
    return None


def is_binary_file(path):
    """ True for regular files that start like an ELF, Mach-O or PE file. """
    return binary_format(path) is not None


def open_binary(path):
    """
    Opens an executable or shared library.

    Returns:
        A :class:`Binary`, or None for symlinks, object files, archives and
        files that aren't ELF, Mach-O or PE binaries.
    """
    if os.path.islink(path) or not os.path.isfile(path):
        return None

    magic = _magic(path)

    if magic == _ELF_MAGIC:
        binary = lief.ELF.parse(path)
        if binary is None:
            return None
        TYPE = lief.ELF.Header.FILE_TYPE
        if binary.header.file_type not in (TYPE.EXEC, TYPE.DYN):
            return None
        return ElfBinary(path, binary)

    if magic in _MACHO_MAGICS:
        fat = lief.MachO.parse(path)
        if fat is None or fat.size == 0:
            return None
        TYPE = lief.MachO.Header.FILE_TYPE
        if fat.at(0).header.file_type not in (TYPE.EXECUTE, TYPE.DYLIB, TYPE.BUNDLE):
            return None
        return MachOBinary(path, fat)

    if magic[:2] == _PE_MAGIC:
        binary = lief.PE.parse(path)
        if binary is None:
            return None
        return PeBinary(path, binary)

    return None
