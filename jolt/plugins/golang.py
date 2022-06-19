from jolt import attributes as jolt_attributes
from jolt import filesystem as fs
from jolt import utils
from jolt import Task


from jolt.pkgs import golang


class attributes(object):
    @staticmethod
    def flags(attrib):
        """
        Decorates a task with an alternative ``flags`` attribute.

        The new attribute will be concatenated with the regular
        ``flags`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
        """
        return utils.concat_attributes("flags", attrib)


@attributes.flags("flags")
@jolt_attributes.requires("requires_go")
class Executable(Task):
    """ Builds a Go executable """

    abstract = True

    binary = "{canonical_name}"
    """ Name of the target binary (defaults to canonical task name) """

    flags = []
    """ List of build flags, passed directly to 'go build' """

    publishdir = "bin/"
    """ The artifact path where the executable is published. """

    requires_go = ["golang"]
    """
    Go toolchain requirement.

    Override to select another version or implementation.

    Example:

      .. code-block:: python

        requires_go = ["golang:version=1.16.4"]

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.binary = self.expand(self.binary)
        self.publishdir = self.expand(self.publishdir)
        golang  # Dummy reference

    def clean(self, tools):
        self.cachedir = tools.builddir("cache", incremental=True)
        tools.rmtree(self.cachedir, onerror=fs.onerror_warning)

    def run(self, deps, tools):
        self.cachedir = tools.builddir("cache", incremental=True)
        self.outdir = tools.builddir()
        self.info("Building {binary}")
        with tools.environ(GOCACHE=self.cachedir):
            tools.run("go build -o {outdir}/{binary} {}", " ".join(self._flags()))

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            artifact.collect("*", self.publishdir)
