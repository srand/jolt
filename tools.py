import subprocess
import os
import filesystem as fs
import log
import threading


def run(cmd, *args, **kwargs):
    output = kwargs.get("output")
    output_on_error = kwargs.get("output_on_error")
    output = output if output is not None else True
    output = False if output_on_error else output

    p = subprocess.Popen(
        cmd.format(*args, **kwargs),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True)

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
                    line = line.rstrip("\r")
                    line = line.rstrip("\n")
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


class AutoTools(object):
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
            self.tools.run("{}/configure --prefix={}",
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
