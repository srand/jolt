
from jolt import Task, Parameter, ListParameter
from jolt import attributes
from jolt import log
from jolt import utils
from jolt.error import raise_task_error_if
from jolt.plugins import podman


import os
import shutil


def linux_arch_to_container_platform(arch):
    """
    Convert Linux architecture to Podman platform.

    Args:
        arch: Linux architecture.

    Returns:
        - linux/amd64
        - linux/arm
        - linux/arm/v5
        - linux/arm64
        - linux/mips
        - linux/ppc64
        - linux/riscv64
        - linux/s390x
    """
    platforms = {
        "arm": "linux/arm",
        "arm64": "linux/arm64",
        "armv5": "linux/arm/v5",
        "mips": "linux/mips64le",
        "powerpc": "linux/ppc64le",
        "riscv": "linux/riscv64",
        "s390": "linux/s390x",
        "x86": "linux/amd64",
    }
    arch = str(arch)
    try:
        return platforms[arch]
    except KeyError:
        raise ValueError(f"Unsupported architecture {arch}")


def linux_arch_to_debian_arch(arch):
    """
    Convert Linux architecture to Debian architecture.

    Args:
        arch: Linux architecture.

    Returns:
        - amd64
        - armhf
        - arm64
        - mips
        - ppc64el
        - riscv64
        - s390x
    """
    debian_arch = {
        "amd64": "amd64",
        "arm": "armhf",
        "arm64": "arm64",
        "armv5": "armel",
        "mips": "mips",
        "powerpc": "ppc64el",
        "riscv": "riscv64",
        "s390": "s390x",
        "x86": "i386",
    }
    return debian_arch[str(arch)]


class ArchParameter(Parameter):
    """
    Linux target architecture parameter.

    Supported values:

      - amd64
      - arm
      - arm64
      - armv5
      - mips
      - powerpc
      - riscv
      - s390
      - x86

    """

    def __init__(self, *args, **kwargs):
        kwargs["values"] = [
            "amd64",
            "arm",
            "arm64",
            "armv5",
            "mips",
            "powerpc",
            "riscv",
            "s390",
            "x86",
        ]
        kwargs["help"] = "Target architecture."
        super().__init__(*args, **kwargs)


class _ContainerImageBase(podman.ContainerImage):
    """ Builds a container image from external source tree """

    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Target architecture [amd64, arm, arm64, armv5, mips, powerpc, riscv, s390, x86] """

    @property
    def target(self):
        return linux_arch_to_container_platform(self.arch)


class _DebianSdkImage(podman.ContainerImage):
    """ Provides a Debian SDK for building Linux kernel and U-Boot """

    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Target architecture """

    dockerfile = """
    FROM debian:{version}-slim
    ARG DEBIAN_FRONTEND=noninteractive
    RUN apt-get update && apt-get install -y crossbuild-essential-{debian_arch}
    """

    version = "stable"
    """ Debian codename/version """

    @property
    def debian_arch(self):
        return {
            "amd64": "amd64",
            "arm": "armhf",
            "arm64": "arm64",
            "mips": "mips",
            "powerpc": "ppc64el",
            "riscv": "riscv64",
            "s390": "s390x",
            "x86": "i386",
        }[str(self.arch)]


