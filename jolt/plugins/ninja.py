import copy
import ninja_syntax as ninja
import platform
import os
import sys

from jolt.tasks import Task
from jolt import config
from jolt import influence
from jolt import log
from jolt import utils
from jolt import filesystem as fs
from jolt.error import raise_task_error_if


class Variable(object):
    def __init__(self, value=None):
        self._value = value

    def create(self, project, writer, deps, tools):
        writer.variable(self.name, self._value)


class EnvironmentVariable(Variable):
    def __init__(self, name=None, default=None, envname=None, prefix=None):
        self.name = name
        self._default = default or ''
        self._envname = envname
        self._prefix = prefix or ""

    def create(self, project, writer, deps, tools):
        envname = self._envname or self.name
        self.value = tools.getenv(envname.upper(), self._default)
        writer.variable(self.name, self._prefix + self.value)


class ToolEnvironmentVariable(EnvironmentVariable):
    def create(self, project, writer, deps, tools):
        super(ToolEnvironmentVariable, self).create(project, writer, deps, tools)
        if not self.value:
            return
        value = self.value.split()[0]
        executable_path = tools.which(value)
        if executable_path:
            writer.variable(self.name + "_path", executable_path)


class ProjectVariable(Variable):
    def __init__(self, name=None, default=None, attrib=None):
        self.name = name
        self._default = default or ''
        self._attrib = attrib

    def create(self, project, writer, deps, tools):
        value = getattr(project, self._attrib or self.name, "")
        if type(value) == list:
            value = " ".join(value)
        writer.variable(self.name, str(value))


class SharedLibraryVariable(Variable):
    def __init__(self, name=None, default=None):
        self.name = name
        self._default = default

    def create(self, project, writer, deps, tools):
        value = self._default if isinstance(project, CXXLibrary) and project.shared else ""
        writer.variable(self.name, str(value))


class GNUPCHVariables(Variable):
    pch_ext = ".pch"
    gch_ext = ".gch"

    def __init__(self):
        pass

    def create(self, project, writer, deps, tools):
        pch = [src for src in project.sources if src.endswith(self.pch_ext)]

        raise_task_error_if(
            len(pch) > 1, project,
            "multiple precompiled headers found, only one is allowed")

        if len(pch) <= 0:
            writer.variable("pch_out", ".")
            return

        project._pch = fs.path.basename(pch[0])
        project._pch_out = project._pch + self.gch_ext

        writer.variable("pch", project._pch)
        writer.variable("pch_flags", "-include $pch")
        writer.variable("pch_out", project._pch_out)


