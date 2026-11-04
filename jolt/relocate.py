"""
Relocation of the binaries in an artifact.

After a task decorated with :func:`jolt.attributes.relocate_binaries` has
published its artifact, install names and rpaths in its binaries are
rewritten to be relative, so that the artifact works from any cache
location. Self-sustained artifacts also get copies of the shared libraries
their binaries link to.

The relative paths between artifacts depend on the layout of the cache.
Change ``LAYOUT_VERSION`` when the layout changes; the source of this
module is part of the identity of relocated tasks.
"""

import contextlib
import os
import platform
import shlex
import shutil
import subprocess

from jolt import binaries
from jolt import log


LAYOUT_VERSION = "1"

RESERVED_RPATH = "/jolt-rpath-reserve/" + "0" * 108
"""
Placeholder rpath that relocated tasks link with on Linux.

It reserves space in the dynamic string table, so that the relative rpaths
written after publish fit in place. When the table must grow, LIEF moves it
into a new segment, and ``strip`` breaks such files. The placeholder is
dropped when the binaries are relocated.
"""

_RELATIVE_PREFIXES = ("$ORIGIN", "${ORIGIN}", "@loader_path", "@executable_path", "@rpath")


def build_environment(tools):
    """
    Linker flags for the build of a relocated task.

    On Linux, rpath space is reserved with :data:`RESERVED_RPATH`. On macOS,
    space for longer install names and rpaths is reserved in the headers.
    """
    system = platform.system()
    if system == "Linux":
        flag = "-Wl,-rpath," + RESERVED_RPATH
    elif system == "Darwin":
        flag = "-Wl,-headerpad_max_install_names"
    else:
        return contextlib.nullcontext()
    ldflags = tools.getenv("LDFLAGS", "")
    if flag in ldflags.split():
        return contextlib.nullcontext()
    return tools.environ(LDFLAGS=(ldflags + " " + flag).strip())


def origin(fmt):
    """ The token for the directory of a binary in rpaths. """
    return "@loader_path" if fmt == "macho" else "$ORIGIN"


def relative_dir(fmt, binary_dir, target_dir):
    """ An rpath to target_dir, relative to a binary in binary_dir. """
    rel = os.path.relpath(target_dir, binary_dir).replace(os.sep, "/")
    return origin(fmt) if rel == "." else origin(fmt) + "/" + rel


def _is_under(path, root):
    path, root = os.path.normpath(path), os.path.normpath(root)
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _resolve_relative(fmt, rpath, binary_dir):
    for token in (origin(fmt), "${ORIGIN}", "@executable_path"):
        if rpath.startswith(token):
            return os.path.normpath(binary_dir + rpath[len(token):])
    return None


def plan_rpaths(fmt, binary_relpath, rpaths, install_prefix, artifact_root, own_rpath,
                dep_roots, links_own_library, current_root=None, self_contained=False):
    """
    Computes the rpaths of a binary after relocation.

    Args:
        fmt: Binary format, ``"elf"`` or ``"macho"``.
        binary_relpath: Path of the binary relative to the artifact root.
        rpaths: Rpaths currently recorded in the binary.
        install_prefix: Prefix the artifact was installed into, or None.
        artifact_root: Final location of the artifact in the cache.
        own_rpath: The artifact's own library folders.
        dep_roots: Final locations of the dependencies' artifacts.
        links_own_library: Whether the binary links to a library in own_rpath.
        current_root: Current location of the artifact's files, used to check
            that folders exist. Defaults to artifact_root.
        self_contained: Drop relative rpaths that lead outside the artifact.

    Returns:
        New rpaths: the artifact's own folders first when the binary links to
        them, then relative rpaths kept as they are, rpaths into the install
        prefix that exist in the artifact, and rpaths into dependencies, all
        made relative. Everything else is dropped.
    """
    current_root = current_root or artifact_root
    binary_dir = os.path.join(artifact_root, os.path.dirname(binary_relpath))
    result = []

    def add(rpath):
        if rpath not in result:
            result.append(rpath)

    if links_own_library:
        for folder in own_rpath:
            add(relative_dir(fmt, binary_dir, os.path.join(artifact_root, folder)))

    for rpath in rpaths:
        if rpath.startswith(_RELATIVE_PREFIXES):
            resolved = _resolve_relative(fmt, rpath, binary_dir)
            if self_contained and resolved is not None and not _is_under(resolved, artifact_root):
                log.verbose("[Relocate] {0}: dropping rpath {1}", binary_relpath, rpath)
                continue
            add(rpath)
            continue

        if install_prefix and _is_under(rpath, install_prefix):
            folder = os.path.relpath(rpath, install_prefix)
            if os.path.isdir(os.path.join(current_root, folder)):
                add(relative_dir(fmt, binary_dir, os.path.join(artifact_root, folder)))
            continue

        if any(_is_under(rpath, root) for root in dep_roots):
            add(relative_dir(fmt, binary_dir, rpath))
            continue

        log.verbose("[Relocate] {0}: dropping rpath {1}", binary_relpath, rpath)

    return result


