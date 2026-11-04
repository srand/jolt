# Relocatable Shared Libraries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shared libraries in artifacts load from any cache location and in self-sustained bundles on Linux, macOS and Windows, through a decorator `@attributes.relocate_binaries()` that the CMake, Autotools and Meson base classes use.

**Architecture:** A new artifact attribute `artifact.rpath` declares library folders and gives consumers build-time rpaths (or `PATH` on Windows). After a decorated task's whole `publish()`, `TaskProxy.publish` calls the relocation module. That module reads every binary through a thin LIEF adapter, rewrites install names and rpaths to be relative and, for self-sustained tasks, bundles the libraries the binaries link to.

**Tech Stack:** Python 3.11+, LIEF 1.0 (`lief` on PyPI), Jolt's test tasks (`testsupport.JoltTest`).

**Spec:** `docs/superpowers/specs/2026-11-04-shared-library-relocation-design.md`

## Global Constraints

- Don't commit: the user said not to. Each task ends with the tests passing and the changes left in the working tree.
- Decorator: `attributes.relocate_binaries(bundle_runtime=False)`, defined in `jolt/tasks.py` right after `common_metadata()`.
- Task class attributes it sets: `relocate_binaries = True` (a task opts out with `False`) and `bundle_runtime_libraries = <bundle_runtime>`.
- LIEF is a regular dependency: `"lief>=1.0"` in both requirement lists of `setup.py`. It's imported only in `jolt/binaries.py`.
- Linux: `RUNPATH` entries, relative ones as `$ORIGIN/...`. macOS: install names `@rpath/<file name>`, rpaths `@loader_path/...`, and an ad-hoc re-sign (`codesign -s - -f <file>`) of each modified file when running on macOS.
- Never write `/jolt-prefix`, the build directory or an absolute path under the cache root into a published binary.
- Never bundled: Windows system DLLs (`KERNEL32.dll`, `api-ms-win-*`, `ext-ms-*`, every DLL found in `%SystemRoot%\System32`), and macOS libraries under `/usr/lib` and `/System`.
- `LAYOUT_VERSION = "1"` in `jolt/relocate.py`. It is part of task identities through the file's hash.
- `cd tests && python3 -m jolt build flake8` passes, and `python3 -m sphinx -b html docs <outdir>` builds without warnings.
- Run tests with `-f`, since test identities don't cover Jolt's own code.

## Review Focus

1. **Read-only files** (libraries installed `0555`/`0444`): they're rewritten and keep their mode. Test in Task 2.
2. **Static archives, object files and non-binaries** (`.a`, `.o`, scripts, data that starts with ELF magic): `open_binary()` returns `None` and their bytes are unchanged. Test in Task 2.
3. **Versioned symlink chains** (`libz.so -> libz.so.1 -> libz.so.1.3.1`): symlinks are never opened as binaries, rewriting happens once on the real file, and bundling recreates the chain. Tests in Tasks 3 and 4.
4. **Binaries that need no change** (static executables, binaries without rpaths into the prefix or cache): their bytes stay identical and they aren't re-signed. Test in Task 3.
5. **Universal (fat) Mach-O files**: each slice is edited the same way. Only checked in Task 7 on macOS, since the Linux tests can't build them.

---

### Task 1: `artifact.rpath` attribute

**Files:**
- Create: `jolt/plugins/rpath.py`
- Modify: `jolt/config.py:351` (add `"rpath"` to `automatic`)
- Test: `tests/int_rpath.jolt` (register `int_rpath` in `tests/all.jolt`)

**Interfaces:**
- Produces: `artifact.rpath`, an `ArtifactListAttribute` named `"rpath"`, with folders relative to the artifact root. `artifact.rpath.append("lib")`, `list(artifact.rpath)`, `artifact.rpath.items()` returns the list. Stored in the manifest under `"rpath"`.
- Produces: `RpathProvider.apply(task, artifact)` / `unapply(task, artifact)`. They do nothing unless `getattr(task, "relocate_binaries", False)` is true.

- [ ] **Step 1: Write the failing tests** in `tests/int_rpath.jolt`, class `RpathInternal(JoltTest)`, `name = "int/rpath"`. Use a fake artifact with `path`, `tools` and the provider, as `int_selfdeploy.jolt` fakes `Artifact`/`Tools`. Patch `platform.system` per test.

