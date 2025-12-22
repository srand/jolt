from jolt import attributes, Parameter, Task
from jolt.pkgs import cbindgen, glslang, libdrm, libglvnd, libva
from jolt.pkgs import libx11, libxshmfence, meson, rust, spirv_llvm, wayland
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cbindgen")
@attributes.requires("requires_git")
@attributes.requires("requires_glslang")
@attributes.requires("requires_libdrm")
@attributes.requires("requires_llvm")
@attributes.requires("requires_libglvnd")
@attributes.requires("requires_libva")
@attributes.requires("requires_libx11_xcb")
@attributes.requires("requires_libxshmfence")
@attributes.requires("requires_meson")
@attributes.requires("requires_rust")
@attributes.requires("requires_spirv_llvm")
@attributes.requires("requires_wayland")
@attributes.common_metadata()
class Mesa(Task):
    name = "mesa"
    version = Parameter("25.3.2", help="Mesa version.")

    requires_cbindgen = ["cbindgen"]
    requires_git = ["git:url=https://gitlab.freedesktop.org/mesa/mesa.git,rev=mesa-{version}"]
    requires_glslang = ["glslang"]
    requires_libdrm = ["libdrm"]
    requires_libglvnd = ["libglvnd"]
    requires_libx11_xcb = ["libx11-xcb"]
    requires_libxshmfence = ["libxshmfence"]
    requires_llvm = ["clang", "llvm"]
    requires_libva = ["libva"]
    requires_meson = ["meson"]
    requires_rust = ["rust", "rust-bindgen"]
    requires_spirv_llvm = ["spirv-llvm-translator"]
    requires_wayland = ["wayland"]

    def run(self, deps, tools):
        try:
            # Patch broken meson.build
            with tools.cwd("{git[mesa]}"):
                tools.replace_in_file(
                    "src/gbm/backends/dri/meson.build",
                    "deps_gbm_dri = []",
                    "deps_gbm_dri = [dep_xcb_dri3]"
                )

            ac = tools.meson()
            ac.configure(
                "{git[mesa]}",
                "buildtype=release",
                "gallium-drivers=auto",
                "glvnd=true",
                "glx=dri",
                "platforms=x11,wayland",
                "shared-llvm=disabled",
                "vulkan-drivers=auto",
            )
            ac.build()
            ac.install()
        finally:
            # Revert patch
            with tools.cwd("{git[mesa]}"):
                tools.replace_in_file(
                    "src/gbm/backends/dri/meson.build",
                    "deps_gbm_dri = [dep_xcb_dri3]",
                    "deps_gbm_dri = []"
                )

    def publish(self, artifact, tools):
        ac = tools.meson()
        ac.publish(artifact)


TaskRegistry.get().add_task_class(Mesa)
