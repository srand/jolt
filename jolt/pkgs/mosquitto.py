from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cjson, compiler, ssl
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cjson")
@attributes.requires("requires_git")
@attributes.requires("requires_ssl_{ssl[on,off]}")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["mosquitto"])
@attributes.requires("requires_compiler")
class Mosquitto(cmake.CMake):
    """ MQTT broker, client library and command line clients """

    name = "mosquitto"
    version = Parameter("2.1.2", help="Mosquitto version.")
    ssl = BooleanParameter(True, help="Enable SSL support.")
    requires_cjson = ["cjson:pic=true"]
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/eclipse-mosquitto/mosquitto.git,rev=v{version}"]
    requires_ssl_on = ["virtual/ssl"]
    srcdir = "{git[mosquitto]}"
    # The library is always shared, and the broker loads plugins.
    # Disabled features would use libraries of the build host: readline
    # (ctrl shell), microhttpd (HTTP API), SQLite (persistence plugin) and
    # xsltproc (documentation). Mosquitto 2.1 links argon2 if found but
    # doesn't use it yet, so it isn't looked for.
    options = [
        "CMAKE_DISABLE_FIND_PACKAGE_argon2=ON",
        "WITH_CTRL_SHELL=OFF",
        "WITH_DOCS=OFF",
        "WITH_HTTP_API=OFF",
        "WITH_LTO=OFF",
        "WITH_PLUGIN_EXAMPLES=OFF",
        "WITH_PLUGIN_PERSIST_SQLITE=OFF",
        "WITH_TESTS=OFF",
        "WITH_TLS={ssl[ON,OFF]}",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        # The headers include those of cJSON, and the C++ library wraps the C library
        with tools.cwd(tools.cmake().installdir, "jolt-prefix", "lib", "pkgconfig"):
            tools.replace_in_file("libmosquitto.pc", "\nLibs:", "\nRequires: libcjson\nLibs:")
            tools.replace_in_file("libmosquittopp.pc", "\nLibs:", "\nRequires: libmosquitto\nLibs:")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.LD_LIBRARY_PATH.append("lib")
        artifact.environ.PATH.append("bin")
        artifact.environ.PATH.append("sbin")


TaskRegistry.get().add_task_class(Mosquitto)