```python
def test_format_parse_roundtrip(self):
    # format() then parse() on a new artifact gives ["lib", "lib64"]
def test_apply_linux_adds_rpath_to_ldflags(self):
    # consumer.relocate_binaries = True, LDFLAGS="-O2"
    # after apply: LDFLAGS == "-O2 -Wl,-rpath,/cache/zlib/x-main/lib"
    # after unapply: LDFLAGS == "-O2"
def test_apply_darwin_adds_headerpad(self):
    # LDFLAGS contains "-Wl,-rpath,/cache/zlib/x-main/lib" and "-Wl,-headerpad_max_install_names" exactly once each,
    # even with two dependencies applied
def test_apply_windows_adds_path(self):
    # PATH starts with "C:\\cache\\zlib\\x-main\\bin"; LDFLAGS unchanged
def test_apply_without_decorator_does_nothing(self):
    # consumer without relocate_binaries: LDFLAGS and PATH unchanged
def test_apply_never_sets_ld_library_path(self):
    # LD_LIBRARY_PATH unchanged on linux
```

- [ ] **Step 2: Run** `cd tests && python3 -m jolt build -f int/rpath`. Expected: the tests fail, because `artifact.rpath` doesn't exist.

- [ ] **Step 3: Implement** the provider in `jolt/plugins/rpath.py`, modelled on `CMakeInfoProvider` in `jolt/plugins/cmake.py:182`. `apply` saves the old `LDFLAGS`/`PATH` value on the attribute and joins paths with `fs.path.join(artifact.path, folder)`. Add `"rpath"` to `automatic` in `jolt/config.py`.

- [ ] **Step 4: Run** `python3 -m jolt build -f int/rpath flake8`. Expected: all pass.

### Task 2: LIEF binary adapter

**Files:**
- Create: `jolt/binaries.py`
- Modify: `setup.py` (add `"lief>=1.0"` to the fallback `install_requires`); `pip install --user "lief>=1.0"` (or into the active venv) for development
- Test: `tests/int_binaries.jolt` (register it in `tests/all.jolt`)

**Interfaces:**
- Produces:

```python
class Binary:
    path: str
    format: str               # "elf", "macho" or "pe"
    is_library: bool          # shared object, dylib, bundle or DLL
    install_name: str | None  # Mach-O LC_ID_DYLIB, otherwise None
    needed: list[str]         # DT_NEEDED, LC_LOAD_DYLIB (+ weak/reexport/lazy), PE imports
    rpaths: list[str]         # DT_RUNPATH (or DT_RPATH if no RUNPATH), LC_RPATH; [] for PE
    interpreter: str | None   # ELF PT_INTERP
    def set_install_name(self, name: str) -> None
    def change_needed(self, old: str, new: str) -> None
    def set_rpaths(self, rpaths: list[str]) -> None   # ELF: writes DT_RUNPATH and removes DT_RPATH
    def save(self) -> bool    # writes only if modified, keeps file mode, re-signs on macOS; returns True if written

def open_binary(path: str) -> Binary | None
```

`open_binary` returns `None` for symlinks, files that LIEF can't parse, ELF `ET_REL`, Mach-O `MH_OBJECT` and archives. A fat Mach-O becomes one `Binary` whose reads come from the first slice and whose edits apply to every slice. `save()` raises `JoltError` naming the file when a Mach-O edit doesn't fit the header padding.

- [ ] **Step 1: Write the failing tests.** Build fixtures with `cc` in a temporary directory: `libfoo.so` (`-shared -fPIC -Wl,-soname,libfoo.so.1`), `prog` linked to it with `-Wl,-rpath,/jolt-prefix/lib`, `foo.o` and `libfoo.a`.

```python
def test_reads_elf(self):
    b = binaries.open_binary("prog")
    self.assertEqual((b.format, b.is_library), ("elf", False))
    self.assertIn("libfoo.so.1", b.needed)
    self.assertEqual(b.rpaths, ["/jolt-prefix/lib"])
    self.assertTrue(b.interpreter.startswith("/"))
def test_set_rpaths_roundtrip(self):
    # set_rpaths(["$ORIGIN/../lib"]); save() is True; reopened rpaths == ["$ORIGIN/../lib"]; prog runs with libfoo in ../lib
def test_save_unmodified_writes_nothing(self):
    # save() is False and the file's bytes and mtime are unchanged
def test_read_only_file_keeps_mode(self):
    # chmod 0o555 libfoo.so, set_rpaths(["$ORIGIN"]), save(); mode is still 0o555
def test_ignores_objects_archives_scripts_symlinks(self):
    # open_binary returns None for foo.o, libfoo.a, a shell script, a file of b"\x7fELF" + garbage, and a symlink to libfoo.so
```

