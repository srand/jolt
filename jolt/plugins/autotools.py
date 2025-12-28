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


def requires(autoconf=True, automake=True, libtool=True):
    """ Decorator to add Autotools requirements to a task. """

    import jolt.pkgs.autoconf
    import jolt.pkgs.automake
    import jolt.pkgs.libtool

    def decorate(cls):
        if autoconf:
            cls = attributes.requires("requires_autoconf")(cls)
            cls.requires_autoconf = ["autoconf"]
        if automake:
            cls = attributes.requires("requires_automake")(cls)
            cls.requires_automake = ["automake"]
        if libtool:
            cls = attributes.requires("requires_libtool")(cls)
            cls.requires_libtool = ["libtool"]

        return cls

    return decorate