class Rule(object):
    """ A source transformation rule.

    Rules are used to transform files from one type to another.
    An example is the rule that compiles a C/C++ file to an object file.
    Ninja tasks can be extended with additional rules beyond those
    already builtin and the builtin rules may also be overridden.

    To define a new rule for a type of file, assign a Rule object
    to an arbitrary attribute of the compilation task being defined.
    Below is an example where a rule has been created to generate Qt moc
    source files from headers.

    .. code-block:: python

      class MyQtProject(CXXExecutable):
          moc_rule = Rule(
              command="moc -o $out $in",
              infiles=[".h"],
              outfiles=["{outdir}/{in_path}/{in_base}_moc.cpp"])

          sources = ["myqtproject.h", "myqtproject.cpp"]

    The moc rule will be run on all ``.h`` header files listed as sources,
    i.e. ``myqtproject.h``. It takes the input header file and generates
    a corresponding moc source file, ``myqtproject_moc.cpp``.
    The moc source file will then automatically be fed to the builtin
    compiler rule from which the output is an object file,
    ``myqtproject_moc.o``.

    """

    def __init__(self, command=None, infiles=None, outfiles=None, depfile=None, deps=None, variables=None, implicit=None, order_only=None):
        """
        Creates a new rule.

        Args:
            command (str, optional):
                The command that will be execute by the rule.
                It can use any of the `variables` created below.

            infiles (str, optional):
                A list of file extensions that the rule should apply to.

            outfiles (str, optional):
                A list of files created by the rule. Regular keyword
                expansion is done on the strings but additional keywords
                are supported, see `variables` below.

            variables (str, optional):
                A dictionary of variables that should be available to Ninja
                when running the command. By default, only $in and $out will be set,
                where $in is a single input file and $out is the output file(s).
                Regular keyword expansion is done on the value strings, see
                :meth:`jolt.Tools.expand`. These additional keywords are supported:

                   - ``in_path`` - the path to the directory where the input file is located
                   - ``in_base`` - the name of the input file, excluding file extension
                   - ``in_ext`` - the input file extension

                Example:

                  .. code-block:: python

                    Rule(command="echo $extension", variables={"extension": "{in_ext}"}, ...)

        """
        self.command = command
        self.variables = variables or {}
        self.depfile = depfile
        self.deps = deps
        self.infiles = infiles or []
        self.outfiles = utils.as_list(outfiles or [])
        self.implicit = implicit
        self.order_only = order_only

    def _out(self, project, infile):
        in_dirname, in_basename = fs.path.split(infile)
        in_base, in_ext = fs.path.splitext(in_basename)

        if in_dirname:
            in_dirname = fs.path.relpath(in_dirname, project.joltdir)

        result_files = []
        for outfile in self.outfiles:
            outfile = project.tools.expand(
                outfile,
                in_path=in_dirname,
                in_base=in_base,
                in_ext=in_ext)

            if outfile.startswith(project.joltdir) and not outfile.startswith(project.outdir):
                outfile = outfile[len(project.joltdir)+1:]
                outfile = fs.path.join(project.outdir, outfile)

            result_files.append(outfile)

        result_vars = {}
        for key, val in self.variables.items():
            result_vars[key] = project.tools.expand(
                val,
                in_path=in_dirname,
                in_base=in_base,
                in_ext=in_ext)

        return result_files, result_vars

    def create(self, project, writer, deps, tools):
        if self.command is not None:
            writer.rule(self.name, tools.expand(self.command), depfile=self.depfile, deps=self.deps, description="$desc")
            writer.newline()

    def build(self, project, writer, infiles, implicit=None):
        result = []
        for infile in utils.as_list(infiles):
            infile_rel = fs.path.relpath(infile, project.outdir)
            outfiles, variables = self._out(project, infile)
            outfiles_rel = [fs.path.relpath(outfile, project.outdir) for outfile in outfiles]
            implicit = (self.implicit or []) + (implicit or [])
            writer.build(outfiles_rel, self.name, infile_rel, variables=variables, implicit=implicit, order_only=self.order_only)
            result.extend(outfiles)
        return result


class Skip(Rule):
    def __init__(self, *args, **kwargs):
        super(Skip, self).__init__(*args, **kwargs)
        self.command = None

    def create(self, project, writer, deps, tools):
        pass

    def build(self, project, writer, infiles):
        return None


class Objects(Rule):
    def __init__(self, *args, **kwargs):
        super(Objects, self).__init__(*args, **kwargs)
        self.command = None

    def create(self, project, writer, deps, tools):
        pass

    def build(self, project, writer, infiles):
        project.objects.extend(utils.as_list(infiles))
        return None


class GNUCompiler(Rule):
    def __init__(self, *args, **kwargs):
        super(GNUCompiler, self).__init__(*args, **kwargs)

    def build(self, project, writer, infiles, implicit=None):
        implicit = implicit or []
        if GNUPCHVariables.pch_ext not in self.infiles and project._pch_out is not None:
            implicit.append(project._pch_out)
        return super(GNUCompiler, self).build(project, writer, infiles, implicit)


class FileListWriter(Rule):
    def __init__(self, name):
        self.name = name

    def _write(self, flp, flhp, data, digest):
        with open(flp, "w") as f:
            f.write(data)
        with open(flhp, "w") as f:
            f.write(digest)

    def _identical(self, flp, flhp, data, digest):
        if not fs.path.exists(flp) or not fs.path.exists(flhp):
            return False

        try:
            with open(flhp, "r") as f:
                disk_digest = f.read()
        except:
            return False

        return digest == disk_digest

    def _data(self, files):
        data = "\n".join(files)
        return data, utils.sha1(data)

    def build(self, project, writer, infiles):
        file_list_path = fs.path.join(project.outdir, "{0}.list".format(self.name))
        file_list_hash_path = fs.path.join(project.outdir, "{0}.hash".format(self.name))
        data, digest = self._data(infiles)
        if not self._identical(file_list_path, file_list_hash_path, data, digest):
            self._write(file_list_path, file_list_hash_path, data, digest)
        project.depimports.append(file_list_path)


