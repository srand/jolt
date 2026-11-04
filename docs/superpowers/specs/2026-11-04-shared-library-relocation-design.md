# Relocatable shared libraries in artifacts

## Why

Jolt installs packages into `/jolt-prefix` and publishes the result as an
artifact. The artifact is unpacked into a cache whose location differs between
machines (`<cachedir>/<name>/<identity>-main`). Programs and libraries that link
against the shared libraries in an artifact must find them, both while Jolt
builds the next package and later, when the binaries are copied to other
machines.

That doesn't work on macOS today:

- Autotools/libtool packages record their configure prefix as the install name
  of each dylib, for example `/jolt-prefix/lib/libffi.8.dylib`. Every binary
  linked against them copies that path into its own load commands. The path
  exists on no machine. Affected today: flex, libedit (`shared=true`),
  libfastjson, libffi, libtool (libltdl), ncurses (`shared=true`), readline,
  and krb5 before it was switched to static on macOS.
- CMake and Meson packages record `@rpath/libfoo.dylib`, but nothing gives the
  consumers an rpath, so those don't resolve either.
- `DYLD_*` variables are stripped by System Integrity Protection whenever
  `/bin/sh` runs, which is how configure and `tools.run` start programs. So
  configure's test programs fail ("cannot run C compiled programs"), and so do
  tools from dependencies that are run during builds.

On Linux, binaries record only library names, and the `LD_LIBRARY_PATH` that
21 packages publish by hand makes builds work. Binaries copied elsewhere still
don't find the libraries. On Windows, binaries record only DLL names, and
`PATH` finds them during builds.

At the user's work, a decorator already solves the copying case on Linux: when a
task has `selfsustained = True`, it reads the linked binaries, collects every
shared library they need from the dependencies into `<artifact>/lib`, and the
binaries are built with the rpath `$ORIGIN/../lib`. This design generalizes that
to Linux, macOS and Windows and adds what builds inside Jolt need.

`selfsustained` is the right trigger: when a self-sustained task's artifact is
in a cache, its requirements are pruned from the graph (`GraphPruner`,
`jolt/graph.py`), so consumers don't get the dependencies' artifacts. Any shared
library a self-sustained artifact needs at runtime must therefore be inside it.

## Goals

1. Shared libraries in artifacts built with the CMake, Autotools and Meson base
   classes can be loaded by consumers during builds in Jolt on Linux, macOS and
   Windows, including configure's test programs and tools from dependencies.
2. Artifacts work from the shared cache on any machine, whatever its cache
   location. No binary in an artifact refers to `/jolt-prefix` or to an absolute
   cache path of the machine that built it.
3. A self-sustained artifact contains every shared library its binaries need
   and works when copied anywhere, on all three platforms.
4. Packages built with the CMake, Autotools and Meson base classes don't need
   recipe changes to get this. The handful of recipes that fix up install
   names or library paths by hand can drop those fixes.

Artifacts that are not self-sustained only need to work inside a Jolt cache,
on any machine. To use binaries outside a Jolt cache (copied to another
machine, put in a Docker image), the task is made self-sustained. On Windows,
binaries that aren't self-sustained find their dependencies' DLLs only through
the `PATH` that Jolt sets.

## Non-goals

- Static libraries are not touched.
- Jolt doesn't generate wrapper scripts or launchers for bundled programs.
- No support for other binary formats than ELF, Mach-O and PE.

## Anti-goals

- Adding a dependency on a path that exists only on the building machine, such
  as an absolute cache path, to a published artifact. This would work locally
  and break silently for everyone else using the shared cache.
- Making each recipe responsible for this. It must be on by default.
- Using `DYLD_*` environment variables on macOS. SIP strips them.

## Decided by the user

- Libraries use `@rpath` install names on macOS; binaries find them through
  rpaths relative to themselves (`@loader_path`, `$ORIGIN`).
- A new artifact metadata attribute, `artifact.rpath`, through which an
  artifact declares the folders that hold its shared libraries.
- Bundling for self-sustained artifacts is driven by the linked binaries: Jolt
  reads what each binary links to, not every library in the dependencies.
- Bundling libraries from outside Jolt artifacts (the toolchain's or the host's
  runtime libraries, the C library and the dynamic loader) is optional and
  disabled by default. When enabled, it includes the C library and the dynamic
  loader. This is needed for cross builds that are later run under Qemu.
- Runtime libraries are classified by what they are, not where they were
  found. The compiler runtimes, the C library and the dynamic loader of a
  Jolt-built toolchain (`gcc`, `gcc/glibc`, `gcc/musl`, LLVM) are only bundled
  when the option is enabled, like those of the build host.
- A bundled dynamic loader is called explicitly
  (`lib/ld-linux-aarch64.so.1 bin/program`). Programs keep their normal
  interpreter path.
- LIEF (the `lief` Python package) is used to read and modify ELF, Mach-O and
  PE binaries.
- The feature is a decorator that the CMake, Autotools and Meson base classes
  use by default. Other tasks can apply it themselves.

## Design

### `artifact.rpath`

