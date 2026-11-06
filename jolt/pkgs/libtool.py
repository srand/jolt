from jolt import attributes, Parameter
from jolt.pkgs import compiler, help2man, texinfo
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_help2man")
@attributes.requires("requires_texinfo")
@autotools.requires(libtool=False)
@attributes.requires("requires_compiler")
class Libtool(autotools.Autotools):
    name = "libtool"
    version = Parameter("2.6.2", help="Libtool version.")

    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=git://git.git.savannah.gnu.org/libtool.git,rev=v{version}"]
    requires_help2man = ["help2man"]
    requires_texinfo = ["texinfo"]
    srcdir = "{git[libtool]}"
    gnulib_url = "https://github.com/coreutils/gnulib.git"
    """ Mirror of gnulib, the submodule that bootstrap otherwise clones from Savannah. """

    def run(self, deps, tools):
        with tools.cwd("{git[libtool]}"):
            # Bootstrap clones gnulib from Savannah, which often fails. It skips
            # the clone when the submodule is already checked out.
            tools.run("git config submodule.gnulib.url {gnulib_url}")
            tools.run("git submodule update --init --depth 1 gnulib")
            tools.run("./bootstrap")
        super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.LIBTOOL = "libtool"
        artifact.environ.ACLOCAL_PATH.append("share/libtool")

    def unpack(self, artifact, tools):
        with tools.cwd(artifact.path):
            tools.replace_in_file(
                "bin/libtoolize",
                artifact.strings.install_prefix,
                artifact.path)


TaskRegistry.get().add_task_class(Libtool)
