from jolt import attributes, Parameter
from jolt.pkgs import ninja, readline
from jolt.plugins import git
from jolt.plugins.ninja import CXXLibrary
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ninja")
@attributes.requires("requires_readline")
class Lua(CXXLibrary):
    name = "lua"
    version = Parameter("5.4.8", help="Lua version.")

    requires_git = ["git:url=https://github.com/lua/lua.git,rev=v{version},hash=true"]
    requires_ninja = ["ninja"]
    requires_readline = ["readline"]
    sources = ["{git[lua]}/*.c"]


TaskRegistry.get().add_task_class(Lua)