class DebianHostSdk(Task):
    """
    Helper task that exports a Debian host's cross-compiler toolchains to consumers.

    The task verifies that the cross-compiler toolchains are installed on the host.
    If not, the task will raise an error with instructions.

    Exported environment variables:

      - ``CC``: Cross-compiler
      - ``CPP``: Cross-preprocessor
      - ``CXX``: Cross-C++ compiler
      - ``CROSS_COMPILE``: Cross-compile prefix

    """
    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Target architecture [amd64, arm, arm64, armv5, mips, powerpc, riscv, s390, x86] """

    def publish(self, artifact, tools):
        arch_to_cross_compile = {
            "amd64": "x86_64-linux-gnu-",
            "arm": "arm-linux-gnueabihf-",
            "arm64": "aarch64-linux-gnu-",
            "armv5": "arm-linux-gnueabi-",
            "mips": "mips-linux-gnu-",
            "powerpc": "powerpc64-linux-gnu-",
            "riscv": "riscv64-linux-gnu-",
            "s390": "s390x-linux-gnu-",
            "x86": "i686-linux-gnu-",
        }
        debian_arch = linux_arch_to_debian_arch(self.arch)
        debian_cross = arch_to_cross_compile[str(self.arch)]
        raise_task_error_if(
            not tools.which(arch_to_cross_compile[str(self.arch)] + "gcc"),
            self, f"Cross compiler not found. Please install crossbuild-essential-{debian_arch} package.")
        artifact.environ.CC = f"{debian_cross}gcc"
        artifact.environ.CPP = f"{debian_cross}cpp"
        artifact.environ.CXX = f"{debian_cross}g++"
        artifact.environ.CROSS_COMPILE = debian_cross


class Initramfs(_ContainerImageBase):
    """
    Builds an initramfs image using Podman.

    The task builds the initramfs image using the given Dockerfile and
    publishes the resulting cpio archive. The task requires the following
    attributes to be set:

    - arch: Target architecture
    - dockerfile: Path to Dockerfile, or Dockerfile content.

    When building images for an architecture other than the host, the
    binfmt-support package must be installed and configured to support the
    target architecture. The package is available in most Linux distributions.

    The location of the resulting cpio archive is stored in the
    'artifact.paths.cpio' attribute.

    """
    abstract = True
    """ Must be subclassed """

    output = ["cpio"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.strings.arch = str(self.arch)
        artifact.paths.cpio = "cpio/{_imagefile}.cpio"


class Squashfs(_ContainerImageBase):
    """
    Builds a squashfs image using Podman.

    The task builds a container image using the given Dockerfile and converts
    the resulting container filesystem to a squashfs image which is published.

    When building images for an architecture other than the host, the
    binfmt-support package must be installed and configured to support running
    applications for the target architecture. The package is available in most
    Linux distributions.

    The location of the resulting squashfs image is stored in the
    ``artifact.paths.squashfs`` artifact attribute.
    """
    abstract = True
    """ Must be subclassed """

    output = ["squashfs"]

    size = None
    """
    Size of the squashfs image.

    Typically used to align the image size to a supported SD card size (power of two).

    Supported units are 'K', 'M', 'G', 'T'.
    """

    def run(self, deps, tools):
        super().run(deps, tools)
        if self.size:
            with tools.cwd(tools.builddir("squashfs")):
                tools.run("fallocate -l {size} image.squashfs")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.strings.arch = str(self.arch)
        artifact.paths.squashfs = "squashfs/{_imagefile}.squashfs"


class Ext4(_ContainerImageBase):
    """
    Builds an ext4 image using Podman.

    The task builds a container image using the given Dockerfile and converts
    the resulting container filesystem to an ext4 image which is published.

    When building images for an architecture other than the host, the
    binfmt-support package must be installed and configured to support running
    applications for the target architecture. The package is available in most
    Linux distributions.

    The location of the resulting squashfs image is stored in the
    ``artifact.paths.squashfs`` artifact attribute.
    """
    abstract = True
    """ Must be subclassed """

    output = ["ext4"]

    size = None
    """
    Size of the ext4 image.

    Typically used to align the image size to a supported SD card size (power of two).

    Supported units are 'K', 'M', 'G', 'T'.
    """

    def run(self, deps, tools):
        super().run(deps, tools)
        if self.size:
            with tools.cwd(tools.builddir("ext4")):
                tools.run("fallocate -l {size} image.ext4")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.strings.arch = str(self.arch)
        artifact.paths.ext4 = "ext4/{_imagefile}.ext4"


class _KernelBase(Task):
    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Linux target architecture [amd64, arm, arm64, mips, powerpc, riscv, s390, x86] """

    defconfig = Parameter("allnoconfig", help="Name of kernel defconfig")
    """ Default configuration """

    features = ListParameter([], help="List of feature configs to apply")
    """
    List of feature configuration snippets to apply.

    If used, the task will search for feature configuration snippets in the
    configured paths and merge them into the selected defconfig.
    """

    configpaths = [
        "{srcdir}/arch/{arch}/configs",
    ]
    """
    Paths to configuration file snippets.

    When building the kernel with features, the task will search for
    feature configuration snippets in these directories. The snippets
    are applied and merged with the selected defconfig.
    """

    defconfigpath = "arch/{arch}/configs/{defconfig}_defconfig"
    """ Path to defconfig file. """

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
        defconfigpath = tools.expand(self.defconfigpath)
        if self.defconfig in ["defconfig"]:
            defconfigpath = os.path.join(os.path.dirname(defconfigpath), "defconfig")

        with tools.cwd(self.srcdir):
            if self.defconfig in ["allnoconfig"]:
                self.info("Generating allnoconfig configuration")
                tools.run("{} make allnoconfig O={objdir}", arch)
                tools.run("{} scripts/kconfig/merge_config.sh -O {objdir} {objdir}/.config {} {}", arch, defconf_conf, " ".join(feature_confs))
            else:
                self.info("Generating {defconfig} configuration")
                tools.run("{} scripts/kconfig/merge_config.sh -O {objdir} {} {} {}", arch, defconfigpath, defconf_conf, " ".join(feature_confs))

            # Run build for each requested target
            for target in self.targets:
                fn = getattr(self, f"run_{target}", None)
                assert fn, f"Dont know how to build {target}"
                with tools.runprefix("{} make {} O={objdir} -j{}", arch, verbose, tools.thread_count()):
                    fn(deps, tools)

    def run_find_defconfig_configs(self, deps, tools):
        """ Finds local overrides for the chosen defconfig """
        configpaths = [tools.expand_path(tools.expand(path)) for path in getattr(self, "configpaths", [])]
        return shutil.which(tools.expand("{defconfig}.config"), os.F_OK, os.pathsep.join(configpaths)) or ""

    def run_find_feature_configs(self, deps, tools):
        """ Finds local overrides for chosen features """
        configpaths = [tools.expand_path(tools.expand(path)) for path in getattr(self, "configpaths", [])]
        return [shutil.which(feature + ".config", os.F_OK, os.pathsep.join(configpaths)) or "" for feature in self.features]

    def publish(self, artifact, tools):
        artifact.strings.arch = str(self.arch)

        for target in self.targets:
            fn = getattr(self, f"publish_{target}", None)
            assert fn, f"Dont know how to publish {target}"
            fn(artifact, tools)


