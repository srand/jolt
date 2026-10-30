from jolt import Download, Parameter, attributes
from jolt.pkgs import compiler, rust
from jolt.plugins import git, rust
from jolt.tasks import TaskRegistry


@attributes.attribute("triple", "triple_{system}_{arch}")
@attributes.arch
@attributes.system
class Rust(Download):
    name = "rust"
    version = Parameter("1.99.1", help="Rust version.")
    url = "https://static.rust-lang.org/dist/rust-{version}-{triple}.tar.xz"
    collect = [{"files": "*", "cwd": "rust-{version}-{triple}"}]
    components = ["cargo", "rustc", "rust-std-{triple}"]
    """ Components installed from the downloaded archive. """

    triple_linux_x86_64 = "x86_64-unknown-linux-gnu"
    """ Target triple on Linux x86-64. """
    triple_windows_x86_64 = "x86_64-pc-windows-msvc"
    """ Target triple on Windows x86-64. """
    triple_darwin_x86_64 = "x86_64-apple-darwin"
    """ Target triple on macOS x86-64. """
    triple_darwin_arm64 = "aarch64-apple-darwin"
    """ Target triple on macOS arm64. """
    triple_linux_aarch64 = "aarch64-unknown-linux-gnu"
    """ Target triple on Linux arm64. """
    triple_windows_arm64 = "aarch64-pc-windows-msvc"
    """ Target triple on Windows arm64. """

    def publish(self, artifact, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self._extractdir, "rust-{version}-{triple}"):
            for component in tools.expand(self.components):
                artifact.collect("*", cwd=component)
        artifact.environ.PATH.append("bin")


@attributes.requires("requires_git")
@attributes.requires("requires_rust")
@attributes.requires("requires_compiler")
class RustBindgen(rust.Rust):
    name = "rust-bindgen"
    version = Parameter("0.73.2", help="rust-bindgen version.")

    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/rust-lang/rust-bindgen.git,rev=v{version}"]
    requires_rust = ["rust"]
    srcdir = "{git[rust-bindgen]}/bindgen-cli"


TaskRegistry.get().add_task_class(Rust)
TaskRegistry.get().add_task_class(RustBindgen)
