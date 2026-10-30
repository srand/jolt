from jolt import attributes, Parameter
from jolt.pkgs import cmake, compiler, vulkan_headers, wayland, xorg
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_headers")
@attributes.requires("requires_{system}")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["vulkan"])
@attributes.requires("requires_compiler")
class VulkanLoader(cmake.CMake):
    """ Vulkan ICD loader """

    name = "vulkan-loader"
    version = Parameter("1.4.366", help="Vulkan-Loader version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/KhronosGroup/Vulkan-Loader.git,rev=v{version}"]
    requires_headers = ["vulkan-headers:version={version}"]
    requires_linux = ["wayland", "xorg/libx11", "xorg/libxcb", "xorg/libxrandr"]
    """ Libraries of the window systems that the loader supports on Linux. """
    srcdir = "{git[Vulkan-Loader]}"
    options = [
        "BUILD_TESTS=OFF",
        "SYSCONFDIR=/etc",
    ]
    """ Options passed to CMake, as ``option[:type]=value``. Drivers and layers are found in the directories of the system. """

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(VulkanLoader)