- [ ] **Step 2: Run** `python3 -m jolt build -f int/binaries`. Expected: the tests fail with `ModuleNotFoundError: jolt.binaries`.

- [ ] **Step 3: Implement** `jolt/binaries.py` with `lief.parse` and `lief.MachO.parse` (for fat files). Use `lief.ELF.DynamicEntryRunPath`, `lief.MachO.RPathCommand` and `lief.PE.Binary.imports`. Re-sign with `subprocess.run(["codesign", "-s", "-", "-f", path])` when `platform.system() == "Darwin"`.

- [ ] **Step 4: Run** `python3 -m jolt build -f int/binaries flake8`. Expected: all pass.

### Task 3: Rewriting install names and rpaths

**Files:**
- Create: `jolt/relocate.py`
- Test: `tests/int_relocate.jolt` (register it in `tests/all.jolt`)

**Interfaces:**
- Consumes: `binaries.open_binary`, `Binary` (Task 2), `artifact.rpath` (Task 1).
- Produces:

```python
LAYOUT_VERSION = "1"
def origin(fmt: str) -> str                      # "$ORIGIN" or "@loader_path"
def relative_dir(fmt: str, binary_dir: str, target_dir: str) -> str
    # absolute dirs in, "$ORIGIN/../lib", "@loader_path", "$ORIGIN/../../../zlib/x-main/lib" out
def plan_rpaths(fmt: str, binary_relpath: str, rpaths: list[str], install_prefix: str,
                artifact_root: str, own_rpath: list[str], dep_roots: list[str],
                links_own_library: bool) -> list[str]
def find_binaries(root: str) -> list[str]         # paths relative to root, symlinks skipped, sorted
def relocate_artifact(node, artifact, tools, deps) -> None
```

`plan_rpaths` keeps entries that are already relative (`$ORIGIN`, `@loader_path`, `@executable_path`). It maps entries under `install_prefix` to the same path inside `artifact_root`, and entries under a dependency root to themselves. It turns the result into a path relative to `fs.path.join(artifact_root, dirname(binary_relpath))` and drops everything else. When `links_own_library` is true, it adds the `own_rpath` folders. Entries are deduplicated with order kept. `artifact_root` is `artifact.final_path`, and dependency roots are the `final_path` of each artifact in `deps.items()`.

`relocate_artifact` does the following, in order:
1. If `artifact.rpath` is empty, publish defaults: `lib` and `lib64` if they hold `.so*`/`.dylib` files, or `bin` on Windows if it holds `.dll` files.
2. For Mach-O libraries whose `install_name` starts with `str(artifact.strings.install_prefix)`, set `@rpath/<basename>`, and change matching `needed` entries in every binary of the artifact.
3. Apply `plan_rpaths` to each binary, then `save()` it.
4. When `node.task.selfsustained`, call `bundle_artifact` (Task 4) instead of keeping dependency-root rpaths.

On Windows (`fmt == "pe"`), steps 2 and 3 do nothing.

- [ ] **Step 1: Write the failing tests.** These use pure functions with string inputs, plus one end-to-end ELF test.

```python
def test_relative_dir(self):
    self.assertEqual(relocate.relative_dir("elf", "/c/a/x-main/bin", "/c/a/x-main/lib"), "$ORIGIN/../lib")
    self.assertEqual(relocate.relative_dir("macho", "/c/a/x-main/lib", "/c/a/x-main/lib"), "@loader_path")
def test_plan_prefix_and_dependency_rpaths(self):
    self.assertEqual(
        relocate.plan_rpaths("macho", "bin/tool", ["/jolt-prefix/lib", "/c/libffi/y-main/lib", "/home/u/build/src", "@loader_path/../share"],
                             "/jolt-prefix", "/c/glib/x-main", ["lib"], ["/c/libffi/y-main"], True),
        ["@loader_path/../lib", "@loader_path/../../../libffi/y-main/lib", "@loader_path/../share"])
def test_plan_drops_missing_prefix_paths(self):
    # "/jolt-prefix/lib/missing" is kept only if the folder exists in artifact_root (create a temp tree)
def test_find_binaries_skips_symlinks(self):
    # a tree with lib/libz.so -> libz.so.1 -> libz.so.1.3.1: only "lib/libz.so.1.3.1" is listed
def test_relocate_elf_end_to_end(self):
    # dep artifact dir with libfoo.so.1; consumer prog built with -Wl,-rpath,<dep>/lib and -Wl,-rpath,/jolt-prefix/lib;
    # relocate_artifact with fake node/artifact/deps; prog's rpaths are all "$ORIGIN/..."; copying both dirs under
    # another common root keeps prog runnable (subprocess.run returns 0)
def test_static_binary_untouched(self):
    # cc -static prog; relocate_artifact; bytes identical
```

