import os
import errno
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

def rmtree(path, ignore_errors=False):
    shutil.rmtree(path, ignore_errors)

def unlink(path, ignore_errors=False):
    try:
        if os.path.isdir(path) and not os.path.islink(path):
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
        if os.name != "nt" or (
                sys.getwindowsversion().major >= 10 and \
                sys.version_info.major >= 3 and \
                sys.version_info.minor >= 8):
            _symlinks = True
        else:
            _symlinks = False
    return _symlinks

def symlink(src, dest, *args, **kwargs):
    if os.name == "nt":
        # Try to use junctions first.
        import ntfsutils.junction
        try:
            ntfsutils.junction.create(src, dest)
            return
        except KeyboardInterrupt as e:
            raise e
        except:
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

def copytree(src, dst, symlinks=False, ignore=None, metadata=True):
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    makedirs(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks, ignore)
            elif metadata:
                shutil.copy2(srcname, dstname)
            else:
                shutil.copy(srcname, dstname)
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        except Exception as err:
            errors.extend(err.args[0])
    try:
        if metadata:
            shutil.copystat(src, dst)
    except WindowsError:
        pass
    except OSError as why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise Exception(errors)

def copy(src, dest, symlinks=False, metadata=True):
    if not path.exists(dest):
        if dest[-1] == os.sep:
            makedirs(dest)
            dest = path.join(dest, path.basename(src))
        else:
            makedirs(path.dirname(dest))
    else:
        if dest[-1] == os.sep:
            dest = path.join(dest, path.basename(src))

    if path.isdir(src):
        copytree(src, dest, symlinks=symlinks, metadata=metadata)
    elif metadata:
        shutil.copy2(src, dest)
    else:
        shutil.copy(src, dest)


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


def get_archive(path):
    return path + ".tar.gz"