A new artifact attribute set, provided by a plugin that is always loaded (like
`environ` and `cxxinfo`). It is a list of folders relative to the artifact root
that contain shared libraries loaded at runtime:

```python
artifact.rpath.append("lib")
```

The decorator publishes it automatically: `lib` (and `lib64` when present) on
Linux and macOS when they contain shared libraries, `bin` on Windows when it
contains DLLs, since CMake and Meson install DLLs next to executables and `lib`
only holds import libraries. Recipes may append other folders, such as
`lib/<triplet>`.

When an artifact with `rpath` is a requirement of a task that uses the
decorator, applying the attribute to the consumer does the following:

| Platform | During the consumer's build |
|----------|-----------------------------|
| Linux    | adds `-Wl,-rpath,<dep path>/<folder>` to `LDFLAGS` |
| macOS    | adds `-Wl,-rpath,<dep path>/<folder>` and `-Wl,-headerpad_max_install_names` to `LDFLAGS` |
| Windows  | adds the folder to `PATH` |

Consumers without the decorator get nothing added to `LDFLAGS`, since nothing
would rewrite the absolute paths in what they publish. `rpath` doesn't set
`LD_LIBRARY_PATH`: on Linux the rpaths are enough, and `LD_LIBRARY_PATH` would
put libraries of Jolt artifacts, such as a Jolt-built `libstdc++`, in front of
the libraries of host tools like cmake, python and git.

