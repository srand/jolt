import copy
import ninja_syntax as ninja
import platform
import os

from jolt.tasks import Task
from jolt import influence
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
        writer.variable(self.name, self._prefix + tools.getenv(envname.upper(), self._default))


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


class Rule(object):
    def __init__(self, command=None, infiles=None, outfiles=None, depfile=None, deps=None, variables=None):
        self.command = command
        self.variables = variables or {}
        self.depfile = depfile
        self.deps = deps
        self.infiles = infiles or []
        self.outfiles = utils.as_list(outfiles or [])

    def _out(self, project, infile):
        in_dirname, in_basename = fs.path.split(infile)
        in_base, in_ext = fs.path.splitext(in_basename)

        if in_dirname.startswith(project.joltdir):
            in_dirname = in_dirname[len(project.joltdir)+1:]

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
            writer.rule(self.name, tools.expand(self.command), depfile=self.depfile, deps=self.deps)
            writer.newline()

    def build(self, project, writer, infiles):
        result = []
        for infile in utils.as_list(infiles):
            outfiles, variables = self._out(project, infile)
            writer.build(outfiles, self.name, infile, variables=variables)
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

        outfiles, variables = self._out(project, project.binary)
        writer.build(outfiles, self.name, infiles, implicit=project.depimports, variables=variables)
        return outfiles


class GNUArchiver(Rule):
    def __init__(self, *args, **kwargs):
        super(GNUArchiver, self).__init__(*args, **kwargs)

    def build(self, project, writer, infiles):
        file_list = FileListWriter("objects")
        file_list.build(project, writer, infiles)

        outfiles, variables = self._out(project, project.binary)
        writer.build(outfiles, self.name, infiles, implicit=project.depimports, variables=variables)
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
                     archive = fs.path.join(artifact.stable_path, path, name)
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


class IncludePaths(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        def expand(path):
            if path[0] in ['=', fs.sep]:
                return tools.expand(path)
            return tools.expand_path(path)

        def expand_artifact(artifact, path):
            if path[0] in ['=', fs.sep]:
                return path
            return fs.path.join(artifact.stable_path, path)

        incpaths = [expand(path) for path in project.incpaths]
        for name, artifact in deps.items():
            incpaths += [expand_artifact(artifact, path)
                         for path in artifact.cxxinfo.incpaths.items()]
        incpaths = ["{0}{1}".format(self.prefix, path) for path in incpaths]
        writer.variable(self.name, " ".join(incpaths))


class LibraryPaths(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        if not isinstance(project, CXXExecutable):
            return
        libpaths = [tools.expand_path(path) for path in project.libpaths]
        for name, artifact in deps.items():
            libpaths += [fs.path.join(artifact.stable_path, path)
                         for path in artifact.cxxinfo.libpaths.items()]
        libpaths = ["{0}{1}".format(self.prefix, path) for path in libpaths]
        writer.variable(self.name, " ".join(libpaths))


class Libraries(Variable):
    def __init__(self, prefix=None, suffix=None):
        self.prefix = prefix or ''
        self.suffix = suffix or ''

    def create(self, project, writer, deps, tools):
        if not isinstance(project, CXXExecutable):
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
    hh = Skip(infiles=[".h", ".hh", ".hpp", ".hxx"])
    obj = Objects(infiles=[".o", ".obj", ".a"])

    joltdir = ProjectVariable()
    outdir = ProjectVariable()
    binary = ProjectVariable()

    ar = EnvironmentVariable(default="ar")
    cc = EnvironmentVariable(default="gcc")
    cxx = EnvironmentVariable(default="g++")
    ld = EnvironmentVariable(default="g++", envname="CXX")
    objcopy = EnvironmentVariable(default="objcopy")

    asflags = EnvironmentVariable(default="")
    cflags = EnvironmentVariable(default="")
    cxxflags = EnvironmentVariable(default="")
    ldflags = EnvironmentVariable(default="")

    extra_asflags = ProjectVariable(attrib="asflags")
    extra_cflags = ProjectVariable(attrib="cflags")
    extra_cxxflags = ProjectVariable(attrib="cxxflags")
    extra_ldflags = ProjectVariable(attrib="ldflags")

    macros = Macros(prefix="-D")
    incpaths = IncludePaths(prefix="-I")
    libpaths = LibraryPaths(prefix="-L")
    libraries = Libraries(prefix="-l")

    compile_c = GNUCompiler(
        command="$cc -x c $cflags $extra_cflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".c"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"])

    compile_cxx = GNUCompiler(
        command="$cxx -x c++ $cxxflags $extra_cxxflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".cc", ".cpp", ".cxx"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"])

    compile_asm = GNUCompiler(
        command="$cc -x assembler $asflags $extra_asflags -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".s", ".asm"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"])

    compile_asm_with_cpp = GNUCompiler(
        "$cc -x assembler-with-cpp $cflags $extra_cflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".S"],
        outfiles=["{outdir}/{in_path}/{in_base}.o"])

    linker = GNULinker(
        command=" && ".join([
            "$ld $ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "mkdir -p $outdir/.debug",
            "$objcopy --only-keep-debug $out $outdir/.debug/$binary",
            "$objcopy --strip-all $out",
            "$objcopy --add-gnu-debuglink=$outdir/.debug/$binary $out"
        ]),
        outfiles=["{outdir}/{binary}"])

    archiver = GNUArchiver(
        command="rm -f $out && $ar cr $out @objects.list",
        outfiles=["{outdir}/lib{binary}.a"])

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
@influence.attribute("macros")
@influence.attribute("sources")
@influence.attribute("binary")
@influence.attribute("publishdir")
@influence.attribute("toolchain")
class CXXProject(Task):
    incpaths = []
    macros = []
    sources = []
    asflags = []
    cflags = []
    cxxflags = []
    depimports = []
    publishdir = None
    source_influence = True
    binary = None
    incremental = True
    abstract = True
    toolchain = None

    def __init__(self, *args, **kwargs):
        super(CXXProject, self).__init__(*args, **kwargs)
        self._init_sources()
        self.toolchain = self.__class__.toolchain() if self.__class__.toolchain else toolchain
        self.asflags = utils.as_list(utils.call_or_return(self, self.__class__._asflags))
        self.cflags = utils.as_list(utils.call_or_return(self, self.__class__._cflags))
        self.cxxflags = utils.as_list(utils.call_or_return(self, self.__class__._cxxflags))
        self.depimports = utils.as_list(utils.call_or_return(self, self.__class__._depimports))
        self.macros = utils.as_list(utils.call_or_return(self, self.__class__._macros))
        self.incpaths = utils.as_list(utils.call_or_return(self, self.__class__._incpaths))
        self.binary = self.expand(self.__class__.binary or self.canonical_name)
        self.publishdir = self.expand(self.__class__.publishdir or '')
        if self.source_influence:
            for source in self.sources:
                self.influence.append(influence.FileInfluence(source))
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

    def _expand_sources(self):
        sources = []
        for source in self.sources:
            l = self.tools.glob(source)
            raise_task_error_if(
                not l and not ('*' in source or '?' in source), self,
                "source file '{0}' not found", fs.path.basename(source))
            sources += l
        sources.sort()
        self.sources = sources

    def _write_ninja_file(self, basedir, deps, tools):
        with open(fs.path.join(basedir, "build.ninja"), "w") as fobj:
            writer = ninja.Writer(fobj)
            self._populate_variables(writer, deps, tools)
            self._populate_rules(writer, deps, tools)
            self._populate_inputs(writer, deps, tools)
            self._populate_project(writer, deps, tools)
            writer.close()

    def find_rule(self, ext):
        rule = self._rule_map.get(ext)
        if rule is None:
            rule = toolchain.find_rule(ext)
        raise_task_error_if(
            not rule, self,
            "no build rule available for files with extension '{0}'", ext)
        return rule

    def _populate_variables(self, writer, deps, tools):
        variables = {}
        for name, var in Toolchain.all_variables(self.toolchain):
            variables[name] = var
        for name, var in Toolchain.all_variables(self):
            variables[name] = var
        for name, var in variables.items():
            var.create(self, writer, deps, tools)
        writer.newline()

    def _populate_rules(self, writer, deps, tools):
        rules = {}
        for name, rule in Toolchain.all_rules(self.toolchain):
            rules[name] = rule
        for name, rule in Toolchain.all_rules(self):
            rules[name] = rule
        for name, rule in rules.items():
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

    def run(self, deps, tools):
        self._expand_sources()
        self.outdir = tools.builddir("build/ninja", self.incremental)
        self._write_ninja_file(self.outdir, deps, tools)
        tools.run("ninja -C {0}", self.outdir)


