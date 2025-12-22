from jolt import Download, Parameter, attributes
from jolt.pkgs import rust
from jolt.plugins import git, rust
from jolt.tasks import TaskRegistry


class Rust(Download):
    name = "rust"
    version = Parameter("1.92.0", help="Rust version.")
    url = "https://static.rust-lang.org/dist/rust-{version}-x86_64-unknown-linux-gnu.tar.xz"
    collect = [{"files": "*", "cwd": "rust-{version}-x86_64-unknown-linux-gnu"}]

    def publish(self, artifact, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self._extractdir, "rust-{version}-x86_64-unknown-linux-gnu"):
            tools.run("./install.sh --prefix=/ --destdir={installdir} --disable-ldconfig")
        with tools.cwd(self.installdir):
            artifact.collect("*")
        artifact.environ.PATH.append("bin")


@attributes.requires("requires_git")
@attributes.requires("requires_rust")
class RustBindgen(rust.Rust):
    name = "rust-bindgen"
    version = Parameter("0.72.1", help="Rust Bindgen version.")

    requires_git = ["git:url=https://github.com/rust-lang/rust-bindgen.git,rev=v{version}"]
    requires_rust = ["rust"]
    srcdir = "{git[rust-bindgen]}"


TaskRegistry.get().add_task_class(Rust)
TaskRegistry.get().add_task_class(RustBindgen)
