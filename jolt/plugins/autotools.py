from jolt import Task, attributes


@attributes.common_metadata()
class Autotools(Task):
    """ Base class for Autotools-based build tasks. """

    abstract = True
    """ This is an abstract base class that should be inherited by concrete tasks. """

    incremental = True
    """
    Whether to use incremental builds.
    If True, the build directories are preserved between runs.
    """

    options = []
    """
    Additional options to pass to the `./configure` script.
    """

    srcdir = None
    """
    Source directory for the Autotools project.

    If None, defaults to the task work directory (joltdir).
    """

    def clean(self, tools):
        at = tools.autotools(incremental=self.incremental)
        at.clean()

    def run(self, deps, tools):
        self.deps = deps
        options = tools.expand(self.options)
        at = tools.autotools(deps, incremental=self.incremental)
        at.configure(self.srcdir or self.joltdir, *options)
        at.build()
        at.install()

    def publish(self, artifact, tools):
        at = tools.autotools(incremental=self.incremental)
        at.publish(artifact)
