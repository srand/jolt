import sys

from jolt import Task
from jolt import filesystem as fs
from jolt.cache import ArtifactStringAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider


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


class PythonEnv(Task):
    """
    Base class for Python virtual environment tasks.

    Builds a Python virtual environment and installs specified packages.

    The venv module from the Python standard library must be available in the
    Python installation used to run the task.
    """

    abstract = True
    """ This is an abstract base class that should be inherited by concrete tasks. """

    requirements = []
    """
    List of Python packages to install in the virtual environment.

    Each entry should be a string suitable for pip, e.g., "package==version".
    """

    def run(self, deps, tools):
        self.installdir = tools.builddir("python-env")

        import venv
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(self.installdir)

        with tools.tmpdir() as tmp, tools.cwd(tmp):
            tools.write_file(
                "requirements.txt",
                "\n".join(self.requirements) + "\n"
            )
            pip_executable = fs.path.join(self.installdir, "bin", "pip")
            tools.run([pip_executable, "install", "-r", "requirements.txt"], shell=False)

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            # Collect installed files
            artifact.collect("*", symlinks=True)

        artifact.environ.PATH.append("bin")
        artifact.strings.install_prefix = self.installdir
        self.unpack(artifact, tools)

    def unpack(self, artifact, tools):
        with tools.cwd(artifact.path):
            # Adjust paths in pyvenv.cfg
            tools.replace_in_file("pyvenv.cfg", artifact.strings.install_prefix, artifact.final_path)

        with tools.cwd(artifact.path, "bin"):
            # Adjust paths in scripts
            for script in tools.glob("*"):
                # Ignore python executables
                if script.startswith("python"):
                    continue
                tools.replace_in_file(script, artifact.strings.install_prefix, artifact.final_path)

        artifact.strings.install_prefix = artifact.final_path
