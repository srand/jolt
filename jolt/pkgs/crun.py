from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, json_c, libcap
from jolt.plugins import git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_json_c")
@attributes.requires("requires_libcap_{caps[on,off]}")
@autotools.requires()
@pkgconfig.requires()
@attributes.requires("requires_compiler")
class CRun(autotools.Autotools):
    name = "crun"
    version = Parameter("1.30.1", help="crun version.")
    caps = BooleanParameter(False, help="Enable capabilities support.")
    systemd = BooleanParameter(False, help="Enable systemd support.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/containers/crun.git,rev={version},submodules=true"]
    requires_json_c = ["json-c"]
    requires_libcap_on = ["libcap"]
    srcdir = "{git[crun]}"
    options = [
        # Unable to get ./configure to pick these up from pkg-config
        "--disable-criu",
        "--disable-seccomp",
        "{caps[,--disable-caps]}",
        "{systemd[,--disable-systemd]}",
    ]

    def run(self, deps, tools):
        if not self.caps:
            return super().run(deps, tools)
        # libcap is looked for with header and library checks, which ignore pkg-config
        with tools.environ(
            CPPFLAGS=tools.run("pkg-config --cflags libcap").strip() + " " + tools.getenv("CPPFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs-only-L libcap").strip() + " " + tools.getenv("LDFLAGS", ""),
        ):
            super().run(deps, tools)


TaskRegistry.get().add_task_class(CRun)
