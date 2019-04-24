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
        shutil.copytree(src, dest, symlinks=symlinks)
    else:
        shutil.copy2(src, dest)


def scandir(scanpath):
    return [os.path.join(path, f)
            for path, dirs, files in os.walk(scanpath)
            for f in files]


def get_archive(path):
    return path + ".tar.gz"
