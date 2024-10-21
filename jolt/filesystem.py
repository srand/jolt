import os
import errno
import functools
import ntpath
import pathlib
import posixpath
import shutil
import tempfile
import sys

from jolt.error import raise_error_if


path = os.path
sep = os.sep
anysep = [posixpath.sep, ntpath.sep]
pathsep = os.pathsep


def as_posix(path):
    return pathlib.Path(path).as_posix()


def as_dirpath(path):
    return path if path[-1] == sep else path + sep


def as_canonpath(path):
    if os.path.isabs(path):
        path = os.path.join("root", os.path.relpath(path, "/"))
    return path.replace("..", "__")


def is_relative_to(pathname, rootdir):
    try:
        pathlib.Path(pathname).relative_to(pathlib.Path(rootdir))
        return True
    except ValueError:
        return False


def userhome():
    return os.path.expanduser("~")


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def mkdir(path):
    try:
        os.mkdir(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


mkdtemp = tempfile.mkdtemp


def exists(path):
    return os.path.exists(path)


def identical_files(path1, path2):
    stat1 = os.stat(path1)
    stat2 = os.stat(path2)
    if stat1.st_size != stat2.st_size:
        return False
    with open(path1, "rb") as f1, open(path2, "rb") as f2:
        for data1, data2 in iter(lambda: (f1.read(0x10000), f2.read(0x10000)), (b'', b'')):
            if data1 != data2:
                return False
    return True


def rename(old, new):
    return os.rename(old, new)


def move(src, dst):
    return shutil.move(src, dst)


def onerror_warning(func, path, exc_info):
    from jolt import log
    if type(exc_info[1]) is OSError:
        msg = exc_info[1].strerror
    else:
        msg = "Reason unknown"
    if os.path.exists(path):
        log.warning("Could not remove file or directory: {} ({})", path, msg)


def rmtree(path, ignore_errors=False, onerror=None):
    def _onerror(func, path, exc_info):
        if os.path.isdir(path):
            try:
                os.rmdir(path)
            except Exception:
                pass
            else:
                return
        if not ignore_errors:
            _, exc, _ = exc_info
            raise exc

    shutil.rmtree(path, onerror=onerror or _onerror)


def unlink(path, ignore_errors=False, tree=False):
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            if tree:
                rmtree(path, ignore_errors=ignore_errors)
            else:
                os.rmdir(path)
        else:
            os.unlink(path)
    except Exception as e:
        if not ignore_errors:
            raise e


_symlinks = None


def has_symlinks():
    global _symlinks
    if _symlinks is None:
        if os.name != "nt" or (sys.getwindowsversion().major >= 10 and sys.version_info.major >= 3 and sys.version_info.minor >= 8):
            _symlinks = True
        else:
            _symlinks = False
    return _symlinks


def symlink(src, dest, *args, **kwargs):
    if os.name == "nt":
        # Try to use junctions first.
        try:
            import _winapi
            _winapi.CreateJunction(src, dest)
            return
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            # Ok, probably linking a file and not a directory
            # trying a regular symlink.
            try:
                os.symlink(src, dest, *args, **kwargs)
            except OSError as e:
                raise_error_if(
                    "symbolic link privilege not held" in str(e),
                    "Permission denied while attempting to create a symlink: {}\n"
                    "Please ensure the 'Create symbolic links' right is granted "
                    "to your user in the 'Local Security Policy'.", dest)
                raise e
    else:
        os.symlink(src, dest, *args, **kwargs)


def linkcopy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy(src, dst)


def _copy_symlink(src, dst, copyfn=None):
    if os.path.lexists(dst):
        unlink(dst, ignore_errors=True)
    if os.path.islink(src):
        return symlink(os.readlink(src), dst)
    return copyfn(src, dst)


def _copy2_symlink(src, dst, copyfn=None):
    if os.path.lexists(dst):
        unlink(dst, ignore_errors=True)
    if os.path.islink(src):
        symlink(os.readlink(src), dst)
        shutil.copystat(src, dst, follow_symlinks=False)
        return
    return copyfn(src, dst)


def copy(src, dst, symlinks=False, hardlink=False, ignore=None, metadata=True):
    dstdir = os.path.dirname(dst)
    if not os.path.isdir(dstdir):
        unlink(dstdir, ignore_errors=True)
        makedirs(dstdir)

    if hardlink:
        copyfn = linkcopy
    else:
        copyfn = shutil.copy2 if metadata else shutil.copy

    if symlinks:
        if metadata:
            copyfn = functools.partial(_copy2_symlink, copyfn=copyfn)
        else:
            copyfn = functools.partial(_copy_symlink, copyfn=copyfn)

    if symlinks and os.path.islink(src):
        return copyfn(src, dst)
    elif not os.path.isdir(src):
        return copyfn(src, dst)

    try:
        return shutil.copytree(
            src, dst,
            symlinks,
            dirs_exist_ok=True,
            copy_function=copyfn,
        )
    except TypeError:
        return shutil.copytree(
            src, dst,
            symlinks,
            copy_function=copyfn,
        )


def scandir(scanpath, filterfn=lambda path: path[0] != ".", relative=False):
    def relresult(path, fp):
        return os.path.relpath(os.path.join(path, fp), scanpath)

    def absresult(path, fp):
        return os.path.join(path, fp)

    resfn = relresult if relative else absresult
    return [resfn(path, f)
            for path, dirs, files in os.walk(scanpath)
            for f in files
            if filterfn(f)]
