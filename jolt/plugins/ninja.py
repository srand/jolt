import platform
from jolt.tasks import *
from jolt import influence
from jolt import utils

import ninja_syntax as ninja


class Variable(object):
    def __init__(self, value=None):
        self._value = None

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
        writer.variable(self.name, str(getattr(project, self._attrib or self.name)))


class Rule(object):
    def __init__(self, command, variables=None, depfile=None, suffix=None,
                 prefix=None, files=None, ):
        self.command = command
        self.variables = variables
        self.depfile = depfile
        self.files = files or []
        self.prefix = prefix or ''
        self.suffix = suffix or ''

    def outfile(self, project, infile):
        dirname, basename = fs.path.split(infile)
        basename = self.prefix + basename + self.suffix
        outfile = fs.path.join(dirname, basename)
        if outfile.startswith(project.joltdir):
            outfile = outfile[len(project.joltdir)+1:]
            outfile = fs.path.join(project.outdir, outfile)
        return outfile

    def create(self, project, writer, deps, tools):
        if self.command is not None:
            writer.rule(self.name, tools.expand(self.command), depfile=self.depfile)
            writer.newline()

    def build(self, project, writer, infiles):
        outfiles = []
        for infile in utils.as_list(infiles):
            outfile = self.outfile(project, infile)
            writer.build(outfile, self.name, infile)
            outfiles.append(outfile)
        return outfiles


class Skip(Rule):
    def __init__(self, files=None):
        self.files = files
        self.command = None

    def create(self, project, writer, deps, tools):
        pass

    def build(self, project, writer, infiles):
        return None


class Objects(Rule):
    def __init__(self, files=None):
        self.files = files
        self.command = None

    def create(self, project, writer, deps, tools):
        pass

    def build(self, project, writer, infiles):
        project.objects.extend(utils.as_list(infiles))
        return None


class GNUCompiler(Rule):
    pass


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
    def build(self, project, writer, infiles):
        file_list = FileListWriter("objects")
        file_list.build(project, writer, infiles)

        outfile = self.outfile(project, project.binary)
        writer.build(outfile, self.name, infiles, implicit=project.depimports)
        return outfile


class GNUArchiver(Rule):
    def build(self, project, writer, infiles):
        file_list = FileListWriter("objects")
        file_list.build(project, writer, infiles)

        outfile = self.outfile(project, project.binary)
        writer.build(outfile, self.name, infiles, implicit=project.depimports)
        return outfile


class GNUDepImporter(Rule):
    def __init__(self, prefix=None, suffix=None):
        self.prefix = prefix
        self.suffix = suffix
        self.files = []
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
            for ext in rule.files:
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
        rule = self._rule_map.get(ext)
        assert rule, "no build rule match for file with extension '{0}'".format(ext)
        return rule

    @staticmethod
    def all_variables(cls):
        return [(key, getattr(cls, key)) for key in dir(cls)
                if isinstance(utils.getattr_safe(cls, key), Variable)]


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
        incpaths = [tools.expand_path(path) for path in project.incpaths]
        for name, artifact in deps.items():
            incpaths += [fs.path.join(artifact.stable_path, path)
                         for path in artifact.cxxinfo.incpaths.items()]
        incpaths = ["{0}{1}".format(self.prefix, path) for path in incpaths]
        writer.variable(self.name, " ".join(incpaths))