class GNULinker(Rule):
    def __init__(self, *args, **kwargs):
        super(GNULinker, self).__init__(*args, **kwargs)

    def build(self, project, writer, infiles):
        file_list = FileListWriter("objects")
        file_list.build(project, writer, infiles)

        infiles_rel = [fs.path.relpath(infile, project.outdir) for infile in infiles]
        outfiles, variables = self._out(project, project.binary)
        outfiles_rel = [fs.path.relpath(outfile, project.outdir) for outfile in outfiles]
        writer.build(outfiles_rel, self.name, infiles_rel, implicit=project.depimports, variables=variables)
        return outfiles


class GNUArchiver(Rule):
    def __init__(self, *args, **kwargs):
        super(GNUArchiver, self).__init__(*args, **kwargs)

    def build(self, project, writer, infiles):
        file_list = FileListWriter("objects")
        file_list.build(project, writer, infiles)

        infiles_rel = [fs.path.relpath(infile, project.outdir) for infile in infiles]
        outfiles, variables = self._out(project, project.binary)
        outfiles_rel = [fs.path.relpath(outfile, project.outdir) for outfile in outfiles]
        writer.build(outfiles_rel, self.name, infiles_rel, implicit=project.depimports, variables=variables)
        return outfiles


class GNUDepImporter(Rule):
    def __init__(self, prefix=None, suffix=None):
        self.prefix = prefix
        self.suffix = suffix
        self.infiles = []
        self.command = None

    def _build_archives(self, project, writer, deps):
        archives = []
        for name, artifact in deps.items():
             for lib in artifact.cxxinfo.libraries.items():
                 name = "{0}{1}{2}".format(self.prefix, lib, self.suffix)
                 for path in artifact.cxxinfo.libpaths.items():
                     archive = fs.path.join(artifact.path, path, name)
                     if fs.path.exists(archive):
                         archives.append(archive)
        return archives

    def build(self, project, writer, deps):
        imports = []
        if isinstance(project, CXXExecutable):
            imports += self._build_archives(project, writer, deps)
        return imports


class Toolchain(object):
    def __init__(self):
        self._rule_map = self.build_rule_map(self)
        self.build_variables(self)

    @staticmethod
    def build_rule_map(cls):
        rule_map = {}
        for name, rule in Toolchain.all_rules(cls):
            rule.name = name
            for ext in rule.infiles:
                rule_map[ext] = rule
        return rule_map

    @staticmethod
    def build_variables(cls):
        for name, var in Toolchain.all_variables(cls):
            var.name = name

    @staticmethod
    def all_rules(cls):
        return [(key, getattr(cls, key)) for key in dir(cls)
                if isinstance(utils.getattr_safe(cls, key), Rule)]

    def find_rule(self, ext):
        return self._rule_map.get(ext)

    @staticmethod
    def all_variables(cls):
        return [(key, getattr(cls, key)) for key in dir(cls)
                if isinstance(utils.getattr_safe(cls, key), Variable)]

    def __str__(self):
        return self.__class__.__name__


