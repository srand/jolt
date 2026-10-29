# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Jolt is a task execution tool: tasks are Python classes in `.jolt` recipe files,
and the output of each task is published as an artifact into a content-addressed
cache shared between users and build workers.

## Commands

- Run Jolt from source with `python3 -m jolt`, in a directory with `.jolt` files.
  Use `-c jolt.cachedir=<dir>` to keep experiments out of the default cache.
- Tests are Jolt tasks in `tests/`: `cd tests && python3 -m jolt build <test>`, for
  example `int/tools`, `api/git` or `flake8` (the linter). Run a single test case
  with a wildcard on the method name: `python3 -m jolt build "int/tools:filter=test_reader*"`.
  `tests/all.jolt` lists the tests that CI runs; register new test files there.
  Test results are cached by the identity of the test task, which doesn't include
  the Jolt code under test: after changing Jolt itself, rerun with `build -f`.
- Test classes derive from `testsupport.JoltTest`. API tests (`api_*.jolt`) describe
  the workspace files of each test case in its docstring with `--- file: <name>`
  sections; internal tests (`int_*.jolt`) are plain unit tests with mocks.
- Go services: `cd services && go test ./pkg/...`, `go build ./cmd/<service>`.
- Documentation: `python3 -m sphinx -b html docs <outdir>`; it should build without
  warnings.
- Regenerate the protobuf code after changing a `.proto` file with
  `python3 -m jolt build jolt/protobufs` from the repository root (uses `shell.nix`).
- Releases are made by the manually triggered `release` GitHub workflow, which runs
  `jolt build all` in `tests/` and then `jolt build default:push=true` from the root.

## Architecture

- **Recipes and tasks:** `jolt/loader.py` finds and loads the `.jolt` files of the
  workspace, and task classes are registered by name in `TaskRegistry`
  (`jolt/tasks.py`). Tasks declare `Parameter`s and `requires`; class decorators in
  `jolt.attributes` add requirements and attributes. Parameter values are expanded
  into strings with `{name}` (`tools.expand`). Resources such as `git:` and `fetch:`
  are tasks too, acquired around the tasks that require them.
- **Build pipeline** (`build` in `jolt/cli.py`): `GraphBuilder` (`jolt/graph.py`)
  creates the task graph and computes the identity of every task; `GraphPruner`
  removes tasks whose artifacts already exist in the local or remote cache
  (`jolt/cache.py`); a strategy in `jolt/scheduler.py` (local, distributed or worker)
  runs the rest. A task's `run(deps, tools)` builds, and `publish(artifact, tools)`
  collects files and metadata (`artifact.environ`, `cxxinfo`, `strings`) that
  consumers see.
- **Task identity:** the hash of the influence providers in `jolt/influence.py`:
  parameters, the source code of the task class and all its base classes, the
  identities of requirements, and files. Editing a base class, even a docstring,
  changes the identity of every task derived from it. The Jolt version isn't part of
  the identity unless enabled.
- **Tools** (`jolt/tools.py`): the API that tasks use to run commands, change
  directories and environment, download and extract files, and drive CMake, Meson
  and Autotools. Incremental build directories persist between builds; CMake and
  Meson configuration in them is discarded when the task's inputs, except its own
  sources, change.
- **Plugins** (`jolt/plugins`): a plugin is loaded when the Jolt configuration has a
  section with its name (a few, such as `environ` and `cxxinfo`, are always loaded).
  Plugins add storage providers (`http`), executors (`scheduler`), CLI hooks
  (`jolt/hooks.py`, for example `email`) and task base classes (`cmake`, `ninja`, `git`).
- **Services** (`services/`, Go): the HTTP cache that stores artifacts, and the
  scheduler and workers for distributed execution, which talk to Jolt over gRPC
  (`jolt/plugins/remote_execution/*.proto`). Their Docker images are built by tasks
  in `build.jolt`.
- **Jobserver:** Jolt hands builds a make jobserver, either a FIFO or the CUSE
  device `/dev/jobserver` (`jobserver_cuse.py`), which can withhold tokens under
  system pressure. Ninja before 1.14 ignores the CUSE device.

## Packages (`jolt/pkgs`)

### Adding a package

- One module per package. Register each task class with
  `TaskRegistry.get().add_task_class()`.
- Add the module import and the task names to `examples/pkgs/pkgs.jolt`, in
  alphabetical order. Use `requires_linux`/`requires_darwin` for platform-specific
  packages.
- Don't write documentation by hand: `docs/_ext/jolt_packages.py` generates the
  package table and class reference from the recipes.
