import os
from jolt import attributes, Alias, BooleanParameter, Download, IntParameter, Parameter
from jolt.pkgs import cpython
from jolt.plugins import git
from jolt.tasks import Task, TaskRegistry
from jolt.error import raise_task_error_if


@attributes.common_metadata()
@attributes.requires("requires_git")
@attributes.requires("requires_python_{python[on,off]}")
@attributes.system
class Boost(Task):
    name = "boost"
    version = Parameter("1.90.0", help="Boost version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    python = BooleanParameter(False, help="Build Boost.Python")
    bits = IntParameter(64, values=[32, 64], help="Boost address-model")
    requires_git = ["git:url=https://github.com/boostorg/boost.git,path={buildroot}/git-boost,rev=boost-{version},submodules=true"]
    requires_python_on = ["cpython"]

    def write_user_config(self, deps, tools):
        content = ""

        if self.python:
            py_exe = tools.which("python3")
            raise_task_error_if(
                py_exe is None, self,
                "Boost.Python requested, but no Python interpreter found in PATH.",
            )

            # Find the dependency where the Python interpreter is located
            py_dep = None
            py_prefix = os.path.dirname(os.path.dirname(py_exe))
            for _, dep in deps.items():
                if dep.path == py_prefix:
                    py_dep = dep
                    break

            raise_task_error_if(
                py_dep is None, self,
                "Boost.Python requested, but the Python dependency could not be found.",
            )

            py_version = str(py_dep.strings.version_major)
            content += f"using python : {py_version} : {py_prefix}/bin/python{py_version} : {py_prefix}/include/python{py_version} : {py_prefix}/lib ;\n"

        tools.write_file(
            self.userconfigfile,
            content,
        )

    def clean(self, tools):
        self.builddir = tools.builddir("build", incremental=True)
        self.installdir = tools.builddir("install")
        tools.rmtree(self.builddir)
        tools.rmtree(self.installdir)

    def run(self, deps, tools):
        self.builddir = tools.builddir("build", incremental=True)
        self.installdir = tools.builddir("install")
        self.userconfigfile = tools.expand_path("{builddir}/user-config.jam")
        self.write_user_config(deps, tools)

        without_libs = []
        if not self.python:
            without_libs.append("python")

        bootstrap_cmd = []
        if without_libs:
            bootstrap_cmd = ["--without-libraries={}".format(",".join(without_libs))]

        b2_cmd = [
            "install",
            "address-model={bits}",
            "link={shared[shared,static]}",
            "--prefix={installdir}",
            "--build-dir={builddir}",
            "--user-config={userconfigfile}",
            "-j{}".format(tools.cpu_count()),
        ]

        with tools.cwd("{git[boost]}"):
            if self.system == "windows":
                bootstrap_cmd = [".\\bootstrap.bat", "msvc"] + bootstrap_cmd
                b2_cmd = [".\\b2"] + b2_cmd
            else:
                bootstrap_cmd = ["./bootstrap.sh"] + bootstrap_cmd
                b2_cmd = ["./b2"] + b2_cmd

            tools.run(" ".join(bootstrap_cmd))
            tools.run(" ".join(b2_cmd))

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")

        with tools.cwd(self.installdir, "lib"):
            for lib in tools.glob("libboost_*.a"):
                name, _ = os.path.splitext(os.path.basename(lib))
                artifact.cxxinfo.libraries.append(name[3:])

            arch = tools.getenv("VSCMD_ARG_TGT_ARCH", "x64")
            for lib in tools.glob(f"lib*-mt-{arch}-*.lib"):
                name, _ = os.path.splitext(lib)
                artifact.cxxinfo.libraries.append(name)


TaskRegistry.get().add_task_class(Boost)
