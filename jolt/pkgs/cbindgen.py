from jolt import attributes
from jolt.pkgs import rust
from jolt.plugins import rust
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_rust")
class CBindgen(rust.Rust):
    name = "cbindgen"
    version = "0.29.2"
    requires_git = ["git:url=https://github.com/mozilla/cbindgen.git,rev=v{version},hash=true"]
    requires_rust = ["rust"]
    srcdir = "{git[cbindgen]}"


TaskRegistry.get().add_task_class(CBindgen)
