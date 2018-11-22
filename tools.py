import subprocess
import os
import filesystem as fs
import log
import threading
import utils
import glob
import multiprocessing
import shutil
import requests
import tarfile
import zipfile
from contextlib import contextmanager


def _run(cmd, cwd, env, *args, **kwargs):
    output = kwargs.get("output")
    output_on_error = kwargs.get("output_on_error")
    output = output if output is not None else True
    output = False if output_on_error else output

    p = subprocess.Popen(
        cmd.format(*args, **kwargs),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        cwd=cwd,
        env=env)

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
                    line = line.decode()
                    if self.output:
                        self.output(line)
                    self.buffer.append(line)
            except Exception as e:
                self.output("{0}", str(e))
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

    assert p.returncode == 0, "command failed: {0}".format(cmd.format(*args, **kwargs))
    return "\n".join(stdout.buffer)


def _replace_in_file(path, search, replace):
    try:
        with open(path) as f:
            data = f.read()
        data = data.replace(search, replace)
        with open(path, "wb") as f:
            f.write(data)
    except:
        assert False, "failed to replace string in file: {0}".format(path)


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
        self._path = "build/{0}".format(task.qualified_name)
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
            self.tools.run("make VERBOSE=yes Q= V=1 -j{0}",
                           self.tools.cpu_count(), output=True)

    def install(self, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            self.tools.run("make install", output=True)

    def publish(self, artifact, files='*', *args, **kwargs):
        with self.tools.cwd(self.installdir):
            artifact.collect(files, *args, **kwargs)


class Tools(object):
    def __init__(self, task=None, cwd=None):
        self._cwd = cwd or os.getcwd()
        self._env = {key: value for key, value in os.environ.items()}
        self._task = task
        self._builddir = {}

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        for dir in self._builddir.values():
            fs.rmtree(dir)
        return False

    def archive(self, filepath, filename):
        filename = self.expand(filename)
        filepath = self.expand(filepath)
        filename = fs.path.join(self.getcwd(), filename)
        filepath = fs.path.join(self.getcwd(), filepath)
        fmt = None
        if filename.endswith(".zip"):
            fmt = "zip"
            basename = filename[:-4]
        elif filename.endswith(".tar"):
            fmt = "tar"
            basename = filename[:-4]
        elif filename.endswith(".tar.gz"):
            fmt = "gztar"
            basename = filename[:-7]
        elif filename.endswith(".tgz"):
            fmt = "gztar"
            basename = filename[:-4]
        elif filename.endswith(".tar.bz2"):
            fmt = "bztar"
            basename = filename[:-8]
        elif filename.endswith(".tar.xz"):
            fmt = "xztar"
            basename = filename[:-8]
        assert fmt, "unknown filetype '{0}': {1}".format(ext, fs.path.basename(filename))
        try:
            shutil.make_archive(basename, fmt, root_dir=filepath)
            return filename
        except Exception as e:
            assert False, "failed to archive directory: {0}".format(filepath)

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

    def cpu_count(self):
        return multiprocessing.cpu_count()

    @contextmanager
    def cwd(self, path, *args, **kwargs):
        path = self.expand(path, *args, **kwargs)
        prev = self._cwd
        self._cwd = fs.path.join(self._cwd, path)
        try:
            assert fs.path.exists(self._cwd) and fs.path.isdir(self._cwd), \
                "failed to change directory to {0}" \
                .format(self._cwd)
            yield self._cwd
        finally:
            self._cwd = prev

    def download(self, url, filename, **kwargs):
        url = self.expand(url)
        filename = self.expand(filename)
        filepath = fs.path.join(self.getcwd(), filename)
        try:
            response = requests.get(url, stream=True, **kwargs)
            name = fs.path.basename(filename)
            size = int(response.headers['content-length'])/1024
            with log.progress("Downloading {0}".format(name), size, "B") as pbar:
                with open(filepath, 'wb') as out_file:
                    chunk_size = 4096
                    for data in response.iter_content(chunk_size=chunk_size):
                        out_file.write(data)
                        pbar.update(len(data))
            return response.status_code == 200
        except:
            log.exception()
            return False

    @contextmanager
    def environ(self, **kwargs):
        for key, value in kwargs.items():
            kwargs[key] = self.expand(value)

        restore = {key: value for key, value in self._env.items()}
        self._env.update(kwargs)
        yield self._env
        for key, value in kwargs.items():
            if key not in restore:
                del self._env[key]
        self._env.update(restore)

    def expand(self, string, *args, **kwargs):
        return self._task._get_expansion(string, *args, **kwargs) \
            if self._task is not None \
            else utils.expand(string, *args, **kwargs)

    def extract(self, filename, filepath):
        filename = self.expand(filename)
        filepath = self.expand(filepath)
        filename = fs.path.join(self.getcwd(), filename)
        filepath = fs.path.join(self.getcwd(), filepath)
        try:
            fs.makedirs(filepath)
            if filename.endswith(".zip"):
                with zipfile.ZipFile(filename, 'r') as zip:
                    zip.extractall(filepath)
            elif filename.endswith(".tar"):
                with tarfile.open(filename, 'r') as tar:
                    tar.extractall(filepath)
            elif filename.endswith(".tar.gz") or filename.endswith(".tgz"):
                with tarfile.open(filename, 'r:gz') as tar:
                    tar.extractall(filepath)
            elif filename.endswith(".tar.bz2"):
                with tarfile.open(filename, 'r:bz2') as tar:
                    tar.extractall(filepath)
            elif filename.endswith(".tar.xz"):
                with tarfile.open(filename, 'r:xz') as tar:
                    tar.extractall(filepath)
            else:
                assert False, "unknown filetype: {0}".format(fs.path.basename(filename))
        except Exception as e:
            assert False, "failed to extract archive: {0}".format(filename)

    def file_size(self, filepath):
        filepath = self.expand(filepath)
        filepath = fs.path.join(self.getcwd(), filepath)
        try:
            stat = os.stat(filepath)
        except:
            assert False, "file not found: {0}".format(filepath)
        else:
            return stat.st_size

    def getcwd(self):
        return fs.path.normpath(self._cwd)

    def getenv(self, key):
        return self._env.get(key)

    def glob(self, path, *args, **kwargs):
        path = self.expand(path, *args, **kwargs)
        files = utils.as_list(glob.glob(fs.path.join(self._cwd, path)))
        if not fs.path.isabs(path):
            files = [file[len(self.getcwd())+1:] for file in files]
        return files

    def map_consecutive(self, callable, iterable):
        return utils.map_consecutive(callable, iterable)

    def map_concurrent(self, callable, iterable):
        return utils.map_concurrent(callable, iterable)

    def replace_in_file(self, path, search, replace):
        path = self.expand(path)
        search = self.expand(search)
        replace = self.expand(replace)
        return _replace_in_file(fs.path.join(self._cwd, path), search, replace)

    def run(self, cmd, *args, **kwargs):
        cmd = self.expand(cmd, *args, **kwargs)
        return _run(cmd, self._cwd, self._env, *args, **kwargs)

    def setenv(self, key, value=None):
        if value is None:
            try:
                del self._env[key]
            except:
                pass
        else:
            self._env[key] = self.expand(value)

    def tmpdir(self, name, *args, **kwargs):
        return _tmpdir(name, cwd=self._cwd)

    def unlink(self, path, *args, **kwargs):
        cmd = self.expand(path, *args, **kwargs)
        return fs.unlink(fs.path.join(self._cwd, path))

    def upload(self, filename, url, auth=None, **kwargs):
        filename = self.expand(filename)
        filename = fs.path.join(self.getcwd(), filename)
        try:
            name = fs.path.basename(filename)
            size = self.file_size(filename)
            with log.progress("Uploading " + name, size, "B") as pbar, \
                 open(filename, 'rb') as fileobj:
                def read():
                    data = fileobj.read(4096)
                    pbar.update(len(data))
                    return data
                response = requests.put(url, data=iter(read, b''), auth=auth, **kwargs)
                return response.status_code == 201
        except:
            log.exception()
            pass
        return False
