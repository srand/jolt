import bz2
import copy
import gzip
import lzma
import subprocess
import os
import platform
import sys
import threading
if os.name != "nt":
    import termios
import glob
import multiprocessing
import shutil
import tarfile
import zipfile
import bz2file
import hashlib
from contextlib import contextmanager

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.runtime import Context


from jolt import cache
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt import config
from jolt.error import JoltCommandError
from jolt.error import raise_error_if
from jolt.error import raise_task_error, raise_task_error_if


def stdout_write(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def stderr_write(line):
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def _run(cmd, cwd, env, preexec_fn, *args, **kwargs):
    output = kwargs.get("output")
    output_on_error = kwargs.get("output_on_error")
    output_rstrip = kwargs.get("output_rstrip", True)
    output_stdio = kwargs.get("output_stdio", False)
    output = output if output is not None else True
    output = False if output_on_error else output
    shell = kwargs.get("shell", True)

    log.debug("Running: '{0}' (CWD: {1})", cmd, cwd)

    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
        cwd=cwd,
        env=env,
        preexec_fn=preexec_fn)

    class Reader(threading.Thread):
        def __init__(self, parent, stream, output=None, logbuf=None):
            super(Reader, self).__init__()
            self.output = output
            self.parent = parent
            self.stream = stream
            self.logbuf = logbuf if logbuf is not None else []
            self.start()

        def run(self):
            line = ""
            try:
                with log.map_thread(self, self.parent):
                    for line in iter(self.stream.readline, b''):
                        if output_rstrip:
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

    stdout_func = log.stdout if not output_stdio else stdout_write
    stderr_func = log.stderr if not output_stdio else stderr_write

    logbuf = []
    stdout = Reader(
        threading.current_thread(), p.stdout,
        output=stdout_func if output else None, logbuf=logbuf)
    stderr = Reader(
        threading.current_thread(), p.stderr,
        output=stderr_func if output else None, logbuf=logbuf)
    p.wait()
    stdout.join()
    stderr.join()

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
        raise JoltCommandError(
            "command failed: {0}".format(
                " ".join(cmd) if type(cmd) == list else cmd.format(*args, **kwargs)),
            stdoutbuf, stderrbuf, p.returncode)
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


class _tmpdir(object):
    def __init__(self, name, cwd=None):
        self._name = name
        self._path = None
        self._cwd = cwd or os.getcwd()

    def __enter__(self):
        try:
            dirname = self._cwd
            fs.makedirs(fs.path.join(dirname, fs.path.dirname(self._name)))
            self._path = fs.mkdtemp(prefix=self._name + "-", dir=dirname)
        except KeyboardInterrupt as e:
            raise e
        except Exception as e:
            raise e
        raise_error_if(not self._path, "failed to create temporary directory")
        return self

    def __exit__(self, type, value, tb):
        if self._path:
            fs.rmtree(self._path, ignore_errors=True)

    @property
    def path(self):
        return self.get_path()

    def get_path(self):
        return self._path


class _CMake(object):
    def __init__(self, deps, tools, incremental=False):
        self.deps = deps
        self.tools = tools
        self.builddir = self.tools.builddir(incremental=incremental)
        self.installdir = self.tools.builddir("install", incremental=incremental)

    def configure(self, sourcedir, *args, generator=None, **kwargs):
        sourcedir = self.tools.expand_path(sourcedir)

        extra_args = list(args)
        extra_args += ["-D{0}={1}".format(key, self.tools.expand(val))
                       for key, val in kwargs.items()]
        extra_args = " ".join(extra_args)

        with self.tools.cwd(self.builddir):
            self.tools.run(
                "cmake {0} -B {1} -DCMAKE_INSTALL_PREFIX={2} {3} {4}",
                sourcedir,
                self.builddir,
                self.installdir,
                utils.option("-G", generator),
                extra_args,
                output=True)

    def build(self, release=True, *args, **kwargs):
        threading_args = ''
        try:
            threading_args = ' -j {}'.format(kwargs.get("threads", self.tools.thread_count())) \
                if "--parallel" in self.tools.run("cmake --help-manual cmake 2>&1", output=False) \
                   else ''
        except Exception:
            pass

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
                           self.tools.getenv("CONFIGURE_FLAGS"),
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


