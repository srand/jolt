from jolt import MultiTask, attributes
from jolt import utils
from jolt.error import JoltCommandError, raise_task_error, raise_task_error_if
from jolt.influence import FileInfluence
from jolt.plugins import ninja
from jolt.plugins import ninja_modules
from jolt.tasks import DynamicSubtask

from copy import copy
import json
import os


cxx_extensions = [".cc", ".cpp", ".cxx"]
cxx_header_extensions = [".h", ".hh", ".hpp", ".hxx"]
cxx_module_extensions = ninja.cxx_module_extensions
bmi_extensions = list(ninja_modules.BMI_EXT.values())

_compiler_ids = {}


class GnuModuleCollation(DynamicSubtask):
    """
    Collates the module dependencies of the scanned C++ sources of a task,
    and expands into the subtasks that compile them.

    Dependencies added to the subtask, for example on generated headers,
    apply to the scans and compilations of all its sources.
    """

    def __init__(self, task, modules):
        super().__init__(task, modules.collate)
        self.modules = modules

    def add_dependency(self, dep):
        self.modules.add_dependency([dep for dep in utils.as_list(dep) if dep is not self])

    def add_scan(self, scan):
        super().add_dependency(scan)


class GnuModules(object):
    """
    The C++ modules of a compilation task.

    Modules must be compiled in dependency order, which is only known once
    the sources have been read. Each C++ source is therefore first scanned
    by the compiler for the modules it provides and requires. A dynamic
    subtask then collates the scan results and expands into the subtasks
    that compile the sources. A compilation outputs the compiled module
    interfaces (BMIs) of the modules its source provides, and depends on
    the BMIs of the modules it imports. A module map, written for each
    source, tells the compiler where the BMIs are.

    The standard library modules, ``std`` and ``std.compat``, are compiled
    from the sources that come with the compiler if imported and not
    published by a requirement. They are scanned and collated anew once
    found to be imported.
    """

    def __init__(self, task, deps, cxx):
        self.task = task
        self.tools = task.tools
        self.cxx = cxx
        self.compiler = self.compiler_id(self.tools, cxx)
        self.dir = os.path.join(task.outdir_rel, "modules")
        self.deps = []
        self.imported = self._import(deps)
        self.provided = {}
        self.sources = []
        self.std_sources = []
        self.collation = None
        self._kwargs = None
        self._std_modules = None

    @staticmethod
    def compiler_id(tools, cxx):
        """ Returns the kind of C++ compiler used: 'gcc' or 'clang'. """
        if cxx not in _compiler_ids:
            try:
                version = tools.run(cxx + " --version", output=False)
            except JoltCommandError:
                version = ""
            _compiler_ids[cxx] = "clang" if "clang" in version.lower() else "gcc"
        return _compiler_ids[cxx]

    def scandeps(self):
        """ Finds the clang-scan-deps that belongs to the compiler. """
        scandeps = self.tools.getenv("CLANG_SCAN_DEPS")
        if scandeps:
            return scandeps
        cxx = self.cxx.split(maxsplit=1)[0]
        dirname, basename = os.path.split(cxx)
        for name in ["clang++", "clang"]:
            if name in basename:
                scandeps = os.path.join(dirname, basename.replace(name, "clang-scan-deps"))
                if os.path.exists(scandeps):
                    return scandeps
        return self.tools.which("clang-scan-deps") or "clang-scan-deps"

    def _import(self, deps):
        """ Collects the modules published by requirements. """
        imported = {}
        for depname, artifact in deps.items():
            manifests = artifact.cxxinfo.modules.items()
            if not manifests:
                continue
            sandbox = self.tools.sandbox(artifact, self.task.incremental)
            for manifest in manifests:
                manifest = os.path.join(sandbox, manifest)
                with open(manifest) as f:
                    data = json.load(f)
                raise_task_error_if(
                    data.get("compiler") != self.compiler, self.task,
                    "C++ modules of '{0}' are compiled with {1} and can't be imported with {2}",
                    depname, data.get("compiler"), self.compiler)
                for name, module in data.get("modules", {}).items():
                    bmi = os.path.join(os.path.dirname(manifest), module["bmi"])
                    imported[name] = {
                        "bmi": self.tools.expand_relpath(bmi, self.task.joltdir),
                        "requires": module.get("requires", []),
                    }
        return imported

    def std_modules(self):
        """ Returns the sources of the standard library modules: {name: path}. """
        if self._std_modules is not None:
            return self._std_modules
        self._std_modules = {}
        for manifest in ["libstdc++.modules.json", "libc++.modules.json"]:
            try:
                path = self.tools.run("{} -print-file-name={}", self.cxx, manifest, output=False).strip()
            except JoltCommandError:
                continue
            if not os.path.isabs(path) or not os.path.exists(path):
                continue
            try:
                with open(path) as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            self._std_modules = {
                module["logical-name"]: os.path.normpath(
                    os.path.join(os.path.dirname(path), module["source-path"]))
                for module in data.get("modules", [])
                if module.get("is-std-library")
            }
            break
        return self._std_modules

    def add_dependency(self, deps):
        """ Makes the scans and compilations of all sources depend on subtasks. """
        self.deps.extend(deps)
        for source in self.sources:
            source["scan"].add_dependency(deps)

    def add(self, sources, **kwargs):
        """ Adds C++ sources to be scanned and compiled. Returns the collation subtask. """
        if self._kwargs is None:
            # Standard library modules are compiled with the flags of the first sources
            self._kwargs = kwargs
        if self.collation is None:
            self.collation = GnuModuleCollation(self.task, self)
            self.task._add_subtask(self.collation)
        for srcfile in utils.as_list(sources):
            srcfile = self.tools.expand_relpath(srcfile, self.task.joltdir)
            self._scan(srcfile, kwargs)
        return [self.collation]

    def _scan(self, srcfile, kwargs, std=False):
        """ Creates the subtask that scans a source for the modules it provides and requires. """
        task = self.task
        if std:
            objfile = os.path.join(task.outdir_rel, "std", os.path.basename(srcfile) + ".o")
        else:
            objfile = task._gnu_objfile(srcfile)
        ddi = objfile + ".ddi"

        if self.compiler == "clang":
            kwargs = dict(kwargs, gnu_scandeps=self.scandeps())
            cmd = task.gnu_scan_cxx_clang_cmd
        else:
            cmd = task.gnu_scan_cxx_cmd
        cmd = self.tools.render(cmd, inputs=srcfile, outputs=ddi, **kwargs)
        scan = task.command(cmd, srcfile, ddi, message="{inputs} [scan]", objfile=objfile, **kwargs)
        scan.add_influence_depfile(ddi + ".d")
        if self.deps:
            scan.add_dependency(self.deps)
        self.collation.add_scan(scan)

        self.sources.append({
            "source": srcfile,
            "object": objfile,
            "ddi": ddi,
            "scan": scan,
            "kwargs": kwargs,
            "std": std,
        })

    def collate(self, collation):
        """ Reads the scan results and returns the subtasks that compile the sources. """
        task = self.task
        ddis = [os.path.join(task.joltdir, source["ddi"]) for source in self.sources]
        try:
            modules = ninja_modules.Modules(ddis, None, self.compiler, self.dir)
            modules.imported = self.imported

            # Scan the standard library modules if imported, then collate again
            missing = modules.missing()
            available = self.std_modules() if missing else {}
            std_sources = [
                available[name] for name in missing
                if name in available and available[name] not in self.std_sources]
            if std_sources:
                self.std_sources.extend(std_sources)
                self.collation = GnuModuleCollation(task, self)
                task._add_subtask(self.collation)
                for source in self.sources:
                    self.collation.add_scan(source["scan"])
                for srcfile in std_sources:
                    srcfile = self.tools.expand_relpath(srcfile, task.joltdir)
                    self._scan(srcfile, self._kwargs, std=True)
                return [self.collation]

            modules.check()
        except ninja_modules.CollateError as e:
            raise_task_error(task, "{}", e)

        self.provided = {
            name: {"bmi": module["bmi"], "requires": module["requires"]}
            for name, module in modules.provided.items()
        }
        units = {unit.ddi: unit for unit in modules.units}
        return [
            self._compile(source, modules, units[os.path.join(task.joltdir, source["ddi"])])
            for source in self.sources
        ]

    def _compile(self, source, modules, unit):
        """ Creates the subtask that compiles a scanned source. """
        task = self.task
        srcfile, objfile = source["source"], source["object"]

        modmap = task.render("{{ modmap }}", objfile + ".modmap", modmap=modules.modmap(unit))
        modmap_file = modmap.outputs[0]

        if self.compiler == "clang":
            modflags = "@" + modmap_file
        else:
            modflags = "-fmodules-ts -fmodule-mapper={} -fdeps-format=p1689r5".format(modmap_file)
        if source["std"]:
            # Not the project's code: warnings are of no use
            modflags += " -w"

        kwargs = dict(source["kwargs"], modflags=modflags)
        cmd = self.tools.render(task.gnu_compile_cxx_cmd, inputs=srcfile, outputs=objfile, **kwargs)
        obj = task.command(cmd, srcfile, objfile, message="{inputs}", **kwargs)

        # The compiled interfaces of the modules provided are outputs too
        for name in unit.provides:
            bmi = modules.provided[name]["bmi"]
            obj.add_output(bmi)
            task._producers[bmi] = obj
            obj.add_dependency(task.mkdirname(bmi))

        obj.add_dependency(modmap)
        for _, bmi in modules.closure(unit):
            obj.add_dependency(bmi)
        if self.deps:
            obj.add_dependency(self.deps)
        if hasattr(task, "_pch_objects"):
            obj.add_dependency(task._pch_objects)
        obj.add_influence_depfile(objfile + ".d")
        return obj

    def manifest(self, imported=False):
        """ Returns the modules to publish: {name: {"bmi": path, "requires": [names]}}. """
        modules = dict(self.imported) if imported else {}
        modules.update(self.provided)
        return modules


