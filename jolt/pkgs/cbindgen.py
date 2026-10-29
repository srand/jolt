from jolt import attributes, Parameter
from jolt.pkgs import rust
from jolt.plugins import rust
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_rust")
@attributes.requires("requires_compiler")
class CBindgen(rust.Rust):
    name = "cbindgen"
    version = Parameter("0.29.4", help="cbindgen version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/mozilla/cbindgen.git,rev=v{version},hash=true"]
    requires_rust = ["rust"]
    srcdir = "{git[cbindgen]}"


TaskRegistry.get().add_task_class(CBindgen)