- Packages that compile anything require the C compiler: add
  `@attributes.requires("requires_compiler")` and
  `requires_compiler = ["virtual/compiler/c"]` (`compiler/c` for the toolchain
  itself: gcc, binutils, C libraries, LLVM). The host compiler, OS and
  architecture are only part of identities through this requirement; without
  it, the shared cache mixes binaries of different platforms. Downloads of
  prebuilt binaries are kept apart by their URLs.
- Prefer depending on other Jolt packages over bundled copies and libraries on the
  build host. Check configure output for dependencies found on the host (paths in
  `/usr`) or silently skipped (`not found`), and add packages for them.

### Versions and sources

- Always declare `version = Parameter("x.y.z", help="<Project> version.")` with the
  spelling of the upstream project, and pin the sources to it: `rev=` on git
  requirements, `{version}` in download URLs. A git requirement without `rev=`
  builds the default branch whatever the version says.
- Before changing a version, check that the tag exists (`git ls-remote --tags`) or
  that the URL returns 200. Tag formats differ (`v{version}`, `release-{version}`,
  `asio-1-38-2`); convert the version with a property when needed. Watch for
  changed version schemes (MySQL went from 9.7 to 26.10).
- Check that dependents still build after major upgrades, and upgrade packages that
  must match together, in one commit: OpenSSL 4 requires CPython 3.15 and MySQL
  26.10, gRPC is tested against a specific protobuf release, and
  spirv-llvm-translator must match the major version of LLVM.
- Release tarballs that contain links to absolute paths (all libtirpc releases)
  can't be extracted by Python 3.14; build from git instead.
- When upstream starts or stops using git submodules, update `submodules=` and the
  published library names (rapidyaml folded c4core into ryml).

### Parameters and attributes

- Pass parameter help by keyword: the second positional argument of
  `BooleanParameter` is `required`, not `help`.
- Use the same descriptions as other packages: `Build shared libraries.`,
  `Build with position independent code.` (`Use ...` in `virtual/*` aliases),
  `Enable <Project> support.`, and end every description with a period.
- Document attributes that aren't parameters with a docstring on the line after
  the assignment: `""" Source directory. """`. The generated reference shows them.
- Attribute names in `@attributes.requires("requires_...")` aren't checked; a
  misspelled attribute silently drops the requirement.

### Building correctly

- Static libraries linked into shared objects must be position independent:
  require `zlib:pic=true`, `libexpat:pic=true` and so on. Give libraries a `pic`
  parameter (`CMAKE_POSITION_INDEPENDENT_CODE`) if they lack one.
- Publish `artifact.environ.CMAKE_PREFIX_PATH.append(".")` so that CMake's
  `find_library`/`find_path` find the package, and `LD_LIBRARY_PATH` for shared
  libraries. CMake's `check_include_file` ignores pkg-config; pass
  `pkg-config --cflags` through `CFLAGS` (see `mysql.py`).
- pkg-config files must name the packages of dependencies (`Requires:`) instead of
  bare `-l` flags, or consumers can't find them. Static libraries need their
  dependencies in `Requires`, not `Requires.private`, since many consumers don't
  pass `--static` (see `libusb.py`, `openldap.py`).
- `find_library` with several names searches every directory for the first name
  before the next, so a host library with another name can win (MySQL found the
  host's `libldap_r` before Jolt's `libldap`). Point such searches at the package.
- Artifacts are relocated from `/jolt-prefix`. pkg-config files are fixed
  automatically, but scripts such as `krb5-config` must be patched, and tools with
  data files must be built relocatable (`bison --enable-relocatable`).
- Runtime configuration should come from the system, not the prefix: OpenSSL uses
  `--openssldir=/etc/ssl`, krb5 `--sysconfdir=/etc`, alsa-lib `/usr/share/alsa`.
- Autotools: `autoreconf` modifies git checkouts, so use `git:clean=true`.
  Options are passed to `configure` through the shell; quote values with spaces.
  Old `install-sh` scripts race in parallel installs; set `install_threads = 1`.
- New toolchains break old code: GCC 15 defaults to C23, where glibc's string
  functions return const pointers when given const pointers. Disable the specific
  warning-as-error rather than all warnings (see `krb5.py`).
- X.org: newer libraries (libXi, libXfixes, libXtst) need the protocol headers of
  `xorgproto`; the separate legacy protocol packages are too old for them.

### Verifying a package

- Build in a scratch workspace outside the repository with its own cache:
  `python3 -m jolt -c jolt.cachedir=<dir>/cache build <task>`. Large builds don't
  fit in a small `/tmp`.
- Build each variant (`:shared=true`, `:pic=true`) and the packages that require it.
- For tools, run the published binary from the cache to check that it is
  relocatable; for libraries, compile and link a small program against it.
- Commit each package or upgrade separately: `pkgs: add <name> <version>`,
  `pkgs: upgrade <name> to <version>`.
