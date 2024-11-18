import bz2
import copy
import getpass
import gzip
import lzma
import subprocess
import os
import platform
import sys
import threading
import time
if os.name != "nt":
    import termios
import glob
import multiprocessing
import re
import shutil
import tarfile
import zipfile
import bz2file
import hashlib
import zstandard
from contextlib import contextmanager
from psutil import NoSuchProcess, Process
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateError
from jinja2.runtime import Context
from jinja2.utils import missing
from requests import Session
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse, urlunparse


from jolt import cache
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt import config
from jolt.error import JoltCommandError, JoltTimeoutError
from jolt.error import raise_error_if
from jolt.error import raise_task_error, raise_task_error_if


http_session = Session()


def stdout_write(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def stderr_write(line):
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


class Reader(threading.Thread):
    def __init__(self, parent, stream, output=None, logbuf=None, output_rstrip=True):
        super(Reader, self).__init__()
        self.output = output
        self.output_rstrip = output_rstrip
        self.parent = parent
        self.stream = stream
        self.logbuf = logbuf if logbuf is not None else []
        self.start()

    def run(self):
        line = ""
        try:
            with log.map_thread(self, self.parent):
                for line in iter(self.stream.readline, b''):
                    if self.output_rstrip:
                        line = line.rstrip()
                    line = line.decode(errors='ignore')
                    if self.output:
                        self.output(line)
                    self.logbuf.append((self, line))
        except Exception as e:
            if self.output:
                self.output("{0}", str(e))
                self.output(line)
            self.logbuf.append((self, line))


def _run(cmd, cwd, env, preexec_fn, *args, **kwargs):
    output = kwargs.get("output")
    output_on_error = kwargs.get("output_on_error")
    output_rstrip = kwargs.get("output_rstrip", True)
    output_stdio = kwargs.get("output_stdio", False)
    return_stderr = kwargs.get("return_stderr", False)
    output = output if output is not None else True
    output = False if output_on_error else output
    shell = kwargs.get("shell", True)
    timeout = kwargs.get("timeout", config.getint("jolt", "command_timeout", 0))
    timeout = timeout if type(timeout) is int and timeout > 0 else None

    log.debug("Running: '{0}' (CWD: {1})", cmd, cwd)
    timedout = False
    try:
        with utils.delayed_interrupt():
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=shell,
                cwd=cwd,
                env=env,
                preexec_fn=preexec_fn,
            )

            stdout_func = log.stdout if not output_stdio else stdout_write
            stderr_func = log.stderr if not output_stdio else stderr_write

            logbuf = []
            stdout = Reader(
                threading.current_thread(),
                p.stdout,
                output=stdout_func if output else None,
                logbuf=logbuf,
                output_rstrip=output_rstrip)
            stderr = Reader(
                threading.current_thread(),
                p.stderr,
                output=stderr_func if output else None,
                logbuf=logbuf,
                output_rstrip=output_rstrip)

        def terminate(pid):
            try:
                process = Process(pid)
                for chld in process.children(recursive=True):
                    chld.terminate()
                process.terminate()
            except NoSuchProcess:
                pass

        def kill(pid):
            try:
                process = Process(pid)
                for chld in process.children(recursive=True):
                    chld.kill()
                process.kill()
            except NoSuchProcess:
                pass

        deadline = time.time() + timeout if timeout is not None else None
        while True:
            timeout = None if deadline is None else max(0, deadline - time.time())
            try:
                p.wait(timeout=timeout)
                break
            except KeyboardInterrupt:
                continue

    except (subprocess.TimeoutExpired, JoltTimeoutError):
        timedout = True
        try:
            terminate(p.pid)
            p.wait(10)
        except subprocess.TimeoutExpired:
            kill(p.pid)
            p.wait()

    finally:
        stdout.join()
        stderr.join()
        p.stdin.close()
        p.stdout.close()
        p.stderr.close()

    if p.returncode != 0 and output_on_error:
        for reader, line in logbuf:
            if reader is stdout:
                log.stdout(line)
            else:
                log.stderr(line)

    stdoutbuf = []
    stderrbuf = []
    for reader, line in logbuf:
        if reader is stdout:
            stdoutbuf.append(line)
        else:
            stderrbuf.append(line)

    if p.returncode != 0:
        stderrbuf = [line for reader, line in logbuf if reader is stderr]
        if timedout:
            raise JoltTimeoutError(
                "Command timeout: {0}".format(
                    " ".join(cmd) if type(cmd) is list else cmd.format(*args, **kwargs)))
        else:
            raise JoltCommandError(
                "Command failed: {0}".format(
                    " ".join(cmd) if type(cmd) is list else cmd.format(*args, **kwargs)),
                stdoutbuf, stderrbuf, p.returncode)
    if return_stderr:
        return "\n".join(stdoutbuf) if output_rstrip else "".join(stdoutbuf), \
            "\n".join(stderrbuf) if output_rstrip else "".join(stderrbuf)
    return "\n".join(stdoutbuf) if output_rstrip else "".join(stdoutbuf)


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


class _CMake(object):
    def __init__(self, deps, tools, incremental=False):
        self.deps = deps
        self.tools = tools
        self.builddir = self.tools.builddir(incremental=incremental)
        self.installdir = self.tools.builddir("install", incremental=False)

    def configure(self, sourcedir, *args, generator=None, **kwargs):
        sourcedir = self.tools.expand_path(sourcedir)

        extra_args = list(args)
        extra_args += ["-D{0}={1}".format(key, self.tools.expand(val))
                       for key, val in kwargs.items()]
        extra_args = " ".join(extra_args)

        with self.tools.cwd(self.builddir):
            self.tools.run(
                "cmake {0} -B{1} -DCMAKE_INSTALL_PREFIX={2} {3} {4}",
                sourcedir,
                self.builddir,
                self.installdir,
                utils.option("-G", generator),
                extra_args,
                output=True)

    def build(self, release=True, *args, **kwargs):
        threading_args = ' -j {}'.format(kwargs.get("threads", self.tools.thread_count()))
        with self.tools.cwd(self.builddir):
            release = "--config Release" if release else ""
            self.tools.run("cmake --build . {0}{1}", release, threading_args, output=True)

    def install(self, release=True, *args, **kwargs):
        with self.tools.cwd(self.builddir):
            release = "--config Release" if release else ""
            self.tools.run("cmake --build . --target install {0}", release, output=True)

    def publish(self, artifact, files='*', *args, **kwargs):
        with self.tools.cwd(self.installdir):
            artifact.collect(files, *args, **kwargs)


class _Meson(object):
    def __init__(self, deps, tools):
        self.deps = deps
        self.tools = tools
        self.builddir = self.tools.builddir()
        self.installdir = self.tools.builddir("install")

    def configure(self, sourcedir, *args, **kwargs):
        sourcedir = self.tools.expand_path(sourcedir)
        self.tools.run("meson --prefix=/ {0} {1}", sourcedir, self.builddir,
                       output=True)

    def build(self, *args, **kwargs):
        self.tools.run("ninja -C {0} ", self.builddir, output=True)

    def install(self, *args, **kwargs):
        self.tools.run("DESTDIR={0} ninja -C {1} install",
                       self.installdir, self.builddir,
                       output=True)

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
        sourcedir = self.tools.expand_path(sourcedir)
        prefix = kwargs.get("prefix", "/")

        if not fs.path.exists(fs.path.join(sourcedir, "configure")):
            with self.tools.cwd(sourcedir):
                self.tools.run("autoreconf -visf", output=True)

        with self.tools.cwd(self.builddir), self.tools.environ(DESTDIR=self.installdir):
            self.tools.run("{0}/configure --prefix={1} {2}",
                           sourcedir, prefix,
                           self.tools.getenv("CONFIGURE_FLAGS", ""),
                           output=True)

    def build(self, *args, **kwargs):
        with self.tools.cwd(self.builddir), self.tools.environ(DESTDIR=self.installdir):
            self.tools.run("make VERBOSE=yes Q= V=1 -j{0}",
                           self.tools.cpu_count(), output=True)

    def install(self, target="install", **kwargs):
        with self.tools.cwd(self.builddir), self.tools.environ(DESTDIR=self.installdir):
            self.tools.run("make {}", target, output=True)

    def publish(self, artifact, files='*', *args, **kwargs):
        with self.tools.cwd(self.installdir):
            artifact.collect(files, *args, **kwargs)


