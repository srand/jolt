from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class VulkanHeaders(cmake.CMake):
    """ Vulkan header files and API registry """

    name = "vulkan-headers"
    version = Parameter("1.4.366", help="Vulkan-Headers version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/KhronosGroup/Vulkan-Headers.git,rev=v{version}"]
    srcdir = "{git[Vulkan-Headers]}"
    options = [
        "VULKAN_HEADERS_ENABLE_MODULE=OFF",
        "VULKAN_HEADERS_ENABLE_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(VulkanHeaders)