class Macros(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        macros = [tools.expand(macro) for macro in project.macros]
        for name, artifact in deps.items():
            macros += artifact.cxxinfo.macros.items()
        macros = ["{0}{1}".format(self.prefix, macro) for macro in macros]
        writer.variable(self.name, " ".join(macros))


class ImportedFlags(Variable):
    def create(self, project, writer, deps, tools):
        asflags = []
        cflags = []
        cxxflags = []
        ldflags = []
        for name, artifact in deps.items():
            asflags += artifact.cxxinfo.asflags.items()
            cflags += artifact.cxxinfo.cflags.items()
            cxxflags += artifact.cxxinfo.cxxflags.items()
            ldflags += artifact.cxxinfo.ldflags.items()
        writer.variable("imported_asflags", " ".join(asflags))
        writer.variable("imported_cflags", " ".join(cflags))
        writer.variable("imported_cxxflags", " ".join(cxxflags))
        writer.variable("imported_ldflags", " ".join(ldflags))


class IncludePaths(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        def expand(path):
            if path[0] in ['=', fs.sep]:
                return tools.expand(path)
            if path[0] in ['-']:
                return tools.expand(path[1:])
            return tools.expand_relpath(path, project.outdir)

        def expand_artifact(sandbox, path):
            if path[0] in ['=', fs.sep]:
                return path
            if path[0] in ['-']:
                return path[1:]
            return tools.expand_relpath(fs.path.join(sandbox, path), project.outdir)

        incpaths = [expand(path) for path in project.incpaths] + ["."]
        for name, artifact in deps.items():
            incs = [path for path in artifact.cxxinfo.incpaths.items()]
            if incs:
                sandbox = tools.sandbox(artifact, project.incremental)
                incpaths += [expand_artifact(sandbox, path) for path in incs]

        incpaths = ["{0}{1}".format(self.prefix, path) for path in incpaths]
        writer.variable(self.name, " ".join(incpaths))


class LibraryPaths(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        if isinstance(project, CXXLibrary) and not project.shared:
            return
        libpaths = [tools.expand_relpath(path, project.outdir) for path in project.libpaths]
        for name, artifact in deps.items():
            libpaths += [fs.path.join(artifact.path, path)
                         for path in artifact.cxxinfo.libpaths.items()]
        libpaths = ["{0}{1}".format(self.prefix, path) for path in libpaths]
        writer.variable(self.name, " ".join(libpaths))


class Libraries(Variable):
    def __init__(self, prefix=None, suffix=None):
        self.prefix = prefix or ''
        self.suffix = suffix or ''

    def create(self, project, writer, deps, tools):
        if isinstance(project, CXXLibrary) and not project.shared:
            return
        libraries = [tools.expand(lib) for lib in project._libraries()]
        for name, artifact in deps.items():
            libraries += artifact.cxxinfo.libraries.items()
        libraries = ["{0}{1}{2}".format(self.prefix, path, self.suffix) for path in libraries]
        writer.variable(self.name, " ".join(libraries))


class GNUFlags(object):
    @staticmethod
    def set(flags, flag, fixup=None):
        flags = flags.split(" ")
        fixup = fixup or []
        flags_out = [flag_out for flag_out in flags if flag_out not in fixup]
        flags_out.append(flag)
        return " ".join(flags_out)


class GNUOptFlags(GNUFlags):
    DEBUG = "-Og"

    @staticmethod
    def set(flags, flag):
        remove = ("-O0", "-O1", "-O2", "-O3", "-Os", "-Ofast", "-Og", "-O")
        return GNUFlags.set(flags, flag, remove)

    @staticmethod
    def set_debug(flags):
        return GNUOptFlags.set(flags, GNUOptFlags.DEBUG)


class GNUToolchain(Toolchain):
    hh = Skip(infiles=[".h", ".hh", ".hpp", ".hxx", GNUPCHVariables.gch_ext])
    obj = Objects(infiles=[".o", ".obj", ".a"])

    joltdir = ProjectVariable()
    outdir = ProjectVariable()
    binary = ProjectVariable()

    ar = ToolEnvironmentVariable(default="ar")
    cc = ToolEnvironmentVariable(default="gcc")
    cxx = ToolEnvironmentVariable(default="g++")
    ld = ToolEnvironmentVariable(default="g++", envname="CXX")
    objcopy = ToolEnvironmentVariable(default="objcopy")

    ccwrap = EnvironmentVariable(default="")
    cxxwrap = EnvironmentVariable(default="")

    asflags = EnvironmentVariable(default="")
    cflags = EnvironmentVariable(default="")
    cxxflags = EnvironmentVariable(default="")
    ldflags = EnvironmentVariable(default="")

    shared_flags = SharedLibraryVariable(default="-fPIC")
    pch_flags = GNUPCHVariables()

    extra_asflags = ProjectVariable(attrib="asflags")
    extra_cflags = ProjectVariable(attrib="cflags")
    extra_cxxflags = ProjectVariable(attrib="cxxflags")
    extra_ldflags = ProjectVariable(attrib="ldflags")

    flags = ImportedFlags()
    macros = Macros(prefix="-D")
    incpaths = IncludePaths(prefix="-I")
    libpaths = LibraryPaths(prefix="-L")
    libraries = Libraries(prefix="-l")

    compile_pch = GNUCompiler(
        command="$cxxwrap $cxx -x c++-header $cxxflags $shared_flags $imported_cxxflags $extra_cxxflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[GNUPCHVariables.pch_ext],
        outfiles=["{outdir}/{in_base}{in_ext}" + GNUPCHVariables.gch_ext],
        variables={"desc": "[PCH] {in_base}{in_ext}"})

    compile_c = GNUCompiler(
        command="$ccwrap $cc -x c $pch_flags $cflags $shared_flags $imported_cflags $extra_cflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".c"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"],
        variables={"desc": "[C] {in_base}{in_ext}"},
        implicit=["$cc_path"])

    compile_cxx = GNUCompiler(
        command="$cxxwrap $cxx -x c++ $pch_flags $cxxflags $shared_flags $imported_cxxflags $extra_cxxflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".cc", ".cpp", ".cxx"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"],
        variables={"desc": "[CXX] {in_base}{in_ext}"},
        implicit=["$cxx_path"])

    compile_asm = GNUCompiler(
        command="$ccwrap $cc -x assembler $pch_flags $asflags $shared_flags $imported_asflags $extra_asflags -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".s", ".asm"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"],
        variables={"desc": "[ASM] {in_base}{in_ext}"},
        implicit=["$cc_path"])

    compile_asm_with_cpp = GNUCompiler(
        "$ccwrap $cc -x assembler-with-cpp $pch_flags $asflags $shared_flags $imported_asflags $extra_asflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".S"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"],
        variables={"desc": "[ASM] {in_base}{in_ext}"},
        implicit=["$cc_path"])

    linker = GNULinker(
        command=" && ".join([
            "$ld $ldflags $imported_ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "mkdir -p .debug",
            "$objcopy --only-keep-debug $out .debug/$binary",
            "$objcopy --strip-all $out",
            "$objcopy --add-gnu-debuglink=.debug/$binary $out"
        ]),
        outfiles=["{outdir}/{binary}"],
        variables={"desc": "[LINK] {binary}"},
        implicit=["$ld_path", "$objcopy_path"])

    dynlinker = GNULinker(
        command=" && ".join([
            "$ld $ldflags -shared $imported_ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "mkdir -p $outdir/.debug",
            "$objcopy --only-keep-debug $out $outdir/.debug/$binary",
            "$objcopy --strip-all $out",
            "$objcopy --add-gnu-debuglink=$outdir/.debug/$binary $out"
        ]),
        outfiles=["{outdir}/lib{binary}.so"],
        variables={"desc": "[LINK] {binary}"},
        implicit=["$ld_path", "$objcopy_path"])

    archiver = GNUArchiver(
        command="rm -f $out && $ar cr $out @objects.list",
        outfiles=["{outdir}/lib{binary}.a"],
        variables={"desc": "[AR] lib{binary}.a"},
        implicit=["$ld_path", "$ar_path"])

    depimport = GNUDepImporter(
        prefix="lib",
        suffix=".a")


