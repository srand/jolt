import os
import errno
import shutil
import tempfile


path = os.path
sep = os.sep
pathsep = os.pathsep


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

mkdtemp = tempfile.mkdtemp

def exists(path):
    return os.path.exists(path)

def rename(old, new):
    return os.rename(old, new)

def move(src, dst):
    return shutil.move(src, dst)

def rmtree(path, ignore_errors=False):
    shutil.rmtree(path, ignore_errors)

def unlink(path, ignore_errors=False):
    try:
        os.unlink(path)
    except:
        if not ignore_errors:
            raise

def symlink(src, dest, *args, **kwargs):
    if os.name == "nt":
        import ntfsutils.junction
        ntfsutils.junction.create(src, dest)
    else:
        os.symlink(src, dest, *args, **kwargs)

def copytree(src, dst, symlinks=False, ignore=None):
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
            else:
                shutil.copy2(srcname, dstname)
            # XXX What about devices, sockets etc.?
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error as err:
            errors.extend(err.args[0])
    try:
        shutil.copystat(src, dst)
    except WindowsError:
        # can't copy file access times on Windows
        pass
    except OSError as why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise Exception(errors)

def copy(src, dest, symlinks=False):
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
        copytree(src, dest, symlinks=symlinks)
    else:
        shutil.copy2(src, dest)


def scandir(scanpath):
    return [os.path.join(path, f)
            for path, dirs, files in os.walk(scanpath)
            for f in files]


def get_archive(path):
    return path + ".tar.gz"
