from jolt import attributes, Parameter
from jolt.pkgs import compiler, zlib, zstd
from jolt.plugins import autotools, fetch, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_libs")
@attributes.requires("requires_src")
@autotools.requires()
@pkgconfig.requires()
@attributes.requires("requires_compiler")
class Elfutils(autotools.Autotools):
    """ Libraries and tools to read and write ELF files and DWARF debug information """

    name = "elfutils"
    version = Parameter("0.197", help="elfutils version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_libs = ["virtual/zlib:pic=true", "zstd:pic=true"]
    """ Libraries used for compressed sections. They are linked into the shared libraries. """
    requires_src = ["fetch:alias=src,url=https://sourceware.org/elfutils/ftp/{version}/elfutils-{version}.tar.bz2"]
    srcdir = "{fetch[src]}/elfutils-{version}"
    options = [
        "--disable-debuginfod",
        "--disable-debuginfod-ima-verification",
        "--disable-demangler",
        "--disable-libdebuginfod",
        "--disable-nls",
        "--disable-stackprof",
        "--with-zlib",
        "--with-zstd",
        "--without-bzlib",
        "--without-lzma",
    ]
    """ Options passed to the ``configure`` script. Only the libraries and tools are built, without debuginfod. """

    def run(self, deps, tools):
        # The compression libraries are looked for with library checks, which ignore pkg-config
        with tools.environ(
            CPPFLAGS=tools.run("pkg-config --cflags zlib libzstd").strip() + " " + tools.getenv("CPPFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs-only-L zlib libzstd").strip() + " " + tools.getenv("LDFLAGS", ""),
        ):
            super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Elfutils)