MSVCCompiler = GNUCompiler
MSVCArchiver = GNUArchiver
MSVCLinker = GNULinker
MSVCDepImporter = GNUDepImporter


class MSVCToolchain(Toolchain):
    hh = Skip(infiles=[".h", ".hh", ".hpp", ".hxx"])
    obj = Objects(infiles=[".o", ".obj", ".a"])

    joltdir = ProjectVariable()
    outdir = ProjectVariable()
    binary = ProjectVariable()

    cl = EnvironmentVariable(default="cl", envname="cl_exe")
    lib = EnvironmentVariable(default="lib", envname="lib_exe")
    link = EnvironmentVariable(default="link", envname="link_exe")

    asflags = EnvironmentVariable(default="")
    cflags = EnvironmentVariable(default="/EHsc")
    cxxflags = EnvironmentVariable(default="/EHsc")
    ldflags = EnvironmentVariable(default="")

    extra_asflags = ProjectVariable(attrib="asflags")
    extra_cflags = ProjectVariable(attrib="cflags")
    extra_cxxflags = ProjectVariable(attrib="cxxflags")
    extra_ldflags = ProjectVariable(attrib="ldflags")
    macros = Macros(prefix="/D")
    incpaths = IncludePaths(prefix="/I")
    libpaths = LibraryPaths(prefix="/LIBPATH:")
    libraries = Libraries(suffix=".lib")

    compile_asm = MSVCCompiler(
        command="$cl /nologo /showIncludes $asflags $extra_asflags $macros $incpaths /c /Tc$in /Fo$out",
        deps="msvc",
        infiles=[".asm", ".s", ".S"],
        outfiles=["{outdir}/{in_path}/{in_base}.obj"])

    compile_c = MSVCCompiler(
        command="$cl /nologo /showIncludes $cxxflags $extra_cxxflags $macros $incpaths /c /Tc$in /Fo$out",
        deps="msvc",
        infiles=[".c"],
        outfiles=["{outdir}/{in_path}/{in_base}.obj"])

    compile_cxx = MSVCCompiler(
        command="$cl /nologo /showIncludes $cxxflags $extra_cxxflags $macros $incpaths /c /Tp$in /Fo$out",
        deps="msvc",
        infiles=[".cc", ".cpp", ".cxx"],
        outfiles=["{outdir}/{in_path}/{in_base}.obj"])

    linker = MSVCLinker(
        command="$link /nologo $ldflags $extra_ldflags $libpaths @objects.list $libraries /out:$out",
        outfiles=["{outdir}/{binary}.exe"])

    archiver = MSVCArchiver(
        command="$lib /nologo /out:$out @objects.list",
        outfiles=["{outdir}/{binary}.lib"])

    depimport = MSVCDepImporter(
        prefix="",
        suffix=".lib")