These absolute rpaths point into the local cache and are only valid on the
building machine; the publish step below rewrites them. `LDFLAGS` is read by
Autotools and Meson, and by CMake on its first configuration (Jolt discards
CMake configuration when a task's inputs change).

Like other attributes, it applies to the consumer through the transitive
requirements unless a requirement is self-sustained.

### Publish step

After the task's `publish()` has completed, including any additions made by
subclasses after `super().publish()`, Jolt scans the artifact for ELF, Mach-O
and PE files and, on Linux and macOS:

1. Sets the install name of each Mach-O dylib whose install name starts with
   the install prefix (`artifact.strings.install_prefix`, usually
   `/jolt-prefix`) to `@rpath/<file name>`, and changes references to such
   names in the artifact's other binaries the same way.
2. Replaces each rpath that points into the artifact's own install prefix with
   the corresponding path relative to the binary (`@loader_path/...` on macOS,
   `$ORIGIN/...` on Linux).
3. Replaces each absolute rpath that points into a dependency's artifact in the
   local cache with the path relative to the binary's final location, for
   example `@loader_path/../../../libffi/<identity>-main/lib`. This is valid on
   every machine because the cache layout is the same everywhere.
4. Adds an rpath to the artifact's own `rpath` folders, relative to the binary,
   to executables and libraries that link to libraries in the same artifact.
5. Removes rpaths to anything else: the build directory, `/jolt-prefix` paths
   that don't exist in the artifact, and absolute paths on the build host.
6. On macOS, re-signs each modified binary with an ad-hoc signature
   (`codesign -s -`), since Apple Silicon refuses to run binaries with an
   invalid signature.

On Windows there is nothing to rewrite: PE files record only DLL names.

### Bundling for self-sustained tasks

When `selfsustained` is true, step 3 is replaced by bundling:

1. For each binary in the artifact, read the libraries it links to (ELF
   `DT_NEEDED`, Mach-O `LC_LOAD_DYLIB` and friends, PE import table).
2. Resolve each name against the `rpath` folders of the task's dependencies,
   the transitive ones included, in requirement order.
3. Copy each library found into the bundle folder, keeping symlinks for
   versioned names on Linux and macOS, and repeat for what the copied
   libraries link to.
4. Point the binaries at the bundle folder: rpath `$ORIGIN/../lib` or
   `@loader_path/../lib` relative to each binary, and `@loader_path` for the
   bundled libraries themselves. On Windows, DLLs are copied into each folder
   that contains an executable, which is the first place Windows looks.
5. Add the bundle folder to the artifact's own `rpath`.

Libraries that are not found in a dependency are system libraries and are left
alone by default. These are never bundled, even with the option enabled:
Windows' own DLLs (`KERNEL32.dll`, `api-ms-win-*`, and so on) and macOS
`/usr/lib` and `/System` libraries.

Libraries found in the artifacts of the task's toolchain, that is the
requirements behind `virtual/compiler/*` and what they require, are runtime
libraries too, and are skipped by default like system libraries. Toolchain
artifacts still publish `rpath`, since programs built with a Jolt toolchain
need its `libstdc++` while Jolt builds and tests them.

With the option enabled, runtime libraries are bundled as well: the C++ runtime (`libstdc++`, `libgcc_s`,
`libc++`), the Microsoft C++ runtime DLLs, other libraries of the toolchain's
sysroot or of the build host, and on Linux the C library and the dynamic
loader. For cross builds, they come from the cross toolchain's sysroot, not
the build host's `/usr/lib`. The loader keeps its file name
(`ld-linux-aarch64.so.1`) in the bundle folder.

### Decorator

The decorator `@attributes.relocate_binaries()`, defined next to
`common_metadata()` in `jolt/tasks.py`, enables the above for a task class
(decided by the user):

- It publishes `artifact.rpath` and runs the publish step.
- It is applied to `CMake`, `Autotools` and `Meson` in `jolt/plugins`, so the
  packages built with them get it.
- Only tasks with the decorator are scanned and rewritten. Tasks that download
  prebuilt binaries are left alone, so their signatures stay intact.
- Packages in `jolt/pkgs` that build shared libraries from a plain `Task`
  (among them OpenSSL, Boost, Mesa and libcap) get the decorator in their
  recipes. Without it, they keep `/jolt-prefix` install names, and bundling
  can't find their libraries in an `rpath` folder.
- Self-sustained tasks that repackage other artifacts (`cpython/embed`,
  `cpython/extend`, `xorg/libx11-xcb`) get the decorator too. Their
  requirements are pruned from the graph, so the libraries they copy must
  find what they link to inside the artifact. Bundling therefore also
  resolves rpaths that are already relative into the cache, not only absolute
  ones.
- A task can opt out, and a task can enable bundling of the runtime libraries
  (the option above) with a class attribute, so that recipes don't repeat the
  decorator.

## Calls made by Claude (not decided by the user)

- **Identity.** Adding the decorator to the base classes changes their source
  and therefore the identity of every derived task, so every package is rebuilt
  once. The decorator also adds an influence on the source of the relocation
  plugin, so that later fixes to it rebuild the artifacts they apply to. The
  Jolt version stays out of identities.
- **Cache layout version.** Rpaths between artifacts depend on the cache layout
  (`<canonical name>/<identity>-main`), which has changed before. The decorator
  adds a layout version string to the identity, and a future layout change
  must change it.
- **LIEF is a regular dependency** of Jolt (`install_requires` in `setup.py`),
  not an optional extra, since every CMake, Autotools and Meson build uses it.
  It is imported only by the relocation plugin.
- **`LDFLAGS` for build-time rpaths** rather than build-system-specific options
  (`CMAKE_BUILD_RPATH`, `-Dc_link_args`), so that all three base classes and
  custom tasks get them the same way.
- **Toolchain libraries are identified by the requirement they come from**
  (`virtual/compiler/*` and its requirements) rather than by a list of library
  names, which would collide with packages such as `libunwind`.
- **`RUNPATH`, not `RPATH`, on Linux**, which is what current linkers write by
  default. `LD_LIBRARY_PATH` set by a user then still takes precedence.
- **Absolute build-time rpaths** in consumers during the build, rewritten
  after publish, rather than computing relative rpaths at link time. The
  location of each binary inside the artifact is only known after install.
- **The 21 hand-written `LD_LIBRARY_PATH` publishes** in `jolt/pkgs` stay
  until the feature is in use, then are removed in a follow-up.

## Constraints and things the builder must handle

- `common_metadata()` (`jolt/tasks.py`) wraps `publish` of the base class, so
  it runs inside `super().publish()`, before additions made by subclasses. The
  publish step must run after the whole `publish()` of the concrete task, for
  example through a hook in the code that calls `publish()`, not by wrapping
  the base class method.
- Mach-O load commands have limited header space. Longer install names need
  `-headerpad_max_install_names` at link time; the publish step must report an
  error naming the binary when a change doesn't fit, not write a broken file.
- Python extension modules on Windows (3.8 and later) don't use `PATH` to find
  their DLLs, and DLLs that plugins in subfolders link to are looked up in the
  executable's folder, not the plugin's. Bundling puts DLLs next to every
  executable, but `.pyd` files and plugins in subfolders need their DLLs in
  their own folder or the executable's; this is documented as a limitation.
- The Linux dynamic loader's path in `PT_INTERP` is absolute and can't be made
  relative. It is left unchanged.
- Existing recipes that already fix install names (`install_name_tool`) or set
  rpaths by hand must keep working when the publish step runs after them.
- `CPythonWin32` and `PythonEnv` (`jolt/plugins/python.py`) collect
  interpreters and DLLs themselves and are not CMake, Autotools or Meson tasks.
  They don't get the decorator.

## Left to the builder

- The name of the plugin, decorator and class attributes.
- How files are recognized as binaries (LIEF's format detection, magic bytes).
- Whether the publish step runs on the worker or the client in distributed
  builds (it runs wherever `publish()` runs).
- How the tests exercise each platform: macOS and Windows behavior can be
  covered with binaries built in CI, and LIEF can parse binaries of other
  platforms on any machine.
- Logging: what is rewritten or bundled is logged in verbose mode.

## Verification

- Build an Autotools package (libffi) and a CMake package (zlib with
  `shared=true`) on macOS and Linux, then a consumer of each that runs a test
  program from configure. Inspect the artifacts (`otool -L -l`,
  `readelf -d`) for `/jolt-prefix` and absolute cache paths.
- On Linux and macOS, copy a consumer's artifact and its dependencies into a
  cache at another location and run its binaries.
- Build a self-sustained task that links several packages, copy its artifact to
  a machine without the dependencies, and run it on Linux, macOS and Windows.
- With bundling of runtime libraries enabled, build for aarch64 with a cross
  toolchain and run the program under `qemu-aarch64` through the bundled loader.
