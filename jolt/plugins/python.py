import os
import sys

from jolt import Task
from jolt import attributes
from jolt import filesystem as fs
from jolt.cache import ArtifactStringAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider
from jolt.error import raise_task_error_if


class PythonVariable(ArtifactStringAttribute):
    def __init__(self, artifact, name):
        super(PythonVariable, self).__init__(artifact, name)

    def apply(self, task, artifact):
        pass

    def unapply(self, task, artifact):
        pass


class PythonListVariable(PythonVariable):
    def __init__(self, artifact, name):
        super(PythonListVariable, self).__init__(artifact, name)

    def append(self, value):
        if self.get_value():
            self.set_value(self.get_value() + ":" + value)
        else:
            self.set_value(value)

    def items(self):
        value = self.get_value()
        return value.split(":") if value is not None else []


class PythonPathVariable(PythonListVariable):
    def __init__(self, artifact, name):
        super(PythonPathVariable, self).__init__(artifact, name)

    def append(self, value):
        if self.get_value():
            self.set_value(self.get_value() + ":" + value)
        else:
            self.set_value(value)

    def items(self):
        value = self.get_value()
        return value.split(":") if value is not None else []

    def apply(self, task, artifact):
        paths = [fs.path.join(artifact.path, path) for path in self.items()]
        sys.path.extend(paths)

    def unapply(self, task, artifact):
        paths = [fs.path.join(artifact.path, path) for path in self.items()]
        for path in paths:
            sys.path.remove(path)


class PythonDictVariable(PythonListVariable):
    def __init__(self, artifact, name):
        super(PythonDictVariable, self).__init__(artifact, name)

    def __setitem__(self, key, value=None):
        item = "{0}={1}".format(key, value) if value is not None else key
        self.append(item)


class Python(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(Python, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        if name.lower() == "path":
            return PythonPathVariable(self._artifact, "PATH")
        assert False, "No such python attribute: {0}".format(name)


@ArtifactAttributeSetProvider.Register
class PythonProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "python", Python(artifact))

    def parse(self, artifact, content):
        if "python" not in content:
            return
        for key, value in content["python"].items():
            setattr(artifact.python, key, value)

    def format(self, artifact, content):
        if "python" not in content:
            content["python"] = {}
        for key, value in artifact.python.items():
            content["python"][key] = str(value)

    def apply(self, task, artifact):
        artifact.python.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.python.unapply(task, artifact)


@attributes.system
@attributes.requires("requires_python")
class PythonEnv(Task):
    """
    Base class for Python virtual environment tasks.

    Builds a Python virtual environment and installs specified packages.

    The venv module from the Python standard library must be available in the
    Python installation used to run the task.
    """

    abstract = True
    """ This is an abstract base class that should be inherited by concrete tasks. """

    executable = "python3"
    """ Python executable to use for creating the virtual environment. """

    requirements = []
    """
    List of Python packages to install in the virtual environment.

    Each entry should be a string suitable for pip, e.g., "package==version".
    """

    def _verify_influence(self, deps, artifact, tools, sources=None):
        # No influence to verify
        return

    def relocate_scripts(self, artifact, tools, frompath, topath):
        bindir = "Scripts" if self.system == "windows" else "bin"

        with tools.cwd(artifact.path, bindir):
            for script in tools.glob("*"):
                if script.startswith("python"):
                    continue
                if os.path.isdir(tools.expand_path(script)):
                    continue
                tools.replace_in_file(script, frompath, topath)

        with tools.cwd(artifact.path):
            if not tools.exists("local/bin"):
                return
            with tools.cwd("local", "bin"):
                for script in tools.glob("*"):
                    tools.replace_in_file(script, frompath, topath)

    def publish(self, artifact, tools):
        # Create a parallel installation by copying a Python installation

        # First locate the Python executable to copy
        py_exe = tools.which(self.executable)
        raise_task_error_if(
            py_exe is None, self,
            f"Python executable '{self.executable}' not found in PATH.",
        )

        # Follow symlinks to get the real executable
        py_exe = fs.path.realpath(py_exe)

        # Determine the Python home directory
        py_home = fs.path.dirname(fs.path.dirname(py_exe))

        # Determine the Python version
        self.version_major = tools.run(
            [py_exe, "-c", "import sys; print(\"{{}}.{{}}\".format(sys.version_info[0], sys.version_info[1]))"],
            shell=False,
            output_on_error=True).strip()

        self.info("Python executable: {0}", py_exe)
        self.info("Python home: {0}", py_home)
        self.info("Python version: {0}", self.version_major)

        # Copy the Python installation to the artifact path
        with tools.cwd(py_home):
            artifact.collect(py_exe, "bin/python3")
            artifact.collect("lib/python3")
            artifact.collect("lib/python{version_major}")
            artifact.collect("lib/libpython{version_major}.*")

        # Create common symlinks
        if self.system != "windows":
            with tools.cwd(artifact.path, "bin"):
                tools.symlink("python3", "python")
                tools.symlink("python3", "python{version_major}")
            with tools.cwd(artifact.path, "lib", "python{version_major}"):
                tools.unlink("sitecustomize.py", ignore_errors=True)

        # Install required packages into the artifact using pip
        with tools.environ(PYTHONHOME=artifact.path):
            py_exe = fs.path.join(artifact.path, "bin", "python3")
            with tools.tmpdir() as tmp, tools.cwd(tmp):
                tools.write_file(
                    "requirements.txt",
                    "\n".join(self.requirements) + "\n"
                )

                pip_cmd = [
                    py_exe,
                    "-m",
                    "pip",
                    "--isolated",
                    "--no-cache-dir",
                    "install",
                    "-r",
                    "requirements.txt",
                    "--prefix", artifact.path,
                    "--break-system-packages",
                ]
                tools.run(pip_cmd, shell=False)

        artifact.environ.PATH.append("bin")
        artifact.environ.PATH.append("local/bin")
        artifact.strings.install_prefix = artifact.path

    def unpack(self, artifact, tools):
        # Relocate the virtual environment by adjusting script paths
        frompath = artifact.strings.install_prefix
        topath = artifact.final_path
        self.relocate_scripts(artifact, tools, frompath, topath)

        artifact.strings.install_prefix = artifact.final_path


def requires(python=True):
    """ Decorator to add Python requirements to a task. """

    import jolt.pkgs.cpython

    def decorate(cls):
        if python:
            cls = attributes.requires("requires_python")(cls)
            cls.requires_python = ["cpython"]

        return cls

    return decorate
