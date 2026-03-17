from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import nasm, perl
from jolt.plugins import cxxinfo, git
from jolt.tasks import ListParameter, TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_perl")
@attributes.requires("requires_{system}_nasm")
@attributes.common_metadata()
@attributes.system
@cxxinfo.publish(libraries=["ssl", "crypto"])
class OpenSSL(Task):
    name = "openssl"
    version = Parameter("3.6.0", help="openssl version.")
    shared = BooleanParameter(False, "Enable shared libraries.")

    requires_git = ["git:url=https://github.com/openssl/openssl.git,rev=openssl-{version}"]
    requires_perl = ["virtual/perl"]
    requires_windows_nasm = ["nasm"]

    target = Parameter(
        required=False,
        values=[
            "BC-32",
            "BC-64",
            "BS2000-OSD",
            "BSD-aarch64",
            "BSD-armv4",
            "BSD-generic32",
            "BSD-generic64",
            "BSD-ia64",
            "BSD-nodef-generic32",
            "BSD-nodef-generic64",
            "BSD-nodef-ia64",
            "BSD-nodef-sparc64",
            "BSD-nodef-sparcv8",
            "BSD-nodef-x86",
            "BSD-nodef-x86-elf",
            "BSD-nodef-x86_64",
            "BSD-ppc",
            "BSD-ppc64",
            "BSD-ppc64le",
            "BSD-riscv32",
            "BSD-riscv64",
            "BSD-sparc64",
            "BSD-sparcv8",
            "BSD-x86",
            "BSD-x86-elf",
            "BSD-x86_64",
            "Cygwin",
            "Cygwin-i386",
            "Cygwin-i486",
            "Cygwin-i586",
            "Cygwin-i686",
            "Cygwin-x86",
            "Cygwin-x86_64",
            "DJGPP",
            "MPE/iX-gcc",
            "OS390-Unix",
            "UEFI",
            "UEFI-x86",
            "UEFI-x86_64",
            "UWIN",
            "VC-CE",
            "VC-CLANG-WIN64-CLANGASM-ARM",
            "VC-WIN32",
            "VC-WIN32-ARM",
            "VC-WIN32-ARM-UWP",
            "VC-WIN32-HYBRIDCRT",
            "VC-WIN32-ONECORE",
            "VC-WIN32-UWP",
            "VC-WIN64-ARM",
            "VC-WIN64-ARM-UWP",
            "VC-WIN64-CLANGASM-ARM",
            "VC-WIN64A",
            "VC-WIN64A-HYBRIDCRT",
            "VC-WIN64A-ONECORE",
            "VC-WIN64A-UWP",
            "VC-WIN64A-masm",
            "VC-WIN64I",
            "aix-cc",
            "aix-cc-solib",
            "aix-clang",
            "aix-gcc",
            "aix64-cc",
            "aix64-cc-solib",
            "aix64-clang",
            "aix64-gcc",
            "aix64-gcc-as",
            "android-arm",
            "android-arm64",
            "android-armeabi",
            "android-mips",
            "android-mips64",
            "android-riscv64",
            "android-x86",
            "android-x86_64",
            "android64",
            "android64-aarch64",
            "android64-mips64",
            "android64-x86_64",
            "bsdi-elf-gcc",
            "cc",
            "darwin-i386",
            "darwin-i386-cc",
            "darwin-ppc",
            "darwin-ppc-cc",
            "darwin64-arm64",
            "darwin64-arm64-cc",
            "darwin64-ppc",
            "darwin64-ppc-cc",
            "darwin64-x86_64",
            "darwin64-x86_64-cc",
            "darwin8-ppc-cc",
            "darwin8-ppc64-cc",
            "gcc",
            "haiku-x86",
            "haiku-x86_64",
            "hpux-ia64-cc",
            "hpux-ia64-gcc",
            "hpux-parisc-cc",
            "hpux-parisc-gcc",
            "hpux-parisc1_1-cc",
            "hpux-parisc1_1-gcc",
            "hpux64-ia64-cc",
            "hpux64-ia64-gcc",
            "hpux64-parisc2-cc",
            "hpux64-parisc2-gcc",
            "hurd-generic32",
            "hurd-generic64",
            "hurd-x86",
            "hurd-x86_64",
            "ios-cross",
            "ios-xcrun",
            "ios64-cross",
            "ios64-xcrun",
            "iossimulator-arm64-xcrun",
            "iossimulator-i386-xcrun",
            "iossimulator-x86_64-xcrun",
            "iossimulator-xcrun",
            "iphoneos-cross",
            "irix-mips3-cc",
            "irix-mips3-gcc",
            "irix64-mips4-cc",
            "irix64-mips4-gcc",
            "linux-aarch64",
            "linux-alpha-gcc",
            "linux-aout",
            "linux-arm64ilp32",
            "linux-arm64ilp32-clang",
            "linux-armv4",
            "linux-c64xplus",
            "linux-elf",
            "linux-generic32",
            "linux-generic64",
            "linux-ia64",
            "linux-latomic",
            "linux-mips32",
            "linux-mips64",
            "linux-ppc",
            "linux-ppc64",
            "linux-ppc64le",
            "linux-sparcv8",
            "linux-sparcv9",
            "linux-x32",
            "linux-x86",
            "linux-x86-clang",
            "linux-x86-latomic",
            "linux-x86_64",
            "linux-x86_64-clang",
            "linux32-riscv32",
            "linux32-s390x",
            "linux64-loongarch64",
            "linux64-mips64",
            "linux64-riscv64",
            "linux64-s390x",
            "linux64-sparcv9",
            "mingw",
            "mingw64",
            "mingwarm64",
            "nonstop-nse",
            "nonstop-nse_64",
            "nonstop-nse_64_put",
            "nonstop-nse_put",
            "nonstop-nsv",
            "nonstop-nsx",
            "nonstop-nsx_64",
            "nonstop-nsx_64_klt",
            "nonstop-nsx_64_put",
            "nonstop-nsx_g",
            "nonstop-nsx_g_tandem",
            "nonstop-nsx_put",
            "sco5-cc",
            "sco5-gcc",
            "solaris-sparcv7-cc",
            "solaris-sparcv7-gcc",
            "solaris-sparcv8-cc",
            "solaris-sparcv8-gcc",
            "solaris-sparcv9-cc",
            "solaris-sparcv9-gcc",
            "solaris-x86-gcc",
            "solaris64-sparcv9-cc",
            "solaris64-sparcv9-gcc",
            "solaris64-x86_64-cc",
            "solaris64-x86_64-gcc",
            "tru64-alpha-cc",
            "tru64-alpha-gcc",
            "uClinux-dist",
            "uClinux-dist64",
            "unixware-2.0",
            "unixware-2.1",
            "unixware-7",
            "unixware-7-gcc",
            "vms-alpha",
            "vms-alpha-p32",
            "vms-alpha-p64",
            "vms-ia64",
            "vms-ia64-p32",
            "vms-ia64-p64",
            "vms-x86_64",
            "vms-x86_64-cross-ia64",
            "vms-x86_64-p32",
            "vms-x86_64-p64",
            "vos-gcc",
        ]
    )

    def clean(self, tools):
        self.builddir = tools.builddir(incremental=True)
        self.installdir = tools.builddir("install")
        tools.rmtree(self.builddir)
        tools.rmtree(self.installdir)

    def run(self, deps, tools):
        self.builddir = tools.builddir(incremental=True)
        self.installdir = tools.builddir("install")
        self.srcdir = tools.expand_path("{git[openssl]}")
        with tools.cwd(self.builddir):
            self.info("Configuring OpenSSL... {builddir}")

            if self.system == "windows":
                tools.run("perl {srcdir}/Configure --prefix={installdir} --openssldir=ssl no-tests {shared[,no-shared]} {target}")
                tools.run("nmake")
                tools.run("nmake install")
            else:
                tools.run("{srcdir}/config --prefix={installdir} no-tests {shared[,no-shared]} {target}")
                tools.run("make -j{}", tools.cpu_count())
                tools.run("make install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.strings.install_prefix = self.installdir
        if self.system == "windows":
            self.publish_pkgconfig(artifact, tools)

    def publish_pkgconfig(self, artifact, tools):
        with tools.cwd(artifact.path):
            for libdir in ["lib", "lib32", "lib64"]:
                if tools.exists(libdir):
                    self.libdir = libdir
                    break

        with tools.tmpdir() as tmp, tools.cwd(tmp):
            tools.write_file(
                "openssl.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/{libdir}
includedir=${{prefix}}/include

Name: OpenSSL
Description: Secure Sockets Layer and cryptography libraries and tools
Version: {version}-{identity}
Requires: libssl libcrypto
""")
            tools.write_file(
                "libcrypto.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/{libdir}
includedir=${{prefix}}/include
enginesdir=${{libdir}}/engines-3

Name: OpenSSL-libcrypto
Description: OpenSSL cryptography library
Version: {version}-{identity}
Libs: -L${{libdir}} -lcrypto
Cflags: -I${{includedir}}
""")
            tools.write_file(
                "libssl.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/{libdir}
includedir=${{prefix}}/include

Name: OpenSSL-libssl
Description: Secure Sockets Layer and cryptography libraries
Version: {version}-{identity}
Libs: -L${{libdir}} -lssl
Cflags: -I${{includedir}}
""")
            artifact.collect("openssl.pc", "{libdir}/pkgconfig/")
            artifact.collect("libcrypto.pc", "{libdir}/pkgconfig/")
            artifact.collect("libssl.pc", "{libdir}/pkgconfig/")


TaskRegistry.get().add_task_class(OpenSSL)
