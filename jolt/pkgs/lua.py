from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import ninja
from jolt.plugins import git
from jolt.plugins.ninja import CXXLibrary
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ninja")
class Lua(CXXLibrary):
    name = "lua"
    version = Parameter("5.4.8", help="Lua version.")
    shared = BooleanParameter(False, help="Build shared libraries.")

    requires_git = ["git:url=https://github.com/lua/lua.git,rev=v{version},hash=true"]
    requires_ninja = ["ninja"]
    sources = [
        "{git[lua]}/lapi.c",
        "{git[lua]}/lauxlib.c",
        "{git[lua]}/lbaselib.c",
        "{git[lua]}/lcode.c",
        "{git[lua]}/lcorolib.c",
        "{git[lua]}/lctype.c",
        "{git[lua]}/ldblib.c",
        "{git[lua]}/ldebug.c",
        "{git[lua]}/ldo.c",
        "{git[lua]}/ldump.c",
        "{git[lua]}/lfunc.c",
        "{git[lua]}/lgc.c",
        "{git[lua]}/linit.c",
        "{git[lua]}/liolib.c",
        "{git[lua]}/llex.c",
        "{git[lua]}/lmathlib.c",
        "{git[lua]}/lmem.c",
        "{git[lua]}/loadlib.c",
        "{git[lua]}/lobject.c",
        "{git[lua]}/lopcodes.c",
        "{git[lua]}/loslib.c",
        "{git[lua]}/lparser.c",
        "{git[lua]}/lstate.c",
        "{git[lua]}/lstring.c",
        "{git[lua]}/lstrlib.c",
        "{git[lua]}/ltable.c",
        "{git[lua]}/ltablib.c",
        "{git[lua]}/ltests.c",
        "{git[lua]}/ltm.c",
        "{git[lua]}/lundump.c",
        "{git[lua]}/lutf8lib.c",
        "{git[lua]}/lvm.c",
        "{git[lua]}/lzio.c",
    ]


TaskRegistry.get().add_task_class(Lua)
