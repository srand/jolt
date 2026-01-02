from jolt import Download, Parameter, attributes
from jolt.pkgs import rust
from jolt.plugins import git, rust
from jolt.tasks import TaskRegistry


@attributes.attribute("triple", "triple_{system}_{arch}")
@attributes.arch
@attributes.system
class Rust(Download):
    name = "rust"
    version = Parameter("1.92.0", help="Rust version.")
    url = "https://static.rust-lang.org/dist/rust-{version}-{triple}.tar.xz"
    collect = [{"files": "*", "cwd": "rust-{version}-{triple}"}]
    components = ["cargo", "rustc", "rust-std-{triple}"]
    
    triple_linux_x86_64 = "x86_64-unknown-linux-gnu"
    triple_windows_x86_64 = "x86_64-pc-windows-msvc"
    triple_darwin_x86_64 = "x86_64-apple-darwin"

    def publish(self, artifact, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self._extractdir, "rust-{version}-{triple}"):
            for component in tools.expand(self.components):
                artifact.collect("*", cwd=component)
        artifact.environ.PATH.append("bin")


@attributes.requires("requires_git")
@attributes.requires("requires_rust")
class RustBindgen(rust.Rust):
    name = "rust-bindgen"
    version = Parameter("0.72.1", help="Rust Bindgen version.")

    requires_git = ["git:url=https://github.com/rust-lang/rust-bindgen.git,rev=v{version}"]
    requires_rust = ["rust"]
    srcdir = "{git[rust-bindgen]}/bindgen-cli"


TaskRegistry.get().add_task_class(Rust)
TaskRegistry.get().add_task_class(RustBindgen)
