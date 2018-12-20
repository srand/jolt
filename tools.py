import subprocess
import os
import threading
import sys
import filesystem as fs
import log
import threading
import termios
import utils
import glob
import multiprocessing
import shutil
import requests
import tarfile
import zipfile
import bz2file
from contextlib import contextmanager


def _run(cmd, cwd, env, *args, **kwargs):
    output = kwargs.get("output")
    output_on_error = kwargs.get("output_on_error")
    output = output if output is not None else True
    output = False if output_on_error else output
    p = subprocess.Popen(
        cmd,
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
                    line = line.decode(errors='ignore')
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
            data = f.read().decode()
        data = data.replace(search, replace)
        with open(path, "wb") as f:
            f.write(data.encode())
    except:
        assert False, "failed to replace string in file: {0}".format(path)


class _String(object):
    def __init__(self, s=None):
        self._str = s or ''

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        pass

    def __str__(self):
        return self._str

    def __get__(self):
        return self._str

    def __add__(self, s):
        return self._str + s

    def __iadd__(self, s):
        self._str += s
        return self

    def endswith(self, substr):
        return self._str.endswith(substr)

    def startswith(self, substr):
        return self._str.startswith(substr)


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

    @property
    def path(self):
        return self.get_path()

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
            self.tools.run("{0}/configure --prefix={1} {2}",
                           sourcedir, self.installdir,
                           self.tools.getenv("CONFIGURE_FLAGS"),
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
    """ A collection of useful tools """

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

    def append_file(self, filepath, content):
        """ Appends data at the end of a file """
        
        filepath = self.expand(filepath)
        filepath = fs.path.join(self.getcwd(), filepath)
        content = self.expand(content)
        with open(path, "ab") as f:
            f.write(content.encode())

    def archive(self, filepath, filename):
        """ Creates a compressed archive """
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
        """ Creates an AutoTools invokation helper """
        return _AutoTools(deps, self)

    def builddir(self, name="build", *args, **kwargs):
        """ Creates a build directory """
        if name not in self._builddir:
            dirname = self._cwd
            fs.makedirs(dirname)
            self._builddir[name] = fs.mkdtemp(prefix=name+"-", dir=dirname)
        return self._builddir[name]

    def chmod(self, filepath, mode):
        """ Changes permissions of files and directories """
        filepath = self.expand(filepath)
        filepath = fs.path.join(self.getcwd(), filepath)
        return os.chmod(filepath, mode)

    def cmake(self, deps=None):
        """ Creates a CMake invokation helper """
        return _CMake(deps, self)

    def copy(self, src, dest, symlinks=False):
        """ Copies file and directories """
        return fs.copy(
            fs.path.join(self.getcwd(), src),
            fs.path.join(self.getcwd(), dest),
            symlinks=symlinks)

    def cpu_count(self):
        """ Returns the number of CPUs on the host """
        return multiprocessing.cpu_count()

    @contextmanager
    def cwd(self, path, *args, **kwargs):
        """ Changes the current working directory """
        path = self.expand(path, *args, **kwargs)
        prev = self._cwd
        if path is not None:
            self._cwd = fs.path.join(self._cwd, path)
        try:
            assert fs.path.exists(self._cwd) and fs.path.isdir(self._cwd), \
                "failed to change directory to {0}" \
                .format(self._cwd)
            yield fs.path.normpath(self._cwd)
        finally:
            self._cwd = prev

    def download(self, url, filename, **kwargs):
        """ Downloads a file using HTTP(S) """
        url = self.expand(url)
        filename = self.expand(filename)
        filepath = fs.path.join(self.getcwd(), filename)
        try:
            response = requests.get(url, stream=True, **kwargs)
            name = fs.path.basename(filename)
            size = int(response.headers['content-length'])
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
        """ Sets variables in an environment context """
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
        """ Expands macros in a string """
        return self._task._get_expansion(string, *args, **kwargs) \
            if self._task is not None \
            else utils.expand(string, *args, **kwargs)

    def extract(self, filename, filepath, files=None):
        """ Extracts an archive """
        filename = self.expand(filename)
        filepath = self.expand(filepath)
        filename = fs.path.join(self.getcwd(), filename)
        filepath = fs.path.join(self.getcwd(), filepath)
        try:
            fs.makedirs(filepath)
            if filename.endswith(".zip"):
                with zipfile.ZipFile(filename, 'r') as zip:
                    if files:
                        zip.extract(files, filepath)
                    else:
                        zip.extractall(filepath)
            elif filename.endswith(".tar"):
                with tarfile.open(filename, 'r') as tar:
                    if files:
                        tar.extract(files, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.gz") or filename.endswith(".tgz"):
                with tarfile.open(filename, 'r:gz') as tar:
                    if files:
                        tar.extract(files, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.bz2"):
                # bz2file module for multistream support
                with bz2file.open(filename) as bz2:
                    with tarfile.open(fileobj=bz2) as tar:
                        if files:
                            tar.extract(files, filepath)
                        else:
                            tar.extractall(filepath)
            elif filename.endswith(".tar.xz"):
                with tarfile.open(filename, 'r:xz') as tar:
                    if files:
                        tar.extract(files, filepath)
                    else:
                        tar.extractall(filepath)
            else:
                assert False, "unknown filetype: {0}".format(fs.path.basename(filename))
        except Exception as e:
            log.exception()
            assert False, "failed to extract archive: {0}".format(filename)

    def file_size(self, filepath):
        """ Returns the size of a file """
        filepath = self.expand(filepath)
        filepath = fs.path.join(self.getcwd(), filepath)
        try:
            stat = os.stat(filepath)
        except:
            assert False, "file not found: {0}".format(filepath)
        else:
            return stat.st_size

    def getcwd(self):
        """ Returns the current working directory """
        return fs.path.normpath(self._cwd)

    def getenv(self, key, default=""):
        """ Returns an environment variable """
        return self._env.get(key, default)

    def glob(self, path, *args, **kwargs):
        """ Enumerates files and directories """
        path = self.expand(path, *args, **kwargs)
        files = utils.as_list(glob.glob(fs.path.join(self._cwd, path)))
        if not fs.path.isabs(path):
            files = [file[len(self.getcwd())+1:] for file in files]
        return files

    def map_consecutive(self, callable, iterable):
        """ Sequential map()"""
        return utils.map_consecutive(callable, iterable)

    def map_concurrent(self, callable, iterable, max_workers=None):
        """ Concurrent map()"""
        return utils.map_concurrent(callable, iterable, max_workers)

    def replace_in_file(self, path, search, replace):
        """ Replaces all occurrences of a substring in a file """
        path = self.expand(path)
        search = self.expand(search)
        replace = self.expand(replace)
        return _replace_in_file(fs.path.join(self._cwd, path), search, replace)

    def run(self, cmd, *args, **kwargs):
        """ Runs a command in a shell interpreter """
        cmd = self.expand(cmd, *args, **kwargs)
        stdi, stdo, stde = None, None, None
        try:
            stdi, stdo, stde = None, None, None
            try:
                stdi = termios.tcgetattr(sys.stdin.fileno())
                stdo = termios.tcgetattr(sys.stdout.fileno())
                stde = termios.tcgetattr(sys.stderr.fileno())
            except:
                pass
            return _run(cmd, self._cwd, self._env, *args, **kwargs)
        finally:
            if stdi:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, stdi)
            if stdo:
                termios.tcsetattr(sys.stdout.fileno(), termios.TCSANOW, stdo)
            if stde:
                termios.tcsetattr(sys.stderr.fileno(), termios.TCSANOW, stde)

    def setenv(self, key, value=None):
        """ Sets an environment variable """
        if value is None:
            try:
                del self._env[key]
            except:
                pass
        else:
            self._env[key] = self.expand(value)

    def symlink(self, src, dest):
        """ Creates a symbolic link """
        src = self.expand(src, *args, **kwargs)
        dst = self.expand(dst, *args, **kwargs)
        fs.symlink(src, dst)

    def tmpdir(self, name, *args, **kwargs):
        """ Creates a temporary directory """
        return _tmpdir(name, cwd=self._cwd)

    def unlink(self, path, *args, **kwargs):
        """Removes a file from disk"""
        cmd = self.expand(path, *args, **kwargs)
        return fs.unlink(fs.path.join(self._cwd, path))

    def upload(self, filename, url, auth=None, **kwargs):
        """ Uploads a file using HTTP """

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

    def write_file(self, filepath, content):
        """ Creates/overwrites a file on disk """
        filepath = self.expand(filepath)
        filepath = fs.path.join(self.getcwd(), filepath)
        content = self.expand(content)
        with open(filepath, "wb") as f:
            f.write(content.encode())
