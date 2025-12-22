from jolt import attributes, Parameter, BooleanParameter
from jolt.pkgs import libpciaccess, meson
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_meson")
@attributes.requires("requires_{intel[intel,no_intel]}")
class Libdrm(meson.Meson):
    name = "libdrm"
    version = Parameter("2.4.131", help="Libdrm version.")

    amdgpu = BooleanParameter(True, help="Enable AMD GPU support.")
    etnaviv = BooleanParameter(True, help="Enable Etnaviv support.")
    exynos = BooleanParameter(True, help="Enable Exynos support.")
    freedreno = BooleanParameter(True, help="Enable Freedreno support.")
    intel = BooleanParameter(True, help="Enable Intel support.")
    nouveau = BooleanParameter(True, help="Enable Nouveau support.")
    omap = BooleanParameter(True, help="Enable OMAP support.")
    radeon = BooleanParameter(True, help="Enable Radeon support.")
    tegra = BooleanParameter(True, help="Enable Tegra support.")
    vc4 = BooleanParameter(True, help="Enable VC4 support.")
    vmwgfx = BooleanParameter(True, help="Enable VMware graphics support.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/mesa/drm.git,rev=libdrm-{version}"]
    requires_intel = ["libpciaccess"]
    requires_meson = ["meson"]
    srcdir = "{git[drm]}"
    options = [
        "amdgpu={amdgpu[enabled,disabled]}",
        "etnaviv={etnaviv[enabled,disabled]}",
        "exynos={exynos[enabled,disabled]}",
        "freedreno={freedreno[enabled,disabled]}",
        "intel={intel[enabled,disabled]}",
        "nouveau={nouveau[enabled,disabled]}",
        "omap={omap[enabled,disabled]}",
        "radeon={radeon[enabled,disabled]}",
        "tegra={tegra[enabled,disabled]}",
        "vc4={vc4[enabled,disabled]}",
        "vmwgfx={vmwgfx[enabled,disabled]}",
    ]


TaskRegistry.get().add_task_class(Libdrm)
