from jolt import attributes, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["asound"])
class AlsaLib(autotools.Autotools):
    """ Advanced Linux Sound Architecture library """

    name = "alsa-lib"
    version = Parameter("1.2.16.1", help="alsa-lib version.")
    requires_src = ["fetch:alias=src,url=https://www.alsa-project.org/files/pub/lib/alsa-lib-{version}.tar.bz2"]
    srcdir = "{fetch[src]}/alsa-lib-{version}"
    options = [
        "--disable-python",
        "--with-configdir=/usr/share/alsa",
        "--with-plugindir=/usr/lib/alsa-lib",
    ]
    """ Options passed to the ``configure`` script. The configuration and plugins of the system are used at runtime. """

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(AlsaLib)
