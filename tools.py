import subprocess
import os
import filesystem as fs



def run(cmd, *args, **kwargs):
    try:
        return subprocess.check_output(cmd.format(*args, **kwargs), shell=True)
    except subprocess.CalledProcessError as e:
        assert e.returncode == 0, "command failed: {}".format(cmd)


class environ(object):
    def __init__(self, **kwargs):
        self._kwargs = kwargs

    def __enter__(self):
        self._restore = {key: value for key, value in os.environ.iteritems()}
        for key, value in self._kwargs.iteritems():
            os.environ[key] = value

    def __exit__(self, type, value, tb):
        for key, value in self._kwargs.iteritems():
            if key not in self._restore:
                del os.environ[key]
        os.environ.update(self._restore)


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


class CMake(object):
    def __init__(self, deps, tools):
        self.deps = deps
        self.tools = tools
        self.builddir = self.tools.builddir()
        self.installdir = self.tools.builddir("install")

    def configure(self, sourcedir, *args, **kwargs):
        sourcedir = sourcedir \
                    if fs.path.isabs(sourcedir) \
                    else fs.path.join(os.getcwd(), sourcedir)

        with self.tools.cwd(self.builddir):
            self.tools.run("cmake {} -DCMAKE_INSTALL_PREFIX={}",
                      sourcedir, self.installdir)

    def build(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("cmake --build .")

    def install(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("cmake --build . --target install")

    def publish(self, artifact, files='*', *args, **kwargs):
        with self.tools.cwd(self.installdir):
            artifact.collect(files, *args, **kwargs)