- [ ] **Step 2: Run** `python3 -m jolt build -f int/relocate`. Expected: the tests fail with `ModuleNotFoundError: jolt.relocate`.

- [ ] **Step 3: Implement** `jolt/relocate.py` with the interfaces above, using `os.path.relpath` for `relative_dir`. Log every rewrite with `log.verbose("[Relocate] {0}: {1} -> {2}", ...)`.

- [ ] **Step 4: Run** `python3 -m jolt build -f int/relocate flake8`. Expected: all pass.

### Task 4: Bundling for self-sustained tasks

**Files:**
- Modify: `jolt/relocate.py`
- Test: `tests/int_relocate.jolt`

**Interfaces:**
- Consumes: Task 3's functions.
- Produces:

```python
def toolchain_roots(node) -> set[str]
    # final paths of the main artifacts of every descendant of node.children whose
    # qualified name starts with "virtual/compiler/", the alias itself included
def resolve_library(name: str, fmt: str, search: list[str]) -> str | None
    # first existing file named basename(name) in the search folders
def bundle_artifact(node, artifact, deps, bundle_runtime: bool) -> list[str]
    # returns the relative paths of the copied files
```

Search order: the `rpath` folders of `deps.items()`, in order, then dependency rpaths already recorded in the binary. A library found under a toolchain root is a runtime library. With `bundle_runtime=True`, names not found are resolved with `cc -print-file-name=<name>` (the compiler from `CC`, or `cc`), and the dynamic loader named by `interpreter` is copied under its basename. The never-bundled lists from Global Constraints always apply.

The destination is `lib`, or each folder that contains a `.exe` on Windows. Symlinks named like the found file's chain are recreated. Copied libraries get the rpath `origin(fmt)`, binaries get the relative dir to `lib`, and `lib` is added to `artifact.rpath`. The process repeats for the copied libraries until nothing new is found.

- [ ] **Step 1: Write the failing tests.**

```python
def test_bundle_copies_needed_and_transitive(self):
    # dep A libfoo.so.1 needs libbar.so.1 from dep B; consumer prog needs libfoo; selfsustained node;
    # bundle_artifact returns ["lib/libbar.so.1", "lib/libfoo.so.1"]; prog runs after moving only the consumer dir
def test_bundle_recreates_symlink_chain(self):
    # libfoo.so.1 -> libfoo.so.1.0 in dep: consumer gets lib/libfoo.so.1.0 and symlink lib/libfoo.so.1
def test_bundle_skips_toolchain_and_system_by_default(self):
    # a lib found under a toolchain root and libc.so.6 are not copied; with bundle_runtime=True both are, plus the loader basename
def test_bundle_windows_next_to_executables(self):
    # pure: with fake Binary objects of format "pe", DLLs from deps are copied into bin/ and tools/ (both have .exe), KERNEL32.dll is not
def test_toolchain_roots(self):
    # fake node graph: consumer -> virtual/compiler/c -> gcc -> gmp; roots == {alias, gcc, gmp final paths}
```

- [ ] **Step 2: Run** `python3 -m jolt build -f int/relocate`. Expected: the new tests fail.

- [ ] **Step 3: Implement** the functions above, and call `bundle_artifact` from `relocate_artifact` when `node.task.selfsustained` is true, passing `node.task.bundle_runtime_libraries`.

- [ ] **Step 4: Run** `python3 -m jolt build -f int/relocate flake8`. Expected: all pass.

### Task 5: Decorator and publish hook

