import subprocess
import os
import filesystem as fs



def run(cmd, *args, **kwargs):
    try:
        return subprocess.check_output(cmd.format(*args, **kwargs), shell=True)
    except subprocess.CalledProcessError as e:
        assert e.returncode == 0, "command failed: {}".format(cmd)


class tmpdir(object):
    def __init__(self, name):
        self._name = name
        self._path = None

    def __enter__(self):
        try:
            dirname = os.getcwd()
            fs.makedirs(dirname)
            self._path = fs.mkdtemp(prefix=self._name + "-", dir=dirname)
        except:
            raise
        assert self._path, "failed to create temporary directory"
        return self

    def __exit__(self, type, value, tb):
        if self._path:
            fs.rmtree(self._path)

    def get_path(self):
        return self._path


class builddir(object):
    def __init__(self, task, remove=False):
        self._path = "build/{}".format(task.qualified_name)
        self._remove = remove

    def __enter__(self):
        try:
            fs.makedirs(self._path)
        except:
            raise
        assert self._path, "failed to create build directory"
        return self

    def __exit__(self, type, value, tb):
        if self._path and self._remove:
            fs.rmtree(self._path)

    def get_path(self):
        return self._path


class cwd(object):
    def __init__(self, path):
        self._path = path
        self._prev = os.getcwd()

    def __enter__(self):
        try:
            os.chdir(self._path)
        except:
            assert False, "failed to change directory to {}".format(self._path)
        return self

    def __exit__(self, type, value, tb):
        try:
            os.chdir(self._prev)
        except:
            pass
