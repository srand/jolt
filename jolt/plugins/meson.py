from jolt import Task, attributes


@attributes.common_metadata()
class Meson(Task):
    """ Base class for Meson-based build tasks. """

    abstract = True
    """ This is an abstract base class that should be inherited by concrete tasks. """

    incremental = True
    """
    Whether to use incremental builds.
    If True, the build directories are preserved between runs.
    """

    options = []
    """
    Additional options to pass to the `meson` command.
    """

    srcdir = None
    """
    Source directory for the Meson project.

    If None, defaults to the task work directory (joltdir).
    """

    def clean(self, tools):
        at = tools.meson(incremental=self.incremental)
        at.clean()

    def run(self, deps, tools):
        self.deps = deps
        options = tools.expand(self.options)
        at = tools.meson(deps, incremental=self.incremental)
        at.configure(self.srcdir or self.joltdir, *options)
        at.build()
        at.install()

    def publish(self, artifact, tools):
        at = tools.meson(incremental=self.incremental)
        at.publish(artifact)
