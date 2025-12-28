from jolt import attributes, Parameter
from jolt.pkgs import help2man, texinfo
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_help2man")
@attributes.requires("requires_texinfo")
@autotools.requires(libtool=False)
class Libtool(autotools.Autotools):
    name = "libtool"
    version = Parameter("2.6.0", help="Libtool version.")

    requires_git = ["git:url=git://git.git.savannah.gnu.org/libtool.git,rev=v{version}"]
    requires_help2man = ["help2man"]
    requires_texinfo = ["texinfo"]
    srcdir = "{git[libtool]}"

    def run(self, deps, tools):
        with tools.cwd("{git[libtool]}"):
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
            tools.replace_in_file(
                "lib/libltdl.la",
                artifact.strings.install_prefix,
                artifact.path)


TaskRegistry.get().add_task_class(Libtool)