class ZipFile(zipfile.ZipFile):
    """ ZipFile customization that preserves file permissions. """

    def extract(self, member, path=None, pwd=None):
        out_path = super().extract(member, path, pwd)

        # Restore permissions, if UNIX permissions are available
        info = self.getinfo(member)
        attr = info.external_attr >> 16
        if attr != 0:
            os.chmod(out_path, attr)

        return out_path

    def extractall(self, path=None, members=None, pwd=None):
        if members is None:
            members = self.namelist()

        for member in members:
            self.extract(member, path, pwd)


class _Tarfile(tarfile.TarFile):
    """ Tarfile customzation that can extract without uid/gids """

    def __init__(self, *args, ignore_owner=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.__ignore_owner = ignore_owner

    def chown(self, *args, **kwargs):
        if self.__ignore_owner:
            return
        return super().chown(*args, **kwargs)


class JinjaTaskContext(Context):
    """
    Helper context for Jinja templates.

    Attempts to resolves any missing keywords by looking up task class attributes.
    """
    def resolve_or_missing(self, key):
        if key in self.vars:
            return self.vars[key]

        if key in self.parent:
            return self.parent[key]

        if key != "task":
            task = self.get("task")
            if task and hasattr(task, key):
                return getattr(task, key)

        return missing


class Namespace(object):
    def __init__(self, child=False):
        self.child = child

    def __enter__(self, *args):
        if not self.child:
            raise NamespaceException()
        return self

    def __exit__(self, type, exc, tb):
        if type == NamespaceException:
            return True
        return False


class NamespaceException(Exception):
    pass


def _subid(id, login):
    """ PIDs allowed to be mapped by a user. """
    with open(f"/etc/sub{id}") as subid:
        try:
            for line in subid:
                user, start, count = line.strip().split(":")
                if login == user:
                    return int(start), int(count)
        except Exception:
            pass
        return None, None


def _default_idmap(type, inner):
    """ Creates a default mapping of uid/gid between namespaces based
        on the requested inner uid/gid. As many ids as possible are mapped
        starting at 0. Requested ids are always mapped. """
    map = []
    outer = os.geteuid()
    start, count = _subid("uid", getpass.getuser())
    if start is None or count is None or count <= 0:
        return [(inner, outer, 1)]
    map.append((inner, outer, 1))
    if count <= 1:
        return map
    if inner == 0:
        map.append((inner + 1, start, count))
    else:
        map.append((0, start, min(inner - 1, count)))
        start += min(inner - 1, count) + 1
        count -= min(inner - 1, count) + 1
        if count > 0:
            map.append((inner + 1, start, count))
    return map


class Tools(object):
    """ A collection of useful tools.

    Any {keyword} arguments, or macros, found in strings passed to
    tool functions are automatically expanded to the value of the
    associated task's parameters and properties. Relative paths are
    made absolute by prepending the current working directory.
    """

    _builddir_lock = threading.RLock()

    def __init__(self, task=None, cwd=None, env=None):
        self._chroot = None
        self._chroot_prefix = []
        self._chroot_path = []
        self._deadline = None
        self._run_prefix = []
        self._preexec_fn = None
        self._cwd = fs.path.normpath(fs.path.join(config.get_workdir(), cwd or config.get_workdir()))
        self._env = copy.deepcopy(env or os.environ)
        self._task = task
        if task:
            self._env["JOLTDIR"] = task.joltdir
            self._env["JOLTBUILDDIR"] = self.buildroot
            self._env["JOLTCACHEDIR"] = config.get_cachedir()
        self._builddir = {}

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        for dir in self._builddir.values():
            fs.rmtree(dir, ignore_errors=True)
        return False

    def append_file(self, pathname, content, expand=True):
        """ Appends data at the end of a file.

        Args:
            pathname (str): Path to file. The file must exist.
            content (str): Data to be appended at the end of the file.
        """

        pathname = self.expand_path(pathname)
        if expand:
            content = self.expand(content)
        with open(pathname, "ab") as f:
            f.write(content.encode())

    def _make_zipfile(self, filename, fmt, rootdir):
        dirname = fs.path.dirname(filename)
        if not fs.path.exists(dirname):
            fs.makedirs(dirname)
        with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(rootdir):
                for name in sorted(dirnames):
                    path = os.path.normpath(os.path.join(dirpath, name))
                    zippath = os.path.relpath(path, rootdir)
                    zf.write(path, zippath)
                for name in filenames:
                    path = os.path.normpath(os.path.join(dirpath, name))
                    zippath = os.path.relpath(path, rootdir)
                    if os.path.isfile(path):
                        zf.write(path, zippath)
        return filename

    def _make_tarfile(self, filename, fmt, rootdir):
        self.mkdirname(filename)
        with tarfile.open(filename, 'w|%s' % fmt) as tar:
            tar.add(rootdir, ".")
        return filename

    def _make_tarzstd(self, filename, rootdir):
        self.mkdirname(filename)
        with open(filename, 'wb') as zstd_file:
            compressor = zstandard.ZstdCompressor(threads=self.thread_count())
            with compressor.stream_writer(zstd_file) as stream:
                with tarfile.open(mode="w|", fileobj=stream) as tar:
                    tar.add(rootdir, ".")
        return filename

    def _extract_tarzstd(self, filename, pathname, files=None):
        with open(filename, 'rb') as zstd_file:
            decompressor = zstandard.ZstdDecompressor()
            with decompressor.stream_reader(zstd_file) as stream:
                with tarfile.open(mode="r|", fileobj=stream) as tar:
                    if files:
                        for file in files:
                            tar.extract(file, pathname)
                    else:
                        tar.extractall(pathname)

    def archive(self, pathname, filename):
        """ Creates a (compressed) archive.

        The type of archive to create is determined by the filename extension.
        Supported formats are:

        - tar
        - tar.bz2
        - tar.gz
        - tar.xz
        - tar.zst
        - zip

        Args:
            pathname (str): Directory path of files to be archived.
            filename (str): Name/path of created archive.
        """
        filename = self.expand_path(filename)
        pathname = self.expand_path(pathname)

        fmt = None
        if filename.endswith(".zip"):
            fmt = "zip"
        elif filename.endswith(".tar"):
            fmt = "tar"
        elif filename.endswith(".tar.gz"):
            if self.which("tar") and self.which("pigz"):
                self.run("tar -I pigz -cf {} -C {} .", filename, pathname)
                return filename
            fmt = "targz"
        elif filename.endswith(".tar.zst"):
            return self._make_tarzstd(filename, rootdir=pathname)
        elif filename.endswith(".tgz"):
            if self.which("tar") and self.which("pigz"):
                self.run("tar -I pigz -cf {} -C {} .", filename, pathname)
                return filename
            fmt = "targz"
        elif filename.endswith(".tar.bz2"):
            fmt = "tarbz2"
        elif filename.endswith(".tar.xz"):
            fmt = "tarxz"
        raise_task_error_if(
            not fmt, self._task,
            "unknown archive type '{0}'", fs.path.basename(filename))
        try:
            if fmt == "zip":
                outfile = self._make_zipfile(filename, fmt, rootdir=pathname)
            else:
                outfile = self._make_tarfile(filename, fmt[3:], rootdir=pathname)
            if outfile != filename:
                shutil.move(outfile, filename)
            return filename
        except Exception:
            raise_task_error(self._task, "failed to create archive from directory '{0}'", pathname)

    def autotools(self, deps=None):
        """ Creates an AutoTools invokation helper """
        return _AutoTools(deps, self)

    @utils.locked(lock='_builddir_lock')
    def builddir(self, name=None, incremental=False, unique=True):
        """ Creates a temporary build directory.

        The build directory will persist for the duration of a task's
        execution. It is automatically removed afterwards.

        Args:
            name (str): Name prefix for the directory. A unique
                autogenerated suffix will also be appended to the
                final name.
            incremental (boolean): If false, the created directory is
                deleted upon completion of the task.

        Returns:
            Path to the created directory.
        """
        name = self.expand(name or "build")
        name = fs.path.join(self.buildroot, name)

        # Append task name
        if self._task is not None and unique:
            name += "-" + utils.canonical(self._task.short_qualified_name)

        dirname = fs.path.join(self.getcwd(), name)
        if incremental:
            dirname += "-inc"

        # Check if incremental build directories are disabled in the configuration
        if incremental not in ["always"] and not config.is_incremental_build():
            incremental = False

        if incremental:
            # Create a unique build directory for each task
            # and store the task name in a hidden file.
            if self._task is not None and unique:
                meta_task = fs.path.join(dirname, ".task")
                if not fs.path.exists(meta_task) \
                   or self.read_file(meta_task) != self._task.qualified_name:
                    fs.rmtree(dirname, ignore_errors=True)
                    fs.makedirs(dirname)

                # Remove the build directory if the task taint has changed (--force or --salt)
                if self._task.taint is not None:
                    meta = fs.path.join(dirname, ".taint")
                    if not fs.path.exists(meta) or self.read_file(meta) != str(self._task.taint):
                        fs.rmtree(dirname, ignore_errors=True)
                        fs.makedirs(dirname)
                        self.write_file(meta, str(self._task.taint))

                self.write_file(meta_task, self._task.qualified_name)
            else:
                fs.makedirs(dirname)
            return dirname

        if name not in self._builddir:
            fs.makedirs(dirname)
            self._builddir[name] = dirname

        return self._builddir[name]

    @property
    def buildroot(self):
        """ Return the root path of all build directories """
        from jolt.loader import JoltLoader
        return fs.path.normpath(JoltLoader.get().build_path)

    def checksum_file(self, filelist, concat=False, hashfn=hashlib.sha1, filterfn=None):
        """ Calculate a checksum of one or multiple files.

        Args:
            filelist (str,list): One or multiple files.
            concat (boolean): Concatenate files and return a single digest. If False,
                a list with one digest for each file is returned. Default: False.
            hashfn: The hash algorithm used. Any type which provides an update() and
                hexdigest() method is accepted. Default: hashlib.sha1
            filterfn: An optional data filter function. It is called repeatedly
                with each block of data read from files as its only argument.
                It should return the data to be included in the checksum.
                Default: None

        Returns:
            A list of checksum digests, or a single digest if files where concatenated.
        """
        files = [self.expand_path(fname) for fname in utils.as_list(filelist)]
        filterfn = filterfn or (lambda data: data)
        result = []
        checksum = hashfn()

        for fname in files:
            with open(fname, "rb") as f:
                for block in iter(lambda: f.read(0x10000), b''):
                    checksum.update(bytes(filterfn(block)))
                result.append(checksum.hexdigest())
            if not concat:
                checksum = hashfn()

        return result[-1] if concat or type(filelist) is str else result

    def chmod(self, pathname, mode):
        """ Changes permissions of files and directories.

        Args:
            pathname (str): Path to a file or directory to change
                permissions for.
            mode (int): Requested permission bits.
        """
        pathname = self.expand_path(pathname)
        return os.chmod(pathname, mode)

    def cmake(self, deps=None, incremental=False):
        """ Creates a CMake invokation helper """
        return _CMake(deps, self, incremental)

    def compress(self, src, dst):
        """ Compress a file.

        Supported formats are:

        - .bz2
        - .gz
        - .xz
        - .zst

        Args:
            src (str): Source file to be compressed.
            dst (str): Destination path for compressed file. The filename extension
                determines the compression algorithm used.
        """
        src = self.expand_path(src)
        dst = self.expand_path(dst)

        ext = dst.rsplit(".", 1)[-1]
        if ext == "bz2":
            with open(src, 'rb') as infp:
                with bz2.open(dst, 'wb') as outfp:
                    for block in iter(lambda: infp.read(0x10000), b''):
                        outfp.write(block)
        elif ext == "gz":
            if self.which("pigz"):
                return self.run("pigz -p {} {}", self.thread_count(), src)
            with open(src, 'rb') as infp:
                with gzip.open(dst, 'wb') as outfp:
                    for block in iter(lambda: infp.read(0x10000), b''):
                        outfp.write(block)
        elif ext == "xz":
            with open(src, 'rb') as infp:
                with lzma.open(dst, 'wb') as outfp:
                    for block in iter(lambda: infp.read(0x10000), b''):
                        outfp.write(block)
        elif ext == "zst":
            with open(src, 'rb') as infp:
                with open(dst, 'wb') as outfp:
                    compressor = zstandard.ZstdCompressor(threads=self.thread_count())
                    with compressor.stream_writer(outfp) as stream:
                        for block in iter(lambda: infp.read(0x10000), b''):
                            stream.write(block)

    def copy(self, src, dst, symlinks=False):
        """ Copies file and directories (recursively).

        The directory tree structure is retained when copying directories.

        Args:
            src (str): Path to a file or directory to be copied.
            dest (str): Destination path. If the string ends with a
                path separator a new directory will
                be created and source files/directories will be copied into
                the new directory. A destination without trailing path
                separator can be used to rename single files, one at a time.
            symlinks (boolean, optional): If True, symlinks are copied.
                The default is False, i.e. the symlink target is copied.
        """
        src = self.expand_path(src)
        dst = self.expand_path(dst)
        return fs.copy(src, dst, symlinks=symlinks)

    def cpu_count(self):
        """ The number of CPUs on the host.

        Returns:
            int: The number of CPUs on the host.
        """

        return multiprocessing.cpu_count()

    def thread_count(self):
        """ Number of threads to use for a task.

        Returns:
            int: number of threads to use.
        """
        threads = config.get("jolt", "threads", self.getenv("JOLT_THREADS", None))
        return int(threads) if threads else self.cpu_count()

    @contextmanager
    def cwd(self, pathname, *args):
        """ Change the current working directory to the specified path.

        This function doesn't change the working directory of the Jolt
        process. It only changes the working directory for tools within
        the tools object.

        Args:
            pathname (str): Path to change to.

        Example:

            .. code-block:: python

                with tools.cwd("subdir") as cwd:
                    print(cwd)
        """
        path = self.expand_path(fs.path.join(str(pathname), *args))
        prev = self._cwd
        try:
            raise_task_error_if(
                not fs.path.exists(path) or not fs.path.isdir(path),
                self._task,
                "failed to change directory to '{0}'", path)
            self._cwd = path
            yield fs.path.normpath(self._cwd)
        finally:
            self._cwd = prev

    def download(self, url, pathname, exceptions=True, auth=None, **kwargs):
        """
        Downloads a file using HTTP.

        Automatically expands any {keyword} arguments in the URL and pathname.

        Basic authentication is supported by including the credentials in the URL.
        Environment variables can be used to hide sensitive information. Specify
        the environment variable name in the URI as e.g.
        ``http://{environ[USER]}:{environ[PASS]}@host``.
        Alternatively, the auth parameter can be used to provide an authentication
        object that is passed to the requests.get() function.

        Throws a JoltError exception on failure.

        Args:
           url (str): URL to the file to be downloaded.
           pathname (str): Name/path of destination file.
           kwargs (optional): Addidional keyword arguments passed on
               directly ``requests.get()``.

        """

        url = self.expand(url)
        pathname = self.expand_path(pathname)

        url_parsed = urlparse(url)
        raise_task_error_if(
            not url_parsed.scheme or not url_parsed.netloc,
            self._task,
            "Invalid URL: '{}'", url)

        if auth is None and url_parsed.username and url_parsed.password:
            auth = HTTPBasicAuth(url_parsed.username, url_parsed.password)

        # Redact password from URL if present
        if url_parsed.password:
            url_parsed = url_parsed._replace(netloc=url_parsed.netloc.replace(url_parsed.password, "****"))

        url_cleaned = urlunparse(url_parsed)

        try:
            response = http_session.get(url, stream=True, auth=auth, **kwargs)
            raise_error_if(
                exceptions and response.status_code not in [200],
                f"Download from '{url_cleaned}' failed with status '{response.status_code}'")

            name = fs.path.basename(pathname)
            size = int(response.headers.get('content-length', 0))
            with log.progress("Downloading {0}".format(utils.shorten(name)), size, "B") as pbar:
                log.verbose("{} -> {}", url_cleaned, pathname)
                with open(pathname, 'wb') as out_file:
                    chunk_size = 4096
                    for data in response.iter_content(chunk_size=chunk_size):
                        out_file.write(data)
                        pbar.update(len(data))
                actual_size = self.file_size(pathname)
                raise_error_if(
                    size != 0 and size != actual_size,
                    f"Downloaded file was truncated to {actual_size}/{size} bytes: {name}")

            return response.status_code == 200
        except Exception as e:
            utils.call_and_catch(self.unlink, pathname)
            raise e

    @contextmanager
    def environ(self, **kwargs):
        """ Set/get environment variables.

        Only child processes spawned by the same tools object will be affected
        by the changed environment.

        The changed environment is only valid within a context and it is
        restored immediately upon leaving the context.

        Args:
            kwargs (optinal): A list of keyword arguments assigning values to
                environment variable.

        Example:

            .. code-block:: python

                with tools.environ(CC="clang"):
                    tools.run("make all")
        """
        restore = {key: value for key, value in self._env.items()}

        for key, value in kwargs.items():
            if value is not None:
                self._env[key] = self.expand(value)
            else:
                self._env.pop(key, None)

        try:
            yield self._env
        finally:
            self._env = restore

    def exists(self, pathname):
        """ Checks if a file or directory exists.

        Args:
            pathname (str): Path to file or directory.

        Returns:
            bool: True if the file or directory exists, False otherwise.
        """
        return fs.path.exists(self.expand_path(pathname))

    def expand(self, string, *args, **kwargs):
        """ Expands keyword arguments/macros in a format string.

        This function is identical to ``str.format()`` but it
        automatically collects keyword arguments from a task's parameters
        and properties.

        It also supports three additional conversion specifiers:

          - c: call method without arguments
          - l: convert string to lower case
          - u: convert string to upper case

        Args:
            string (str): The string to be expanded.
            args (str, optional): Additional positional values required
                by the format string.
            kwargs (str, optional): Additional keyword values required by
                the format string.

        Returns:
            str: Expanded string.

        Example:

            .. code-block:: python

                target = Parameter(default="all")
                verbose = "yes"

                def run(self, deps, tools):
                    print(tools.expand("make {target} VERBOSE={verbose}"))  # "make all VERBOSE=yes"

        """
        return self._task.expand(string, *args, **kwargs) \
            if self._task is not None \
            else utils.expand(string, *args, **kwargs)

    def expand_path(self, pathname, *args, **kwargs):
        """ Expands keyword arguments/macros in a pathname format string.

        This function is identical to ``str.format()`` but it
        automatically collects keyword arguments from a task's parameters
        and properties.

        The function also makes relative paths absolute by prepending the
        current working directory.

        Args:
            pathname (str): The pathname to be expanded.
            args (str, optional): Additional positional values required
                by the format pathname.
            kwargs (str, optional): Additional keyword values required by
                the format pathname.

        Return
            str: Expanded string.
        """

        if type(pathname) is list:
            return [self.expand_path(path) for path in pathname]

        path = fs.path.join(self.getcwd(), self.expand(pathname, *args, **kwargs))
        # Ensure to retain any trailing path separator which is used as
        # indicator of directory paths
        psep = fs.sep if path[-1] in fs.anysep else ""
        return fs.path.normpath(path) + psep

    def expand_relpath(self, pathname, relpath=None, *args, **kwargs):
        """ Expands keyword arguments/macros in a pathname format string.

        This function is identical to ``str.format()`` but it
        automatically collects keyword arguments from a task's parameters
        and properties.

        The function also makes absolute paths relative to a specified
        directory.

        Args:
            pathname (str): The pathname to be expanded.
            relpath (str, optional): Directory to which the returned path will be relative.
                If not provided, the ``joltdir`` attribute is used.
            args (str, optional): Additional positional values required
                by the format pathname.
            kwargs (str, optional): Additional keyword values required by
                the format pathname.

        Return
            str: Expanded string.
        """

        if not relpath:
            relpath = self._task.joltdir if self._task else self.getcwd()
        pathname = self.expand(pathname, *args, **kwargs)
        relpath = self.expand(relpath, *args, **kwargs)
        pathname = fs.path.join(self.getcwd(), pathname)
        # Ensure to retain any trailing path separator which is used as
        # indicator of directory paths
        psep = fs.sep if pathname[-1] in fs.anysep else ""
        return fs.path.relpath(pathname, relpath) + psep

    def extract(self, filename, pathname, files=None, ignore_owner=False):
        """ Extracts files in an archive.

        Supported formats are:

        - tar
        - tar.bz2
        - tar.gz
        - tar.xz
        - tar.zst
        - zip

        Args:
            filename (str): Name/path of archive file to be extracted.
            pathname (str): Destination path for extracted files.
            files (list, optional): List of files the be extracted
                from the archive. If not provided, all files are
                extracted.

        """
        filename = self.expand_path(filename)
        filepath = self.expand_path(pathname)
        ignore_owner_tar = "--no-same-owner" if ignore_owner else ""
        try:
            fs.makedirs(filepath)
            if filename.endswith(".zip"):
                with ZipFile(filename, 'r') as zip:
                    zip.extractall(filepath, files)
            elif filename.endswith(".tar"):
                with _Tarfile.open(filename, 'r', ignore_owner=ignore_owner) as tar:
                    if files:
                        for file in files:
                            tar.extract(file, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.gz") or filename.endswith(".tgz"):
                if self.which("tar") and self.which("pigz"):
                    self.run("tar -I pigz {} -xf {} -C {} {}",
                             ignore_owner_tar, filename, filepath,
                             " ".join(files) if files else "")
                    return
                with _Tarfile.open(filename, 'r:gz', ignore_owner=ignore_owner) as tar:
                    if files:
                        for file in files:
                            tar.extract(file, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.bz2"):
                # bz2file module for multistream support
                with bz2file.open(filename) as bz2:
                    with _Tarfile.open(fileobj=bz2, ignore_owner=ignore_owner) as tar:
                        if files:
                            for file in files:
                                tar.extract(file, filepath)
                        else:
                            tar.extractall(filepath)
            elif filename.endswith(".tar.xz"):
                with _Tarfile.open(filename, 'r:xz', ignore_owner=ignore_owner) as tar:
                    if files:
                        for file in files:
                            tar.extract(file, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.zst"):
                try:
                    self._extract_tarzstd(filename, filepath, files)
                except tarfile.StreamError as e:
                    raise_task_error(self._task, "failed to extract archive '{0}': {1}", filename, str(e))
            else:
                raise_task_error(self._task, "unknown archive type '{0}'", fs.path.basename(filename))
        except Exception:
            log.exception()
            raise_task_error(self._task, "failed to extract archive '{0}'", filename)

    def file_size(self, pathname):
        """ Determines the size of a file.

        Args:
            pathname (str): Name/path of file for which the size is requested.

        Returns:
            int: The size of the file in bytes.
        """
        pathname = self.expand_path(pathname)
        try:
            stat = os.stat(pathname)
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            raise_task_error(self._task, "file not found '{0}'", pathname)
        else:
            return stat.st_size

    def getcwd(self):
        """ Returns the current working directory. """
        return fs.path.normpath(self._cwd)

    def getenv(self, key, default=None):
        """ Returns the value of an environment variable.

        Only child processes spawned by the same tools object can see
        the environment variables and their values returned by this method.
        Don't assume the same variables are set in the Jolt process' environment.
        """
        return self._env.get(key, default)

    def glob(self, pathname, expand=False):
        """ Enumerates files and directories.

        Args:
            pathname (str): A pathname pattern used to match files to be
                included in the returned list of files and directories.
                The pattern may contain simple shell-style
                wildcards such as '*' and '?'. Note: files starting with a
                dot are not matched by these wildcards.
            expand (boolean): Expand matches to absolute paths. Default: false.

        Returns:
            A list of file and directory pathnames. The pathnames are relative
            to the current working directory unless the ``pathname`` argument
            was absolute.

        Example:

            .. code-block:: python

                textfiles = tools.glob("*.txt")
        """
        path = self.expand_path(pathname)
        files = utils.as_list(glob.glob(path, recursive=True))
        if expand:
            files = [self.expand_path(file) for file in files]
        elif not fs.path.isabs(pathname):
            files = [self.expand_relpath(file, self.getcwd()) for file in files]
        return list(sorted(files))

    def isdir(self, pathname):
        """ Determines if a path is a directory.

        Args:
            pathname (str): Path to a file or directory.

        Returns:
            boolean: True if the path is a directory, False otherwise.
        """
        pathname = self.expand_path(pathname)
        return fs.path.isdir(pathname)

    def mkdir(self, pathname, recursively=True):
        """ Create directory. """

        pathname = self.expand_path(pathname)
        if recursively:
            fs.makedirs(pathname)
        else:
            fs.mkdir(pathname)

    def mkdirname(self, pathname, recursively=True):
        """ Create parent directory. """

        pathname = self.expand_path(pathname)
        pathname = fs.path.dirname(pathname)
        if pathname:
            self.mkdir(pathname, recursively)

    def move(self, src, dst):
        """
        Move/rename file.

        Args:
            src (str): Path to a file or directory to be moved.
            dest (str): Destination path. If the destination is
                an existing directory, then src is moved inside
                that directory. If the destination already exists
                but is not a directory, it may be overwritten.
                If the destination is not on the same filesystem, the
                source file or directory is copied to the destination
                and then removed.
        """

        src = self.expand_path(src)
        dst = self.expand_path(dst)
        return shutil.move(src, dst)

    def map_consecutive(self, callable, iterable):
        """ Same as ``map()``. """
        return utils.map_consecutive(callable, iterable)

    def map_concurrent(self, callable, iterable, max_workers=None):
        """ Concurrent `~map()`.

        Args:
            callable: A callable object to be executed for each item in
                the collection.
            iterable: An iterable collection of items.
            max_workers (optional): The maximum number of worker threads
                allowed to be spawned when performing the work. The
                default is the value returned by
                :func:`jolt.Tools.cpu_count()`.

        Returns:
            list: List of return values.


        Example:

            .. code-block:: python

                def compile(self, srcfile):
                    objfile = srcfile + ".o"
                    tools.run("gcc -c {0} -o {1}", srcfile, objfile)
                    return objfile

                srcfiles = ["test.c", "main.c"]
                objfiles = tools.map_concurrent(compile, srcfiles)

        """
        return utils.map_concurrent(callable, iterable, max_workers)

    def meson(self, deps=None):
        """ Creates a Meson invokation helper """
        return _Meson(deps, self)

    @contextmanager
    def nixpkgs(self, nixfile=None, packages=None, pure=False, path=None, options=None):
        """
        Creates a Nix environment with the specified packages.

        Args:
            nixfile (str): Path to a Nix expression file.
            packages (list): List of Nix packages to include in environment.
            pure (boolean): Create a pure environment.
            path (list): List of Nix expression paths.
            options (dict): Nix configuration options.

        Example:

            .. code-block:: python

                def run(self, deps, tools):
                    with tools.nixpkgs(packages=["gcc13"]):
                        tools.run("gcc --version")

        """

        # Check if Nix is available
        raise_task_error_if(
            not self.which("nix-shell"),
            self._task,
            "Nix not available on this system")

        nixfile = self.expand_path(nixfile) if nixfile else ""
        pathflags = " ".join([f"-I {path}" for path in path or []])
        options = " ".join([f"--option {k} {v}" for k, v in (options or {}).items()])
        pureflag = "--pure" if pure else ""
        packages = "-p " + " ".join(packages) if packages else ""

        # Expand all placeholders
        options = self.expand(options)
        packages = self.expand(packages)
        pathflags = self.expand(pathflags)

        # Use cached-nix-shell is available
        nixshell = "cached-nix-shell" if self.which("cached-nix-shell") else "nix-shell"

        # Run nix-shell to stage packages and environment
        env = self.run(
            "{} {} {} {} --run 'env -0' {}",
            nixshell,
            pathflags,
            pureflag,
            packages,
            nixfile,
            output_on_error=True)
        env = env.strip().strip("\x00")
        env = dict(line.split("=", 1) for line in env.split('\x00'))

        # Add host path first to environment PATH
        host_path = env.get("HOST_PATH", None)
        if host_path:
            env["PATH"] = host_path + os.pathsep + env["PATH"]

        # Enter the environment
        old_env = self._env
        try:
            if pure:
                self._env = env
            else:
                self._env = copy.deepcopy(env)
                self._env.update(env)
            yield
        finally:
            self._env = old_env

    def render(self, template, **kwargs):
        """ Render a Jinja template string.

        Args:
            template (str): Jinja template string.
            kwargs (dict): Keywords made available to the template context.
               Task attributes are automatically available.

        Returns:
            str: Renderered template data.

        """
        try:
            env = Environment(
                loader=FileSystemLoader(self.getcwd()),
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True)
            env.context_class = JinjaTaskContext
            env.filters["prefix"] = utils.prefix
            env.filters["suffix"] = utils.suffix
            tmpl = env.from_string(template)
            return tmpl.render(task=self._task, tools=self, **kwargs)
        except TemplateError as e:
            log.debug("Template error: {}", template)
            raise_task_error(self._task, "Template error: {}", e)

    def render_file(self, template, **kwargs):
        """ Render a Jinja template file.

        Args:
            template (str): Filesystem path to template file.
            kwargs (dict): Keywords made available to the template context.
               Task attributes are automatically available.

        Returns:
            str: Renderered template data.

        """
        try:
            env = Environment(
                loader=FileSystemLoader(self.getcwd()),
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True)
            env.context_class = JinjaTaskContext
            tmpl = env.get_template(self.expand(template))
            return tmpl.render(task=self._task, tools=self, **kwargs)
        except TemplateError as e:
            log.debug("Template error: {}", template)
            raise_task_error(self._task, "Template error: {}", e)

    def replace_in_file(self, pathname, search, replace, regex=False):
        """ Replaces all occurrences of a substring in a file.

        Args:
            pathname (str): Name/path of file to modify.
            search (str): Substring to be replaced.
            replace (str): Replacement substring.
            regex (boolean): Interpret search parameter as
                a regular expression matching the string to
                be replaced.

        Example:

            .. code-block:: python

                version = Parameter(default="1.0")

                def run(self, deps, tools):
                    tools.replace_in_file("Makefile", "VERSION := 0.9", "VERSION := {version}")
        """
        pathname = self.expand_path(pathname)
        search = self.expand(search)
        replace = self.expand(replace)
        try:
            with open(pathname, "rb") as f:
                data = f.read()
            if regex:
                data = re.sub(search.encode(), replace.encode(), data)
            else:
                data = data.replace(search.encode(), replace.encode())
            with open(pathname, "wb") as f:
                f.write(data)
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            raise_task_error(self._task, "Failed to replace string in file '{0}'", pathname)

    def rmtree(self, pathname, *args, **kwargs):
        """Removes a directory tree from disk.

        Args:
            pathname (str): Path to the file or directory to be removed.
            ignore_errors (boolean, optional): Ignore files that can't be deleted.
                The default is ``False``.

        """
        pathname = self.expand_path(pathname, *args, **kwargs)
        return fs.rmtree(pathname, **kwargs)

    def rsync(self, srcpath, dstpath, *args, **kwargs):
        """ Synchronizes files from one directory to another.

        The function performs a smart copy of files from the
        ``srcpath`` directory to the ``dstpath`` directory in
        such a way that ``dstpath`` will mirror ``srcpath``.

        If ``dstpath`` is empty, the files are copied normally.

        If ``dstpath`` already contains a sub or superset of the
        files in ``srcpath``, files are either copied or deleted
        depending on their presence in the source directory. Common
        files are only copied if the file content differs, thereby
        retaining metadata (such as timestamps) of identical files
        already present in ``dstpath``.

        Args:
            srcpath (str): Path to source directory.
                The directory must exist.
            dstpath (str): Path to destination directory.

        """

        def _scandir(scanpath, filterfn=lambda path: path[0] != "."):
            def relresult(path, fp):
                return os.path.relpath(os.path.join(path, fp), scanpath)
            resfn = relresult
            result = []

            for path, dirs, files in os.walk(scanpath):
                for d in dirs:
                    if filterfn(d):
                        result.append((True, resfn(path, d)))
                for f in files:
                    if filterfn(f):
                        result.append((False, resfn(path, f)))

            return result

        srcpath = self.expand_path(srcpath, *args, **kwargs)
        dstpath = self.expand_path(dstpath, *args, **kwargs)
        srcfiles = set(_scandir(srcpath))
        dstfiles = set(_scandir(dstpath))
        added_files = list(srcfiles - dstfiles)
        deleted_files = list(dstfiles - srcfiles)
        common_files = srcfiles.intersection(dstfiles)

        # Remove files first, then directories
        for dir, fp in sorted(deleted_files, key=lambda n: (n[0], -len(n[1]))):
            dst = fs.path.join(dstpath, fp)
            if dir:
                fs.rmtree(dst)
            else:
                fs.unlink(dst)

        # Add new directories, then files
        for dir, fp in sorted(added_files, key=lambda n: (not n[0], n[1])):
            src = fs.path.join(srcpath, fp)
            dst = fs.path.join(dstpath, fp)
            if dir:
                fs.makedirs(dst)
            else:
                fs.copy(src, dst, metadata=False)

        # Refresh existing files
        for dir, fp in filter(lambda n: not n[0], common_files):
            src = fs.path.join(srcpath, fp)
            dst = fs.path.join(dstpath, fp)
            if not fs.identical_files(src, dst):
                fs.copy(src, dst, metadata=False)

    def run(self, cmd, *args, **kwargs):
        """
        Runs a command in a shell interpreter.

        These additional environment variables will be set when the command is run:

            - ``JOLTDIR`` - Set to :attr:`Task.joltdir <jolt.tasks.Task.joltdir>`
            - ``JOLTCACHEDIR`` - Set to the location of the Jolt cache

        A JoltCommandError exception is raised on failure.

        Args:
            cmd (str): Command format string.
            args: Positional arguments for the command format string.
            kwargs: Keyword arguments for the command format string.
            output (boolean, optional): By default, the executed command's
                output will be written to the console. Set to ``False`` to
                disable all output.
            output_on_error (boolean, optional): If ``True``, no output is
                written to the console unless the command fails.
                The default is ``False``.
            output_rstrip (boolean, optional): By default, output written
                to stdout is stripped from whitespace at the end of the
                string. This can be disabled by setting this argument to False.
            shell (boolean, optional): Use a shell to run the command.
                Default: True.
            timeout (int, optional): Timeout in seconds. The command will
                first be terminated if the timeout expires. If the command
                refuses to terminate, it will be killed after an additional
                10 seconds have passed. Default: None.

        Example:

            .. code-block:: python

                target = Parameter(default="all")
                verbose = "yes"

                def run(self, deps, tools):
                    tools.run("make {target} VERBOSE={verbose} JOBS={0}", tools.cpu_count())

        """
        kwargs.setdefault("shell", True)

        # Append command prefix before expanding string
        if self._chroot_prefix or self._run_prefix:
            if type(cmd) is list:
                cmd = self._chroot_prefix + self._run_prefix + cmd
            else:
                cmd = " ".join(self._chroot_prefix + self._run_prefix) + " " + cmd

        if self._deadline is not None:
            remaining = int(self._deadline - time.time() + 0.5)
            timeout = kwargs.get("timeout", remaining)
            kwargs["timeout"] = min(remaining, timeout)

        cmd = self.expand(cmd, *args, **kwargs)

        stdi, stdo, stde = None, None, None
        try:
            stdi, stdo, stde = None, None, None
            try:
                stdi = termios.tcgetattr(sys.stdin.fileno())
                stdo = termios.tcgetattr(sys.stdout.fileno())
                stde = termios.tcgetattr(sys.stderr.fileno())
            except KeyboardInterrupt as e:
                raise e
            except Exception:
                pass

            return _run(cmd, self._cwd, self._env, self._preexec_fn, *args, **kwargs)

        finally:
            if stdi:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, stdi)
            if stdo:
                termios.tcsetattr(sys.stdout.fileno(), termios.TCSANOW, stdo)
            if stde:
                termios.tcsetattr(sys.stderr.fileno(), termios.TCSANOW, stde)

    @contextmanager
    def runprefix(self, cmdprefix, *args, **kwargs):
        """
        Adds a command prefix to all commands executed by :func:`~run`.

        A new prefix is appended to any existing prefix.

        Args:
            cmdprefix (str, list): The command prefix. The string, or list,
                is expanded with :func:`~expand`.
            args (str, optional): Additional positional values passed to
                :func:`~expand`.
            kwargs (str, optional): Additional keyword values passed to
                :func:`~expand`.

        Example:

          .. code-block:: python

            with tools.runprefix("docker exec container"):
                tools.run("ls")


        The above code is equivalent to:

          .. code-block:: python

            tools.run("docker exec container ls")

        """
        cmdprefix = self.expand(cmdprefix, *args, **kwargs)
        if type(cmdprefix) is str:
            cmdprefix = cmdprefix.split()

        old_prefix = copy.copy(self._run_prefix)
        self._run_prefix += cmdprefix
        try:
            yield
        finally:
            self._run_prefix = old_prefix

    @utils.locked(lock='_builddir_lock')
    def sandbox(self, artifact, incremental=False, reflect=False):
        """ Creates a temporary build directory populated with the contents of an artifact.

        Files are copied using rsync.

        Args:
            artifact (cache.Artifact): A task artifact to be copied
                into the sandbox.
            incremental (boolean): If false, the created directory is
                deleted upon completion of the task.
            reflect (boolean): If true, a virtual sandbox is constructed
                from artifact metadata only. Files are not copied, but
                instead symlinks are created pointing at the origin of each
                file contained within the artifact. The sandbox reflects
                the artifact with a live view of the the current workspace.

        Returns:
            str: Path to the build directory..

        Example:

            .. code-block:: python

              def run(self, deps, tools):
                 sandbox = tools.sandbox(deps["boost"], incremental=True)
        """

        raise_error_if(
            type(artifact) is not cache.Artifact,
            "non-artifact passed as argument to Tools.sandbox()")

        suffix = utils.canonical(artifact.task.short_qualified_name)

        if reflect:
            sandbox_name = "sandboxes-reflected/" + suffix
        else:
            sandbox_name = "sandboxes/" + suffix

        path = self.builddir(sandbox_name, incremental=incremental, unique=False)
        if reflect:
            return self._sandbox_reflect(artifact, path)
        return self._sandbox_rsync(artifact, path)

    def _sandbox_validate(self, artifact, path):
        meta = fs.path.join(self.getcwd(), path, ".artifact")
        return meta if not fs.path.exists(meta) or self.read_file(meta) != artifact.path else None

    def _sandbox_rsync(self, artifact, path):
        meta = self._sandbox_validate(artifact, path)
        if meta:
            fs.unlink(meta, ignore_errors=True)
            self.rsync(artifact.path, path)
            self.write_file(meta, artifact.path)
        return path

    def _sandbox_reflect(self, artifact, path):
        meta = self._sandbox_validate(artifact, path)
        if meta:
            fs.rmtree(path)
            fs.makedirs(path)
            for relsrcpath, reldstpath in artifact.files.items():
                srcpath = fs.path.normpath(fs.path.join(artifact.task.joltdir, relsrcpath))
                dstpath = fs.path.normpath(fs.path.join(path, reldstpath))
                if dstpath != fs.path.realpath(dstpath):
                    log.debug("Cannot symlink '{} -> {}', parent directory already symlinked",
                              srcpath, dstpath)
                    continue
                if fs.path.isdir(dstpath):
                    files = fs.scandir(srcpath)
                    for file in files:
                        relfile = file[len(srcpath) + 1:]
                        self.symlink(file, fs.path.join(dstpath, relfile))
                else:
                    self.symlink(srcpath, dstpath)

                # Restore missing srcfiles if they resided in a build directory
                if srcpath.startswith(artifact.tools.buildroot) and \
                   not fs.path.exists(srcpath):
                    fs.copy(fs.path.join(artifact.path, reldstpath), srcpath, symlinks=True)
            self.write_file(meta, artifact.path)
        return path

    def setenv(self, key, value=None):
        """ Sets or unset an environment variable.

        Only child processes spawned by the same tools object can see
        the set environment variable and its value.
        Don't assume the same variable is set in the Jolt process' environment.

        Args:
            key (str): Name of variable to set.
            value (str): Value of the variable or ``None`` to unset it.

        """
        if value is None:
            try:
                del self._env[key]
            except KeyboardInterrupt as e:
                raise e
            except Exception:
                pass
        else:
            self._env[key] = self.expand(value)

    def symlink(self, src, dst, replace=True, relative=True):
        """ Creates a symbolic link.

        Args:
            src (str): Path to target file or directory.
            dst (str): Name/path of symbolic link.
            replace (boolean): Replace existing file or link. Default: false.
            relative (boolean): Create link using relative path to target.
                Default: false (absolute path).
        """
        src = self.expand_path(src) if not relative else self.expand(src)
        dst = self.expand_path(dst)
        dstdir = fs.path.dirname(dst) if dst[-1] != fs.sep else dst
        if replace and fs.path.lexists(dst):
            self.unlink(dst)
        if not fs.path.isdir(dstdir):
            fs.makedirs(dstdir)
        fs.symlink(src, dst)

    @contextmanager
    def timeout(self, seconds):
        """ Context manager to set a timeout for a block of code.

        A TimeoutError exception is raised if the block of code does not
        complete within the specified time.

        Args:
            seconds (int): Timeout in seconds.

        Example:

                .. code-block:: python

                    with tools.timeout(5):
                        tools.run("sleep 10")

        """
        if seconds is None:
            yield
            return

        with utils.timeout(seconds, JoltTimeoutError):
            old_deadline = self._deadline
            try:
                if old_deadline is None:
                    self._deadline = time.time() + seconds
                else:
                    self._deadline = min(old_deadline, time.time() + seconds)
                yield
            finally:
                self._deadline = old_deadline

    @contextmanager
    def tmpdir(self, name=None):
        """ Creates a temporary directory.

        The directory is only valid within a context and it is removed
        immediately upon leaving the context.

        Args:
            name (str): Name prefix for the directory. A unique
                autogenerated suffix will also be appended to the
                final name.

        Example:

            .. code-block:: python

                with tools.tmpdir() as tmp, tools.cwd(tmp):
                    tools.write_file("tempfile", "tempdata")

        """
        dirname = None
        try:
            self.mkdir(self.buildroot)
            dirname = fs.mkdtemp(prefix=(name or "tmpdir") + "-", dir=self.buildroot)
            yield fs.path.normpath(dirname)
        finally:
            if dirname:
                self.rmtree(dirname, ignore_errors=True)

    def unlink(self, pathname, *args, **kwargs):
        """Removes a file from disk.

        To remove directories, use :func:`~jolt.Tools.rmtree`.

        Args:
            pathname (str): Path to the file to be removed.

        """
        pathname = self.expand_path(pathname, *args, **kwargs)
        return fs.unlink(pathname, ignore_errors=kwargs.get("ignore_errors", False))

    @contextmanager
    @utils.deprecated
    def chroot(self, chroot, *args, path=None, **kwargs):
        """
        Experimental: Use chroot as root filesystem when running commands.

        Mounts the specified chroot as the root filesystem in a new Linux namespace,
        which is used when calling Tools.run().

        Requires a Linux host.

        Args:
            chroot (str, artifact): Path to rootfs directory, or an artifact
                with a 'rootfs' metadata path (artifact.paths.rootfs).
            path (list): List of directory paths within the chroot to add to
                the PATH environment variable, e.g. ["/usr/bin", "/bin"].
                By default, the current PATH is used also within the chroot.

        Example:

            .. code-block:: python

              with tools.choot("path/to/rootfs"):
                  tools.run("ls")

        """
        raise_error_if(platform.system() != "Linux", "Tools.chroot() is only supported on Linux")

        raise_task_error_if(
            not self.which("newuidmap") and not self.which("/usr/bin/newuidmap"), self._task,
            "No usable 'newuidmap' found in PATH")

        raise_task_error_if(
            not self.which("newgidmap") and not self.which("/usr/bin/newuidmap"), self._task,
            "No usable 'newgidmap' found in PATH")

        if type(chroot) is cache.Artifact:
            raise_task_error_if(
                not str(chroot.paths.rootfs), self._task,
                "No 'rootfs' path in artifact")
            chroot = chroot.paths.rootfs

        chroot = self.expand_path(chroot, *args, **kwargs)
        raise_task_error_if(
            not fs.path.exists(chroot) or not fs.path.isdir(chroot),
            self._task, "failed to change root to '{0}'", chroot)

        bind = []

        mount_dev = kwargs.get("mount_dev", True)
        mount_etc = kwargs.get("mount_etc", True)
        mount_home = kwargs.get("mount_home", False)
        mount_proc = kwargs.get("mount_proc", True)
        mount_joltdir = kwargs.get("mount_joltdir", True)
        mount_cachedir = kwargs.get("mount_cachedir", True)
        mount_builddir = kwargs.get("mount_builddir", True)
        mount = kwargs.get("mount", [])
        raise_task_error_if(
            type(mount) is not list,
            self._task, "Expected a list as mount argument to Tools.chroot()")
        mount = [self.expand(m) for m in mount]

        if mount_etc:
            bind.append("/etc/group")
            bind.append("/etc/hostname")
            bind.append("/etc/hosts")
            bind.append("/etc/passwd")
            bind.append("/etc/resolv.conf")

        if mount_home:
            bind.append("/home")

        if mount_joltdir and self._task:
            from jolt.loader import get_workspacedir
            bind.append(get_workspacedir())

        if mount_cachedir:
            bind.append(config.get_cachedir())

        if mount_builddir:
            bind.append(self.buildroot)

        if mount:
            for m in mount:
                bind.append(m)

        if mount_dev:
            bind.append("/dev")

        if mount_proc:
            bind.append("/proc")

        unshare = os.path.join(os.path.dirname(__file__), "chroot.py")

        old_chroot = self._chroot
        old_chroot_path = self._chroot_path
        old_chroot_prefix = self._chroot_prefix
        self._chroot = chroot

        if path:
            self._chroot_path = path
        else:
            self._chroot_path = self._env.get("PATH")
            self._chroot_path = self._chroot_path.split(fs.pathsep) if self._chroot_path else []

        try:
            with self.tmpdir("chroot") as bindroot:
                self._chroot_prefix = [
                    sys.executable,
                    unshare,
                    "-b",
                ] + bind + [
                    "-c",
                    chroot,
                    "-t",
                    bindroot,
                    "--shell={shell}",
                    "--",
                ]
                yield
        finally:
            self._chroot = old_chroot
            self._chroot_path = old_chroot_path
            self._chroot_prefix = old_chroot_prefix

    def _unshare(self, uidmap, gidmap):
        from ctypes import CDLL
        libc = CDLL("libc.so.6")

        CLONE_NEWNS = 0x00020000
        CLONE_NEWUSER = 0x10000000

        uidmap = [str(id) for map in uidmap for id in map]
        gidmap = [str(id) for map in gidmap for id in map]
        newuidmap = self.which("newuidmap")
        raise_task_error_if(
            not newuidmap, self._task,
            "No usable 'newuidmap' found in PATH")

        newgidmap = self.which("newgidmap")
        raise_task_error_if(
            not newgidmap, self._task,
            "No usable 'newgidmap' found in PATH")

        sem = multiprocessing.Semaphore(0)
        parent = os.getpid()
        child = os.fork()
        if child == 0:
            sem.acquire()
            pid = os.fork()
            if pid == 0:
                os.execve(newuidmap, ["newuidmap", str(parent)] + uidmap, {})
                os._exit(1)
            os.waitpid(pid, 0)
            os.execve(newgidmap, ["newgidmap", str(parent)] + gidmap, {})
            os._exit(1)
        assert libc.unshare(CLONE_NEWNS | CLONE_NEWUSER) == 0
        sem.release()
        os.waitpid(child, 0)

    @contextmanager
    def unshare(self, uid=0, gid=0, groups=[0], uidmap=None, gidmap=None):
        """
        Experimental: Create a Linux namespace.

        This method yields a new Linux namespace in which Python code may be executed.
        By default, the current user is mapped to root inside the namespace and all
        other users and groups are automatically mapped to the other user's configured
        subuids and subgids.

        The main use-case for namespaces is to fake the root user which may be useful
        in a number of situations:

          - to allow chroot() without beeing root
          - to allow mount() without beeing root
          - to preserve file ownership after tar file extraction
          - etc...

        Requires a Linux host.

        Note that the fork() system call is used. Changes made to variables
        will not persist after leaving the namespace.

        Args:
           uid (int): Requested uid inside the namespace. This is always mapped
               to the uid of the caller.
           gid (int): Requested gid inside the namespace. This is always mapped
               to the gid of the caller.
           uidmap (list): List of uids to map in the namespace. A list of tuples
               is expected: (inner uid, outer id, number of ids to map).
           gidmap (list): List of gids to map in the namespace. A list of tuples
               is expected: (inner gid, outer id, number of ids to map).

        Example:

            .. code-block:: python

              with tools.unshare() as ns, ns:
                  # Inside namespace
                  tools.run("whoami")  # "root"
              # Back outside namespace, namespace destructed

        """

        gidmap = gidmap or _default_idmap("gid", gid)
        uidmap = uidmap or _default_idmap("uid", uid)

        raise_task_error_if(
            not gidmap, self._task,
            "Invalid gid map: {}", gidmap)
        raise_task_error_if(
            not uidmap, self._task,
            "Invalid uid map: {}", uidmap)
        raise_task_error_if(
            not self.which("newuidmap"), self._task,
            "No usable 'newuidmap' found in PATH")
        raise_task_error_if(
            not self.which("newgidmap"), self._task,
            "No usable 'newgidmap' found in PATH")

        msgq = multiprocessing.JoinableQueue()
        pid = os.fork()
        if pid == 0:
            try:
                self._unshare(uidmap, gidmap)
                os.setuid(uid)
                os.setgid(gid)
                # if uid == 0 and gid == 0:
                #     os.setgroups(groups)
                yield Namespace(msgq)
            except Exception as exc:
                msgq.put(exc)
            else:
                msgq.put(None)
            msgq.join()
            os._exit(0)
        try:
            yield Namespace()
        except NamespaceException:
            pass
        exc = msgq.get()
        msgq.task_done()
        os.waitpid(pid, 0)
        if exc:
            raise exc

    def upload(self, pathname, url, exceptions=True, auth=None, **kwargs):
        """
        Uploads a file using HTTP (PUT).

        Automatically expands any {keyword} arguments in the URL and pathname.

        Basic authentication is supported by including the credentials in the URL.
        Environment variables can be used to hide sensitive information. Specify
        the environment variable name in the URI as e.g.
        ``http://{environ[USER]}:{environ[PASS]}@host``.
        Alternatively, the auth parameter can be used to provide an authentication
        object that is passed to the requests.get() function.

        Throws a JoltError exception on failure.

        Args:
           pathname (str): Name/path of file to be uploaded.
           url (str): Destination URL.
           auth (requests.auth.AuthBase, optional): Authentication helper.
               See requests.auth for details.
           kwargs (optional): Addidional keyword arguments passed on
               directly to `~requests.put()`.

        """
        pathname = self.expand_path(pathname)
        url = self.expand(url)
        name = fs.path.basename(pathname)
        size = self.file_size(pathname)

        url_parsed = urlparse(url)
        raise_task_error_if(
            not url_parsed.scheme or not url_parsed.netloc,
            self._task,
            "Invalid URL: '{}'", url)

        if auth is None and url_parsed.username and url_parsed.password:
            auth = HTTPBasicAuth(url_parsed.username, url_parsed.password)

        # Redact password from URL if present
        if url_parsed.password:
            url_parsed = url_parsed._replace(netloc=url_parsed.netloc.replace(url_parsed.password, "****"))

        url_cleaned = urlunparse(url_parsed)

        with log.progress("Uploading " + utils.shorten(name), size, "B") as pbar, \
             open(pathname, 'rb') as fileobj:
            log.verbose("{} -> {}", pathname, url_cleaned)

            def read():
                data = fileobj.read(4096)
                pbar.update(len(data))
                return data

            response = http_session.put(url, data=iter(read, b''), auth=auth, **kwargs)
            raise_error_if(
                exceptions and response.status_code not in [201, 204],
                f"Upload to '{url_cleaned}' failed with status '{response.status_code}'")
        return response.status_code in [201, 204]

    def read_file(self, pathname, binary=False):
        """ Reads a file. """
        pathname = self.expand_path(pathname)
        with open(pathname, "rb" if binary else "r") as f:
            return f.read()

    def read_depfile(self, pathname):
        """
        Reads a Make dependency file.

        Returns:
            dict: Dictionary of files and their dependencies.
        """
        pathname = self.expand_path(pathname)
        with open(pathname) as f:
            data = f.read()

        data = data.strip()
        data = data.replace("\\\n", "")
        data = data.splitlines()

        deps = {}

        for line in data:
            # Skip empty lines and comments
            if not line or line[0] == "#":
                continue

            parts = line.split(":", 1)
            raise_error_if(len(parts) != 2, "Depfile parse error: '{}'", line)
            outputs, inputs = parts[0], parts[1]
            outputs, inputs = outputs.strip(), inputs.strip()
            # Temporarily replace escaped spaces in names so that
            # the list of dependencies can be split.
            outputs, inputs = outputs.replace("\\ ", "\x00"), inputs.replace("\\ ", "\x00")

            for output in outputs.split():
                output = output.replace("\x00", " ")
                for input in inputs.split():
                    input = input.replace("\x00", " ")
                    if output not in deps:
                        deps[output] = []
                    deps[output].append(input)

        return deps

    def which(self, executable):
        """ Find executable in PATH.

        Args:
            executable (str): Name of executable to be found.

        Returns:
            str: Full path to the executable.
        """
        executable = self.expand(executable)
        path = self._env.get("PATH")

        if self._chroot:
            path = path.split(fs.pathsep) if path else []
            path = [os.path.join(self._chroot, p.lstrip(fs.sep)) for p in self._chroot_path] + path
            path = fs.pathsep.join(path)

        result = shutil.which(executable, path=path)
        if result and self._chroot and result.startswith(self._chroot):
            result = result[len(self._chroot):]
        return result

    def write_file(self, pathname, content=None, expand=True, **kwargs):
        """ Creates a file.

        Note:
            Existing files are overwritten.

        Args:
            pathname (str): Name/path of file to be created.
            content (str, optional): Data to be written to the file.
            expand (boolean, optional): Expand macros in file content.
               Default: True.
            **kwargs (dict, optional): Additional key value dictionary
                used in macro expansion.
        """
        pathname = self.expand_path(pathname)
        if content is None:
            content = ''
        if expand:
            content = self.expand(content, **kwargs)
        with open(pathname, "wb") as f:
            f.write(content.encode())

    @property
    def wsroot(self):
        """ Return the root path of all build directories """
        from jolt.loader import get_workspacedir
        return fs.path.normpath(get_workspacedir())