def find_binaries(root):
    """ Paths, relative to root, of the binaries in a directory tree. Symlinks are skipped. """
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            if binaries.is_binary_file(path):
                found.append(os.path.relpath(path, root).replace(os.sep, "/"))
    return sorted(found)


def _install_name_rename(binary, install_prefix, own_rpath=()):
    """ The new install name of a Mach-O dylib in the install prefix, or None. """
    name = binary.install_name
    if binary.format != "macho" or not name or not install_prefix or not _is_under(name, install_prefix):
        return None
    relpath = os.path.relpath(name, install_prefix).replace(os.sep, "/")
    for folder in sorted(own_rpath, key=len, reverse=True):
        if relpath.startswith(folder.rstrip("/") + "/"):
            return "@rpath/" + relpath[len(folder.rstrip("/")) + 1:]
    return "@rpath/" + os.path.basename(name)


def _apply_renames(binary, renames):
    if binary.format != "macho":
        return
    if binary.install_name in renames:
        binary.set_install_name(renames[binary.install_name])
    for old, new in renames.items():
        if old in binary.needed:
            binary.change_needed(old, new)


def rewrite_install_names(opened, install_prefix, own_rpath=()):
    """
    Changes Mach-O install names in the install prefix to ``@rpath/<name>``.

    Names in frameworks keep their path below the library folder, for
    example ``@rpath/QtCore.framework/Versions/A/QtCore``. References to
    the changed names in all the binaries are changed too.

    Args:
        opened: List of (relative path, Binary) tuples.
        install_prefix: Prefix the artifact was installed into.
        own_rpath: The artifact's library folders.

    Returns:
        Dictionary of old install names to new ones.
    """
    renames = {}
    for relpath, binary in opened:
        new = _install_name_rename(binary, install_prefix, own_rpath)
        if new:
            renames[binary.install_name] = new
            log.verbose("[Relocate] {0}: install name {1} -> {2}", relpath, binary.install_name, new)
    for relpath, binary in opened:
        _apply_renames(binary, renames)
    return renames


def _library_suffixes():
    system = platform.system()
    if system == "Windows":
        return (".dll",)
    if system == "Darwin":
        return (".dylib", ".so")
    return (".so",)


def _is_library_name(name):
    name = name.lower()
    return any(name.endswith(s) or (s + ".") in name for s in _library_suffixes())


def default_rpath(root):
    """ The library folders of an artifact: lib and lib64, or bin on Windows. """
    folders = ["bin"] if platform.system() == "Windows" else ["lib", "lib64"]
    result = []
    for folder in folders:
        path = os.path.join(root, folder)
        if os.path.isdir(path) and any(_is_library_name(f) or f.endswith(".framework") for f in os.listdir(path)):
            result.append(folder)
    return result


def _own_library_names(root, own_rpath):
    names = set()
    for folder in own_rpath:
        path = os.path.join(root, folder)
        if os.path.isdir(path):
            names.update(os.listdir(path))
    return names


def _dep_roots(deps):
    return [artifact.final_path for _, artifact in deps.items()]


def toolchain_roots(node):
    """
    Locations of the toolchain's artifacts.

    These are the main artifacts of the requirements of a task named
    ``virtual/compiler/*``, and of everything they require.
    """
    roots = set()
    visited = set()

    def visit(child):
        if id(child) in visited:
            return
        visited.add(id(child))
        for artifact in child.artifacts:
            if getattr(artifact, "is_main", lambda: True)():
                roots.add(artifact.final_path)
        for grandchild in list(getattr(child, "descendants", None) or child.children):
            visit(grandchild)

    # Transitive aliases are only in descendants, children leaves them out
    for child in list(getattr(node, "descendants", None) or node.children):
        if child.qualified_name.startswith("virtual/compiler/"):
            visit(child)
    return roots


_WINDOWS_SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "comctl32.dll", "comdlg32.dll", "crypt32.dll", "dbghelp.dll",
    "gdi32.dll", "imm32.dll", "iphlpapi.dll", "kernel32.dll", "kernelbase.dll", "msvcrt.dll",
    "ncrypt.dll", "netapi32.dll", "ntdll.dll", "ole32.dll", "oleaut32.dll", "psapi.dll",
    "rpcrt4.dll", "secur32.dll", "setupapi.dll", "shell32.dll", "shlwapi.dll", "ucrtbase.dll",
    "user32.dll", "userenv.dll", "uxtheme.dll", "version.dll", "winmm.dll", "ws2_32.dll",
}


