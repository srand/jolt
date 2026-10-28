from jolt import attributes, ListParameter, Parameter
from jolt.pkgs import binutils, glibc, gmp, mpc, mpfr, musl
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_libs")
@attributes.requires("requires_src")
@attributes.requires("requires_{_variant}")
@autotools.options("options_{_variant}")
class Gcc(autotools.Autotools):
    """
    GNU compilers

    Native compilers find the assembler and linker at runtime, for example from
    the binutils package. Cross compilers are built for targets without an
    operating system, such as arm-none-eabi, and include binutils for their
    target. Since there is no C library, only the compilers and libgcc are
    built for them, without threads and shared libraries, not the runtime
    libraries of other languages. They can also build C libraries for Linux
    targets, such as glibc for aarch64-linux-gnu.
    """

    name = "gcc"
    version = Parameter("16.2.0", help="GCC version.")
    languages = ListParameter(
        ["c", "cxx"],
        values=["c", "cxx", "fortran", "go", "m2", "objc", "objcxx"],
        help="Languages to build compilers for.",
    )
    target = Parameter(required=False, help="Target of a cross compiler, such as arm-none-eabi. Native compilers if not set.")
    requires_cross = ["binutils:target={target}"]
    """ Assembler and linker of the target, included in the cross compiler. """
    requires_libs = ["gmp", "mpc", "mpfr"]
    """ Libraries used by the compilers. """
    requires_native = []
    """ Native compilers use the assembler and linker found at runtime. """
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/gcc/gcc-{version}/gcc-{version}.tar.xz"]
    srcdir = "{fetch[src]}/gcc-{version}"
    options = [
        "--disable-bootstrap",
        "--disable-multilib",
        "--disable-nls",
        "--enable-languages={_languages}",
        "--with-gmp={_gmp}",
        "--with-mpc={_mpc}",
        "--with-mpfr={_mpfr}",
        "--without-isl",
        "--without-zstd",
        # Documentation requires makeinfo
        "MAKEINFO=true",
    ]
    options_cross = [
        "--disable-shared",
        "--disable-threads",
        "--target={target}",
        "--with-newlib",
        "--without-headers",
    ]
    """ Options passed to the ``configure`` script for cross compilers. """
    options_native = []
    """ Options passed to the ``configure`` script for native compilers. """

    @property
    def _variant(self):
        return "cross" if self.target.is_set() else "native"

    @property
    def _languages(self):
        # The names of GCC contain the separator of list parameters
        names = {"cxx": "c++", "objcxx": "obj-c++"}
        return ",".join(names.get(language, language) for language in self.languages)

    @property
    def _gmp(self):
        return self.deps["gmp"].path

    @property
    def _mpc(self):
        return self.deps["mpc"].path

    @property
    def _mpfr(self):
        return self.deps["mpfr"].path

    def run(self, deps, tools):
        if self._variant == "native":
            return super().run(deps, tools)

        # Without a C library, only the compilers and libgcc can be built
        self.deps = deps
        at = tools.autotools(deps, incremental=self.incremental)
        at.configure(self.srcdir, *tools.expand(self._options()))
        with tools.cwd(at.builddir):
            tools.run("make -j{} all-gcc all-target-libgcc", tools.cpu_count())
        at.install("install-gcc install-target-libgcc")
        self._install_binutils(deps, tools)

    def _install_binutils(self, deps, tools):
        # Cross compilers find the tools of their target in their own installation
        binutils = deps[tools.expand("binutils:target={target}")]
        with tools.cwd(tools.autotools().installdir, "jolt-prefix"):
            binutils.copy("*", "./", symlinks=True)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        # Describe the compilers to the tasks that use them
        prefix = tools.expand("{target}-") if self.target.is_set() else ""
        artifact.environ.CC = prefix + "gcc"
        if "cxx" in self.languages:
            artifact.environ.CXX = prefix + "g++"
        if "fortran" in self.languages:
            artifact.environ.FC = prefix + "gfortran"
        if self.target.is_set():
            for tool in ["ar", "nm", "objcopy", "ranlib", "strip"]:
                setattr(artifact.environ, tool.upper(), prefix + tool)
        with tools.cwd(tools.autotools().installdir, "jolt-prefix", "bin"):
            artifact.strings.target = tools.run("./{}gcc -dumpmachine", prefix, output=False).strip()


class GccSysroot(Gcc):
    """
    Base class of cross compilers that include a C library

    The compilers are built for Linux targets and include binutils and the C
    library for their target. The C library is installed in a system root in
    the installation, which the compilers use by default, and the runtime
    libraries of all languages are built.
    """

    abstract = True
    libc = None
    """ Name of the C library task, which must take a ``target`` parameter. """
    target = Parameter(help="Target of the compilers, such as aarch64-linux-gnu.")
    requires_sysroot = ["binutils:target={target}", "{libc}:target={target}"]
    """ Assembler, linker and C library of the target, included in the compilers. """
    options_sysroot = [
        "--target={target}",
        "--with-build-sysroot={_sysroot}",
        "--with-sysroot=/jolt-prefix/{target}/sysroot",
    ]
    """ Options passed to the ``configure`` script. """

    @property
    def _variant(self):
        return "sysroot"

    @property
    def _sysroot(self):
        return self.deps[self.tools.expand("{libc}:target={target}")].path

    def run(self, deps, tools):
        # The compilers are built with the host compiler, not with the cross
        # compiler that built the C library
        tools_env = ["AR", "CC", "CXX", "FC", "NM", "OBJCOPY", "RANLIB", "STRIP"]
        with tools.environ(**{name: None for name in tools_env}):
            autotools.Autotools.run(self, deps, tools)
        libc = deps[tools.expand("{libc}:target={target}")]
        sysroot = tools.expand_path("{}/jolt-prefix/{target}/sysroot", tools.autotools().installdir)
        tools.mkdir(sysroot)
        with tools.cwd(sysroot):
            libc.copy("*", "./", symlinks=True)
        self._install_binutils(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.paths.sysroot = tools.expand("{target}/sysroot")


class GccGlibc(GccSysroot):
    """ GNU compilers with the GNU C library, for targets such as aarch64-linux-gnu """

    name = "gcc/glibc"
    libc = "glibc"


class GccMusl(GccSysroot):
    """ GNU compilers with the musl C library, for targets such as aarch64-linux-musl """

    name = "gcc/musl"
    libc = "musl"
    target = Parameter(help="Target of the compilers, such as aarch64-linux-musl.")
    options_sysroot = GccSysroot.options_sysroot + [
        # The sanitizers require glibc
        "--disable-libsanitizer",
    ]
    """ Options passed to the ``configure`` script. """


TaskRegistry.get().add_task_class(Gcc)
TaskRegistry.get().add_task_class(GccGlibc)
TaskRegistry.get().add_task_class(GccMusl)
