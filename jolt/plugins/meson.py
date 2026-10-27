from jolt import Task, attributes


@attributes.common_metadata()
class Meson(Task):
    """ Base class for Meson-based build tasks. """

    abstract = True
    """ This is an abstract base class that should be inherited by concrete tasks. """

    incremental = True
    """ Keep build directories between builds, so that builds are incremental. """

    options = []
    """ Options passed to Meson, as ``option=value``. """

    srcdir = None
    """ Source directory. If not set, the working directory of the task is used. """

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


def requires(meson=True, ninja=True):
    """ Decorator to add Meson and Ninja requirements to a task. """

    import jolt.pkgs.meson
    import jolt.pkgs.ninja

    def decorate(cls):
        if meson:
            cls = attributes.requires("requires_meson")(cls)
            cls.requires_meson = ["meson"]
        if ninja:
            cls = attributes.requires("requires_ninja")(cls)
            cls.requires_ninja = ["ninja"]
        return cls

    return decorate
