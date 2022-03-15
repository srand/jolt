import copy
from itertools import zip_longest
import ninja_syntax as ninja
import os
import sys

from jolt.tasks import Task, attributes as task_attributes
from jolt import config
from jolt.influence import DirectoryInfluence, FileInfluence
from jolt.influence import HashInfluenceProvider, TaskAttributeInfluence
from jolt import log
from jolt import utils
from jolt import filesystem as fs
from jolt.error import raise_task_error_if
from jolt.error import JoltError, JoltCommandError


class CompileError(JoltError):
    def __init__(self):
        super().__init__("Compilation failed")


class attributes:
    @staticmethod
    def asflags(attrib, prepend=False):
        """
        Decorates a task with an alternative ``asflags`` attribute.

        The new attribute will be concatenated with the regular
        ``asflags`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("asflags", attrib, prepend)

    @staticmethod
    def cflags(attrib, prepend=False):
        """
        Decorates a task with an alternative ``cflags`` attribute.

        The new attribute will be concatenated with the regular
        ``asflags`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("cflags", attrib, prepend)

    @staticmethod
    def cxxflags(attrib, prepend=False):
        """
        Decorates a task with an alternative ``cxxflags`` attribute.

        The new attribute will be concatenated with the regular
        ``cxxflags`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("cxxflags", attrib, prepend)

    @staticmethod
    def incpaths(attrib, prepend=False):
        """
        Decorates a task with an alternative ``incpaths`` attribute.

        The new attribute will be concatenated with the regular
        ``incpaths`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("incpaths", attrib, prepend)

    @staticmethod
    def ldflags(attrib, prepend=False):
        """
        Decorates a task with an alternative ``ldflags`` attribute.

        The new attribute will be concatenated with the regular
        ``ldflags`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("ldflags", attrib, prepend)

    @staticmethod
    def libpaths(attrib, prepend=False):
        """
        Decorates a task with an alternative ``libpaths`` attribute.

        The new attribute will be concatenated with the regular
        ``libpaths`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("libpaths", attrib, prepend)

    @staticmethod
    def libraries(attrib, prepend=False):
        """
        Decorates a task with an alternative ``libraries`` attribute.

        The new attribute will be concatenated with the regular
        ``libraries`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("libraries", attrib, prepend)

    @staticmethod
    def macros(attrib, prepend=False):
        """
        Decorates a task with an alternative ``macros`` attribute.

        The new attribute will be concatenated with the regular
        ``macros`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("macros", attrib, prepend)

    @staticmethod
    def sources(attrib, prepend=False):
        """
        Decorates a task with an alternative ``sources`` attribute.

        The new attribute will be concatenated with the regular
        ``sources`` attribute.

        Args:
            attrib (str): Name of alternative attribute.
                Keywords are expanded.
            prepend (boolean): Prepend the value of the alternative
                attribute. Default: false (append).
        """
        return utils.concat_attributes("sources", attrib, prepend)


class influence:
    @staticmethod
    def _list(attrib, provider=FileInfluence):
        def _decorate(cls):
            _old_influence = cls._influence

            def _influence(self, *args, **kwargs):
                influence = _old_influence(self, *args, *kwargs)
                items = getattr(self, attrib, [])
                if callable(items):
                    items = items()
                for item in items:
                    influence.append(provider(item))
                return influence

            cls._influence = _influence
            return cls
        return _decorate

    @staticmethod
    def incpaths(provider=DirectoryInfluence):
        return influence._list("_incpaths", provider)

    @staticmethod
    def libpaths(provider=DirectoryInfluence):
        return influence._list("_libpaths", provider)

    @staticmethod
    def sources(provider=FileInfluence):
        return influence._list("_sources", provider)


class Variable(HashInfluenceProvider):
    def __init__(self, value=None):
        self._value = value

    def create(self, project, writer, deps, tools):
        writer.variable(self.name, self._value)

    @utils.cached.instance
    def get_influence(self, task):
        return "V: value={}".format(self._value)


class HostVariable(Variable):
    def __init__(self, value=None):
        self._value = value

    def create(self, project, writer, deps, tools):
        writer.variable(self.name, self._value[os.name])

    @utils.cached.instance
    def get_influence(self, task):
        return "HV: value={}".format(self._value)


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

    @utils.cached.instance
    def get_influence(self, task):
        return "EV: default={},envname={},prefix={}".format(
            self._default, self._envname, self._prefix)


class ToolVariable(Variable):
    def create(self, project, writer, deps, tools):
        super().create(project, writer, deps, tools)
        executable = self._value.split()[0]
        executable_path = tools.which(executable)
        if executable_path:
            writer.variable(self.name + "_path", executable_path)

    @utils.cached.instance
    def get_influence(self, task):
        return "TV"


class ToolEnvironmentVariable(Variable):
    def __init__(self, name=None, default=None, envname=None, prefix=None, abspath=False):
        self.name = name
        self._default = default or ''
        self._envname = envname
        self._prefix = prefix or ""
        self._abspath = abspath

    def create(self, project, writer, deps, tools):
        envname = self._envname or self.name
        value = tools.getenv(envname.upper(), self._default)
        executable_and_args = value.split(maxsplit=1) or [""]
        executable = executable_and_args[0]
        executable_path = tools.which(executable)

        if executable_path:
            writer.variable(self.name + "_path", executable_path)
            if self._abspath:
                executable_and_args[0] = utils.quote_path(executable_path)

        writer.variable(self.name, self._prefix + " ".join(executable_and_args))

    @utils.cached.instance
    def get_influence(self, task):
        return "ToolEnvironment: default={},envname={},prefix={},abspath={}".format(
            self._default, self._envname, self._prefix, self._abspath)


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

    @utils.cached.instance
    def get_influence(self, task):
        return "PV: default={},attrib={}".format(self._default, self._attrib)


class SharedLibraryVariable(Variable):
    def __init__(self, name=None, default=None):
        self.name = name
        self._default = default

    def create(self, project, writer, deps, tools):
        value = self._default if isinstance(project, CXXLibrary) and project.shared else ""
        writer.variable(self.name, str(value))

    @utils.cached.instance
    def get_influence(self, task):
        return "SLV: default={}".format(self._default)


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
        writer.variable("pch_flags", "")
        writer.variable("pch_out", project._pch_out)

    @utils.cached.instance
    def get_influence(self, task):
        return "PCHV"


class Rule(HashInfluenceProvider):
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

    def __init__(self, command=None, infiles=None, outfiles=None, depfile=None, deps=None, variables=None, implicit=None, order_only=None, aggregate=False):
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

            aggregate (boolean, optional):
                When this attribute is set, the Rule will aggregate all input
                files and transform them with a single command. This is
                useful, for example, when creating linking and archiving rules.
                In aggregating rules the ``$in`` Ninja variable expands to all
                matched input files, while the ``outfiles`` / ``$out`` variable
                is expanded using the first input in the set, if the ``in_*``
                keywords are used at all.

                By default, a rule is applied once for each matched input file
                for improved parallelism.

                Example:

                  In this example, the rule concatenates all header files into
                  a single precompiled header.

                  .. code-block:: python

                    pch = Rule(
                       command="cat $in > $out",
                       infiles=["*.h"],
                       outfiles=["{outdir}/all.pch"],
                       aggregate=True)
        """
        self.command = command
        self.variables = variables or {}
        self.depfile = depfile
        self.deps = deps
        self.infiles = infiles or []
        self.outfiles = utils.as_list(outfiles or [])
        self.implicit = implicit or []
        self.order_only = order_only
        self.aggregate = aggregate

    def _out(self, project, infile):
        in_dirname, in_basename = fs.path.split(infile)
        in_base, in_ext = fs.path.splitext(in_basename)

        if in_dirname and fs.path.isabs(in_dirname):
            in_dirname = fs.path.relpath(in_dirname, project.joltdir)

        result_files = []
        for outfile in self.outfiles:
            outfile = project.tools.expand(
                outfile,
                in_path=in_dirname,
                in_base=in_base,
                in_ext=in_ext)

            if outfile.startswith(project.joltdir) and not outfile.startswith(project.outdir):
                outfile = outfile[len(project.joltdir) + 1:]
                outfile = fs.path.join(project.outdir, outfile)

            result_files.append(outfile.replace("..", "__"))

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
            command = "cmd /c " + self.command if os.name == "nt" else self.command
            writer.rule(self.name, tools.expand(command), depfile=self.depfile, deps=self.deps, description="$desc")
            writer.newline()

    def output(self, project, infiles):
        outfiles, _ = self._out(project, utils.as_list(infiles)[0])
        return outfiles

    def build(self, project, writer, infiles, implicit=None):
        result = []
        infiles = utils.as_list(infiles)
        infiles_rel = [fs.path.relpath(infile, project.outdir) for infile in infiles]
        implicit = (self.implicit or []) + (implicit or [])

        if self.aggregate:
            outfiles, variables = self._out(project, infiles[0])
            outfiles_rel = [fs.path.relpath(outfile, project.outdir) for outfile in outfiles]
            writer.build(outfiles_rel, self.name, infiles_rel, variables=variables, implicit=implicit, order_only=self.order_only)
            result.extend(outfiles)
        else:
            for infile, infile_rel in zip(infiles, infiles_rel):
                outfiles, variables = self._out(project, infile)
                outfiles_rel = [fs.path.relpath(outfile, project.outdir) for outfile in outfiles]
                writer.build(outfiles_rel, self.name, infile_rel, variables=variables, implicit=implicit, order_only=self.order_only)
                result.extend(outfiles)
        return result

    @utils.cached.instance
    def get_influence(self, task):
        return "R: cmd={},var={},in={},out={},impl={},order={},dep={}.{}".format(
            self.command, utils.as_stable_string_list(self.variables),
            self.infiles, self.outfiles, self.implicit,
            self.order_only, self.deps, self.depfile)


class Skip(Rule):
    def __init__(self, *args, **kwargs):
        super(Skip, self).__init__(*args, **kwargs)
        self.command = None

    def create(self, project, writer, deps, tools):
        pass

    def build(self, project, writer, infiles):
        return None

    @utils.cached.instance
    def get_influence(self, task):
        return "S" + super().get_influence(task)


@task_attributes.system
class MakeDirectory(Rule):
    command_linux = "mkdir -p $out"
    command_windows = "if not exist $out mkdir $out"

    def __init__(self, name):
        super(MakeDirectory, self).__init__(
            command=getattr(self, "command_" + self.system))
        self.dirname = name

    def create(self, project, writer, deps, tools):
        super().create(project, writer, deps, tools)
        writer.build(fs.path.normpath(self.dirname), self.name, [], variables={"desc": "[MKDIR] " + self.dirname})

    def build(self, project, writer, infiles):
        return None

    @utils.cached.instance
    def get_influence(self, task):
        return "MD" + super().get_influence(task)


class GNUCompiler(Rule):
    def __init__(self, *args, **kwargs):
        super(GNUCompiler, self).__init__(*args, **kwargs)

    def create(self, project, writer, deps, tools):
        super().create(project, writer, deps, tools)

    def build(self, project, writer, infiles, implicit=None):
        implicit = implicit or []
        if GNUPCHVariables.pch_ext not in self.infiles and project._pch_out is not None:
            implicit.append(project._pch_out)
        return super(GNUCompiler, self).build(project, writer, infiles, implicit)

    @utils.cached.instance
    def get_influence(self, task):
        return "GC" + super().get_influence(task)


class FileListWriter(Rule):
    def __init__(self, name, posix=False):
        self.name = name
        self.posix = posix

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
        except Exception:
            return False

        return digest == disk_digest

    def _data(self, project, files):
        data = "\n".join(files)
        return data, utils.sha1(data)

    def build(self, project, writer, infiles):
        infiles = [fs.as_posix(infile) for infile in infiles] if self.posix else infiles
        file_list_path = fs.path.join(project.outdir, "{0}.list".format(self.name))
        file_list_hash_path = fs.path.join(project.outdir, "{0}.hash".format(self.name))
        data, digest = self._data(project, infiles)
        if not self._identical(file_list_path, file_list_hash_path, data, digest):
            self._write(file_list_path, file_list_hash_path, data, digest)
        writer.depimports.append(file_list_path)

    @utils.cached.instance
    def get_influence(self, task):
        return "FL" + super().get_influence(task)


class GNUMRIWriter(FileListWriter):
    """
    Creates an AR instruction script.

    All input object files and libraries are be added to the target libary.

    """

    def __init__(self, name, outfiles):
        super().__init__(name)
        self.outfiles = outfiles

    def _data(self, project, infiles):
        data = "create {}\n".format(self.outfiles[0])
        for infile in infiles:
            _, ext = fs.path.splitext(infile)
            if ext == ".a":
                data += "addlib {}\n".format(infile)
            else:
                data += "addmod {}\n".format(infile)
        data += "save\nend\n"
        return data, utils.sha1(data)

    @utils.cached.instance
    def get_influence(self, task):
        return "MRI" + super().get_influence(task)


class GNULinker(Rule):
    def __init__(self, *args, **kwargs):
        super(GNULinker, self).__init__(*args, aggregate=True, **kwargs)

    def build(self, project, writer, infiles):
        writer._objects = infiles
        project._binaries, _ = self._out(project, project.binary)
        file_list = FileListWriter("objects", posix=True)
        file_list.build(project, writer, infiles)
        return super().build(project, writer, infiles, implicit=writer.depimports)

    @utils.cached.instance
    def get_influence(self, task):
        return "L" + super().get_influence(task)


class GNUArchiver(Rule):
    def __init__(self, *args, **kwargs):
        super(GNUArchiver, self).__init__(*args, aggregate=True, **kwargs)

    def build(self, project, writer, infiles):
        writer._objects = infiles
        project._binaries, _ = self._out(project, project.binary)
        file_list = GNUMRIWriter("objects", project._binaries)
        file_list.build(project, writer, infiles)
        super().build(project, writer, infiles, implicit=writer.depimports)

    def get_influence(self, task):
        return "GA" + super().get_influence(task)


class GNUDepImporter(Rule):
    def __init__(self, prefix=None, suffix=None):
        self.prefix = prefix
        self.suffix = suffix
        self.infiles = []
        self.command = None

    def _build_archives(self, project, writer, deps):
        archives = []
        for name, artifact in deps.items():
            if artifact.cxxinfo.libpaths.items():
                sandbox = project.tools.sandbox(artifact, project.incremental)
            for lib in artifact.cxxinfo.libraries.items():
                name = "{0}{1}{2}".format(self.prefix, lib, self.suffix)
                for path in artifact.cxxinfo.libpaths.items():
                    archive = fs.path.join(sandbox, path, name)
                    if fs.path.exists(archive):
                        archives.append(archive)
        return archives

    def build(self, project, writer, deps):
        imports = []
        if isinstance(project, CXXExecutable):
            imports += self._build_archives(project, writer, deps)
        if isinstance(project, CXXLibrary):
            imports += self._build_archives(project, writer, deps)
            if not project.shared and project.selfsustained:
                writer.sources.extend(imports)
        return imports

    def get_influence(self, task):
        return "GD" + super().get_influence(task)


class Toolchain(object):
    def __init__(self):
        self._rules_by_ext = self.build_rules_and_vars(self)

    @staticmethod
    def build_rules_and_vars(cls):
        rule_map = {}
        rules, vars = Toolchain.all_rules_and_vars(cls)
        for name, rule in rules:
            rule.name = name
            for ext in rule.infiles:
                rule_map[ext] = rule
        for name, var in vars:
            var.name = name
        return rule_map

    def find_rule(self, ext):
        return self._rules_by_ext.get(ext)

    @staticmethod
    def all_rules_and_vars(cls):
        vars = []
        rules = []
        for key in dir(cls):
            obj = getattr(cls, key)
            if isinstance(obj, Variable):
                vars.append((key, obj))
            elif isinstance(obj, Rule):
                rules.append((key, obj))
        return rules, vars

    def __str__(self):
        return self.__class__.__name__


class Macros(Variable):
    def __init__(self, prefix=None, attrib="macros", imported=True):
        self.prefix = prefix or ''
        self.attrib = attrib
        self.imported = imported

    def create(self, project, writer, deps, tools):
        macros = []
        if self.attrib:
            macros = [tools.expand(macro) for macro in getattr(project, self.attrib)]
        if self.imported:
            for _, artifact in deps.items():
                macros += artifact.cxxinfo.macros.items()
        macros = ["{0}{1}".format(self.prefix, macro) for macro in macros]
        writer.variable(self.name, " ".join(macros))

    @utils.cached.instance
    def get_influence(self, task):
        return "Macros: prefix={}".format(self.prefix)


class ImportedFlags(Variable):
    def create(self, project, writer, deps, tools):
        asflags = []
        cflags = []
        cxxflags = []
        ldflags = []
        for _, artifact in deps.items():
            asflags += artifact.cxxinfo.asflags.items()
            cflags += artifact.cxxinfo.cflags.items()
            cxxflags += artifact.cxxinfo.cxxflags.items()
            ldflags += artifact.cxxinfo.ldflags.items()
        writer.variable("imported_asflags", " ".join(asflags))
        writer.variable("imported_cflags", " ".join(cflags))
        writer.variable("imported_cxxflags", " ".join(cxxflags))
        writer.variable("imported_ldflags", " ".join(ldflags))


class IncludePaths(Variable):
    def __init__(self, prefix=None, attrib="incpaths", imported=True, outdir=True):
        self.prefix = prefix or ''
        self.outdir = outdir
        self.attrib = attrib
        self.imported = imported

    def create(self, project, writer, deps, tools):
        def expand(path):
            if path[0] in ['=', fs.sep]:
                return tools.expand(path)
            if path[0] in ['-']:
                path = tools.expand_path(path[1:])
            return tools.expand_relpath(path, project.outdir)

        def expand_artifact(sandbox, path):
            if path[0] in ['=', fs.sep]:
                return path
            if path[0] in ['-']:
                path = fs.path.join(project.joltdir, path[1:])
            return tools.expand_relpath(fs.path.join(sandbox, path), project.outdir)

        incpaths = []
        if self.outdir:
            incpaths += ["."]
        if self.attrib:
            incpaths += [expand(path) for path in getattr(project, self.attrib)]
        if self.imported:
            for _, artifact in deps.items():
                incs = artifact.cxxinfo.incpaths.items()
                if incs:
                    sandbox = tools.sandbox(artifact, project.incremental)
                    incpaths += [expand_artifact(sandbox, path) for path in incs]

        incpaths = ["{0}{1}".format(self.prefix, path) for path in incpaths]
        writer.variable(self.name, " ".join(incpaths))

    @utils.cached.instance
    def get_influence(self, task):
        return "IncludePaths: prefix={}".format(self.prefix)


class LibraryPaths(Variable):
    def __init__(self, prefix=None, attrib="libpaths", imported=True):
        self.prefix = prefix or ''
        self.attrib = attrib
        self.imported = imported

    def create(self, project, writer, deps, tools):
        if isinstance(project, CXXLibrary) and not project.shared:
            return
        libpaths = []
        if self.attrib:
            libpaths = [tools.expand_relpath(path, project.outdir) for path in getattr(project, self.attrib)]
        if self.imported:
            for _, artifact in deps.items():
                libs = artifact.cxxinfo.libpaths.items()
                if libs:
                    sandbox = tools.sandbox(artifact, project.incremental)
                    libpaths += [fs.path.join(sandbox, path) for path in libs]
        libpaths = ["{0}{1}".format(self.prefix, path) for path in libpaths]
        writer.variable(self.name, " ".join(libpaths))

    @utils.cached.instance
    def get_influence(self, task):
        return "LibraryPaths: prefix={}".format(self.prefix)


class Libraries(Variable):
    def __init__(self, prefix=None, suffix=None, attrib="libraries", imported=True):
        self.prefix = prefix or ''
        self.suffix = suffix or ''
        self.attrib = attrib
        self.imported = imported

    def create(self, project, writer, deps, tools):
        if isinstance(project, CXXLibrary) and not project.shared:
            return
        libraries = []
        if self.attrib:
            libraries = [tools.expand(lib) for lib in getattr(project, self.attrib)]
        if self.imported:
            for _, artifact in deps.items():
                libraries += artifact.cxxinfo.libraries.items()
        libraries = ["{0}{1}{2}".format(self.prefix, path, self.suffix) for path in libraries]
        writer.variable(self.name, " ".join(libraries))

    @utils.cached.instance
    def get_influence(self, task):
        return "Libraries: prefix={},suffix={}".format(self.prefix, self.suffix)


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
    bin = Skip(infiles=[".dll", ".elf", ".exe", ".out", ".so"])

    joltdir = ProjectVariable()
    outdir = ProjectVariable()
    binary = ProjectVariable()

    ar = ToolEnvironmentVariable(default="ar", abspath=True)
    cc = ToolEnvironmentVariable(default="gcc", abspath=True)
    cxx = ToolEnvironmentVariable(default="g++", abspath=True)
    ld = ToolEnvironmentVariable(default="g++", envname="CXX", abspath=True)
    objcopy = ToolEnvironmentVariable(default="objcopy", abspath=True)
    ranlib = ToolEnvironmentVariable(default="ranlib", abspath=True)
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

    mkdir_debug = MakeDirectory(name=".debug")

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
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}{in_ext}.o"],
        variables={"desc": "[C] {in_base}{in_ext}"},
        implicit=["$cc_path"])

    compile_cxx = GNUCompiler(
        command="$cxxwrap $cxx -x c++ $pch_flags $cxxflags $shared_flags $imported_cxxflags $extra_cxxflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".cc", ".cpp", ".cxx"],
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}{in_ext}.o"],
        variables={"desc": "[CXX] {in_base}{in_ext}"},
        implicit=["$cxx_path"])

    compile_asm = GNUCompiler(
        command="$ccwrap $cc -x assembler $pch_flags $asflags $shared_flags $imported_asflags $extra_asflags -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".s", ".asm"],
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}{in_ext}.o"],
        variables={"desc": "[ASM] {in_base}{in_ext}"},
        implicit=["$cc_path"])

    compile_asm_with_cpp = GNUCompiler(
        command="$ccwrap $cc -x assembler-with-cpp $pch_flags $asflags $shared_flags $imported_asflags $extra_asflags $macros $incpaths -MMD -MF $out.d -c $in -o $out",
        deps="gcc",
        depfile="$out.d",
        infiles=[".S"],
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}{in_ext}.o"],
        variables={"desc": "[ASM] {in_base}{in_ext}"},
        implicit=["$cc_path"])

    linker = GNULinker(
        command=" && ".join([
            "$ld $ldflags $imported_ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "$objcopy_path --only-keep-debug $out .debug/$binary",
            "$objcopy_path --strip-all $out",
            "$objcopy_path --add-gnu-debuglink=.debug/$binary $out"
        ]),
        infiles=[".o", ".obj", ".a"],
        outfiles=["{outdir}/{binary}"],
        variables={"desc": "[LINK] {binary}"},
        implicit=["$ld_path", "$objcopy_path", ".debug"])

    dynlinker = GNULinker(
        command=" && ".join([
            "$ld $ldflags -shared $imported_ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "$objcopy_path --only-keep-debug $out .debug/lib$binary.so",
            "$objcopy_path --strip-all $out",
            "$objcopy_path --add-gnu-debuglink=.debug/lib$binary.so $out"
        ]),
        infiles=[".o", ".obj", ".a"],
        outfiles=["{outdir}/lib{binary}.so"],
        variables={"desc": "[LINK] {binary}"},
        implicit=["$ld_path", "$objcopy_path", ".debug"])

    archiver = GNUArchiver(
        command="$ar -M < objects.list && $ranlib $out",
        infiles=[".o", ".obj", ".a"],
        outfiles=["{outdir}/lib{binary}.a"],
        variables={"desc": "[AR] lib{binary}.a"},
        implicit=["$ld_path", "$ar_path"])

    depimport = GNUDepImporter(
        prefix="lib",
        suffix=".a")


class MinGWToolchain(GNUToolchain):
    linker = GNULinker(
        command=" && ".join([
            "$ld $ldflags $imported_ldflags $extra_ldflags $libpaths -Wl,--start-group @objects.list -Wl,--end-group -o $out -Wl,--start-group $libraries -Wl,--end-group",
            "$objcopy --only-keep-debug $out .debug/$binary.exe",
            "$objcopy --strip-all $out",
            "$objcopy --add-gnu-debuglink=.debug/$binary.exe $out"
        ]),
        outfiles=["{outdir}/{binary}.exe"],
        variables={"desc": "[LINK] {binary}"},
        implicit=["$ld_path", "$objcopy_path", ".debug"])


class MSVCArchiver(Rule):
    def __init__(self, *args, **kwargs):
        super(MSVCArchiver, self).__init__(*args, aggregate=True, **kwargs)

    def build(self, project, writer, infiles):
        writer._objects = infiles
        project._binaries, _ = self._out(project, project.binary)
        file_list = FileListWriter("objects", project._binaries)
        file_list.build(project, writer, infiles)
        super().build(project, writer, infiles, implicit=writer.depimports)

    def get_influence(self, task):
        return "MSVCArchiver" + super().get_influence(task)


MSVCCompiler = GNUCompiler
MSVCLinker = GNULinker
MSVCDepImporter = GNUDepImporter


class MSVCToolchain(Toolchain):
    hh = Skip(infiles=[".h", ".hh", ".hpp", ".hxx"])
    bin = Skip(infiles=[".dll", ".exe"])

    joltdir = ProjectVariable()
    outdir = ProjectVariable()
    binary = ProjectVariable()

    cl = ToolEnvironmentVariable(default="cl", envname="cl_exe", abspath=True)
    lib = ToolEnvironmentVariable(default="lib", envname="lib_exe", abspath=True)
    link = ToolEnvironmentVariable(default="link", envname="link_exe", abspath=True)

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
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}.obj"],
        variables={"desc": "[ASM] {in_base}{in_ext}"},
        implicit=["$cl_path"])

    compile_c = MSVCCompiler(
        command="$cl /nologo /showIncludes $cxxflags $extra_cxxflags $macros $incpaths /c /Tc$in /Fo$out",
        deps="msvc",
        infiles=[".c"],
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}.obj"],
        variables={"desc": "[C] {in_base}{in_ext}"},
        implicit=["$cl_path"])

    compile_cxx = MSVCCompiler(
        command="$cl /nologo /showIncludes $cxxflags $extra_cxxflags $macros $incpaths /c /Tp$in /Fo$out",
        deps="msvc",
        infiles=[".cc", ".cpp", ".cxx"],
        outfiles=["{outdir}/{binary}.dir/{in_path}/{in_base}.obj"],
        variables={"desc": "[CXX] {in_base}{in_ext}"},
        implicit=["$cl_path"])

    linker = MSVCLinker(
        command="$link /nologo $ldflags $extra_ldflags $libpaths @objects.list $libraries /out:$out",
        infiles=[".o", ".obj", ".lib"],
        outfiles=["{outdir}/{binary}.exe"],
        variables={"desc": "[LINK] {binary}"},
        implicit=["$link_path"])

    archiver = MSVCArchiver(
        command="$lib /nologo /out:$out @objects.list",
        infiles=[".o", ".obj", ".lib"],
        outfiles=["{outdir}/{binary}.lib"],
        variables={"desc": "[LIB] {binary}"},
        implicit=["$lib_path"])

    depimport = MSVCDepImporter(
        prefix="",
        suffix=".lib")


if os.name == "nt":
    toolchain = MSVCToolchain()
else:
    toolchain = GNUToolchain()


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
        self.binary = self.expand(utils.call_or_return(self, self.__class__._binary))

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

        self.influence.append(TaskAttributeInfluence("asflags"))
        self.influence.append(TaskAttributeInfluence("cflags"))
        self.influence.append(TaskAttributeInfluence("cxxflags"))
        self.influence.append(TaskAttributeInfluence("depimports"))
        self.influence.append(TaskAttributeInfluence("incpaths"))
        self.influence.append(TaskAttributeInfluence("ldflags"))
        self.influence.append(TaskAttributeInfluence("libpaths"))
        self.influence.append(TaskAttributeInfluence("libraries"))
        self.influence.append(TaskAttributeInfluence("macros"))
        self.influence.append(TaskAttributeInfluence("sources"))
        self.influence.append(TaskAttributeInfluence("binary"))
        self.influence.append(TaskAttributeInfluence("publishdir"))
        self.influence.append(TaskAttributeInfluence("toolchain"))

        if self.source_influence:
            for source in self.sources:
                self.influence.append(FileInfluence(source))
        self._init_rules_and_vars()

    def _init_rules_and_vars(self):
        self._rules_by_ext = {}
        self._rules = []
        self._variables = []

        if isinstance(self, CXXExecutable):
            self._linker = self.toolchain.linker
        elif isinstance(self, CXXLibrary):
            if self.shared:
                self._linker = self.toolchain.dynlinker
            else:
                self._linker = self.toolchain.archiver

        rules, variables = Toolchain.all_rules_and_vars(self)
        for name, var in variables:
            var = copy.copy(var)
            setattr(self, name, var)
            var.name = name
            self._variables.append(var)
            self.influence.append(var)
        for name, rule in rules:
            rule = copy.copy(rule)
            setattr(self, name, rule)
            rule.name = name
            for ext in rule.infiles:
                self._rules_by_ext[ext] = rule
            self._rules.append(rule)
            self.influence.append(rule)

    def _init_sources(self):
        self.sources = utils.as_list(utils.call_or_return(self, self.__class__._sources))

    def _verify_influence(self, deps, artifact, tools):
        # Verify that listed sources and their dependencies are influencing
        sources = set(self.sources + getattr(self, "headers", []))
        with tools.cwd(self.outdir):
            depfiles = [obj + ".d" for obj in getattr(self._writer, "_objects", [])]
            for depfile in depfiles:
                try:
                    data = tools.read_file(depfile)
                except Exception:
                    continue
                data = data.split(":", 1)
                if len(data) <= 1:
                    continue

                depsrcs = data[1]
                depsrcs = depsrcs.split()
                depsrcs = [f.rstrip("\\").strip() for f in depsrcs]
                depsrcs = [tools.expand_relpath(dep, self.joltdir) for dep in filter(lambda n: n, depsrcs)]
                sources = sources.union(depsrcs)
        super()._verify_influence(deps, artifact, tools, sources)

    def _expand_headers(self):
        headers = []
        for header in getattr(self, "headers", []):
            list = self.tools.glob(header)
            raise_task_error_if(
                not list and not ('*' in header or '?' in header), self,
                "header file '{0}' not found", fs.path.basename(header))
            headers += list
        self.headers = headers

    def _expand_sources(self):
        sources = []
        for source in self.sources:
            list = self.tools.glob(source)
            raise_task_error_if(
                not list and not ('*' in source or '?' in source), self,
                "listed source file '{0}' not found in workspace", fs.path.basename(source))
            sources += list
        self.sources = sources

    def _write_ninja_file(self, basedir, deps, tools, filename="build.ninja"):
        self._write_ninja_cache(deps, tools)
        with open(fs.path.join(basedir, filename), "w") as fobj:
            writer = ninja.Writer(fobj)
            writer.depimports = [tools.expand_relpath(dep, self.outdir)
                                 for dep in self.depimports]
            writer.objects = []
            writer.sources = copy.copy(self.sources)
            self._populate_rules_and_variables(writer, deps, tools)
            self._populate_inputs(writer, deps, tools)
            writer.close()
            return writer

    def _write_ninja_cache(self, deps, tools):
        """ Hooked from ninja-cache plugin """

    def _write_shell_file(self, basedir, deps, tools, writer):
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
                    objects=[fs.path.relpath(o, self.outdir) for o in writer.objects]))
        tools.chmod(filepath, 0o777)

    def find_rule(self, ext):
        if not ext:
            return Skip()
        rule = self._rules_by_ext.get(ext)
        if rule is None:
            rule = self.toolchain.find_rule(ext)
        raise_task_error_if(
            not rule, self,
            "no build rule available for files with extension '{0}'", ext)
        return rule

    def _populate_rules_and_variables(self, writer, deps, tools):
        tc_rules, tc_vars = Toolchain.all_rules_and_vars(self.toolchain)

        variables = set()
        for var in self._variables:
            var.create(self, writer, deps, tools)
            variables.add(var.name)
        for name, var in tc_vars:
            if name not in variables:
                var.create(self, writer, deps, tools)
        writer.newline()

        rules = set()
        for rule in self._rules:
            rule.create(self, writer, deps, tools)
            rules.add(rule.name)
        for name, rule in tc_rules:
            if name not in rules:
                rule.create(self, writer, deps, tools)
        writer.newline()

    def _populate_inputs(self, writer, deps, tools, sources=None):
        # Source process queue
        sources = sources or writer.sources
        if not sources:
            return

        sources = list(zip_longest(copy.copy(sources), [None]))
        sources = [(tools.expand_path(source), origin) for source, origin in sources]

        # Aggregated list of sources for each rule
        rule_source_list = {}

        while sources:
            source, origin = sources.pop()
            _, ext = fs.path.splitext(source)
            rule = self.find_rule(ext)

            if rule is origin:
                # Don't feed sources back to rules from where they originated,
                # as it may cause dependency cycles.
                continue

            try:
                rule_source_list[rule].append(source)
                # Aggregating rules only have one set of outputs
                # while regular rules produce one set of outputs
                # for each input.
                if not rule.aggregate:
                    output = rule.output(self, source)
                    if output:
                        sources.extend(zip_longest(output, [rule]))
            except KeyError:
                rule_source_list[rule] = [source]
                output = rule.output(self, source)
                if output:
                    sources.extend(zip_longest(output, [rule]))

        # No more inputs/outputs to process, now emit all build rules
        for rule, source_list in rule_source_list.items():
            source_list = list(map(tools.expand_path, source_list))
            rule.build(self, writer, source_list)

        # Done
        writer.newline()

    def _populate_project(self, writer, deps, tools):
        pass

    def _binary(self):
        return utils.call_or_return(self, self.__class__.binary) or self.canonical_name

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

    def _get_keepdepfile(self, tools):
        try:
            tools.run("ninja -d list", output=False)
        except JoltCommandError as e:
            return " -d keepdepfile" if "keepdepfile" in "".join(e.stdout) else ""
        return ""

    def run(self, deps, tools):
        """
        Generates a Ninja build file and invokes Ninja to build the project.

        The build file and all intermediate files are written to a build
        directory within the workspace. By default, the directory persists
        between different invokations of Jolt to allow projects to be built
        incrementally. The behavior can be changed with the ``incremental``
        class attribute.
        """

        self._expand_headers()
        self._expand_sources()
        self.outdir = tools.builddir("ninja", self.incremental)
        self._writer = self._write_ninja_file(self.outdir, deps, tools)
        verbose = " -v" if log.is_verbose() else ""
        threads = config.get("jolt", "threads", tools.getenv("JOLT_THREADS", None))
        threads = " -j" + threads if threads else ""
        depsfile = self._get_keepdepfile(tools)
        try:
            tools.run("ninja{3}{2} -C {0} {1}", self.outdir, verbose, threads, depsfile)
        except JoltCommandError as e:
            with utils.ignore_exception(), self.report() as report:
                self._report_errors(report, "\n".join(e.stdout))
            raise CompileError()

    def shell(self, deps, tools):
        """
        Invoked to start a debug shell.

        The method prepares the environment with attributes exported by task requirement
        artifacts. The shell is entered by passing the ``-g`` flag to the build command.

        For Ninja tasks, a special ``compile`` command is made available inside
        the shell. The command can be used to compile individual source files which
        is useful when troubleshooting compilation errors. Run ``compile -h`` for
        help.

        Task execution resumes normally when exiting the shell.
        """
        self._expand_headers()
        self._expand_sources()
        self.outdir = tools.builddir("ninja", self.incremental)
        writer = self._write_ninja_file(self.outdir, deps, tools)
        self._write_shell_file(self.outdir, deps, tools, writer)
        pathenv = self.outdir + os.pathsep + tools.getenv("PATH")
        with tools.cwd(self.outdir), tools.environ(PATH=pathenv):
            print()
            print("Use the 'compile' command to build individual compilation targets")
            super(CXXProject, self).shell(deps, tools)

    def _report_errors(self, report, logbuffer):
        # GCC style errors
        report.add_regex_errors_with_file(
            "Compiler Error",
            r"(?P<location>(?P<file>.*?):(?P<line>[0-9]+):(?P<col>[0-9]+)): (?P<message>.*)",
            logbuffer,
            self.outdir,
            lambda err: not err["message"].startswith("note:"))

        # other compiler errors
        report.add_regex_errors_with_file(
            "Compiler Error",
            r"(?P<location>(?P<file>.*?)\((?P<line>[0-9]+)\)): (?P<message>error: .*)",
            logbuffer,
            self.outdir)

        # Linker errors
        report.add_regex_errors(
            "Linker Error",
            r"(?P<location>(?P<file>.*?):(.*?)): (?P<message>(undefined reference|multiple definition).*)",
            logbuffer)
        report.add_regex_errors(
            "Linker Error",
            r"(?P<location>ld): error: (?P<message>.*)",
            logbuffer)


class CXXLibrary(CXXProject):
    """
    Builds a C/C++ library.
    """

    abstract = True
    shared = False

    headers = []
    """ List of public headers to be published with the artifact """

    publishapi = "include/"
    """ The artifact path where public headers are published. """

    publishdir = "lib/"
    """ The artifact path where the library is published. """

    selfsustained = False
    """ Consume this library independently from its requirements.

    When self-sustained, all static libraries listed as requirements are merged
    into the final library. Merging can also be achieved by listing libraries
    as source files.

    See :func:`Task.selfsustained <jolt.Task.selfsustained>` for general information.
    """

    strip = True
    """
    Remove debug information from binary.

    When using the GNU toolchain, debug information is kept in a separate binary
    which is either published or not depending on the value of this attribute.
    It's found in a .debug directory if present.

    Only applicable to shared libraries.
    """

    def __init__(self, *args, **kwargs):
        super(CXXLibrary, self).__init__(*args, **kwargs)
        self.headers = utils.as_list(utils.call_or_return(self, self.__class__._headers))
        self.publishlib = self.publishdir
        if self.source_influence:
            for header in self.headers:
                self.influence.append(FileInfluence(header))
        self.influence.append(TaskAttributeInfluence("headers"))
        self.influence.append(TaskAttributeInfluence("publishapi"))
        self.influence.append(TaskAttributeInfluence("shared"))

    def _headers(self):
        return utils.call_or_return(self, self.__class__.headers)

    def _populate_inputs(self, writer, deps, tools):
        writer.depimports += self.toolchain.depimport.build(self, writer, deps)
        super(CXXLibrary, self)._populate_inputs(writer, deps, tools)

    def publish(self, artifact, tools):
        """
        Publishes the library.

        By default, the library is collected into a directory as specified
        by the ``publishdir`` class attribute. Library path metadata
        for this directory as well as linking metadata is automatically exported.
        The relative path of the library within the artifact is also exported as
        a metadata string. It can be read by consumers by accessing
        ``artifact.strings.library``.

        Public headers listed in the ``headers`` class attribute are collected into
        a directory as specified by the ``publishapi`` class attribute.
        Include path metadata for this directory is automatically exported.

        """

        with tools.cwd(self.outdir):
            if not self.shared:
                artifact.collect("*{binary}.a", self.publishlib)
                artifact.collect("*{binary}.lib", self.publishlib)
            else:
                artifact.collect("*{binary}.dll", self.publishlib)
                artifact.collect("*{binary}.so", self.publishlib)
            if self.shared and not self.strip:
                artifact.collect(".debug/*{binary}.so", self.publishdir)

        if self.headers:
            for header in self.headers:
                artifact.collect(header, self.publishapi)
            artifact.cxxinfo.incpaths.append(self.publishapi)

        if hasattr(self, "_binaries"):
            artifact.cxxinfo.libpaths.append(self.publishlib)
            artifact.cxxinfo.libraries.append(self.binary)
            artifact.strings.library = fs.path.join(
                self.publishdir, fs.path.basename(self._binaries[0]))


CXXLibrary.__doc__ += CXXProject.__doc__


class CXXExecutable(CXXProject):
    """
    Builds a C/C++ executable.
    """

    abstract = True

    selfsustained = True
    """ Consume this executable independently from its requirements.

    When self-sustained, all shared libraries listed as requirements are
    published toghether with the executable.

    See :func:`Task.selfsustained <jolt.Task.selfsustained>` for general information.
    """

    publishdir = "bin/"
    """ The artifact path where the binary is published. """

    strip = True
    """
    Remove debug information from binary.

    When using the GNU toolchain, debug information is kept in a separate binary
    which is either published or not depending on the value of this attribute.
    It's found in a .debug directory if present.

    Only applicable to shared libraries.
    """

    def __init__(self, *args, **kwargs):
        super(CXXExecutable, self).__init__(*args, **kwargs)
        self.strip = utils.call_or_return(self, self.__class__._strip)
        self.influence.append(TaskAttributeInfluence("strip"))

    def _populate_inputs(self, writer, deps, tools):
        writer.depimports += self.toolchain.depimport.build(self, writer, deps)
        super(CXXExecutable, self)._populate_inputs(writer, deps, tools)

    def _populate_project(self, writer, deps, tools):
        outputs = self.toolchain.linker.build(self, writer, [o for o in reversed(writer.objects)])
        super(CXXExecutable, self)._populate_inputs(writer, deps, tools, outputs)

    def _strip(self):
        return utils.call_or_return(self, self.__class__.strip)

    def publish(self, artifact, tools):
        """
        Publishes the linked executable.

        By default, the executable is collected into a directory as specified
        by the ``publishdir`` class attribute. The relative path of the executable
        within the artifact is exported as a metadata string. It can be read by
        consumers by accessing ``artifact.strings.executable``.

        The method appends the ``PATH`` environment variable with the path to
        the executable to allow consumers to run it easily.

        """

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
