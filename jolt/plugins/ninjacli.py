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


def sha1sum(path):
    sha = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            sha.update(f.read())
    except:
        sha.update(str(uuid.uuid4()).encode())
    return sha.hexdigest()


class Depfile(object):
    def __init__(self, objfile, dependencies=None, cmdline=None):
        self.valid = False
        self.product = ""
        self.cmdline = cmdline
        self.path = objfile + ".d"

        if not dependencies:
            if not os.path.exists(self.path):
                return

            with open(self.path) as f:
                self.data = f.read()

            self.data = self.data.replace("\n", "")
            self.data = self.data.replace("\r", "")
            self.data = self.data.replace("\\", "")

            index = self.data.find(":")
            if index < 0:
                return

            self.data = self.data[index+1:]
            dependencies = [dep for dep in self.data.split(" ") if dep]
            dependencies = [os.path.normpath(dep) for dep in dependencies]

        self.product = objfile
        self.dependencies = dependencies
        self.valid = True

    def _hash_file(self, filepath):
        digest = _hash_cache.get(filepath)
        if digest:
            return digest
        _hash_cache[filepath] = digest = sha1sum(filepath)
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
        except:
            pass

    def write(self):
        with open(self._path, "w") as f:
            f.write(json.dumps(self._data, indent=2))

    def add_library(self, library_file):
        self._data["filename"] = library_file

    def add_object_file(self, object_file, cmdline):
        objname = os.path.basename(object_file)
        depfile = Depfile(object_file, cmdline=cmdline)
        objects = self.objects
        objects[objname] = {"digest": depfile.hash, "deps": depfile.dependencies}
        self._data["objects"] = objects

        if objname in self._objects:
            print("error: object file name collision: {}".format(objname))
            sys.exit(1)
        self._objects.add(objname)

    def get_object(self, objfile):
        objdir = os.path.dirname(objfile)
        objname = os.path.basename(objfile)
        data = self.objects.get(objname)
        if not data:
            return False

        try:
            os.makedirs(objdir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                #print("error: failed to create directory: {}", objdir)
                sys.exit(1)

        rv = subprocess.call(["ar", "x", self.library, objname], cwd=objdir)
        if rv != 0:
            return False
        with open(objfile+".d", "w") as f:
            f.write("{}: {}".format(objfile, " ".join(data["deps"])))
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
        self._sources = {}

    def add_manifest(self, manifest):
        objects = {}
        for objname, objdata in manifest.objects.items():
            obj = self._objects.get(str(objname), [])
            deps = [join(self._builddir, dep) for dep in objdata["deps"]]
            obj.append({
                "digest": objdata["digest"],
                "manifest": manifest.path,
                "deps": Depfile(objname, dependencies=deps).hash_deps})
            self._objects[str(objname)] = obj

    def load_manifests(self, cachedir, task):
        pattern = "{cachedir}/{task}/*/.ninja.json".format(cachedir=cachedir, task=task)
        for manifest in glob.glob(pattern):
            manifest = LibraryManifest(manifest)
            manifest.read()
            self.add_manifest(manifest)

    def load(self):
        try:
            with open(join(self._builddir, ".cache.json")) as f:
                self._objects = json.load(f)
        except:
            pass

    def save(self):
        with open(join(self._builddir, ".cache.json"), "w") as f:
            json.dump(self._objects, f, indent=2)

    def lookup(self, objfile, cmdline):
        objname = os.path.basename(objfile)
        for objdata in self._objects.get(objname, []):
            dep = Depfile(objname, objdata["deps"], cmdline)
            if dep.hash == objdata["digest"]:
                return LibraryManifest(objdata["manifest"])


class LockFile(object):
    def __init__(self, path=".", *args, **kwargs):
        from fasteners import process_lock
        self._file = process_lock.InterProcessLock(os.path.join(path, ".ninja.lock"))

    def __enter__(self, *args, **kwargs):
        self._file.acquire()
        return self

    def __exit__(self, *args, **kwargs):
        self._file.release()
        pass


###############################################################################

def argscan(args, arg):
    try:
        index = args.index(arg)
    except ValueError:
        return None
    if len(args) <= index+1:
        return None
    return args[index+1]


def cli(compiler_args):
    objfile = argscan(sys.argv, "-o")

    if os.getenv("NINJACACHE_DISABLE", "0") != "1":
        depfile = Depfile(objfile)

        cache = Cache(os.getcwd())
        cache.load()
        manifest = cache.lookup(objfile, compiler_args)
        if manifest:
            print("match")
            manifest.read()
            if manifest.get_object(objfile):
                with LockFile():
                    manifest = LibraryManifest(".ninja.json")
                    manifest.read()
                    manifest.add_object_file(objfile, compiler_args)
                    manifest.write()
                    return

    rv = subprocess.call(compiler_args)
    if rv != 0:
        sys.exit(rv)

    with LockFile():
        manifest = LibraryManifest(".ninja.json")
        manifest.read()
        manifest.add_object_file(objfile, compiler_args)
        manifest.write()


if __name__ == "__main__":
    compiler_args = sys.argv[sys.argv.index("--")+1:]
    cli(compiler_args)