if os.name == "nt":
    toolchain = MSVCToolchain()
else:
    toolchain = GNUToolchain()


@influence.attribute("asflags")
@influence.attribute("cflags")
@influence.attribute("cxxflags")
@influence.attribute("depimports")
@influence.attribute("incpaths")
@influence.attribute("ldflags")
@influence.attribute("libpaths")
@influence.attribute("libraries")
@influence.attribute("macros")
@influence.attribute("sources")
@influence.attribute("binary")
@influence.attribute("publishdir")
@influence.attribute("toolchain")
class CXXProject(Task):
    """

    The task recognizes these source file types:
    .asm, .c, .cc, .cpp, .cxx, .h, .hh, .hpp, .hxx, .pch, .s, .S

    Other file types can be supported through additional rules,
    see the :class:`Rule <jolt.plugin.ninja.Rule>` class.

    On Linux, GCC/Binutils is the default toolchain used.
    The default toolchain can be overridden by setting the
    environment variables ``AR``, ``CC``, ``CXX`` and ``LD``.
    The prefered method is to assign these variables through the
    artifact of a special task that you depend on.

    On Windows, Visual Studio is the default toolchain and it
    must be present in the ``PATH``. Run Jolt from a developer
    command prompt.

    Additionally, these environment variables can be used to
    customize toolchain behavior on any platform:

     - ``ASFLAGS`` - compiler flags used for assembly code
     - ``CFLAGS`` - compiler flags used for C code
     - ``CXXFLAGS`` - compiler flags used for C++ code
     - ``LDFLAGS`` - linker flags

    """

    asflags = []
    """ A list of compiler flags used when compiling assembler files. """

    cflags = []
    """ A list of compiler flags used when compiling C files. """

    cxxflags = []
    """ A list of compiler flags used when compiling C++ files. """

    depimports = []
    """ List of implicit dependencies """

    incpaths = []
    """ List of preprocessor include paths """

    libpaths = []
    """ A list of library search paths used when linking. """

    libraries = []
    """ A list of libraries to link with. """

    ldflags = []
    """ A list of linker flags to use. """

    macros = []
    """ List of preprocessor macros to set """

    sources = []
    """ A list of sources to compile.

    Path names may contain simple shell-style wildcards such as
    '*' and '?'. Note: files starting with a dot are not matched
    by these wildcards.

    Example:

      .. code-block:: python

        sources = ["src/*.cpp"]
    """

    publishdir = None

    source_influence = True
    """ Let the contents of source files influence the identity of the task artifact.

    When ``True``, a source file listed in the ``sources`` attribute will
    cause a rebuild of the task if modified.

    Source influence can hurt performance since every files needs to be hashed.
    It is safe to set this flag to ``False`` if all source files reside in a
    ``git`` repository listed as a dependency with the ``requires`` attribute or
    if the task uses the ``git.influence`` decorator.

    Always use ``source_influence`` if you are unsure whether it is needed or not.
    """

    binary = None
    """ Name of the target binary (defaults to canonical task name) """

    incremental = True
    """ Compile incrementally.

    If incremental build is disabled, all intermediate files from a
    previous build will be removed before the execution begins.
    """

    abstract = True
    toolchain = None

    def __init__(self, *args, **kwargs):
        super(CXXProject, self).__init__(*args, **kwargs)
        self._init_sources()
        self.toolchain = self.__class__.toolchain() if self.__class__.toolchain else toolchain
        self.binary = self.expand(self.__class__.binary or self.canonical_name)

        self.asflags = self.expand(utils.as_list(utils.call_or_return(self, self.__class__._asflags)))
        self.cflags = self.expand(utils.as_list(utils.call_or_return(self, self.__class__._cflags)))
        self.cxxflags = self.expand(utils.as_list(utils.call_or_return(self, self.__class__._cxxflags)))
        self.ldflags = self.expand(utils.as_list(utils.call_or_return(self, self.__class__._ldflags)))

        self.depimports = utils.as_list(utils.call_or_return(self, self.__class__._depimports))
        self.incpaths = utils.as_list(utils.call_or_return(self, self.__class__._incpaths))
        self.libpaths = utils.as_list(utils.call_or_return(self, self.__class__._libpaths))
        self.libraries = utils.as_list(utils.call_or_return(self, self.__class__._libraries))
        self.macros = utils.as_list(utils.call_or_return(self, self.__class__._macros))
        self._pch_out = None
        self.publishdir = self.expand(self.__class__.publishdir or '')
        if self.source_influence:
            for source in self.sources:
                self.influence.append(influence.FileInfluence(source))
        else:
            self._verify_influence()
        self._init_variables()
        self._init_rules()
        self._rule_map = Toolchain.build_rule_map(self)

    def _init_variables(self):
        for name, var in Toolchain.all_variables(self):
            var = copy.copy(var)
            setattr(self, name, var)
            var.name = name

    def _init_rules(self):
        for name, rule in Toolchain.all_rules(self):
            rule = copy.copy(rule)
            setattr(self, name, rule)

    def _init_sources(self):
        self.sources = utils.as_list(utils.call_or_return(self, self.__class__._sources))

    def _verify_influence(self):
        sources = set(self.sources)
        for ip in self.influence:
            if not isinstance(ip, influence.FileInfluence):
                continue
            ok = [source for source in sources
                  if self.expand(source).startswith(self.expand(ip.path))]
            sources.difference_update(ok)
        for source in sources:
            log.warning("Missing influence: {} ({})", source, self.name)
            self.influence.append(influence.FileInfluence(source))

    def _expand_sources(self):
        sources = []
        for source in self.sources:
            l = self.tools.glob(source)
            raise_task_error_if(
                not l and not ('*' in source or '?' in source), self,
                "source file '{0}' not found", fs.path.basename(source))
            sources += l
        self.sources = sources

    def _write_ninja_file(self, basedir, deps, tools):
        with open(fs.path.join(basedir, "build.ninja"), "w") as fobj:
            writer = ninja.Writer(fobj)
            self._populate_variables(writer, deps, tools)
            self._populate_rules(writer, deps, tools)
            self._populate_inputs(writer, deps, tools)
            self._populate_project(writer, deps, tools)
            writer.close()

    def _write_shell_file(self, basedir, deps, tools):
        filepath = fs.path.join(basedir, "compile")
        with open(filepath, "w") as fobj:
            data = """#!{executable}
import sys
import subprocess

objects = {objects}

def help():
    print("usage: compile [-a] [-l] [target-pattern]")
    print("")
    print("  -a               Build all targets")
    print("  -l               List all build targets")
    print("  target-pattern   Compile build targets containing this substring")

def main():
    if len(sys.argv) <= 1:
        help()
    elif [arg for arg in sys.argv[1:] if arg == "-l"]:
        for object in objects:
            print(object)
    elif [arg for arg in sys.argv[1:] if arg == "-a"]:
        subprocess.call(["ninja", "-v"])
    else:
        targets = []
        for arg in sys.argv[1:]:
            matches = [t for t in objects if arg in t]
            if not matches:
                print("error: no such build target")
            targets.extend(matches)
        if not targets:
            return
        subprocess.call(["ninja", "-v"] + targets)

if __name__ == "__main__":
    main()

"""
            fobj.write(
                data.format(
                    executable=sys.executable,
                    objects=[fs.path.relpath(o, self.outdir) for o in self.objects]))
        tools.chmod(filepath, 0o777)

    def find_rule(self, ext):
        rule = self._rule_map.get(ext)
        if rule is None:
            rule = toolchain.find_rule(ext)
        raise_task_error_if(
            not rule, self,
            "no build rule available for files with extension '{0}'", ext)
        return rule

    def _populate_variables(self, writer, deps, tools):
        variables = set()
        for name, var in Toolchain.all_variables(self):
            var.create(self, writer, deps, tools)
            variables.add(name)
        for name, var in Toolchain.all_variables(self.toolchain):
            if name not in variables:
                var.create(self, writer, deps, tools)
        writer.newline()

    def _populate_rules(self, writer, deps, tools):
        rules = set()
        for name, rule in Toolchain.all_rules(self):
            rule.create(self, writer, deps, tools)
            rules.add(name)
        for name, rule in Toolchain.all_rules(self.toolchain):
            if name not in rules:
                rule.create(self, writer, deps, tools)
        writer.newline()

    def _populate_inputs(self, writer, deps, tools):
        self.objects = []
        sources = copy.copy(self.sources)
        while sources:
            source = sources.pop()
            _, ext = fs.path.splitext(source)
            rule = self.find_rule(ext)
            output = rule.build(self, writer, tools.expand_path(source))
            sources.extend(output or [])
        writer.newline()

    def _populate_project(self, writer, deps, tools):
        pass

    def _incpaths(self):
        return utils.call_or_return(self, self.__class__.incpaths)

    def _ldflags(self):
        return utils.call_or_return(self, self.__class__.ldflags)

    def _libpaths(self):
        return utils.call_or_return(self, self.__class__.libpaths)

    def _libraries(self):
        return utils.call_or_return(self, self.__class__.libraries)

    def _macros(self):
        return utils.call_or_return(self, self.__class__.macros)

    def _sources(self):
        return utils.call_or_return(self, self.__class__.sources)

    def _asflags(self):
        return utils.call_or_return(self, self.__class__.asflags)

    def _cflags(self):
        return utils.call_or_return(self, self.__class__.cflags)

    def _cxxflags(self):
        return utils.call_or_return(self, self.__class__.cxxflags)

    def _depimports(self):
        return utils.call_or_return(self, self.__class__.depimports)

    def clean(self, tools):
        self.outdir = tools.builddir("ninja", self.incremental)
        tools.rmtree(self.outdir, ignore_errors=True)

    def run(self, deps, tools):
        self._expand_sources()
        self.outdir = tools.builddir("ninja", self.incremental)
        self._write_ninja_file(self.outdir, deps, tools)
        verbose = "-v" if log.is_verbose() else ""
        threads = config.get("jolt", "threads", tools.getenv("JOLT_THREADS", None))
        threads = "-j " + threads if threads else ""
        tools.run("ninja -d keepdepfile {2} -C {0} {1}", self.outdir, verbose, threads)

    def shell(self, deps, tools):
        self._expand_sources()
        self.outdir = tools.builddir("ninja", self.incremental)
        self._write_ninja_file(self.outdir, deps, tools)
        self._write_shell_file(self.outdir, deps, tools)
        pathenv = self.outdir + os.pathsep + tools.getenv("PATH")
        with tools.cwd(self.outdir), tools.environ(PATH=pathenv):
            print()
            print("Use the 'compile' command to build individual compilation targets")
            super(CXXProject, self).shell(deps, tools)


