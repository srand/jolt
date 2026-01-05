from jolt import attributes, Parameter, Task
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_texinfo")
@autotools.requires(automake=False, libtool=False)
class Automake(autotools.Autotools):
    name = "automake"
    version = Parameter("1.18.1", help="Automake version.")
    requires_git = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/automake/automake-{version}.tar.xz"]
    requires_texinfo = ["texinfo"]
    srcdir = "{fetch[src]}/automake-{version}"

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

        for file in tools.glob(artifact.path + "/share/automake-*/Automake/Config.pm"):
            tools.replace_in_file(
                file,
                artifact.strings.install_prefix,
                artifact.final_path)

        with tools.cwd(artifact.path):
            for file in tools.glob("share/aclocal-*"):
                artifact.environ.ACLOCAL_PATH.append(file)

        artifact.strings.install_prefix = artifact.final_path


TaskRegistry.get().add_task_class(Automake)