class JinjaTaskContext(Context):
    """
    Helper context for Jinja templates.

    Attempts to resolves any missing keywords by looking up task class attributes.
    """
    def resolve_or_missing(self, key):
        if key != "task":
            task = self.get("task")
            if task and hasattr(task, key):
                return getattr(task, key)
        return super(JinjaTaskContext, self).resolve_or_missing(key)


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
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            fs.makedirs(dirname)
        with tarfile.open(filename, 'w|%s' % fmt) as tar:
            tar.add(rootdir, ".")
        return filename

    def archive(self, pathname, filename):
        """ Creates a (compressed) archive.

        The type of archive to create is determined by the filename extension.
        Supported formats are:

        - tar
        - tar.bz2
        - tar.gz
        - tar.xz
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
            if shutil.which("tar") and shutil.which("pigz"):
                self.run("tar -I pigz -cf {} -C {} .", filename, pathname)
                return filename
            fmt = "targz"
        elif filename.endswith(".tgz"):
            if shutil.which("tar") and shutil.which("pigz"):
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
            if self._task is not None and unique:
                meta_task = fs.path.join(dirname, ".task")
                if not fs.path.exists(meta_task) \
                   or self.read_file(meta_task) != self._task.qualified_name:
                    fs.rmtree(dirname, ignore_errors=True)
                    fs.makedirs(dirname)

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
            fs.makedirs(fs.path.dirname(dirname))
            self._builddir[name] = fs.mkdtemp(
                prefix=fs.path.basename(dirname) + "-",
                dir=fs.path.dirname(dirname))

        return self._builddir[name]

    @property
    def buildroot(self):
        """ Return the root path of all build directories """
        from jolt.loader import get_workspacedir
        return fs.path.normpath(fs.path.join(get_workspacedir(), "build"))

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

        return result[-1] if concat or type(filelist) == str else result

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
            if shutil.which("pigz"):
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

    def download(self, url, pathname, exceptions=True, **kwargs):
        """
        Downloads a file using HTTP.

        Throws a JoltError exception on failure.

        Args:
           url (str): URL to the file to be downloaded.
           pathname (str): Name/path of destination file.
           kwargs (optional): Addidional keyword arguments passed on
               directly ``requests.get()``.

        """

        url = self.expand(url)
        pathname = self.expand_path(pathname)
        try:
            from requests.api import get

            response = get(url, stream=True, **kwargs)
            raise_error_if(
                exceptions and response.status_code not in [200],
                f"Download from '{url}' failed with status '{response.status_code}'")

            name = fs.path.basename(pathname)
            size = int(response.headers.get('content-length', 0))
            with log.progress("Downloading {0}".format(name), size, "B") as pbar:
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
        """ Expands keyword arguments/macros in a format string.

        This function is identical to ``str.format()`` but it
        automatically collects keyword arguments from a task's parameters
        and properties.

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

        pathname = self.expand(pathname, *args, **kwargs)
        relpath = self.expand(relpath or self._task.joltdir, *args, **kwargs)
        pathname = fs.path.join(self.getcwd(), pathname)
        # Ensure to retain any trailing path separator which is used as
        # indicator of directory paths
        psep = fs.sep if pathname[-1] in fs.anysep else ""
        return fs.path.relpath(pathname, relpath) + psep

    def extract(self, filename, pathname, files=None):
        """ Extracts files in an archive.

        Supported formats are:

        - tar
        - tar.bz2
        - tar.gz
        - tar.xz
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
        try:
            fs.makedirs(filepath)
            if filename.endswith(".zip"):
                with ZipFile(filename, 'r') as zip:
                    zip.extractall(filepath, files)
            elif filename.endswith(".tar"):
                with tarfile.open(filename, 'r') as tar:
                    if files:
                        for file in files:
                            tar.extract(file, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.gz") or filename.endswith(".tgz"):
                if shutil.which("tar") and shutil.which("pigz"):
                    self.run("tar -I pigz -xf {} -C {} {}", filename, filepath,
                             " ".join(files) if files else "")
                    return
                with tarfile.open(filename, 'r:gz') as tar:
                    if files:
                        for file in files:
                            tar.extract(file, filepath)
                    else:
                        tar.extractall(filepath)
            elif filename.endswith(".tar.bz2"):
                # bz2file module for multistream support
                with bz2file.open(filename) as bz2:
                    with tarfile.open(fileobj=bz2) as tar:
                        if files:
                            for file in files:
                                tar.extract(file, filepath)
                        else:
                            tar.extractall(filepath)
            elif filename.endswith(".tar.xz"):
                with tarfile.open(filename, 'r:xz') as tar:
                    if files:
                        for file in files:
                            tar.extract(file, filepath)
                    else:
                        tar.extractall(filepath)
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

    def getenv(self, key, default=""):
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
        return files

    def mkdir(self, pathname, recursively=True):
        """ Create directory. """

        pathname = self.expand_path(pathname)
        if recursively:
            fs.makedirs(pathname)
        else:
            fs.mkdir(pathname)

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

    def render(self, template, **kwargs):
        """ Render a Jinja template string.

        Args:
            template (str): Jinja template string.
            kwargs (dict): Keywords made available to the template context.
               Task attributes are automatically available.

        Returns:
            str: Renderered template data.

        """
        env = Environment(
            loader=FileSystemLoader(self.getcwd()),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True)
        env.context_class = JinjaTaskContext
        tmpl = env.from_string(template)
        return tmpl.render(task=self._task, tools=self, **kwargs)

    def render_file(self, template, **kwargs):
        """ Render a Jinja template file.

        Args:
            template (str): Filesystem path to template file.
            kwargs (dict): Keywords made available to the template context.
               Task attributes are automatically available.

        Returns:
            str: Renderered template data.

        """
        env = Environment(
            loader=FileSystemLoader(self.getcwd()),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True)
        env.context_class = JinjaTaskContext
        tmpl = env.get_template(self.expand(template))
        return tmpl.render(task=self._task, tools=self, **kwargs)

    def replace_in_file(self, pathname, search, replace):
        """ Replaces all occurrences of a substring in a file.

        Args:
            pathname (str): Name/path of file to modify.
            search (str): Substring to be replaced.
            replace (str): Replacement substring.

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
            data = data.replace(search.encode(), replace.encode())
            with open(pathname, "wb") as f:
                f.write(data)
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            raise_task_error(self._task, "failed to replace string in file '{0}'", pathname)

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

        Example:

            .. code-block:: python

                target = Parameter(default="all")
                verbose = "yes"

                def run(self, deps, tools):
                    tools.run("make {target} VERBOSE={verbose} JOBS={0}", tools.cpu_count())

        """
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
            if self._run_prefix:
                if type(cmd) == list:
                    cmd = self._run_prefix + cmd
                else:
                    cmd = " ".join(self._run_prefix) + " " + cmd
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
        if type(cmdprefix) == str:
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

        suffix = utils.canonical(artifact.get_task().short_qualified_name)

        if reflect:
            sandbox_name = "sandbox-reflect-" + suffix
        else:
            sandbox_name = "sandbox-" + suffix

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
                srcpath = fs.path.normpath(fs.path.join(artifact.get_task().joltdir, relsrcpath))
                dstpath = fs.path.normpath(fs.path.join(path, reldstpath))
                if fs.path.isdir(dstpath):
                    files = fs.scandir(srcpath)
                    for file in files:
                        relfile = file[len(srcpath) + 1:]
                        self.symlink(file, fs.path.join(dstpath, relfile))
                else:
                    self.symlink(srcpath, dstpath)

                # Restore missing srcfiles if they resided in a build directory
                if srcpath.startswith(artifact.get_task().tools.buildroot) and \
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

    def tmpdir(self, name):
        """ Creates a temporary directory.

        The directory is only valid within a context and it is removed
        immediately upon leaving the context.

        Args:
            name (str): Name prefix for the directory. A unique
                autogenerated suffix will also be appended to the
                final name.

        Example:

            .. code-block:: python

                with tools.tmpdir("temp") as tmp, tools.cwd(tmp.path):
                    tools.write_file("tempfile", "tempdata")

        """
        return _tmpdir(name, cwd=self._cwd)

    def unlink(self, pathname, *args, **kwargs):
        """Removes a file from disk.

        To remove directories, use :func:`~jolt.Tools.rmtree`.

        Args:
            pathname (str): Path to the file to be removed.

        """
        pathname = self.expand_path(pathname, *args, **kwargs)
        return fs.unlink(pathname)

    @contextmanager
    def chroot(self, chroot, *args, **kwargs):
        """
        Experimental: Use chroot as root filesystem when running commands.

        Mounts the specified chroot as the root filesystem in a new mount namespace,
        which is used in calls to Tools.run().

        Requires a Linux host and the 'unshare' utility program.

        Example:

            .. code-block:: python

              with tools.choot("path/to/rootfs"):
                  tools.run("ls")

        """
        raise_error_if(platform.system() != "Linux", "Tools.chroot() is only supported on Linux")

        chroot = self.expand_path(chroot, *args, **kwargs)
        raise_task_error_if(
            not fs.path.exists(chroot) or not fs.path.isdir(chroot),
            self._task, "failed to change root to '{0}'", chroot)

        mount_dev = kwargs.get("mount_dev", True)
        mount_etc = kwargs.get("mount_etc", True)
        mount_home = kwargs.get("mount_home", False)
        mount_proc = kwargs.get("mount_proc", True)
        mount_joltdir = kwargs.get("mount_joltdir", True)
        mount_cachedir = kwargs.get("mount_cachedir", True)
        mount_builddir = kwargs.get("mount_builddir", True)

        overlaydir = self.builddir("overlay")
        overlayrootdir = fs.path.join(overlaydir, "root")
        with self.cwd(overlaydir):
            self.mkdir("root")
            self.mkdir("work")
            self.mkdir("uppr")
        overlayopts = f"upperdir={overlaydir}/uppr,workdir={overlaydir}/work,lowerdir={chroot}"
        chrootoverlay = overlayrootdir

        def unshare_chroot():
            Tools._unshare()

            from ctypes import CDLL, c_char_p
            libc = CDLL("libc.so.6")

            MS_BIND = 4096
            MS_REC = 16384

            def mount_overlay():
                libc.mount(
                    c_char_p("overlay".encode("utf-8")),
                    c_char_p(chrootoverlay.encode("utf-8")),
                    c_char_p("overlay".encode("utf-8")),
                    0,
                    c_char_p(overlayopts.encode("utf-8"))) == 0

            def mount_bind(path):
                if os.path.isdir(path):
                    os.makedirs(chrootoverlay + path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(chrootoverlay + path), exist_ok=True)
                    with open(chrootoverlay + path, "a"):
                        pass
                assert libc.mount(
                    c_char_p(path.encode("utf-8")),
                    c_char_p((chrootoverlay + path).encode("utf-8")),
                    None,
                    MS_BIND | MS_REC,
                    None) == 0

            mount_overlay()
            if mount_dev:
                mount_bind("/dev")
            if mount_etc:
                mount_bind("/etc/group")
                mount_bind("/etc/hostname")
                mount_bind("/etc/resolv.conf")
                mount_bind("/etc/passwd")
            if mount_proc:
                mount_bind("/proc")
            if mount_home:
                mount_bind("/home")
            if mount_joltdir and self._task:
                mount_bind(self._task.joltdir)
            if mount_cachedir:
                mount_bind(config.get_cachedir())
            if mount_builddir:
                mount_bind(self.buildroot)

            os.chroot(chrootoverlay)
            os.chdir(self.getcwd())

        def catcher():
            try:
                unshare_chroot()
            except Exception as e:
                import traceback
                with open("/tmp/exception", "w") as f:
                    f.write(traceback.format_exc())
                raise e

        old_chroot = self._chroot
        old_preexec_fn = self._preexec_fn
        self._chroot = chroot
        self._preexec_fn = unshare_chroot
        try:
            yield self._chroot
        finally:
            self._chroot = old_chroot
            self._preexec_fn = old_preexec_fn

    @staticmethod
    def _unshare():
        from ctypes import CDLL
        libc = CDLL("libc.so.6")

        CLONE_NEWNS = 0x00020000
        CLONE_NEWUSER = 0x10000000

        uid = os.getuid()
        gid = os.getgid()

        assert libc.unshare(CLONE_NEWNS | CLONE_NEWUSER) == 0

        def map_ids(filename, ids):
            with open(filename, 'w') as file_:
                idmap = ""
                for new_id, old_id, count in ids:
                    idmap += f"{new_id} {old_id} {count}\n"
                file_.write(idmap)

        def map_uids(uids):
            return map_ids("/proc/self/uid_map", uids)

        def map_gids(uids):
            with open("/proc/self/setgroups", "w") as f:
                f.write("deny")
            return map_ids("/proc/self/gid_map", uids)

        map_uids([(uid, uid, 1)])
        map_gids([(gid, gid, 1)])

    def upload(self, pathname, url, exceptions=True, auth=None, **kwargs):
        """
        Uploads a file using HTTP (PUT).

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
        name = fs.path.basename(pathname)
        size = self.file_size(pathname)
        with log.progress("Uploading " + name, size, "B") as pbar, open(pathname, 'rb') as fileobj:
            def read():
                data = fileobj.read(4096)
                pbar.update(len(data))
                return data
            from requests.api import put
            response = put(url, data=iter(read, b''), auth=auth, **kwargs)
            raise_error_if(
                exceptions and response.status_code not in [201, 204],
                f"Upload to '{url}' failed with status '{response.status_code}'")
        return response.status_code in [201, 204]

    def read_file(self, pathname, binary=False):
        """ Reads a file. """
        pathname = self.expand_path(pathname)
        with open(pathname, "rb" if binary else "r") as f:
            return f.read()

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
            path = fs.pathsep.join(
                [self._chroot + p for p in path.split(fs.pathsep)]) + fs.pathsep + path
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
