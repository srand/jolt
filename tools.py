import subprocess
import os
import filesystem as fs
import log
import threading
import utils
import glob
from contextlib import contextmanager


def _run(cmd, cwd, *args, **kwargs):
    output = kwargs.get("output")
    output_on_error = kwargs.get("output_on_error")
    output = output if output is not None else True
    output = False if output_on_error else output

    p = subprocess.Popen(
        cmd.format(*args, **kwargs),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        cwd=cwd)

    class Reader(threading.Thread):
        def __init__(self, stream, output=None):
            super(Reader, self).__init__()
            self.output = output
            self.stream = stream
            self.buffer = []
            self.start()

        def run(self):
            try:
                for line in iter(self.stream.readline, b''):
                    line = line.rstrip()
                    if self.output:
                        self.output(line)
                    self.buffer.append(line)
            except Exception as e:
                self.output("{}", str(e))
                if output:
                    self.output(line)
                self.buffer.append(line)

    stdout = Reader(p.stdout, output=log.stdout if output else None)
    stderr = Reader(p.stderr, output=log.stderr if output else None)
    p.wait()
    stdout.join()
    stderr.join()

    if p.returncode != 0 and output_on_error:
        log.stdout("STDOUT:")
        for line in stdout.buffer:
            log.stdout(line)
        log.stderr("STDERR:\r\n")
        for line in stderr.buffer:
            log.stderr(line)

    assert p.returncode == 0, "command failed: {}".format(cmd.format(*args, **kwargs))
    return "\n".join(stdout.buffer)


def replace_in_file(path, search, replace):
    try:
        with open(path) as f:
            data = f.read()
        data = data.replace(search, replace)
        with open(path, "wb") as f:
            f.write(data)
    except:
        assert False, "failed to replace string in file: {}".format(path)


class _environ(object):
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


class _tmpdir(object):
    def __init__(self, name, cwd=None):
        self._name = name
        self._path = None
        self._cwd = cwd or os.getcwd()

    def __enter__(self):
        try:
            dirname = self._cwd
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


class _CMake(object):
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
            self.tools.run("cmake {0} -DCMAKE_INSTALL_PREFIX={1}",
                           sourcedir, self.installdir,
                           output=True)

    def build(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("cmake --build .", output=True)

    def install(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("cmake --build . --target install", output=True)

    def publish(self, artifact, files='*', *args, **kwargs):
        with self.tools.cwd(self.installdir):
            artifact.collect(files, *args, **kwargs)


class _AutoTools(object):
    def __init__(self, deps, tools):
        self.deps = deps
        self.tools = tools
        self.builddir = self.tools.builddir()
        self.installdir = self.tools.builddir("install")

    def configure(self, sourcedir, *args, **kwargs):
        sourcedir = sourcedir \
                    if fs.path.isabs(sourcedir) \
                    else fs.path.join(os.getcwd(), sourcedir)

        if not fs.path.exists(fs.path.join(sourcedir, "configure")):
            with self.tools.cwd(sourcedir):
                self.tools.run("autoreconf -visf", output=True)

        with self.tools.cwd(self.builddir):
            self.tools.run("{0}/configure --prefix={1}",
                           sourcedir, self.installdir,
                           output=True)

    def build(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("make VERBOSE=yes Q= V=1", output=True)

    def install(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("make install", output=True)

    def publish(self, artifact, files='*', *args, **kwargs):
        with self.tools.cwd(self.installdir):
            artifact.collect(files, *args, **kwargs)


class Tools(object):
    def __init__(self, task=None, cwd=None):
        self._cwd = cwd or os.getcwd()
        self._task = task
        self._builddir = {}

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        for dir in self._builddir.values():
            fs.rmtree(dir)
        return False

    def _get_expansion(self, string, *args, **kwargs):
        return self._task._get_expansion(string, *args, **kwargs) \
            if self._task is not None \
            else utils.expand_macros(string, *args, **kwargs)

    def autotools(self, deps=None):
        return _AutoTools(deps, self)

    def builddir(self, name="build", *args, **kwargs):
        if name not in self._builddir:
            dirname = self._cwd
            fs.makedirs(dirname)
            self._builddir[name] = fs.mkdtemp(prefix=name+"-", dir=dirname)
        return self._builddir[name]

    def cmake(self, deps=None):
        return _CMake(deps, self)

    def copy(self, src, dest):
        return fs.copy(
            fs.path.join(self.getcwd(), src),
            fs.path.join(self.getcwd(), dest))

    @contextmanager
    def cwd(self, path, *args, **kwargs):
        path = self._get_expansion(path, *args, **kwargs)
        prev = self._cwd
        self._cwd = fs.path.join(self._cwd, path)
        try:
            assert fs.path.exists(self._cwd) and fs.path.isdir(self._cwd), \
                "failed to change directory to {}" \
                .format(self._cwd)
            yield self._cwd
        finally:
            self._cwd = prev

    def environ(self, **kwargs):
        for key, value in kwargs.iteritems():
            kwargs[key] = self._get_expansion(value)
        return _environ(**kwargs)

    def getcwd(self):
        return fs.path.normpath(self._cwd)

    def glob(self, path, *args, **kwargs):
        path = self._get_expansion(path, *args, **kwargs)
        files = utils.as_list(glob.glob(fs.path.join(self._cwd, path)))
        if not fs.path.isabs(path):
            files = [file[len(self.getcwd())+1:] for file in files]
        return files

    def map_consecutive(self, callable, iterable):
        return utils.map_consecutive(callable, iterable)

    def map_concurrent(self, callable, iterable):
        return utils.map_concurrent(callable, iterable)

    def replace_in_file(self, path, search, replace):
        path = self._get_expansion(path)
        search = self._get_expansion(search)
        replace = self._get_expansion(replace)
        return replace_in_file(fs.path.join(self._cwd, path), search, replace)

    def run(self, cmd, *args, **kwargs):
        cmd = self._get_expansion(cmd, *args, **kwargs)
        return _run(cmd, self._cwd, *args, **kwargs)

    def tmpdir(self, name, *args, **kwargs):
        return _tmpdir(name, cwd=self._cwd)

    def unlink(self, path, *args, **kwargs):
        cmd = self._get_expansion(path, *args, **kwargs)
        return fs.unlink(fs.path.join(self._cwd, path))
