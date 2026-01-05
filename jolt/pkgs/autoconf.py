from jolt import attributes, Parameter
from jolt.pkgs import help2man, texinfo
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_help2man")
@attributes.requires("requires_texinfo")
class Autoconf(autotools.Autotools):
    name = "autoconf"
    version = Parameter("2.72", help="Autoconf version.")
    requires_git = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/autoconf/autoconf-{version}.tar.gz"]
    requires_help2man = ["help2man"]
    requires_texinfo = ["texinfo"]
    srcdir = "{fetch[src]}/autoconf-{version}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        self.unpack(artifact, tools)

    def unpack(self, artifact, tools):
        with tools.cwd(artifact.path, "bin"):
            for file in tools.glob("*"):
                tools.replace_in_file(
                    file,
                    artifact.strings.install_prefix,
                    artifact.final_path)

        with tools.cwd(artifact.path, "share/autoconf"):
            tools.replace_in_file(
                "autom4te.cfg",
                artifact.strings.install_prefix,
                artifact.final_path)

        artifact.strings.install_prefix = artifact.final_path


TaskRegistry.get().add_task_class(Autoconf)
