from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cmake, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["mbedtls", "mbedx509", "tfpsacrypto"])
@attributes.requires("requires_compiler")
class MbedTls(cmake.CMake):
    """ TLS and cryptography library for embedded systems """

    name = "mbedtls"
    version = Parameter("4.2.0", help="Mbed TLS version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    # Release tarballs include the TF-PSA-Crypto submodule and the generated
    # files, which git checkouts generate with Python and Jinja.
    requires_src = ["fetch:alias=src,url=https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-{version}/mbedtls-{version}.tar.bz2"]
    srcdir = "{fetch[src]}/mbedtls-{version}"
    options = [
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "ENABLE_PROGRAMS=OFF",
        "ENABLE_TESTING=OFF",
        "GEN_FILES=OFF",
        "MBEDTLS_FATAL_WARNINGS=OFF",
        "USE_SHARED_MBEDTLS_LIBRARY={shared[ON,OFF]}",
        "USE_STATIC_MBEDTLS_LIBRARY={shared[OFF,ON]}",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        if not self.shared:
            # The static libraries are useless without the libraries they
            # require, also without --static.
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                for pc in ["mbedtls.pc", "mbedx509.pc"]:
                    tools.replace_in_file(pc, "Requires.private:", "Requires:")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(MbedTls)
