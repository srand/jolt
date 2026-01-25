from jolt import attributes, BooleanParameter, Parameter
from jolt.tasks import TaskRegistry
from jolt.plugins import cxxinfo, fetch, ninja


@attributes.requires("requires_src")
@attributes.system
@ninja.attributes.cflags("cflags_linux_pic_{pic[on,off]}")
class LibBzip2(ninja.CXXLibrary):
    name = "libbzip2"
    binary = "bzip2"
    version = Parameter("1.0.8", help="bzip2 version.")
    pic = BooleanParameter(True, help="Build position independent code")
    shared = BooleanParameter(False, help="Build shared libraries")
    cstd = 90
    cflags_darwin_pic_on = ["-fPIC"]
    cflags_linux_pic_on = ["-fPIC"]
    incremental = False
    requires_src = ["fetch:alias=src,url=https://sourceware.org/pub/bzip2/bzip2-{version}.tar.gz"]
    source_influence = False
    sources = [
        "{fetch[src]}/bzip2-{version}/blocksort.c",
        "{fetch[src]}/bzip2-{version}/bzlib.c",
        "{fetch[src]}/bzip2-{version}/bzlib.h",
        "{fetch[src]}/bzip2-{version}/compress.c",
        "{fetch[src]}/bzip2-{version}/crctable.c",
        "{fetch[src]}/bzip2-{version}/decompress.c",
        "{fetch[src]}/bzip2-{version}/huffman.c",
        "{fetch[src]}/bzip2-{version}/randtable.c",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.environ.CMAKE_PREFIX_PATH.append(".")

        with tools.cwd("{fetch[src]}/bzip2-{version}"):
            artifact.collect("bzlib.h", "include/")


TaskRegistry.get().add_task_class(LibBzip2)