@influence.attribute("shared")
class CXXLibrary(CXXProject):
    abstract = True
    shared = False
    publishdir = "lib/"

    def __init__(self, *args, **kwargs):
        super(CXXLibrary, self).__init__(*args, **kwargs)

    def _populate_inputs(self, writer, deps, tools):
        self.depimports += self.toolchain.depimport.build(self, writer, deps)
        super(CXXLibrary, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        self.toolchain.archiver.build(self, writer, self.objects)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            artifact.collect("*{binary}.a", "lib/")
            artifact.collect("*{binary}.dll", "lib/")
            artifact.collect("*{binary}.lib", "lib/")
            artifact.collect("*{binary}.so", "lib/")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append(self.binary)


@influence.attribute("ldflags")
@influence.attribute("libpaths")
@influence.attribute("libraries")
class CXXExecutable(CXXProject):
    abstract = True
    libpaths = []
    libraries = []
    ldflags = []
    publishdir = "bin/"

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.ldflags = utils.as_list(utils.call_or_return(self, self.__class__._ldflags))
        self.libpaths = utils.as_list(utils.call_or_return(self, self.__class__._libpaths))
        self.libraries = utils.as_list(utils.call_or_return(self, self.__class__._libraries))

    def _populate_inputs(self, writer, deps, tools):
        self.depimports += self.toolchain.depimport.build(self, writer, deps)
        super(CXXExecutable, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        self.toolchain.linker.build(self, writer, self.objects)

    def _ldflags(self):
        return utils.call_or_return(self, self.__class__.ldflags)

    def _libpaths(self):
        return utils.call_or_return(self, self.__class__.libpaths)

    def _libraries(self):
        return utils.call_or_return(self, self.__class__.libraries)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            if os.name == "nt":
                artifact.collect(self.binary + '.exe', self.publishdir)
            else:
                artifact.collect(self.binary, self.publishdir)
                artifact.collect(".debug", self.publishdir)
        artifact.environ.PATH.append(self.publishdir)
        artifact.strings.executable = fs.path.join(
            self.publishdir, self.binary)
