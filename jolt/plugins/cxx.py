from jolt import MultiTask, attributes
from jolt import utils
from jolt.error import raise_task_error, raise_task_error_if
from jolt.influence import FileInfluence
from jolt.plugins import ninja

from copy import copy
import os


class GnuToolchain(object):
    gnu_ar = "ar"
    gnu_as = "as"
    gnu_cc = "gcc"
    gnu_cxx = "g++"
    gnu_ld = "g++"

    def _gnu_tool(self, env, default):
        tool = self.tools.which(self.tools.getenv(env, default))
        raise_task_error_if(not tool, self, f"Tool '{default}' not found in PATH")
        return tool

    gnu_archive_cmd = "{gnu_ar} -M <{inputs}"
    gnu_compile_asm_cmd = "{gnu_cc} -x assembler -MMD -MF {outputs}.d {asflags} -c {inputs} -o {outputs}"
    gnu_compile_asm_cpp_cmd = "{gnu_cc} -x assembler-with-cpp -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{asflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_compile_c_cmd = "{gnu_cc} -x c -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{cflags_imported} {cflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_compile_cxx_cmd = "{gnu_cxx} -x c++ -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{cxxflags_imported} {cxxflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_compile_pch_cmd = "{gnu_cxx} -x c++-header -MMD -MF {outputs}.d {% if shared %}-fPIC {% endif %}{cxxflags_imported} {cxxflags} {{(macros_imported+macros)|prefix('-D')|join(' ')}} {{(incpaths+incpaths_imported)|prefix('-I')|join(' ')}} -c {inputs} -o {outputs}"
    gnu_link_cmd = "{gnu_ld} {ldflags} @{inputs} {% if shared %}-shared {% endif %}{{(libpaths+libpaths_imported)|prefix('-L')|join(' ')}} {{(libraries+libraries_imported)|prefix('-l')|join(' ')}} -o {outputs}"

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
            srcfile = os.path.relpath(srcfile, self.joltdir)
            objfile = os.path.relpath(os.path.join(self.outdir, srcfile + ".o"), self.joltdir)
            cmd = self.tools.render(cmd, inputs=srcfile, outputs=objfile, **kwargs)
            obj = self.command(
                cmd,
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
        kwargs["asflags_imported"] = kwargs.pop("asflags_imported", self._import_listattr("asflags"))
        return self.gnu_compile_generic(self.gnu_compile_asm_cmd, sources, **kwargs)

    def gnu_compile_asm_cpp(self, sources, **kwargs):
        kwargs["gnu_as"] = self._gnu_tool("AS", self.gnu_as)

        kwargs["asflags"] = kwargs.pop("asflags", self._asflags())
        kwargs["asflags_imported"] = kwargs.pop("asflags_imported", self._import_listattr("asflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._import_pathlistattr("incpaths"))
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_pathlistattr("macros"))
        return self.gnu_compile_generic(self.gnu_compile_asm_cpp_cmd, sources, **kwargs)

    def gnu_compile_c(self, sources, **kwargs):
        kwargs["gnu_cc"] = self._gnu_tool("CC", self.gnu_cc)

        kwargs["cflags"] = kwargs.pop("cflags", self._cflags())
        kwargs["cflags_imported"] = kwargs.pop("cflags_imported", self._import_listattr("cflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._import_pathlistattr("incpaths"))
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_pathlistattr("macros"))
        return self.gnu_compile_generic(self.gnu_compile_c_cmd, sources, **kwargs)

    def gnu_compile_cxx(self, sources, **kwargs):
        kwargs["gnu_cxx"] = self._gnu_tool("CXX", self.gnu_cxx)

        kwargs["cxxflags"] = kwargs.pop("cxxflags", self._cxxflags())
        kwargs["cxxflags_imported"] = kwargs.pop("cxxflags_imported", self._import_listattr("cxxflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._import_pathlistattr("incpaths"))
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_pathlistattr("macros"))

        return self.gnu_compile_generic(self.gnu_compile_cxx_cmd, sources, **kwargs)

    def gnu_compile_h(self, sources, **kwargs):
        return []

    def gnu_compile_pch(self, sources, **kwargs):
        raise_task_error_if(hasattr(self, "_pch_objects"), self, "Multiple precompiled headers found, only one allowed")
    
        kwargs["gnu_cxx"] = self._gnu_tool("CXX", self.gnu_cxx)
        kwargs["cxxflags"] = kwargs.pop("cxxflags", self._cxxflags())
        kwargs["cxxflags_imported"] = kwargs.pop("cxxflags_imported", self._import_listattr("cxxflags"))
        kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._incpaths())
        kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._import_pathlistattr("incpaths"))
        kwargs["macros"] = kwargs.pop("macros", self._macros())
        kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_pathlistattr("macros"))

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

        kwargs["gnu_ld"] = self._gnu_tool("LD", self.gnu_ld)

        kwargs["ldflags"] = kwargs.pop("ldflags", self._ldflags())
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
        inputs = self._to_subtask_list(inputs)
        inputs = self._to_output_files(inputs)
        target = self.tools.expand(target)
        mrilist = self.render(
            "create {{target}}\n{% for input in inputs %}{% if input[-2:] == '.a' %}addlib {{input}}\n{% else %}addmod {{ input }}\n{% endif %}{% endfor %}save\nend\n",
            outputs, target=target, inputs=inputs)

        return mrilist


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
            proto_cmd = "{protoc} -I{in_path} {{(incpaths_imported+incpaths)|prefix('-I')|join(' ')}} {protoflags} --dependency_out={depfile} --{generator}_out={outdir_rel}{% if generator_plugin %} --plugin=protoc-gen-{generator}={generator_plugin}{% endif %} {inputs}"
            protoflags = []
            protogenerator = "cpp"

            def run(self, deps, tools):
                self.protoc = self._gnu_tool("PROTOC", self.protoc)
                super().run(deps, tools)

            def context(self, input=None, **kwargs):
                kwargs = copy(kwargs)

                kwargs["asflags"] = kwargs.pop("cflags", self._cflags())
                kwargs["asflags_imported"] = kwargs.pop("asflags_imported", self._import_listattr("asflags"))

                kwargs["cflags"] = kwargs.pop("cflags", self._cflags())
                kwargs["cflags_imported"] = kwargs.pop("cflags_imported", self._import_listattr("cflags"))

                kwargs["cxxflags"] = kwargs.pop("cxxflags", self._cxxflags())
                kwargs["cxxflags_imported"] = kwargs.pop("cxxflags_imported", self._import_listattr("cxxflags"))

                kwargs["incpaths"] = ["{outdir_rel}"] + kwargs.pop("incpaths", self._incpaths())
                kwargs["incpaths_imported"] = kwargs.pop("incpaths_imported", self._import_pathlistattr("incpaths"))

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
                kwargs["macros_imported"] = kwargs.pop("macros_imported", self._import_pathlistattr("macros"))

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

            def _compile_proto(self, inputs, **kwargs):
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

                generator = kwargs.get("protogenerator", getattr(self, "protogenerator"))
                proto_fn = getattr(self, "compile_proto_" + generator, None)
                raise_task_error_if(not proto_fn, self, "Protobuf generator '{}' is not supported", generator)
                proto_job = proto_fn(protobufs, **kwargs)
                proto_sources = self._to_output_files(proto_job)
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

    def filelist(self, inputs, outputs):
        inputs = self._to_subtask_list(inputs)
        inputs = self._to_output_files(inputs)
        objlist = self.render(
            "{% for input in inputs %}{{ input }}\n{% endfor %}",
            outputs, inputs=inputs)

        return objlist

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
            elif ext in [".cc", ".cpp", ".cxx"]:
                outputs.extend(self.compile_cxx(source))
            elif ext in [".h"]:
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

        return outputs

    def compile_lib(self, sources):
        return self._to_subtask_list(sources)

    def generate(self, deps, tools):
        self.deps = deps
        self.outdir = self.tools.builddir("outputs", incremental=True)
        self.outdir_rel = self.tools.expand_relpath(self.outdir, self.joltdir)

        sources = self.glob_sources(deps)
        objects = self.compile(sources)


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
        objects = self.compile(sources)
        if self.shared:
            binary = self.link(self.binary, objects)
        else:
            binary = self.archive(self.binary, objects)

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
        objects = self.compile(sources)
        binary = self.link(self.binary, objects)

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