**Files:**
- Modify: `jolt/tasks.py` (new `relocate_binaries` after `common_metadata`, ~line 1278)
- Modify: `jolt/graph.py:975` `TaskProxy.publish`
- Modify: `jolt/plugins/cmake.py:58`, `jolt/plugins/autotools.py:4`, `jolt/plugins/meson.py:18` (apply the decorator)
- Modify: `docs/reference.rst:69` (add `relocate_binaries` to the members) and document `artifact.rpath` with the other artifact attributes
- Test: `tests/api_relocate.jolt` (register it in `tests/all.jolt`)

**Interfaces:**
- Consumes: `relocate.relocate_artifact(node, artifact, tools, deps)`.
- Produces: `attributes.relocate_binaries(bundle_runtime=False)`. It sets `cls.relocate_binaries = True` and `cls.bundle_runtime_libraries = bundle_runtime`, and applies `influence.files(<path of jolt/relocate.py>)` and `influence.files(<path of jolt/binaries.py>)`. Its docstring states the Windows `.pyd`/plugin limitation from the spec.

In `TaskProxy.publish`, after `publish(artifact, self.tools)` and before `_verify_influence`: if `artifact.is_main()` and `getattr(self.task, "relocate_binaries", False)`, call `relocate.relocate_artifact(self, artifact, self.tools, context)`.

- [ ] **Step 1: Write the failing API tests.** The workspace in the docstring has a dependency task that compiles `libfoo.so` with `cc` and installs it into `{installdir}/jolt-prefix/lib`, and a consumer that links `prog` against it with `$LDFLAGS`. Both are plain `Task`s with `@attributes.relocate_binaries()`.

```python
def test_consumer_gets_relative_rpath(self):
    # build consumer; readelf -d on the artifact's bin/prog shows RUNPATH starting with "$ORIGIN" and no "/jolt-prefix" or cache root
def test_selfsustained_bundles(self):
    # consumer with selfsustained = True: artifact has lib/libfoo.so; prog runs from a copy of the artifact alone
def test_opt_out(self):
    # relocate_binaries = False on the consumer: no rewrite happens and LDFLAGS has no -Wl,-rpath
def test_identity_changes_with_relocate_source(self):
    # the task's influence strings include jolt/relocate.py
```

- [ ] **Step 2: Run** `python3 -m jolt build -f api/relocate`. Expected: the tests fail with `AttributeError: relocate_binaries`.

- [ ] **Step 3: Implement** the decorator, the hook, the three base-class decorations and the docs.

- [ ] **Step 4: Run** `python3 -m jolt build -f api/relocate int/rpath int/binaries int/relocate flake8`, then `python3 -m sphinx -b html docs <scratch>/docs`. Expected: all pass, with no Sphinx warnings.

### Task 6: Recipes outside the base classes

**Files:**
- Modify: `jolt/pkgs/openssl.py`, `jolt/pkgs/boost.py`, `jolt/pkgs/mesa.py`, `jolt/pkgs/libcap.py` (add `@attributes.relocate_binaries()` to the plain-`Task` classes that build shared libraries)
- Modify: `jolt/pkgs/cpython.py` (`cpython/embed`, `cpython/extend`) and `jolt/pkgs/xorg.py` (`xorg/libx11-xcb`)

- [ ] **Step 1:** In a scratch workspace with its own cache, build `zlib:shared=true`, `libffi`, `openssl:shared=true`, `xorg/libx11-xcb` and `cpython/embed`. Run `readelf -d` on each `.so` and executable in their artifacts. Expected: no `/jolt-prefix` and no cache-root paths, and `RUNPATH` only `$ORIGIN...`.
- [ ] **Step 2:** Copy `xorg/libx11-xcb`'s artifact to a directory outside the cache and link and run a test program against it with `-L` and `-Wl,-rpath` to the copy. Expected: it runs.
- [ ] **Step 3:** Run `python3 -m jolt build -f int/pkgs flake8` in `tests/`. Expected: pass.

### Task 7: macOS and Windows verification

Run only after the user agrees to commit and push, since the Packages workflow builds from master.

- [ ] **Step 1:** In the Packages workflow logs on macOS, check that the configure tests of libedit, glib and krb5 that used to fail with "cannot run C compiled programs" now pass. Check that `otool -L` of a few artifacts (add a debug step if needed) shows only `@rpath` names, with no `/jolt-prefix`.
- [ ] **Step 2:** On Windows, check that the self-sustained repackaging tasks contain the DLLs next to their executables.
- [ ] **Step 3:** Report the remaining failures to the user rather than fixing them in this plan.
