import subprocess
import os
import threading
import sys
import threading
import termios
import glob
import multiprocessing
import shutil
import requests
import tarfile
import zipfile
import bz2file
from contextlib import contextmanager

from jolt import filesystem as fs
from jolt import log
from jolt import utils


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
                if self.output:
                    self.output("{0}", str(e))
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
    """ A collection of useful tools.

    Any {keyword} arguments, or macros, found in strings passed to
    tool functions are automatically expanded to the value of the
    associated task's parameters and properties. Relative paths are
    made absolute by prepending the current working directory.
    """

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

    def append_file(self, pathname, content):
        """ Appends data at the end of a file.

        Args:
            pathname (str): Path to file. The file must exist.
            content (str): Data to be appended at the end of the file.
        """

        pathname = self.expand_path(pathname)
        content = self.expand(content)
        with open(path, "ab") as f:
            f.write(content.encode())

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
            shutil.make_archive(basename, fmt, root_dir=pathname)
            return filename
        except Exception as e:
            assert False, "failed to archive directory: {0}".format(pathname)

    def autotools(self, deps=None):
        """ Creates an AutoTools invokation helper """
        return _AutoTools(deps, self)

    def builddir(self, name="build"):
        """ Creates a temporary build directory.

        The build directory will persist for the duration of a task's
        execution. It is automatically removed afterwards.

        Args:
            name (str): Name prefix for the directory. A unique
                autogenerated suffix will also be appended to the
                final name.

        Returns:
            Path to the created directory.
        """
        name = self.expand(name)

        if name not in self._builddir:
            dirname = self.getcwd()
            fs.makedirs(dirname)
            self._builddir[name] = fs.mkdtemp(prefix=name+"-", dir=dirname)

        return self._builddir[name]


    def chmod(self, pathname, mode):
        """ Changes permissions of files and directories.

        Args:
            pathname (str): Path to a file or directory to change
                permissions for.
            mode (int): Requested permission bits.
        """
        pathname = self.expand_path(pathname)
        return os.chmod(pathname, mode)

    def cmake(self, deps=None):
        """ Creates a CMake invokation helper """
        return _CMake(deps, self)

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

    @contextmanager
    def cwd(self, pathname, *args, **kwargs):
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
        path = self.expand_path(pathname, *args, **kwargs)
        prev = self._cwd
        try:
            assert fs.path.exists(self._cwd) and fs.path.isdir(self._cwd), \
                "failed to change directory to {0}" \
                .format(self._cwd)
            self._cwd = path
            yield fs.path.normpath(self._cwd)
        finally:
            self._cwd = prev

    def download(self, url, pathname, **kwargs):
        """ Downloads a file using HTTP.

        Args:
           url (str): URL to the file to be downloaded.
           pathname (str): Name/path of destination file.
           kwargs (optional): Addidional keyword arguments passed on
               directly ``requests.get()``.

        """
        url = self.expand(url)
        pathname = self.expand_path(pathname)
        try:
            response = requests.get(url, stream=True, **kwargs)
            name = fs.path.basename(pathname)
            size = int(response.headers['content-length'])
            with log.progress("Downloading {0}".format(name), size, "B") as pbar:
                with open(pathname, 'wb') as out_file:
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
        return self._task._get_expansion(string, *args, **kwargs) \
            if self._task is not None \
            else utils.expand(string, *args, **kwargs)

    def expand_path(self, pathname, *args, **kwargs):
        """ Expands keyword arguments(macros in a pathname format string.

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

        pathname = fs.path.join(self.getcwd(), pathname)
        return self.expand(pathname, *args, **kwargs)

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

    def file_size(self, pathname):
        """ Determines the size of a file.

        Args:
            pathname (str): Name/path of file for which the size is requested.

        Returns:
            int: The size of the file in bytes.
        """
        filepath = self.expand_path(pathname)
        try:
            stat = os.stat(pathname)
        except:
            assert False, "file not found: {0}".format(pathname)
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

    def glob(self, pathname):
        """ Enumerates files and directories.

        Args:
            pathname (str): A pathname pattern used to match files to be
                included in the returned list of files and directories.
                The pattern may contain simple shell-style
                wildcards such as '*' and '?'. Note: files starting with a
                dot are not matched by these wildcards.

        Returns:
            A list of file and directory pathnames. The pathnames are relative
            to the current working directory unless the ``pathname`` argument
            was absolute.

        Example:

            .. code-block:: python

                textfiles = tools.glob("*.txt")
        """
        path = self.expand_path(pathname)
        files = utils.as_list(glob.glob(path))
        if not fs.path.isabs(pathname):
            files = [file[len(self.getcwd())+1:] for file in files]
        return files

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
            with open(pathname) as f:
                data = f.read().decode()
            data = data.replace(search, replace)
            with open(pathname, "wb") as f:
                f.write(data.encode())
        except:
            assert False, "failed to replace string in file: {0}".format(path)

    def rmtree(self, pathname, *args, **kwargs):
        """Removes a directory tree from disk.

        Args:
            pathname (str): Path to the file or directory to be removed.
            ignore_errors (boolean, optional): Ignore files that can't be deleted.
                The default is ``False``.

        """
        cmd = self.expand_path(pathname, *args, **kwargs)
        return fs.rmtree(pathname, **kwargs)

    def run(self, cmd, *args, **kwargs):
        """ Runs a command in a shell interpreter.

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
            except:
                pass
        else:
            self._env[key] = self.expand(value)

    def symlink(self, src, dest):
        """ Creates a symbolic link.

        Args:
            src (str): Path to target file or directory.
            dest (str): Name/path of symbolic link.
        """
        src = self.expand_path(src, *args, **kwargs)
        dst = self.expand_path(dst, *args, **kwargs)
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
        cmd = self.expand_path(pathname, *args, **kwargs)
        return fs.unlink(pathname)

    def upload(self, pathname, url, auth=None, **kwargs):
        """ Uploads a file using HTTP (PUT).

        Args:
           pathname (str): Name/path of file to be uploaded.
           url (str): Destination URL.
           auth (requests.auth.AuthBase, optional): Authentication helper.
               See requests.auth for details.
           kwargs (optional): Addidional keyword arguments passed on
               directly to `~requests.put()`.

        """

        pathname = self.expand_path(pathname)
        try:
            name = fs.path.basename(pathname)
            size = self.file_size(pathname)
            with log.progress("Uploading " + name, size, "B") as pbar, \
                 open(pathname, 'rb') as fileobj:
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

    def write_file(self, pathname, content=None):
        """ Creates a file.

        Note:
            Existing files are overwritten.

        Args:
            pathname (str): Name/path of file to be created.
            content (str, optional): Data to be written to the file.
        """
        pathname = self.expand_path(pathname)
        content = self.expand(content) if content is not None else ''
        with open(pathname, "wb") as f:
            f.write(content.encode())
