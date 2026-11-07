from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, python, ssl
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_python")
@attributes.requires("requires_ssl_{ssl[on,off]}")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["open62541"])
@attributes.requires("requires_compiler")
class Open62541(cmake.CMake):
    """ OPC UA client and server library """

    name = "open62541"
    version = Parameter("1.5.10", help="open62541 version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    ssl = BooleanParameter(True, help="Enable SSL support.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/open62541/open62541.git,rev=v{version}"]
    # The code generators are Python scripts
    requires_python = ["python"]
    requires_ssl_on = ["virtual/ssl:shared={shared}"]
    srcdir = "{git[open62541]}"
    # Mbed TLS 4 isn't supported. The submodules are only needed by
    # multicast discovery, MQTT, the XML nodeset loader and tests.
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "UA_BUILD_EXAMPLES=OFF",
        "UA_BUILD_UNIT_TESTS=OFF",
        "UA_ENABLE_ENCRYPTION={ssl[OPENSSL,OFF]}",
        "UA_FORCE_WERROR=OFF",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
            # Shared libraries list the paths to the OpenSSL libraries of the
            # build as -l options. pkg-config finds OpenSSL by its package name.
            tools.replace_in_file("open62541.pc", r" -l/\S+", "", regex=True)
        if not self.shared:
            # The static library is useless without its dependencies, also without --static
            with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("open62541.pc", "Requires.private:", "Requires:")
                tools.replace_in_file("open62541.pc", "\nLibs.private:", "")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Open62541)
