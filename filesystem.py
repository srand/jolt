import os
import errno
import shutil
import zipfile
import tempfile
import tarfile


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

def unlink(path):
    os.unlink(path)

def symlink(src, dest, *args, **kwargs):
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

make_archive = shutil.make_archive

def make_archive(file, path, remove=False):
    shutil.make_archive(file, "gztar", root_dir=path)
    if remove:
        rmtree(path)
    return get_archive(path)

def extract_archive(file, path, remove=False):
    name, ext = os.path.splitext(file)
    if not ext:
        ext = ".tar.gz"
        file += ext
    if ext == ".tar.gz":
        with tarfile.open(file, 'r:gz') as tar:
            makedirs(path)
            tar.extractall(path)
        if remove:
            os.unlink(file)
        return
    assert False, "unsupported file extension: {0}".format(ext)


def get_archive(path):
    return path + ".tar.gz"