class UBoot(_KernelBase):
    """
    Builds u-boot makefile target(s) and publishes the result.

    An implementor must subclass this task and set the following attributes:

      - srcdir: Path to U-boot source tree

    It is recommended to use a task dependency to setup the
    required tools by adding them to ``PATH`` and/or setting the ``CROSS_COMPILE``
    environment variable. When building on a Debian host, the
    :class:`jolt.plugins.linux.DebianHostSdk` helper task can be used to export
    the cross-compiler tools.

    """
    abstract = True

    defconfig = Parameter("allnoconfig", help="Name of u-boot defconfig")
    """ Default configuration """

    targets = ListParameter(
        ["uboot"],
        values=["tools", "uboot"],
        help="Targets to build and publish",
    )
    """ Build targets [tools, uboot] """

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


@utils.concat_attributes("dtbs", "dtbs_{defconfig}")
class Kernel(_KernelBase):
    """
    Builds kernel makefile target(s) and publishes the result.

    Targets are selected by assigning the ``targets`` parameter. The following
    values are supported:

        - ``binary``: Build kernel binary
        - ``dtbs``: Build device trees
        - ``dtc``: Build device tree compiler
        - ``gzimage``: Build gzipped kernel image
        - ``image``: Build kernel image
        - ``modules``: Build kernel modules
        - ``uimage``: Build uImage
        - ``vmlinux``: Build vmlinux
        - ``zimage``: Build zImage

    Mutliple targets can be selected at once, such as ``vmlinux+dtbs+modules``.
    The resulting artifacts are published into different directories
    based on the target name.

    It is recommended to use a task dependency to setup the
    required tools by adding them to ``PATH`` and/or setting the ``CROSS_COMPILE``
    environment variable. When building on a Debian host, the
    :class:`jolt.plugins.linux.DebianHostSdk` helper task can be used to export
    the cross-compiler tools.

    The following tools are required to be available in PATH:

        - bison
        - flex
        - make
        - gcc

    Artifact path attributes are created to point to the published files.

    """

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
    """ Build targets [binary, dtbs, dtc, gzimage, image, modules, uimage, vmlinux, zimage] """

    def run_binary(self, deps, tools):
        self.info("Building binary kernel ...")
        tools.run("LOADADDR={loadaddr} vmlinux")
        objcopy = tools.getenv("OBJCOPY", tools.getenv("CROSS_COMPILE", "") + "objcopy")
        tools._run_prefix = []  # Hack to cancel previous prefix
        tools.run("{} -O binary -R .note -R .comment -S {objdir}/vmlinux {objdir}/vmlinux.bin", objcopy)

    def run_dtbs(self, deps, tools):
        self.info("Building device trees ...")
        if not self._dtbs():
            tools.run("dtbs")
        else:
            tools.run(" ".join(self._dtbs()))

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
            if not self._dtbs():
                artifact.collect("**/*.dtb", "dtbs/")
            else:
                for dtb in self._dtbs():
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
    """
    Builds a kernel module from external source tree.

    The task is based on the :class:`Kernel` task and builds a kernel module
    from the given source tree specified by the ``srcdir_module`` attribute.
    The ``targets`` attribute is set to ``modules`` by default.

    See :class:`Kernel` for additional information on building kernel targets.
    In particular, the ``srcdir`` attribute must be set to the kernel source tree
    to build the modules against.
    """

    abstract = True
    """ Must be subclassed """

    srcdir_module = None
    """ Path to kernel module source tree """

    targets = ["modules"]
    """ Build targets [modules] """

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


