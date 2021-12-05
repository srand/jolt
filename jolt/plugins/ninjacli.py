import glob
import sys
import os
import subprocess
import hashlib
import json
import errno
import uuid
join = os.path.join


_hash_cache = {}


class Depfile(object):
    def __init__(self, objfile, dependencies=None, cmdline=None):
        self.valid = False
        self.product = ""
        self.cmdline = cmdline
        self.path = objfile + ".d"
        self.dependencies = []

        if not dependencies:
            if not os.path.exists(self.path):
                return

            with open(self.path) as f:
                data = f.read()

            data = data.split(":", 1)
            if len(data) <= 1:
                return

            dependencies = data[1]
            dependencies = dependencies.split()
            dependencies = [f.rstrip("\\").strip() for f in dependencies]
            dependencies = [os.path.normpath(f)
                            for f in filter(lambda n: n, dependencies)]

        self.product = objfile
        self.dependencies = dependencies or []
        self.valid = True

    def _hash_file(self, filepath):
        digest = _hash_cache.get(filepath)
        if digest:
            return digest

        sha = hashlib.sha1()
        try:
            with open(filepath, "rb") as f:
                sha.update(f.read())
        except Exception:
            sha.update(str(uuid.uuid4()).encode())

        _hash_cache[filepath] = digest = sha.hexdigest()
        return digest

    @property
    def hash_cmdline(self):
        sha_cmd = hashlib.sha1(str(self.cmdline).replace(os.getenv("JOLT_CACHEDIR"), "").encode())
        return sha_cmd.hexdigest()

    @property
    def hash_deps(self):
        if type(self.dependencies) == str:
            return self.dependencies
        sha = hashlib.sha1()
        for dep in sorted(self.dependencies):
            fh = self._hash_file(dep)
            sha.update(fh.encode())
        return sha.hexdigest()

    @property
    def hash(self):
        sha = hashlib.sha1()
        sha.update(self.hash_cmdline.encode())
        sha.update(self.hash_deps.encode())
        return sha.hexdigest()


class LibraryManifest(object):
    def __init__(self, path):
        self._path = path
        self._data = {}
        self._objects = set()

    def read(self):
        try:
            with open(self._path, "r") as f:
                self._data = json.loads(f.read())
        except Exception:
            pass

    def write(self):
        with open(self._path, "w") as f:
            f.write(json.dumps(self._data, indent=2))

    def add_library(self, library_file):
        self._data["filename"] = library_file

    def add_object_file(self, objpath, cmdline):
        depfile = Depfile(objpath, cmdline=cmdline)
        objects = self.objects
        objects[objpath] = {"digest": depfile.hash, "deps": depfile.dependencies}
        self._data["objects"] = objects

        if objpath in self._objects:
            print("error: object file name collision: {}".format(objpath))
            sys.exit(1)
        self._objects.add(objpath)

    def get_object(self, objpath, builddir):
        objdir = join(builddir, os.path.dirname(objpath))
        data = self.objects.get(objpath)
        if not data:
            return False

        try:
            os.makedirs(objdir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                return False

        rv = subprocess.call([os.getenv("AR", "ar"), "x", self.library, objpath], cwd=objdir)
        if rv != 0:
            return False

        with open(objpath + ".d", "w") as f:
            f.write("{}: {}\n".format(objpath, " ".join(data["deps"])))
            return True

        return False

    @property
    def objects(self):
        return self._data.get("objects", {})

    @property
    def library(self):
        return os.path.join(os.path.dirname(self._path), self._data["filename"])

    @property
    def path(self):
        return self._path


class Cache(object):
    def __init__(self, builddir):
        self._builddir = builddir
        self._objects = {}
        self._objnames = {}
        self._sources = {}

    def add_manifest(self, manifest):
        for objpath, objdata in manifest.objects.items():
            objname = os.path.basename(objpath)
            objpath_known = self._objnames.get(objname, objpath)
            if objpath_known != objpath:
                # Multiple objects with the same basename.
                # No way to know which object will be extracted
                # from the archive. Remove entries and fall back
                # to compilation.
                try:
                    self._objnames[objname] = None
                    del self._objects[objpath_known]
                except KeyError:
                    pass
                continue
            self._objnames[objname] = objpath
            obj = self._objects.get(str(objpath), [])
            deps = [join(self._builddir, dep) for dep in objdata["deps"]]
            obj.append({
                "digest": objdata["digest"],
                "manifest": manifest.path,
                "deps": Depfile(objpath, dependencies=deps).hash_deps})
            self._objects[str(objpath)] = obj

    def load_manifests(self, cachedir, task):
        pattern = "{cachedir}/{task}/*/.ninja.json".format(cachedir=cachedir, task=task)
        manifests = glob.glob(pattern)

        maxartifacts = int(os.getenv("NINJACACHE_MAXARTIFACTS", 0))
        if maxartifacts > 0:
            manifests = manifests[:maxartifacts]

        for manifest in manifests:
            manifest = LibraryManifest(manifest)
            manifest.read()
            self.add_manifest(manifest)

    def load(self):
        with open(join(self._builddir, ".cache.json")) as f:
            self._objects = json.load(f)

    def save(self):
        with open(join(self._builddir, ".cache.json"), "w") as f:
            json.dump(self._objects, f, indent=2)

    def lookup(self, objpath, cmdline):
        for objdata in self._objects.get(objpath, []):
            dep = Depfile(objpath, objdata["deps"], cmdline)
            if dep.hash == objdata["digest"]:
                manifest = LibraryManifest(objdata["manifest"])
                manifest.read()
                return manifest


class LockFile(object):
    def __init__(self, path=".", *args, **kwargs):
        from fasteners import process_lock
        self._file = process_lock.InterProcessLock(os.path.join(path, ".ninja.lock"))

    def __enter__(self, *args, **kwargs):
        self._file.acquire()
        return self

    def __exit__(self, *args, **kwargs):
        self._file.release()


###############################################################################

def argscan(args, arg):
    try:
        index = args.index(arg)
    except ValueError:
        return None
    if len(args) <= index + 1:
        return None
    return args[index + 1]


def verbose(fmt, *args, **kwargs):
    if os.getenv("NINJACACHE_VERBOSE", "0") == "1":
        print(fmt.format(*args, **kwargs))


def cli(compiler_args):
    objfile = argscan(sys.argv, "-o")

    if os.getenv("NINJACACHE_DISABLE", "0") != "1":
        cache = Cache(os.getcwd())
        cache.load()
        manifest = cache.lookup(objfile, compiler_args)
        if manifest:
            if manifest.get_object(objfile, os.getcwd()):
                verbose("Reusing {} from {}", objfile, manifest.library)
                with LockFile():
                    manifest = LibraryManifest(".ninja.json")
                    manifest.read()
                    manifest.add_object_file(objfile, compiler_args)
                    manifest.write()
                    sys.exit(0)
            else:
                verbose("Extraction from library failed, rule will be executed normally")

    rv = subprocess.call(compiler_args)
    if rv != 0:
        sys.exit(rv)

    with LockFile():
        manifest = LibraryManifest(".ninja.json")
        manifest.read()
        manifest.add_object_file(objfile, compiler_args)
        manifest.write()


if __name__ == "__main__":
    compiler_args = sys.argv[sys.argv.index("--") + 1:]
    cli(compiler_args)