@influence.attribute("shared")
class CXXLibrary(CXXProject):
    """
    Builds a C/C++ library.
    """

    abstract = True
    shared = False

    publishdir = "lib/"
    """ The artifact path where the library is published. """

    def __init__(self, *args, **kwargs):
        super(CXXLibrary, self).__init__(*args, **kwargs)

    def _populate_inputs(self, writer, deps, tools):
        self.depimports += self.toolchain.depimport.build(self, writer, deps)
        super(CXXLibrary, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        if self.shared:
            self.outfiles = self.toolchain.dynlinker.build(self, writer, self.objects)
        else:
            self.outfiles = self.toolchain.archiver.build(self, writer, self.objects)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            artifact.collect("*{binary}.a", self.publishdir)
            artifact.collect("*{binary}.dll", self.publishdir)
            artifact.collect("*{binary}.lib", self.publishdir)
            artifact.collect("*{binary}.so", self.publishdir)
        artifact.cxxinfo.libpaths.append(self.publishdir)
        artifact.cxxinfo.libraries.append(self.binary)
        artifact.strings.library = fs.path.join(
            self.publishdir, fs.path.basename(self.outfiles[0]))

CXXLibrary.__doc__ += CXXProject.__doc__


@influence.attribute("strip")
class CXXExecutable(CXXProject):
    """
    Builds a C/C++ executable.
    """

    abstract = True
    selfsustained = True

    publishdir = "bin/"
    """ The artifact path where the binary is published. """

    strip = True
    """ Strip binary from debug information. """

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.strip = utils.call_or_return(self, self.__class__._strip)

    def _populate_inputs(self, writer, deps, tools):
        self.depimports += self.toolchain.depimport.build(self, writer, deps)
        super(CXXExecutable, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        self.toolchain.linker.build(self, writer, [o for o in reversed(self.objects)])

    def _strip(self):
        return utils.call_or_return(self, self.__class__.strip)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            if os.name == "nt":
                artifact.collect(self.binary + '.exe', self.publishdir)
            else:
                artifact.collect(self.binary, self.publishdir)
                if not self.strip:
                    artifact.collect(".debug", self.publishdir)
        artifact.environ.PATH.append(self.publishdir)
        artifact.strings.executable = fs.path.join(
            self.publishdir, self.binary)

CXXExecutable.__doc__ += CXXProject.__doc__