@utils.concat_attributes("configs", "configs")
class FIT(Task):
    """
    Builds and publishes a FIT Image.

    The task builds a FIT image using the given kernel, device tree and ramdisk
    tasks and publishes the resulting image. Multiple FIT configurations can be
    created by defining the ``configs`` attribute. The image is optinally signed
    using the provided key.

    The task requires the ``mkimage`` tool to be available in PATH.
    """

    abstract = True
    """ Must be subclassed """

    configs = {}
    """
    FIT configurations to create.

    Dictionary of 2 or 3 element tuples according to this format:

    .. code-block:: python

      configs = {
        "<name of config>": ("<name of kernel task>", "<name of dtb>"),
        "<name of config with ramdisk>": ("<name of kernel task>", "<name of dtb>", "<name of ramdisk task>"),
      }

    Example:

    .. code-block:: python

      requires = [
        "kernel=linux/kernel:arch=arm,targets=dtbs+binary_gz,defconfig=bcm2835",
        "ramdisk=busybox/irfs:arch=armv7"
      ]

      configs = {
        "conf-rpi0w": ("kernel", "bcm2835-rpi-zero-w.dtb"),
        "conf-rpi0w-irfs": ("kernel", "bcm2835-rpi-zero-w.dtb", "ramdisk"),
      }

    Loaded from defs/{defconfig}.py
    """

    config_default = None
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
            {% if deps[kernel].strings.loadaddr %}
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
            {% if deps[kernel].strings.loadaddr_fdt %}
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
            data = /incbin/("{{deps[ramdisk].paths.cpio}}");
            type = "ramdisk";
            arch = "{{deps[ramdisk].strings.arch}}";
            os = "linux";
            {% if deps[ramdisk].strings.compression %}
            compression = "{{deps[ramdisk].strings.compression}}";
            {% else %}
            compression = "none";
            {% endif %}
            hash {
                algo = "sha256";
            };
        };

        {% endfor %}
    };

    configurations {
        {% if config_default %}
        default = "conf@{{config_default}}";
        {% endif %}

        {% for name, config in _configs().items() %}
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
                        {% if signature_key_name %}
                        key-name-hint = "{{signature_key_name}}";
                        {% endif %}
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
        assert tools.which("mkimage"), "mkimage is required to build the FIT image"

        kernels = []
        dtbs = []
        ramdisks = []

        # Add kernels and dtbs to individual lists
        for name, config in self._configs().items():
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
            print(its)

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


@attributes.attribute("binary", "binary_{arch}")
class Qemu(Task):
    """
    Runs Qemu with the given kernel, initramfs and rootfs.

    The task automatically selects the correct Qemu binary for the architecture
    and builds the command line arguments based on the provided kernel, initramfs
    and rootfs tasks.

    Additional arguments can be passed to QEMU by setting the ``arguments``
    attribute.

    The selected Qemu binary must be available in PATH.
    """

    abstract = True
    """ Must be subclassed """

    arch = ArchParameter()
    """ Target architecture [amd64, arm, arm64, mips, powerpc, riscv, s390, x86] """

    arguments = []
    """ Additional arguments to pass to QEMU """

    binary = None
    """ Name of QEMU binary """

    binary_arm = "qemu-system-arm"
    binary_arm64 = "qemu-system-aarch64"
    binary_mips = "qemu-system-mips"
    binary_powerpc = "qemu-system-ppc"
    binary_riscv = "qemu-system-riscv64"
    binary_s390 = "qemu-system-s390x"
    binary_x86 = "qemu-system-x86_64"

    cacheable = False
    """ Task is not cacheable """

    dtb = None
    """ Path to device tree in kernel artifact """

    initrd = None
    """ Name of initrd/ramfs task, if any """

    kernel = None
    """ Name of kernel task """

    machine = None
    """ Target machine """

    memory = None
    """ Memory size. Example: 512M """

    rootfs = None
    """ Name of rootfs task, if any """

    def requires(self):
        r = []
        if self.kernel:
            r.append("kernel=" + self.kernel)
        if self.initrd:
            r.append("initrd=" + self.initrd)
        if self.rootfs:
            r.append("rootfs=" + self.rootfs)
        return r

    def run(self, deps, tools):
        assert tools.which(self.binary), "{binary} is required to run QEMU"
        assert self.machine, "Machine type is required to run QEMU"

        self.deps = deps

        # Get kernel and initrd paths
        arguments = self.expand(self.arguments)
        dtb = ["-dtb", os.path.join(str(deps[self.kernel].paths.dtbs), self.dtb)] if self.dtb else []
        initrd = ["-initrd", str(deps[self.initrd].paths.cpio)] if self.initrd else []
        kernel = ["-kernel", str(deps[self.kernel].paths.zimage)] if self.kernel else []
        memory = ["-m", self.memory] if self.memory else []

        # Run QEMU
        binary = tools.which(self.binary)

        cmdline = [
            binary,
            "-M", self.machine,
        ] + kernel + dtb + initrd + memory + arguments

        self.info("Running QEMU with command: {}", cmdline)

        os.execv(binary, cmdline)
