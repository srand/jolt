from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import openssl
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ssl_{ssl[on,off]}")
@cmake.requires()
@cmake.use_ninja()
class PahoMQTT_C(cmake.CMake):
    name = "paho/mqtt-c"
    version = Parameter("1.3.15", help="Paho MQTT C version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    ssl = BooleanParameter(True, help="Enable SSL support")
    requires_git = ["git:url=https://github.com/eclipse/paho.mqtt.c.git,rev=v{version}"]
    requires_ssl_on = ["openssl"]
    srcdir = "{git[paho.mqtt.c]}"
    options = [
        "PAHO_BUILD_SHARED={shared[ON,OFF]}",
        "PAHO_BUILD_STATIC={shared[OFF,ON]}",
        "PAHO_WITH_SSL={ssl[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.shared:
            artifact.cxxinfo.libraries.append("paho-mqtt3c")
        else:
            artifact.cxxinfo.libraries.append("paho-mqtt3c-static")


@attributes.requires("requires_git")
@attributes.requires("requires_mqtt_c")
@cmake.requires()
@cmake.use_ninja()
class PahoMQTT_CXX(cmake.CMake):
    name = "paho/mqtt-cxx"
    version = Parameter("1.5.2", help="Paho MQTT C++ version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    ssl = BooleanParameter(True, help="Enable SSL support")
    requires_git = ["git:url=https://github.com/eclipse/paho.mqtt.cpp.git,rev=v{version}"]
    requires_mqtt_c = ["paho/mqtt-c:shared={shared},ssl={ssl}"]
    srcdir = "{git[paho.mqtt.cpp]}"
    options = [
        "PAHO_BUILD_SHARED={shared[ON,OFF]}",
        "PAHO_BUILD_STATIC={shared[OFF,ON]}",
        "PAHO_WITH_SSL={ssl[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.shared:
            artifact.cxxinfo.libraries.append("paho-mqttpp3")
        else:
            artifact.cxxinfo.libraries.append("paho-mqttpp3-static")


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class PahoMQTT_Embedded_C(cmake.CMake):
    name = "paho/mqtt-embedded-c"
    version = "1.1.0"
    requires_git = ["git:url=https://github.com/eclipse/paho.mqtt.embedded-c.git,rev=v{version}"]
    srcdir = "{git[paho.mqtt.embedded-c]}"
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]


TaskRegistry.get().add_task_class(PahoMQTT_C)
TaskRegistry.get().add_task_class(PahoMQTT_CXX)
TaskRegistry.get().add_task_class(PahoMQTT_Embedded_C)
