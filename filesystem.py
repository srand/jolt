import os
import errno
import shutil
import zipfile


path = os.path
sep = os.sep
pathsep = os.pathsep


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def rename(old, new):
    return os.rename(old, new)

def rmtree(path):
    shutil.rmtree(path)

def unlink(path):
    os.unlink(path)
    
def copy(src, dest):
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
        shutil.copytree(src, dest)
    else:
        shutil.copyfile(src, dest)


def scandir(scanpath):
    return [os.path.join(path, f)
            for path, dirs, files in os.walk(scanpath)
            for f in files]

make_archive = shutil.make_archive

def make_archive(file, path, remove=False):
    shutil.make_archive(file, "zip", root_dir=path)
    if remove:
        rmtree(path)
    return get_archive(path)

def extract_archive(file, path, remove=False):
    name, ext = os.path.splitext(file)
    if not ext:
        ext = ".zip"
        file += ext
    if ext == ".zip":
        with zipfile.ZipFile(file) as zip:
            makedirs(path)
            zip.extractall(path)
        if remove:
            os.unlink(file)
        return
    assert False, "unsupported file extension: {}".format(ext)


def get_archive(path):
    return path + ".zip"