class GnuToolchain(object):
    gnu_ar = "ar"
    gnu_as = "as"
    gnu_cc = "gcc"
    gnu_cxx = "g++"
    gnu_ld = "g++"

    def _gnu_tool(self, env, default):
        cmd = self.tools.getenv(env, default).split()
        tool = self.tools.which(cmd[0])
        raise_task_error_if(not tool, self, f"Tool '{default}' not found in PATH")
        cmd[0] = tool
        return " ".join(cmd)

    gnu_archive_cmd = "{gnu_ar} -M <{inputs}"
    gnu_compile_asm_cmd = "{gnu_cc} -x assembler -MMD -MF {outputs}.d {asflags} -c {inputs} -o {outputs}"
    gnu_compile_asm_cpp_cmd = "{gnu_cc} -x assembler-with-cpp -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{asflags_imported} {asflags_environ} {asflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_compile_c_cmd = "{gnu_cc} -x c -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{cflags_imported} {cflags_environ} {cflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_compile_cxx_cmd = "{gnu_cxx} -x c++ -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{cxxflags_imported} {cxxflags_environ} {cxxflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} {modflags} -c {inputs} -o {outputs}"
    gnu_scan_cxx_cmd = "{gnu_cxx} -x c++ {% if shared %}-fPIC {% endif %}{cxxflags_imported} {cxxflags_environ} {cxxflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -fmodules-ts -fdeps-format=p1689r5 -fdeps-file={outputs} -fdeps-target={objfile} -MM -MF {outputs}.d -MT {outputs} {inputs}"
    gnu_scan_cxx_clang_cmd = "{gnu_scandeps} -format=p1689 -- {gnu_cxx} -x c++ {% if shared %}-fPIC {% endif %}{cxxflags_imported} {cxxflags_environ} {cxxflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -MMD -MF {outputs}.d -MT {outputs} -c {inputs} -o {objfile} > {outputs}"
    gnu_compile_pch_cmd = "{gnu_cxx} -x c++-header -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{cxxflags_imported} {cxxflags_environ} {cxxflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_link_cmd = "{gnu_ld} {% if shared %}-shared {% endif %}{ldflags_imported} {ldflags_environ} {ldflags} -Wl,--start-group @{inputs} -Wl,--end-group {{(libpaths+libpaths_imported)|prefix('-L')|join(' ')}} -o {outputs} -Wl,--start-group {{(libraries+libraries_imported)|prefix('-l')|join(' ')}} -Wl,--end-group"

    def _gnu_objfile(self, srcfile):
        """ Returns the object file of a source file, relative to joltdir. """
        return self.tools.expand_relpath(os.path.join(self.outdir, srcfile + ".o"), self.joltdir)

    def gnu_archive(self, binary, objects, **kwargs):
        command = kwargs.pop("command", self.gnu_archive_cmd)

        kwargs["gnu_ar"] = self._gnu_tool("AR", self.gnu_ar)

        outputs = ["{outdir_rel}/lib{binary}.a"]
        objlist = self.gnu_mrilist(objects, outputs[0], "{outdir_rel}/objects.mri")
        command = self.tools.render(command, inputs=objlist, outputs=outputs, **kwargs)

        binary = self.command(
            command,
            inputs=objlist,
            outputs=outputs,
            message="{binary}",
            **kwargs)
        binary.add_dependency(objects)
        return binary

    def gnu_compile_generic(self, cmd, sources=[], **kwargs):
        objects = []

        for srcfile in utils.as_list(sources):
            srcfile = self.tools.expand_relpath(srcfile, self.joltdir)
            objfile = self._gnu_objfile(srcfile)
            rendered = self.tools.render(cmd, inputs=srcfile, outputs=objfile, **kwargs)
            obj = self.command(
                rendered,
                srcfile, objfile,
                message="{inputs}",
                **kwargs)
            obj.add_influence_depfile(objfile + ".d")
            if hasattr(self, "_pch_objects"):
                obj.add_dependency(self._pch_objects)
            objects.append(obj)

        return objects

    def gnu_compile_asm(self, sources, **kwargs):
        kwargs["gnu_as"] = self._gnu_tool("AS", self.gnu_as)

        kwargs["asflags"] = kwargs.pop("asflags", self._asflags())
        kwargs["asflags_environ"] = kwargs.pop("asflags_environ", self.tools.getenv("ASFLAGS", ""))
        kwargs["asflags_imported"] = kwargs.pop("asflags_imported", self._import_listattr("asflags"))
        return self.gnu_compile_generic(self.gnu_compile_asm_cmd, sources, **kwargs)

    def gnu_compile_asm_cpp(self, sources, **kwargs):
        kwargs["gnu_as"] = self._gnu_tool("AS", self.gnu_as)

        kwargs["asflags"] = kwargs.pop("asflags", self._asflags())
        kwargs["asflags_environ"] = kwargs.pop("asflags_environ", self.tools.getenv("ASFLAGS", ""))
        kwargs["asflags_imported"] = kwargs.pop("asflags_imported", self._import_listattr("asflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._task_incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._imported_incpaths())
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_listattr("macros"))
        return self.gnu_compile_generic(self.gnu_compile_asm_cpp_cmd, sources, **kwargs)

    def gnu_compile_c(self, sources, **kwargs):
        kwargs["gnu_cc"] = self._gnu_tool("CC", self.gnu_cc)

        kwargs["cflags"] = kwargs.pop("cflags", self._cflags())
        kwargs["cflags_environ"] = kwargs.pop("cflags_environ", self.tools.getenv("CFLAGS", ""))
        kwargs["cflags_imported"] = kwargs.pop("cflags_imported", self._import_listattr("cflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._task_incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._imported_incpaths())
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_listattr("macros"))
        return self.gnu_compile_generic(self.gnu_compile_c_cmd, sources, **kwargs)

    def gnu_compile_cxx(self, sources, **kwargs):
        kwargs["gnu_cxx"] = self._gnu_tool("CXX", self.gnu_cxx)

        kwargs["cxxflags"] = kwargs.pop("cxxflags", self._cxxflags())
        kwargs["cxxflags_environ"] = kwargs.pop("cxxflags_environ", self.tools.getenv("CXXFLAGS", ""))
        kwargs["cxxflags_imported"] = kwargs.pop("cxxflags_imported", self._import_listattr("cxxflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._task_incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._imported_incpaths())
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_listattr("macros"))

        modules = getattr(self, "_gnu_modules", None)
        if modules is not None:
            return modules.add(sources, **kwargs)

        kwargs["modflags"] = kwargs.pop("modflags", "")
        return self.gnu_compile_generic(self.gnu_compile_cxx_cmd, sources, **kwargs)

    def gnu_compile_h(self, sources, **kwargs):
        return []

    def gnu_compile_pch(self, sources, **kwargs):
        raise_task_error_if(hasattr(self, "_pch_objects"), self, "Multiple precompiled headers found, only one allowed")

        kwargs["gnu_cxx"] = self._gnu_tool("CXX", self.gnu_cxx)
        kwargs["cxxflags"] = kwargs.pop("cxxflags", self._cxxflags())
        kwargs["cxxflags_environ"] = kwargs.pop("cxxflags_environ", self.tools.getenv("CXXFLAGS", ""))
        kwargs["cxxflags_imported"] = kwargs.pop("cxxflags_imported", self._import_listattr("cxxflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._task_incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._imported_incpaths())
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_listattr("macros"))

        sources = self._to_subtask_list(sources)
        objects = []

        for srcsubtask in sources:
            for srcfile in srcsubtask.outputs:
                srcfile = os.path.relpath(srcfile, self.joltdir)
                objfile = os.path.basename(srcfile)
                objfile = os.path.relpath(os.path.join(self.outdir, objfile + ".gch"), self.joltdir)
                cmd = self.tools.render(self.gnu_compile_pch_cmd, inputs=srcfile, outputs=objfile, **kwargs)
                obj = self.command(
                    cmd,
                    srcfile, objfile,
                    message="{inputs}",
                    **kwargs)
                obj.add_influence_depfile(objfile + ".d")
                objects.append(obj)

        self._pch_objects = objects

        return objects

    def gnu_link(self, binary, objects, **kwargs):
        command = kwargs.pop("command", self.gnu_link_cmd)

        kwargs["gnu_ld"] = self._gnu_tool("CXX", self.gnu_ld)

        kwargs["ldflags"] = kwargs.pop("ldflags", self._ldflags())
        kwargs["ldflags_environ"] = kwargs.pop("ldflags_environ", self.tools.getenv("LDFLAGS", ""))
        kwargs["ldflags_imported"] = kwargs.pop("ldflags_imported", self._import_listattr("ldflags"))

        kwargs["libpaths"] = kwargs.pop("libpaths", self._libpaths())
        kwargs["libpaths_imported"] = kwargs.pop("libpaths_imported", self._import_pathlistattr("libpaths"))

        kwargs["libraries"] = kwargs.pop("libraries", self._libraries())
        kwargs["libraries_imported"] = kwargs.pop("libraries_imported", self._import_listattr("libraries"))

        objlist = self.filelist(objects, "{outdir}/objects.list")
        if getattr(self, "shared", False):
            outputs = ["{outdir_rel}/lib{binary}.so"]
        else:
            outputs = ["{outdir_rel}/{binary}"]
        command = self.tools.render(command, inputs=objlist, outputs=outputs, **kwargs)

        binary = self.command(
            command,
            inputs=objlist,
            outputs=outputs,
            message="{binary}",
            **kwargs)
        binary.add_dependency(objects)
        return binary

    def gnu_mrilist(self, inputs, target, outputs):
        target = self.tools.expand(target)

        def mrilist(inputs):
            lines = ["create " + target]
            for input in inputs:
                lines.append(("addlib " if input.endswith(".a") else "addmod ") + input)
            lines += ["save", "end"]
            return "".join(line + "\n" for line in lines)

        return self._linklist(mrilist, inputs, outputs)

    def gnu_init_modules(self, deps):
        self._gnu_modules = GnuModules(self, deps, self._gnu_tool("CXX", self.gnu_cxx))

    def gnu_import_libraries(self, deps):
        archives = []
        for name, artifact in deps.items():
            for lib in artifact.cxxinfo.libraries.items():
                name = f"lib{lib}.a"
                for path in artifact.cxxinfo.libpaths.items():
                    archive = os.path.join(artifact.path, path, name)
                    if os.path.exists(archive):
                        sandbox = self.tools.sandbox(artifact, self.incremental)
                        archive = os.path.join(sandbox, path, name)
                        archives.append(archive)
        return archives


def flatbuffer():
    def decorate(cls):
        class WithFlatbufferCompilation(cls):
            abstract = True

            flatc = "flatc"
            flatbuffer_cmd = "{{flatc}} --{{generator}} {fbflags} {{incpaths|prefix('-I ')|join(' ')}} -o {{outdir}} {inputs} && {{flatc}} -M --{{generator}} {fbflags} {{incpaths|prefix('-I ')|join(' ')}} -o {{outdir}} {inputs} > {depfile}"
            fbflags = []

            def run(self, deps, tools):
                super().run(deps, tools)

            def compile_flatbuffer(self, inputs, **kwargs):
                kwargs["flatc"] = self._gnu_tool("FLATC", self.flatc)

                jobs = []

                for input in inputs:
                    context = self.context(input, **kwargs)
                    context["generator"] = kwargs.pop("generator", "cpp")

                    command = self.tools.render(self.flatbuffer_cmd, **context)
                    depfile = self.tools.expand("{outdir}/{input}.d", input=input, **context)
                    outputs = []

                    depfiledir = self.mkdirname(depfile)

                    flatbuffer_job = self.command(
                        command,
                        inputs=input,
                        outputs=self.tools.expand(outputs, **context),
                        message="{inputs} [{generator}]",
                        depfile=depfile,
                        **context)

                    flatbuffer_job.add_dependency(depfiledir)
                    flatbuffer_job.add_influence_depfile(depfile)
                    jobs.append(flatbuffer_job)

                return jobs

            def compile(self, sources, **kwargs):
                flatbuffers, sources = self.filter_by_ext(sources, ".fbs")
                if not flatbuffers:
                    return super().compile(sources, **kwargs)

                flatbuffer_job = self.compile_flatbuffer(flatbuffers, **kwargs)
                flatbuffer_sources = self._to_output_files(flatbuffer_job)
                flatbuffer_outputs = self.compile(flatbuffer_sources, **kwargs)

                outputs = self.compile(sources, **kwargs)
                for output in outputs:
                    output.add_dependency(flatbuffer_outputs)

                return outputs + flatbuffer_outputs

        return WithFlatbufferCompilation

    return decorate


def protobuf():
    def decorate(cls):
        class WithProtobufCompilation(cls):
            abstract = True

            protoc = "protoc"
            proto_cmd = "{protoc} {{(incpaths_imported+incpaths)|prefix('-I')|join(' ')}} -I{in_path} {protoflags} --dependency_out={depfile} --{generator}_out={outdir_rel}{% if generator_plugin %} --plugin=protoc-gen-{generator}={generator_plugin}{% endif %} {inputs}"
            protoflags = []
            protogenerator = "cpp"

            def context(self, input=None, **kwargs):
                kwargs = copy(kwargs)

                kwargs["asflags"] = kwargs.pop("cflags", self._cflags())
                kwargs["asflags_imported"] = kwargs.pop("asflags_imported", self._import_listattr("asflags"))

                kwargs["cflags"] = kwargs.pop("cflags", self._cflags())
                kwargs["cflags_imported"] = kwargs.pop("cflags_imported", self._import_listattr("cflags"))

                kwargs["cxxflags"] = kwargs.pop("cxxflags", self._cxxflags())
                kwargs["cxxflags_imported"] = kwargs.pop("cxxflags_imported", self._import_listattr("cxxflags"))

                kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._task_incpaths())
                kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._imported_incpaths())

                if hasattr(self, "_ldflags"):
                    kwargs["ldflags"] = kwargs.pop("ldflags", self._ldflags())
                    kwargs["ldflags_imported"] = kwargs.pop("ldflags_imported", self._import_listattr("ldflags"))

                if hasattr(self, "_libpaths"):
                    kwargs["libpaths"] = kwargs.pop("libpaths", self._libpaths())
                    kwargs["libpaths_imported"] = kwargs.pop("libpaths_imported", self._import_pathlistattr("libpaths"))

                if hasattr(self, "_libraries"):
                    kwargs["libraries"] = kwargs.pop("libraries", self._libraries())
                    kwargs["libraries_imported"] = kwargs.pop("libraries_imported", self._import_listattr("libraries"))

                kwargs["macros"] = kwargs.pop("macros", self._macros())
                kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_listattr("macros"))

                if input:
                    kwargs["in_path"] = os.path.dirname(input) or "."
                    kwargs["in_base"], kwargs["in_ext"] = os.path.splitext(os.path.basename(input))

                return kwargs

            def compile_proto_cpp(self, inputs, **kwargs):
                depfile = "{outdir_rel}/{in_base}.pb.d"
                outputs = [
                    "{outdir_rel}/{in_base}.pb.h",
                    "{outdir_rel}/{in_base}.pb.cc",
                ]
                kwargs["depfile"] = kwargs.pop("depfile", depfile)
                kwargs["generator"] = kwargs.pop("generator", "cpp")
                kwargs["outputs"] = kwargs.pop("outputs", outputs)

                return self._compile_proto(inputs, **kwargs)

            def compile_proto_cpp_grpc(self, inputs, **kwargs):
                return self.compile_proto_cpp(inputs, **kwargs) + \
                    self.compile_proto_grpc(inputs, generator_plugin="grpc_cpp_plugin", **kwargs)

            def compile_proto_grpc(self, inputs, **kwargs):
                depfile = "{outdir_rel}/{in_base}.grpc.pb.d"
                outputs = [
                    "{outdir_rel}/{in_base}.grpc.pb.h",
                    "{outdir_rel}/{in_base}.grpc.pb.cc",
                ]
                kwargs["depfile"] = kwargs.pop("depfile", depfile)
                kwargs["generator"] = kwargs.pop("generator", "grpc")
                kwargs["generator_plugin"] = self.tools.which(kwargs.pop("generator_plugin", "grpc_cpp_plugin"))
                kwargs["outputs"] = kwargs.pop("outputs", outputs)
                return self._compile_proto(inputs, **kwargs)

            def compile_proto_python(self, inputs, **kwargs):
                depfile = "{outdir_rel}/{in_base}_pb2.py.d"
                outputs = [
                    "{outdir_rel}/{in_base}_pb2.py",
                ]
                kwargs["command"] = kwargs.pop("command", self.proto_cmd)
                kwargs["depfile"] = kwargs.pop("depfile", depfile)
                kwargs["generator"] = kwargs.pop("generator", "python")
                kwargs["outputs"] = kwargs.pop("outputs", outputs)
                return self._compile_proto(inputs, **kwargs)

            def compile_proto_python_grpc(self, inputs, **kwargs):
                depfile = "{outdir_rel}/{in_base}_pb2_grpc.py.d"
                outputs = [
                    "{outdir_rel}/{in_base}_pb2_grpc.py",
                ]
                kwargs["protoc"] = kwargs.pop("protoc", "python -m grpc_tools.protoc")
                kwargs["command"] = kwargs.pop("command", self.proto_cmd)
                kwargs["depfile"] = kwargs.pop("depfile", depfile)
                kwargs["generator"] = kwargs.pop("generator", "grpc_python")
                kwargs["outputs"] = kwargs.pop("outputs", outputs)
                return self._compile_proto(inputs, **kwargs)

            def _compile_proto(self, inputs, **kwargs):
                if "protoc" not in kwargs:
                    kwargs["protoc"] = self._gnu_tool("PROTOC", self.protoc)

                jobs = []

                for input in inputs:
                    context = self.context(input, **kwargs)

                    command = self.tools.render(context.pop("command", self.proto_cmd), **context)
                    depfile = context.pop("depfile")
                    depfile = self.tools.expand(depfile, **context)
                    outputs = context.pop("outputs")

                    proto_job = self.command(
                        command,
                        inputs=input,
                        outputs=self.tools.expand(outputs, **context),
                        message="{inputs} [{generator}]",
                        depfile=depfile,
                        **context)

                    proto_job.add_influence_depfile(depfile)
                    jobs.append(proto_job)

                return jobs

            def compile(self, sources, **kwargs):
                protobufs, sources = self.filter_by_ext(sources, ".proto")
                if not protobufs:
                    return super().compile(sources, **kwargs)

                proto_sources = []
                generators = utils.as_list(kwargs.get("protogenerator", getattr(self, "protogenerator", [])))
                for generator in generators:
                    proto_fn = getattr(self, "compile_proto_" + generator, None)
                    raise_task_error_if(not proto_fn, self, "Protobuf generator '{}' is not supported", generator)
                    proto_job = proto_fn(protobufs, **kwargs)
                    proto_sources += self._to_output_files(proto_job)
                proto_outputs = self.compile(proto_sources, **kwargs)

                outputs = self.compile(sources, **kwargs)
                for output in outputs:
                    output.add_dependency(proto_job)

                return outputs + proto_outputs

        WithProtobufCompilation.__doc__ = cls.__doc__
        WithProtobufCompilation.__name__ = cls.__name__
        return WithProtobufCompilation

    return decorate


@attributes.method("archive", "{toolchain}_archive")
@attributes.method("compile_asm", "{toolchain}_compile_asm")
@attributes.method("compile_asm_cpp", "{toolchain}_compile_asm_cpp")
@attributes.method("compile_c", "{toolchain}_compile_c")
@attributes.method("compile_cxx", "{toolchain}_compile_cxx")
@attributes.method("compile_h", "{toolchain}_compile_h")
@attributes.method("compile_pch", "{toolchain}_compile_pch")
@attributes.method("import_libraries", "{toolchain}_import_libraries")
@attributes.method("init_modules", "{toolchain}_init_modules")
@attributes.method("link", "{toolchain}_link")
@ninja.attributes.asflags("asflags")
@ninja.attributes.cflags("cflags")
@ninja.attributes.cxxflags("cxxflags")
@ninja.attributes.incpaths("incpaths")
@ninja.attributes.ldflags("ldflags")
@ninja.attributes.libpaths("libpaths")
@ninja.attributes.libraries("libraries")
@ninja.attributes.macros("macros")
@ninja.attributes.sources("sources")
@flatbuffer()
@protobuf()
class Compilation(GnuToolchain, MultiTask):
    abstract = True

    binary = "{canonical_name}"

    incremental = True

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

    toolchain = "gnu"

    cxxmodules = None
    """
    Build with support for C++ modules (boolean). Default: automatic

    With modules, each C++ source file is first scanned for the modules it
    exports and imports. The sources are then compiled in the order their
    imports dictate. A file that exports a module may have any C++ source
    file extension.

    By default, modules are used if the sources include a file with a
    module interface extension (.c++m, .ccm, .cppm, .cxxm, .ixx), or if a
    requirement publishes modules. Set the attribute to ``True`` to use
    modules in other cases, for example if the only module imported is
    ``std``. Set it to ``False`` to never scan the sources.

    The standard library modules ``std`` and ``std.compat`` are built into
    the task if imported and not published by a requirement.

    A :class:`Library` publishes its modules. Tasks that depend on the
    library can import them. The compiled module interfaces are published,
    which requires importers to use the same compiler and compatible flags.

    Only implemented for GCC (14 or later) and Clang.
    Header units are not supported.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.binary = self.expand(utils.call_or_return(self, self.__class__.binary))
        if self.source_influence:
            for source in self._sources():
                self.influence.append(FileInfluence(source))

    def _import_listattr(self, attribute):
        result = []
        for _, artifact in self.deps.items():
            result.extend(list(getattr(artifact.cxxinfo, attribute, []).items()))
        return result

    def _import_pathlistattr(self, attribute):
        result = []
        for _, artifact in self.deps.items():
            result.extend([os.path.join(artifact.path, path) for path in list(getattr(artifact.cxxinfo, attribute, []).items())])
        return result

    @utils.cached.instance
    def _task_incpaths(self):
        result = []

        for path in self._incpaths():
            if path[0] in ['=', os.sep]:
                path = self.tools.expand(path)
            if path[0] in ['-']:
                path = self.tools.expand_relpath(path[1:], self.joltdir)
            result.append(path)

        return result

    @utils.cached.instance
    def _imported_incpaths(self):
        self.depsdir = self.tools.builddir("deps", incremental=self.incremental)

        result = []
        for _, artifact in self.deps.items():
            symlink = os.path.join(self.depsdir, utils.canonical(artifact.task.short_qualified_name), artifact.name)
            self.tools.symlink(artifact.path, symlink, replace=True)

            for path in list(getattr(artifact.cxxinfo, "incpaths", []).items()):
                if path[0] in ['=', os.sep]:
                    path = self.tools.expand(path)
                    result.append(path)
                elif path[0] in ['-']:
                    path = self.tools.expand_relpath(path[1:], self.joltdir)
                    result.append(path)
                else:
                    path = os.path.join(symlink, path)
                    path = os.path.relpath(path, self.joltdir)
                    result.append(path)
        return result

    def _use_modules(self, deps, sources):
        """ Returns True if the task is to be built with support for C++ modules. """
        if self.cxxmodules is not None:
            return bool(self.cxxmodules)
        for source in sources:
            _, ext = os.path.splitext(source)
            if ext in cxx_module_extensions:
                return True
        for _, artifact in deps.items():
            if artifact.cxxinfo.modules.items():
                return True
        return False

    def _init_modules(self, deps, sources):
        self._gnu_modules = None
        if self._use_modules(deps, sources):
            self.init_modules(deps)

    def _linklist(self, fn, inputs, outputs):
        """
        Creates a subtask that writes a list of link inputs to a file.

        The list is made when the subtask is ready to run, once dynamic
        subtasks among the inputs have expanded. Compiled module interfaces
        are not linked and left out.
        """
        inputs = self._to_subtask_list(inputs)

        def files():
            return [
                path for path in self._to_output_files(inputs)
                if os.path.splitext(path)[1] not in bmi_extensions]

        def write(subtask):
            data = fn(files())
            for output in subtask.outputs:
                self.tools.write_file(output, data, expand=False)

        write.__name__ = fn.__name__
        subtask = self.call(write, outputs)
        subtask.add_influence(lambda: fn(files()))
        # Dynamic inputs must expand before the list can be made
        dynamic = [input for input in inputs if input.dynamic]
        if dynamic:
            subtask.add_dependency(dynamic)
        self._add_output_dirs(subtask)
        return subtask

    def filelist(self, inputs, outputs):
        def filelist(inputs):
            return "".join(input + "\n" for input in inputs)

        return self._linklist(filelist, inputs, outputs)

    def filter_by_ext(self, inputs, exts):
        exts = utils.as_list(exts)
        inputs = self._to_subtask_list(inputs)
        inputs = self._to_output_files(inputs)

        matches = []
        mismatches = []
        for input in inputs:
            _, ext = os.path.splitext(input)
            if ext in exts:
                matches.append(input)
            else:
                mismatches.append(input)

        return matches, mismatches

    def glob(self, paths):
        result = []
        for path in paths:
            found = self.tools.glob(path)
            raise_task_error_if(
                not found and not ('*' in path or '?' in path), self,
                "Listed source file '{0}' not found in workspace", os.path.basename(path))
            result += found
        return result

    def glob_headers(self):
        return self.glob(self._headers())

    def glob_sources(self, deps=None):
        sources_imported = self._import_pathlistattr("sources") if deps else []
        return self.glob(self._sources() + sources_imported)

    def compile(self, sources):
        outputs = []
        newsources = []

        for source in utils.as_list(sources):
            _, ext = os.path.splitext(source)
            if ext in [".pch"]:
                self.compile_pch(source)
            else:
                pass

        sources += newsources

        for source in utils.as_list(sources):
            _, ext = os.path.splitext(source)
            if ext in [".a"]:
                outputs.extend(self.compile_lib(source))
            elif ext in [".c"]:
                outputs.extend(self.compile_c(source))
            elif ext in cxx_extensions + cxx_module_extensions:
                outputs.extend(self.compile_cxx(source))
            elif ext in cxx_header_extensions:
                outputs.extend(self.compile_h(source))
            elif ext in [".pch"]:
                pass
            elif ext in [".py"]:
                pass
            elif ext in [".s"]:
                outputs.extend(self.compile_asm(source))
            elif ext in [".S"]:
                outputs.extend(self.compile_asm_cpp(source))
            else:
                raise_task_error(self, "Unknown file extension: {}", source)

        # With modules, all C++ sources share one collation subtask
        return utils.unique_list(outputs)

    def compile_lib(self, sources):
        return self._to_subtask_list(sources)

    def generate(self, deps, tools):
        self.deps = deps
        self.outdir = self.tools.builddir("outputs", incremental=True)
        self.outdir_rel = self.tools.expand_relpath(self.outdir, self.joltdir)

        sources = self.glob_sources(deps)
        self._init_modules(deps, sources)
        return self.compile(sources)


@ninja.attributes.headers("headers")
class Library(Compilation):
    abstract = True

    headers = []

    publishapi = "include/"
    """ The artifact path where the library is published. """

    publishdir = "lib/"
    """ The artifact path where the library is published. """

    shared = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.source_influence:
            for header in self._headers():
                self.influence.append(FileInfluence(header))

    def generate(self, deps, tools):
        self.deps = deps
        self.outdir = self.tools.builddir("outputs", incremental=True)
        self.outdir_rel = self.tools.expand_relpath(self.outdir, self.joltdir)

        sources = self.glob_sources(deps)
        self._init_modules(deps, sources)
        if self.selfsustained:
            sources += self.import_libraries(deps)
        objects = self.compile(sources)
        if self.shared:
            binary = self.link(self.binary, objects)
        else:
            binary = self.archive(self.binary, objects)
        return binary

    def publish(self, artifact, tools):
        for header in self._headers():
            artifact.collect(header, self.publishapi)

        with tools.cwd(self.outdir):
            if not self.shared:
                if artifact.collect("lib{binary}.a", self.publishdir):
                    artifact.cxxinfo.libpaths.append(self.publishdir)
                    artifact.cxxinfo.libraries.append("{binary}")
            else:
                if artifact.collect("lib{binary}.so", self.publishdir):
                    artifact.cxxinfo.libpaths.append(self.publishdir)
                    artifact.cxxinfo.libraries.append("{binary}")
                artifact.collect("{binary}.dll", self.publishdir)
            if artifact.collect("{binary}.lib", self.publishdir):
                artifact.cxxinfo.libpaths.append(self.publishdir)
                artifact.cxxinfo.libraries.append("{binary}")

        self.publish_modules(artifact, tools)

    def publish_modules(self, artifact, tools):
        """
        Publishes the C++ modules of the library.

        The compiled module interfaces (BMIs) are collected into the directory
        ``modules/<binary>`` within the ``publishdir`` directory, together
        with a manifest, ``modules.json``, that lists the modules, their
        BMIs and the modules they import. The path to the manifest is
        exported as metadata in ``artifact.cxxinfo.modules``.

        If the library is self-sustained, the modules of its requirements
        are published too.
        """
        modules = getattr(self, "_gnu_modules", None)
        if not modules:
            return

        published = modules.manifest(imported=self.selfsustained)
        if not published:
            return

        moddir = os.path.join(self.publishdir, "modules", self.binary)
        data = {"compiler": modules.compiler, "modules": {}}
        with tools.cwd(self.joltdir):
            for name, module in sorted(published.items()):
                artifact.collect(module["bmi"], moddir + "/", flatten=True)
                data["modules"][name] = {
                    "bmi": os.path.basename(module["bmi"]),
                    "requires": module.get("requires", []),
                }

        with tools.cwd(tools.builddir("modules")):
            tools.write_file("modules.json", json.dumps(data, indent=2, sort_keys=True) + "\n", expand=False)
            artifact.collect("modules.json", moddir + "/")
        artifact.cxxinfo.modules.append(os.path.join(moddir, "modules.json"))


class Executable(Compilation):
    abstract = True

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

    def generate(self, deps, tools):
        self.deps = deps
        self.outdir = self.tools.builddir("outputs", incremental=True)
        self.outdir_rel = self.tools.expand_relpath(self.outdir, self.joltdir)

        sources = self.glob_sources(deps)
        self._init_modules(deps, sources)
        objects = self.compile(sources)
        binary = self.link(self.binary, objects)
        return binary

    def publish(self, artifact, tools):
        with tools.cwd(self.outdir):
            if os.name == "nt":
                binary = artifact.collect(self.binary + '.exe', self.publishdir)
            else:
                binary = artifact.collect(self.binary, self.publishdir)
            if not self.strip:
                artifact.collect(".debug", self.publishdir)
            if binary:
                artifact.environ.PATH.append(self.publishdir)
                artifact.strings.executable = os.path.join(
                    self.publishdir, self.binary)
