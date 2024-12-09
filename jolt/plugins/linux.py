
from jolt import Task, Parameter, ListParameter
from jolt import log
from jolt import utils
from jolt.error import raise_task_error_if
from jolt.plugins import git


import os
import shutil



class ArchParameter(Parameter):
    def __init__(self, *args, **kwargs):
        kwargs["values"] = ["arm", "arm64", "x86"]
        kwargs["help"] = "Target architecture"
        super().__init__(*args, **kwargs)


class _KernelBase(Task):
    """
    Builds kernel makefile target(s) and publishes the result.

    """

    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Target architecture """

    defconfig = Parameter("allnoconfig", help="Name of kernel defconfig")
    """ Default configuration """

    features = ListParameter([], help="List of feature configs to apply")

    featurepaths = []
    """ Paths to feature configuration files """

    configpath = "arch/{arch}/configs/{defconfig}_defconfig"

    srcdir = None
    """ Location of Linux kernel source tree """

    targets = ListParameter(help="Targets to build and publish")
    """ Override and set accepted values """

    def clean(self, tools):
        self.moddir = tools.builddir("modules")
        self.objdir = tools.builddir("objects", incremental=True)
        tools.rmtree(self.moddir)
        tools.rmtree(self.objdir)

    def run(self, deps, tools):
        raise_task_error_if(not tools.which("bison"), self, "bison is required to build the kernel")
        raise_task_error_if(not tools.which("flex"), self, "flex is required to build the kernel")
        raise_task_error_if(not tools.which("make"), self, "make is required to build the kernel")

        self.objdir = tools.builddir("objects", incremental=True)

        config = tools.expand_path("{objdir}/.config")
        tools.unlink(config, ignore_errors=True)

        arch = f"ARCH={self.arch}" if self.arch else ""
        verbose = "V=1" if log.is_verbose() else ""
        defconf_conf = self.run_find_defconfig_configs(deps, tools)
        feature_confs = self.run_find_feature_configs(deps, tools)
        configpath = tools.expand(self.configpath)

        with tools.cwd(self.srcdir):
            if self.defconfig in ["allnoconfig"]:
                self.info("Generating allnoconfig configuration")
                tools.run("{} make allnoconfig O={objdir}", arch)
            else:
                self.info("Generating {defconfig} configuration")
                tools.run("{} scripts/kconfig/merge_config.sh -O {objdir} {} {} {}", arch, configpath, defconf_conf, " ".join(feature_confs))

            # Run build for each requested target
            for target in self.targets:
                fn = getattr(self, f"run_{target}", None)
                assert fn, f"Dont know how to build {target}"
                with tools.runprefix("{} make {} O={objdir} -j{}", arch, verbose, tools.thread_count()):
                    fn(deps, tools)

    def run_find_defconfig_configs(self, deps, tools):
        """ Finds local overrides for the chosen defconfig """
        configpaths = [tools.expand_path(path) for path in getattr(self, "configpaths", [])]
        return shutil.which(tools.expand("{defconfig}.cfg"), 0, os.pathsep.join(configpaths)) or ""

    def run_find_feature_configs(self, deps, tools):
        """ Finds local overrides for chosen features """
        configpaths = [tools.expand_path(path) for path in getattr(self, "configpaths", [])]
        return [shutil.which(feature + ".cfg", 0, os.pathsep.join(configpaths)) or "" for feature in self.features]

    def publish(self, artifact, tools):
        artifact.strings.arch = str(self.arch)

        for target in self.targets:
            fn = getattr(self, f"publish_{target}", None)
            assert fn, f"Dont know how to publish {target}"
            fn(artifact, tools)


class UBoot(_KernelBase):
    """
    Builds u-boot makefile target(s) and publishes the result.

    """
    abstract = True

    defconfig = Parameter("allnoconfig", help="Name of u-boot defconfig")
    """ Default configuration """

    targets = ListParameter(
        ["uboot"],
        values=["tools", "uboot"],
        help="Targets to build and publish",
    )

    def run_tools(self, deps, tools):
        self.info("Building tools ...")
        tools.run("tools")

    def run_uboot(self, deps, tools):
        self.info("Building u-boot ...")
        tools.run("u-boot.bin")

    def publish_tools(self, artifact, tools):
        self.info("Publishing tools ...")
        with tools.cwd(self.objdir):
            artifact.collect("tools/mkimage")
            artifact.environ.PATH.append("tools")

    def publish_uboot(self, artifact, tools):
        self.info("Publishing u-boot ...")
        with tools.cwd(self.objdir):
            artifact.collect("*.bin")



class Kernel(_KernelBase):
    abstract = True
    """ Must be subclassed """

    dtbs = []
    """
    List of device trees to build when the 'dtbs' target is requested.

    If empty, all device trees associated with the target architecture are built.
    """

    loadaddr = 0
    """
    Kernel load address.
    """

    loadaddr_fdt = 0
    """
    Device-tree load address.
    """

    targets = ListParameter(
        ["vmlinux"],
        values=["binary", "dtbs", "dtc", "gzimage", "image", "modules", "uimage", "vmlinux", "zimage"],
        help="Targets to build and publish",
    )

    def run_binary(self, deps, tools):
        self.info("Building binary kernel ...")
        tools.run("LOADADDR={loadaddr} vmlinux")
        objcopy = tools.getenv("OBJCOPY", tools.getenv("CROSS_COMPILE", "") + "objcopy")
        tools._run_prefix = []  # Hack to cancel previous prefix
        tools.run("{} -O binary -R .note -R .comment -S {objdir}/vmlinux {objdir}/vmlinux.bin", objcopy)

    def run_dtbs(self, deps, tools):
        self.info("Building device trees ...")
        if not self.dtbs:
            tools.run("dtbs")
        else:
            tools.run(" ".join(self.dtbs))

    def run_dtc(self, deps, tools):
        self.info("Building device tree compiler ...")
        tools.run("CONFIG_DTC=y scripts")

    def run_modules(self, deps, tools):
        self.info("Building modules ...")
        self.moddir = tools.builddir("modules")
        tools.run("INSTALL_MOD_PATH={moddir} modules")
        tools.run("INSTALL_MOD_PATH={moddir} modules_install")

    def run_image(self, deps, tools):
        self.info("Building Image ...")
        tools.run("LOADADDR={loadaddr} Image")

    def run_gzimage(self, deps, tools):
        self.info("Building Image.gz ...")
        tools.run("LOADADDR={loadaddr} Image.gz")

    def run_uimage(self, deps, tools):
        self.info("Building uImage ...")
        tools.run("LOADADDR={loadaddr} uImage")

    def run_vmlinux(self, deps, tools):
        self.info("Building vmlinux ...")
        tools.run("vmlinux")

    def run_zimage(self, deps, tools):
        self.info("Building zImage ...")
        tools.run("zImage")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)

        if self.loadaddr != 0:
            artifact.strings.loadaddr = str(self.loadaddr)
        if self.loadaddr_fdt != 0:
            artifact.strings.loadaddr_fdt = str(self.loadaddr_fdt)

    def publish_binary(self, artifact, tools):
        self.info("Publishing binary ...")
        with tools.cwd(self.objdir):
            artifact.collect("vmlinux.bin", "binary/")
            artifact.paths.binary = "binary/vmlinux.bin"

    def publish_dtbs(self, artifact, tools):
        self.info("Publishing device trees ...")
        with tools.cwd(self.objdir, "arch/{arch}/boot/dts"):
            if not self.dtbs:
                artifact.collect("**/*.dtb", "dtbs/")
            else:
                for dtb in self.dtbs:
                    artifact.collect(dtb, "dtbs/")
            artifact.paths.dtbs = "dtbs"

    def publish_dtc(self, artifact, tools):
        self.info("Publishing device tree compiler ...")
        with tools.cwd(self.objdir, "scripts/dtc"):
            artifact.collect("dtc", "bin/")
            artifact.environ.PATH.append("bin")

    def publish_modules(self, artifact, tools):
        self.info("Publishing modules ...")
        with tools.cwd(self.moddir):
            artifact.collect(".", "modules/", symlinks=True)
            artifact.paths.modules = "modules"

        with tools.cwd(self.objdir):
            if os.path.exists(tools.expand_path("Module.symvers")):
                artifact.collect("Module.symvers")
                artifact.paths.symvers = "Module.symvers"

    def publish_image(self, artifact, tools):
        self.info("Publishing Image ...")
        with tools.cwd(self.objdir, "arch/{arch}/boot"):
            artifact.collect("Image", "image/")
            artifact.paths.image = "image/Image"

    def publish_gzimage(self, artifact, tools):
        self.info("Publishing Image.gz ...")
        with tools.cwd(self.objdir, "arch/{arch}/boot"):
            artifact.collect("Image.gz", "gzimage/")
            artifact.paths.gzimage = "gzimage/Image.gz"

    def publish_uimage(self, artifact, tools):
        self.info("Publishing uImage ...")
        with tools.cwd(self.objdir, "arch/{arch}/boot"):
            artifact.collect("uImage", "uimage/")
            artifact.paths.uimage = "uimage/uImage"

    def publish_vmlinux(self, artifact, tools):
        self.info("Publishing vmlinux ...")
        with tools.cwd(self.objdir):
            artifact.collect("vmlinux", "vmlinux/")
            artifact.paths.vmlinux = "vmlinux/vmlinux"

    def publish_zimage(self, artifact, tools):
        self.info("Publishing zImage ...")
        with tools.cwd(self.objdir, "arch/{arch}/boot"):
            artifact.collect("zImage", "zimage/")
            artifact.paths.zimage = "zimage/zImage"


class Module(Kernel):
    """ Builds a kernel module from external source tree """

    abstract = True
    """ Must be subclassed """

    srcdir_module = None
    """ Path to kernel module source tree """

    def run(self, deps, tools):
        self.targets = ["modules"]
        super().run(deps, tools)

    def run_modules(self, deps, tools):
        with tools.cwd(self.objdir):
            for _, artifact in deps.items():
                if str(artifact.paths.symvers):
                    self.info("Copying Module.symvers")
                    tools.copy(str(artifact.paths.symvers), ".")

        self.info("Building modules ...")
        self.moddir = tools.builddir("modules")
        tools.run("INSTALL_MOD_PATH={moddir} modules_prepare")
        tools.run("INSTALL_MOD_PATH={moddir} M={joltdir}/{srcdir_module} modules")
        tools.run("INSTALL_MOD_PATH={moddir} M={joltdir}/{srcdir_module} modules_install")


@utils.concat_attributes("fit_configs", "fit_configs")
class FitImage(Task):
    """
    Builds and publishes a FIT Image.
    """

    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Architecture """

    fit_configs = {}
    """
    FIT configurations to create.

    Dictionary of 2 or 3 element tuples according to this format:

    fit_configs = {
      "<name of config>": ("<name of kernel task>", "<name of dtb>"),
      "<name of config with ramdisk>": ("<name of kernel task>", "<name of dtb>", "<name of ramdisk task>"),
    }

    Example:

    requires = [
      "kernel=linux/kernel:arch=arm,targets=dtbs+binary_gz,defconfig=bcm2835",
      "ramdisk=busybox/irfs:arch=armv7"
    ]

    fit_configs = {
      "conf-rpi0w": ("kernel", "bcm2835-rpi-zero-w.dtb"),
      "conf-rpi0w-irfs": ("kernel", "bcm2835-rpi-zero-w.dtb", "ramdisk"),
    }

    Loaded from defs/{defconfig}.py
    """

    fit_default = None
    """ Default FIT configuration """

    _template = """/dts-v1/;

/ {
    description = "U-Boot fitImage";

    images {
        {% for i, kernel in enumerate(_kernels) %}
        kernel@{{kernel}} {
            description = "Linux kernel";
            {% if str(deps[kernel].paths.zimage) %}
            data = /incbin/("{{deps[kernel].paths.zimage}}");
            compression = "none";
            {% elif str(deps[kernel].paths.gzimage) %}
            data = /incbin/("{{deps[kernel].paths.gzimage}}");
            compression = "gzip";
            {% elif str(deps[kernel].paths.image) %}
            data = /incbin/("{{deps[kernel].paths.image}}");
            compression = "none";
            {% else %}
            #error "Kernel type not supported."
            {% endif %}
            type = "kernel";
            arch = "{{deps[kernel].strings.arch}}";
            os = "linux";
            {% if deps[kernel].strings.loadaddr.get_value() %}
            load = <{{deps[kernel].strings.loadaddr}}>;
            entry = <{{deps[kernel].strings.loadaddr}}>;
            {% endif %}
            hash {
                algo = "sha256";
            };
        };

        {% endfor %}
        {% for kernel, dtb in _dtbs %}
        fdt@{{path.basename(dtb)}} {
            description = "Flattened Device Tree blob";
            data = /incbin/("{{deps[kernel].paths.dtbs}}/{{dtb}}");
            type = "flat_dt";
            arch = "{{deps[kernel].strings.arch}}";
            compression = "none";
            os = "linux";
            {% if deps[kernel].strings.loadaddr_fdt.get_value() %}
            load = <{{deps[kernel].strings.loadaddr_fdt}}>;
            {% endif %}
            hash {
                    algo = "sha256";
            };
        };

        {% endfor %}
        {% for ramdisk in _ramdisks %}
        ramdisk@{{ramdisk}} {
            description = "Ramdisk";
            data = /incbin/("{{deps[ramdisk].paths.ramdisk}}");
            type = "ramdisk";
            arch = "{{deps[ramdisk].strings.arch}}";
            os = "linux";
            compression = "{{deps[ramdisk].strings.compression}}";
            hash {
                algo = "sha256";
            };
        };

        {% endfor %}
    };

    configurations {
        {% if fit_default %}
        default = "conf@{{fit_default}}";
        {% endif %}

        {% for name, config in _fit_configs().items() %}
        conf@{{name}} {
                {% if len(config) > 2 %}
                description = "Linux kernel, FDT blob, Ramdisk";
                {% else %}
                description = "Linux kernel, FDT blob";
                {% endif %}
                kernel = "kernel@{{config[0]}}";
                os = "linux";
                fdt = "fdt@{{path.basename(config[1])}}";
                {% if len(config) > 2 %}
                ramdisk = "ramdisk@{{config[2]}}";
                {% endif %}

                hash {
                        algo = "sha256";
                };
                signature {
                        algo = "sha256,rsa2048";
                        key-name-hint = "{{signature_key_name}}";
                        {% if len(config) > 2 %}
                        sign-images = "kernel", "fdt", "ramdisk";
                        {% else %}
                        sign-images = "kernel", "fdt";
                        {% endif %}
                };
        };

        {% endfor %}
    };
};
    """

    signature_key_name = None
    """ Name of key used to sign image. If None, image won't be signed. """

    signature_key_path = None
    """ Directory path to signature key """


    def run(self, deps, tools):
        kernels = []
        dtbs = []
        ramdisks = []

        # Add kernels and dtbs to individual lists
        for name, config in self._fit_configs().items():
            kernels.append(config[0])
            dtbs.append((config[0], config[1]))
            try:
                ramdisks.append(config[2])
            except IndexError:
                pass
        dtbs = list(set(dtbs))
        kernels = list(set(kernels))

        # Render image device tree source template
        self.info("Rendering FIT image source file")
        its = tools.render(
            self._template,
            enumerate=enumerate,
            len=len,
            path=os.path,
            print=print,
            str=str,
            deps=deps,
            _dtbs=list(set(dtbs)),
            _kernels=list(set(kernels)),
            _ramdisks=list(set(ramdisks)))

        with tools.cwd(tools.builddir()):
            tools.write_file("fitImage.its", its, expand=False)

            self.info("Building FIT image")
            tools.run(["mkimage", "-V"], shell=False)
            tools.run(["mkimage", "-D", "-I dts -O dtb -p 2000", "-f", "fitImage.its", "fitImage"], shell=False)

            # Optionally sign the image
            if self.signature_key_name:
                self.info("Signing FIT image")
                signature_key_path = tools.expand_path(self.signature_key_path)
                tools.copy("fitImage", "fitImage.unsigned")
                tools.run(["mkimage", "-D", "-I dts -O dtb -p 2000", "-F", "-k", signature_key_path, "-r", "fitImage"], shell=False)

    def publish(self, artifact, tools):
        with tools.cwd(tools.builddir()):
            artifact.collect("fitImage")
            artifact.collect("fitImage.unsigned")
            artifact.collect("fitImage.its")
            artifact.paths.fitimage = "fitImage"
