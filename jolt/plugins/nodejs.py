from jolt import attributes as jolt_attributes
from jolt import utils
from jolt import Task


from jolt.pkgs import nodejs


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
@jolt_attributes.requires("requires_node")
class RunScript(Task):
    """ Runs an npm script """

    abstract = True

    flags = []
    """ List of build flags, passed directly to 'go build' """

    script = "build"
    """ Script name as defined in package.json """

    requires_node = ["nodejs"]
    """
    NodeJS requirement.

    Override to select another version or implementation.

    Example:

      .. code-block:: python

        requires_go = ["nodejs:version=16.15.1"]

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.script = self.expand(self.script)
        nodejs  # Dummy reference

    def run(self, deps, tools):
        self.info("Running {script}")
        tools.run("npm run {script} -- {}", " ".join(self._flags()))


class RunBuildScript(RunScript):
    """ Runs the npm build script and publishes the result """

    abstract = True

    script = "build"

    def run(self, deps, tools):
        self.outdir = tools.builddir()
        with tools.environ(BUILD_PATH=self.outdir):
            self.info("Installing deps")
            tools.run("npm ci --legacy-peer-deps")
            super().run(deps, tools)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            artifact.collect("*")