def _never_bundled(fmt, name):
    """ Libraries of the operating system, which are never bundled. """
    if fmt == "pe":
        lower = os.path.basename(name).lower()
        if lower in _WINDOWS_SYSTEM_DLLS or lower.startswith(("api-ms-win-", "ext-ms-")):
            return True
        system_root = os.environ.get("SystemRoot")
        return bool(system_root) and os.path.isfile(os.path.join(system_root, "System32", lower))
    if fmt == "macho":
        return name.startswith(("/usr/lib/", "/System/"))
    return False


def _framework_subpath(name):
    """ The path of a library below the folder of its framework, or None. """
    parts = name.split("/")
    for index, part in enumerate(parts):
        if part.endswith(".framework"):
            return "/".join(parts[index:])
    return None


def _framework_root(path):
    """ The .framework directory that a file is in, or None. """
    parts = path.split(os.sep)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index].endswith(".framework"):
            return os.sep.join(parts[:index + 1])
    return None


def resolve_library(name, fmt, search):
    """ The first file in the search folders with the file name of a library, or None. """
    basename = os.path.basename(name)
    subpath = _framework_subpath(name) if fmt == "macho" else None
    for folder in search:
        if subpath and os.path.isfile(os.path.join(folder, subpath)):
            return os.path.join(folder, subpath)
        path = os.path.join(folder, basename)
        if os.path.isfile(path):
            return path
        if fmt == "pe" and os.path.isdir(folder):
            for entry in os.listdir(folder):
                if entry.lower() == basename.lower():
                    return os.path.join(folder, entry)
    return None


