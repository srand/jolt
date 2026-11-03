from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, ncurses
from jolt.plugins import cxxinfo, git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ncurses")
@autotools.requires()
@pkgconfig.requires()
@cxxinfo.publish(libraries=["edit"])
@attributes.requires("requires_compiler")
class Libedit(autotools.Autotools):
    name = "libedit"
    version = Parameter("20260512-3.1", help="libedit version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["fetch:alias=src,url=https://thrysoee.dk/editline/libedit-{version}.tar.gz"]
    requires_ncurses = ["ncurses:pic=true"]
    """
    Linked statically: the install name of the shared libraries on macOS is in
    /jolt-prefix, and programs that configure runs can't load them.
    """
    srcdir = "{fetch[src]}/libedit-{version}"
    options = [
        "--disable-examples",
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
    ]

    def run(self, deps, tools):
        with tools.environ(
            CFLAGS=tools.run("pkg-config --cflags ncurses").strip() + " " + tools.getenv("CFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs ncurses").strip() + " " + tools.getenv("LDFLAGS", ""),
        ):
            super().run(deps, tools)
        if not self.shared:
            # Consumers of the static library must link ncurses
            with tools.cwd(tools.autotools().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("libedit.pc", "Requires:\n", "Requires: ncurses\n")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libedit)