class LibraryPaths(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        if isinstance(project, CXXLibrary):
            return
        libpaths = [tools.expand_path(path) for path in project.libpaths]
        for name, artifact in deps.items():
            libpaths += [fs.path.join(artifact.stable_path, path)
                         for path in artifact.cxxinfo.libpaths.items()]
        libpaths = ["{0}{1}".format(self.prefix, path) for path in libpaths]
        writer.variable(self.name, " ".join(libpaths))


class Libraries(Variable):
    def __init__(self, prefix=None):
        self.prefix = prefix or ''

    def create(self, project, writer, deps, tools):
        if isinstance(project, CXXLibrary):
            return
        libraries = [tools.expand(lib) for lib in project._libraries()]
        for name, artifact in deps.items():
            libraries += artifact.cxxinfo.libraries.items()
        libraries = ["{0}{1}".format(self.prefix, path) for path in libraries]
        writer.variable(self.name, " ".join(libraries))


class GNUFlags(object):
    @staticmethod
    def set(flags, flag, fixup=None):
        flags = flags.split(" ")
        fixup = fixup or []
        flags = [flag for flag in flags if flag not in fixup]
        flags.append(flag)
        return " ".join(flags)


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
    hh = Skip(files=[".h", ".hh", ".hpp", ".hxx"])
    obj = Objects(files=[".o", ".obj", ".a"])

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

    macros = Macros(prefix="-D")
    incpaths = IncludePaths(prefix="-I")
    libpaths = LibraryPaths(prefix="-L")
    libraries = Libraries(prefix="-l")

    compile_c = GNUCompiler(
        command="$cc -x c $cflags $extra_cflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        depfile="$out.d",
        files=[".c"],
        suffix=".o")

    compile_cxx = GNUCompiler(
        command="$cxx -x c++ $cxxflags $extra_cxxflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        depfile="$out.d",
        files=[".cc", ".cpp", ".cxx"],
        suffix=".o")

    compile_asm = GNUCompiler(
        command="$cc -x assembler $asflags $extra_asflags -MMD -MF $out.d -c $in -o $out",
        depfile="$out.d",
        files=[".s", ".asm"],
        suffix=".o")

    compile_asm_with_cpp = GNUCompiler(
        "$cc -x assembler-with-cpp $cflags $extra_cflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        depfile="$out.d",
        files=[".S"],
        suffix=".o")

    link = GNULinker(
        command=" && ".join([
            "$ld $ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "mkdir -p $outdir/.debug",
            "$objcopy --only-keep-debug $out $outdir/.debug/$binary",
            "$objcopy --strip-all $out",
            "$objcopy --add-gnu-debuglink=$outdir/.debug/$binary $out"
        ]))

    archive = GNUArchiver(
        command="$ar cr $out @objects.list",
        prefix="lib",
        suffix=".a")

    depimport = GNUDepImporter(
        prefix="lib",
        suffix=".a")


toolchain = GNUToolchain()


@influence.attribute("incpaths")
@influence.attribute("macros")
@influence.attribute("sources")
@influence.attribute("binary")
class CXXProject(Task):
    incpaths = []
    macros = []
    sources = []
    depimports = []
    source_influence = True
    binary = None
    incremental = True
    abstract = True

    def __init__(self, *args, **kwargs):
        super(CXXProject, self).__init__(*args, **kwargs)
        self._init_sources()
        self.macros = utils.as_list(utils.call_or_return(self, self.__class__._macros))
        self.incpaths = utils.as_list(utils.call_or_return(self, self.__class__._incpaths))
        self.binary = self.__class__.binary or self.canonical_name
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
        sources = utils.as_list(utils.call_or_return(self, self.__class__._sources))
        self.sources = []
        for l in map(self.tools.glob, sources):
            self.sources += l
        self.sources.sort()

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
        assert rule, "no build rule match for file with extension '{0}'".format(ext)
        return rule

    def _populate_variables(self, writer, deps, tools):
        for name, var in Toolchain.all_variables(toolchain):
            var.create(self, writer, deps, tools)
        for name, var in Toolchain.all_variables(self):
            var.create(self, writer, deps, tools)
        writer.newline()

    def _populate_rules(self, writer, deps, tools):
        for name, rule in Toolchain.all_rules(toolchain):
            rule.create(self, writer, deps, tools)
        for name, rule in Toolchain.all_rules(self):
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

    def run(self, deps, tools):
        self.outdir = tools.builddir("build/ninja", self.incremental)
        self._write_ninja_file(self.outdir, deps, tools)
        tools.run("ninja -C {0}", self.outdir)


@influence.attribute("shared")
class CXXLibrary(CXXProject):
    abstract = True
    shared = False

    def __init__(self, *args, **kwargs):
        super(CXXLibrary, self).__init__(*args, **kwargs)

    def _populate_inputs(self, writer, deps, tools):
        self.depimports += toolchain.depimport.build(self, writer, deps)
        super(CXXLibrary, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        toolchain.archive.build(self, writer, self.objects)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            artifact.collect("*.a", "lib/")
            artifact.collect("*.so", "lib/")
            artifact.collect("*.dll", "lib/")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append(self.binary)


@influence.attribute("libpaths")
@influence.attribute("libraries")
class CXXExecutable(CXXProject):
    abstract = True
    libpaths = []
    libraries = []

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.libpaths = utils.as_list(utils.call_or_return(self, self.__class__.libpaths))
        self.libraries = utils.as_list(utils.call_or_return(self, self.__class__.libraries))

    def _populate_inputs(self, writer, deps, tools):
        self.depimports += toolchain.depimport.build(self, writer, deps)
        super(CXXExecutable, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        toolchain.link.build(self, writer, self.objects)

    def _libpaths(self):
        return utils.call_or_return(self, self.__class__.libpaths)

    def _libraries(self):
        return utils.call_or_return(self, self.__class__.libraries)

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            if platform.system() == "Windows":
                artifact.collect(self.binary + '.exe', "bin/")
            else:
                artifact.collect(self.binary, "bin/")
                artifact.collect(".debug", "bin/")
        artifact.environ.PATH.append("bin")