def _toolchain_file(node, name):
    """ Asks the compiler where a runtime library is, or returns None. """
    tools = getattr(node, "tools", None)
    compiler = tools.getenv("CC", "cc") if tools is not None else "cc"
    try:
        result = subprocess.run(
            shlex.split(compiler) + ["-print-file-name=" + name],
            capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    path = result.stdout.strip()
    return path if os.path.isabs(path) and os.path.isfile(path) else None


def _copy_framework(found, destdir, root):
    """ Copies the whole framework that a library is in. Returns created relative paths. """
    framework = _framework_root(found)
    dest_framework = os.path.join(destdir, os.path.basename(framework))
    dest = os.path.join(dest_framework, os.path.relpath(found, framework))
    if os.path.lexists(dest_framework):
        return [], dest
    shutil.copytree(framework, dest_framework, symlinks=True)
    created = []
    for dirpath, dirnames, filenames in os.walk(dest_framework):
        for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            created.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return created, dest


def _copy_library(found, destdir, root):
    """ Copies a library and the symlinks leading to it. Returns created relative paths. """
    if _framework_root(found):
        return _copy_framework(found, destdir, root)
    created = []
    os.makedirs(destdir, exist_ok=True)
    path = found
    while os.path.islink(path):
        target = os.readlink(path)
        if os.path.dirname(target):
            break
        link = os.path.join(destdir, os.path.basename(path))
        if not os.path.lexists(link):
            os.symlink(target, link)
            created.append(link)
        path = os.path.join(os.path.dirname(path), target)
    dest = os.path.join(destdir, os.path.basename(path))
    if not os.path.lexists(dest):
        shutil.copy2(os.path.realpath(path), dest)
        os.chmod(dest, os.stat(dest).st_mode | 0o200)
        created.append(dest)
    return [os.path.relpath(p, root).replace(os.sep, "/") for p in created], dest


def _binary_search_dirs(fmt, binary, roots):
    """ Folders in the given roots that a binary's own rpaths lead to. """
    binary_dir = os.path.dirname(binary.path)
    dirs = []
    for rpath in binary.rpaths:
        resolved = _resolve_relative(fmt, rpath, binary_dir)
        if resolved is None and os.path.isabs(rpath):
            resolved = rpath
        if resolved is None or not os.path.isdir(resolved):
            continue
        if any(_is_under(resolved, root) for root in roots):
            dirs.append(resolved)
    return dirs


def bundle_artifact(node, artifact, deps, bundle_runtime):
    """
    Copies the shared libraries that the artifact's binaries link to into it.

    Libraries are looked for in the ``rpath`` folders of the dependencies and
    in the folders the binaries' rpaths lead to. Libraries of the toolchain
    and those that aren't found are only bundled when bundle_runtime is true,
    which also bundles the dynamic loader. Libraries of the operating system
    are never bundled.

    Libraries are copied into ``lib``, or on Windows next to each executable.

    Returns:
        Sorted relative paths of the copied files and symlinks.
    """
    root = artifact.path
    search = []
    for _, dep in deps.items():
        for folder in dep.rpath:
            search.append(os.path.join(dep.path, folder))
    toolchain = toolchain_roots(node)
    # Only dependencies and the artifact itself, not host folders
    roots = [dep.path for _, dep in deps.items()] + [root]

    # Paths, not parsed binaries: they take more memory than their files
    queue = [os.path.join(root, relpath) for relpath in find_binaries(root)]
    if not queue:
        return []

    formats = {path: binaries.binary_format(path) for path in queue}
    if all(f == "pe" for f in formats.values()):
        fmt = "pe"
        destdirs = sorted({os.path.dirname(p) for p in queue if p.lower().endswith(".exe")})
        if not destdirs:
            # Only DLLs: they find the DLLs they need in their own folders
            destdirs = [os.path.join(root, folder) for folder in (list(artifact.rpath) or default_rpath(root) or ["bin"])]
    else:
        fmt = next(f for f in formats.values() if f != "pe")
        destdirs = [os.path.join(root, "lib")]

    present = set()
    for destdir in destdirs:
        if os.path.isdir(destdir):
            present.update(os.listdir(destdir))

    copied = []
    loaders = set()

    def bundle(found):
        nonlocal copied
        for destdir in destdirs:
            created, dest = _copy_library(found, destdir, root)
            copied += created
            present.add(os.path.basename(found))
            if destdir == destdirs[0]:
                queue.append(dest)

    while queue:
        binary = binaries.open_binary(queue.pop(0))
        if binary is None:
            continue
        interpreter = binary.interpreter
        needed = binary.needed
        search_dirs = search + _binary_search_dirs(fmt, binary, roots)
        binary = None

        if bundle_runtime and interpreter and interpreter not in loaders:
            loaders.add(interpreter)
            if os.path.basename(interpreter) not in present and os.path.isfile(interpreter):
                bundle(interpreter)

        for name in needed:
            basename = os.path.basename(name)
            if basename in present or _never_bundled(fmt, name):
                continue

            found = resolve_library(name, fmt, search_dirs)
            runtime = found is not None and any(_is_under(found, t) for t in toolchain)
            if found is None and bundle_runtime:
                found, runtime = _toolchain_file(node, basename), True
            if found is None or (runtime and not bundle_runtime):
                continue

            log.verbose("[Relocate] Bundling {0}", found)
            bundle(found)

    if fmt != "pe" and copied and "lib" not in list(artifact.rpath):
        artifact.rpath.append("lib")

    return sorted(copied)


def relocate_artifact(node, artifact, tools, deps):
    """
    Relocates the binaries in a published artifact.

    Args:
        node: The task proxy that published the artifact.
        artifact: The published artifact.
        tools: Task tools.
        deps: Dependency context of the task.
    """
    root = artifact.path
    final_root = artifact.final_path

    for folder in default_rpath(root):
        if folder not in list(artifact.rpath):
            artifact.rpath.append(folder)

    install_prefix = artifact.strings.install_prefix
    install_prefix = str(install_prefix) if install_prefix is not None else None

    self_contained = bool(node.task.selfsustained)
    if self_contained:
        bundle_artifact(node, artifact, deps, node.task.bundle_runtime_libraries)
        dep_roots = []
    else:
        dep_roots = _dep_roots(deps)

    own_rpath = list(artifact.rpath)
    own_names = _own_library_names(root, own_rpath)
    relpaths = find_binaries(root)

    # Binaries are parsed one at a time, they take more memory than their files
    renames = {}
    for relpath in relpaths:
        if binaries.binary_format(os.path.join(root, relpath)) != "macho":
            continue
        binary = binaries.open_binary(os.path.join(root, relpath))
        new = _install_name_rename(binary, install_prefix, own_rpath) if binary is not None else None
        if new:
            renames[binary.install_name] = new
            log.verbose("[Relocate] {0}: install name {1} -> {2}", relpath, binary.install_name, new)
        binary = None

    for relpath in relpaths:
        binary = binaries.open_binary(os.path.join(root, relpath))
        if binary is None:
            continue
        _apply_renames(binary, renames)
        if binary.format != "pe":
            links_own = any(os.path.basename(name) in own_names for name in binary.needed)
            rpaths = plan_rpaths(
                binary.format, relpath, binary.rpaths, install_prefix, final_root,
                own_rpath, dep_roots, links_own, current_root=root, self_contained=self_contained)
            binary.set_rpaths(rpaths)
        if binary.save():
            log.verbose("[Relocate] {0}: rewritten", relpath)
        binary = None
