from jolt import attributes, Task


@attributes.common_metadata()
class Rust(Task):
    """ Base class for Rust-based build tasks. """

    abstract = True

    srcdir = None
    """
    Source directory for the Rust project.

    If None, defaults to the task work directory (joltdir).
    """

    def run(self, deps, tools):
        self.builddir = tools.builddir(incremental=True)
        self.installdir = tools.builddir("install")
        with tools.cwd(self.srcdir or self.joltdir):
            tools.run("cargo install --path . --target-dir={builddir} --root={installdir}")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
