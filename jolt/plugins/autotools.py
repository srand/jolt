from jolt import Task, attributes, utils


@attributes.common_metadata()
class Autotools(Task):
    """ Base class for Autotools-based build tasks. """

    abstract = True
    """ This is an abstract base class that should be inherited by concrete tasks. """

    incremental = True
    """ Keep build directories between builds, so that builds are incremental. """

    libtool = False
    """
    Publish libtool archives (.la).

    The archives refer to the installation prefix and to the archives of
    other libraries by absolute paths, which are invalid once the artifact
    is relocated. They are removed by default, since libraries are found
    without them. Keep them for projects that load modules with libltdl,
    and relocate them with :func:`jolt.plugins.libtool.relocate`.
    """

    options = []
    """ Options passed to the ``configure`` script. """

    install_threads = None
    """
    Number of parallel jobs used by ``make install``.

    If not set, make runs as many jobs as the build. Set to 1 for projects
    whose install scripts race when directories are created by parallel jobs.
    """

    srcdir = None
    """ Source directory. If not set, the working directory of the task is used. """

    def clean(self, tools):
        at = tools.autotools(incremental=self.incremental)
        at.clean()

    def run(self, deps, tools):
        self.deps = deps
        options = tools.expand(self._options())
        at = tools.autotools(deps, incremental=self.incremental)
        at.configure(self.srcdir or self.joltdir, *options)
        at.build()
        at.install(threads=self.install_threads)

    def publish(self, artifact, tools):
        at = tools.autotools(incremental=self.incremental)
        at.publish(artifact)
        if not self.libtool:
            with tools.cwd(artifact.path):
                for archive in tools.glob("**/*.la"):
                    tools.unlink(archive)

    def _options(self):
        return self.options


def options(attrib):
    """
    Decorates an Autotools task with an alternative ``options`` attribute.

    The new attribute will be concatenated with the regular
    ``options`` attribute.

    Args:
        attrib (str): Name of alternative attribute.
            Keywords are expanded.
    """
    return utils.concat_attributes("options", attrib)


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
