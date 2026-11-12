#!/usr/bin/env python
"""
Collates C++ module dependency information for the Ninja plugin.

The compiler scans each C++ source file and writes the names of the modules
it provides and requires to a P1689 file. This script, which Ninja runs once
all files of a project are scanned, combines those files into:

 - a Ninja dyndep file, telling Ninja which compiled module interfaces (BMIs)
   each object file's compilation writes and reads, and thereby in which
   order sources must be compiled.

 - a module map for each object file, telling the compiler where to write
   and find the BMIs.

 - a manifest listing the modules of the project.

The script is run by Ninja and must not depend on anything but the standard
library.
"""

import argparse
import json
import os
import sys


BMI_EXT = {"gcc": ".gcm", "clang": ".pcm"}


class CollateError(Exception):
    pass


def bmi_name(module, compiler):
    """ File name of the BMI of a module. """
    return module.replace(":", "-") + BMI_EXT[compiler]


def ninja_escape(path):
    return path.replace("$", "$$").replace(" ", "$ ").replace(":", "$:")


def write_if_changed(path, data):
    """ Writes a file, unless it already has the content. Returns True if written. """
    try:
        with open(path) as f:
            if f.read() == data:
                return False
    except OSError:
        pass
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w") as f:
        f.write(data)
    return True


def read_args(args):
    """ Expands @file arguments, with one argument per line in the file. """
    result = []
    for arg in args:
        if arg.startswith("@"):
            with open(arg[1:]) as f:
                result.extend(line.strip() for line in f if line.strip())
        else:
            result.append(arg)
    return result


class Unit(object):
    """ A scanned translation unit. """

    def __init__(self, ddi):
        try:
            with open(ddi) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise CollateError("{}: cannot read module dependencies: {}".format(ddi, e))

        rules = data.get("rules") or [{}]
        rule = rules[0]
        self.ddi = ddi
        self.object = rule.get("primary-output") or ddi
        self.provides = []
        self.requires = []

        for provided in rule.get("provides", []):
            self.provides.append(provided["logical-name"])

        for required in rule.get("requires", []):
            name = required["logical-name"]
            if required.get("lookup-method", "by-name") != "by-name":
                raise CollateError(
                    "{}: imports header unit {}: header units are not supported".format(
                        self.object, name))
            if name not in self.requires:
                self.requires.append(name)


class Modules(object):
    """ The modules known to a project: its own and those of its requirements. """

    def __init__(self, ddis, imports=None, compiler="gcc", moddir=""):
        self.compiler = compiler
        self.units = [Unit(ddi) for ddi in ddis]
        self.imported = {}
        self.provided = {}

        if imports:
            with open(imports) as f:
                self.imported = json.load(f).get("modules", {})

        for unit in self.units:
            for name in unit.provides:
                other = self.provided.get(name)
                if other is not None:
                    raise CollateError(
                        "module '{}' is provided by both {} and {}".format(
                            name, other["object"], unit.object))
                self.provided[name] = {
                    "bmi": os.path.join(moddir, bmi_name(name, compiler)),
                    "object": unit.object,
                    "requires": unit.requires,
                }

    def find(self, name):
        return self.provided.get(name) or self.imported.get(name)

    def missing(self):
        """ Names of required modules that no one provides. """
        missing = []
        for unit in self.units:
            for name in unit.requires:
                if not self.find(name) and name not in missing:
                    missing.append(name)
        return missing

    def closure(self, unit):
        """
        All modules a unit needs to read, directly or indirectly, in the order found.

        Returns a list of (name, bmi) tuples.
        """
        result = []
        seen = set(unit.provides)
        queue = list(unit.requires)
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            module = self.find(name)
            if module is None:
                continue
            result.append((name, module["bmi"]))
            queue.extend(module.get("requires", []))
        return result

    def check(self):
        for unit in self.units:
            for name in unit.requires:
                if not self.find(name):
                    raise CollateError(
                        "{}: imports module '{}', which neither the project "
                        "nor its requirements provide".format(unit.object, name))

    def modmap(self, unit):
        """ The module map of a unit, in the format of the compiler. """
        provides = [(name, self.provided[name]["bmi"]) for name in unit.provides]
        requires = self.closure(unit)

        if self.compiler == "gcc":
            # Module mapper file: <module> <bmi>
            lines = ["{} {}".format(name, bmi) for name, bmi in provides + requires]
        else:
            # Response file with compiler flags
            lines = []
            if provides:
                lines.append("-x c++-module")
            for name, bmi in provides:
                lines.append('"-fmodule-output={}"'.format(bmi))
            for name, bmi in requires:
                lines.append('"-fmodule-file={}={}"'.format(name, bmi))
        return "".join(line + "\n" for line in lines)

    def dyndep(self):
        lines = ["ninja_dyndep_version = 1"]
        for unit in self.units:
            outputs = [self.provided[name]["bmi"] for name in unit.provides]
            inputs = [bmi for _, bmi in self.closure(unit)]
            line = "build " + ninja_escape(unit.object)
            if outputs:
                line += " | " + " ".join(map(ninja_escape, outputs))
            line += ": dyndep"
            if inputs:
                line += " | " + " ".join(map(ninja_escape, inputs))
            lines.append(line)
        return "".join(line + "\n" for line in lines)

    def manifest(self):
        return json.dumps({
            "compiler": self.compiler,
            "modules": self.provided,
            "imported": self.imported,
        }, indent=2, sort_keys=True) + "\n"


def collate(args):
    modules = Modules(read_args(args.ddi), args.imports, args.compiler, args.moddir)
    modules.check()
    os.makedirs(args.moddir, exist_ok=True)
    for unit in modules.units:
        write_if_changed(unit.object + ".modmap", modules.modmap(unit))
    write_if_changed(args.manifest, modules.manifest())
    write_if_changed(args.dd, modules.dyndep())


def probe(args):
    modules = Modules(read_args(args.ddi), args.imports)
    data = json.dumps({"missing": modules.missing()}, indent=2) + "\n"
    write_if_changed(args.out, data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    cmd = commands.add_parser("collate", help="write dyndep file, module maps and manifest")
    cmd.add_argument("--compiler", choices=sorted(BMI_EXT), default="gcc")
    cmd.add_argument("--dd", required=True, help="dyndep file to write")
    cmd.add_argument("--manifest", required=True, help="manifest file to write")
    cmd.add_argument("--moddir", required=True, help="directory where BMIs are written")
    cmd.add_argument("--imports", help="manifest of modules provided by requirements")
    cmd.add_argument("ddi", nargs="*", help="P1689 files, or @file listing them")
    cmd.set_defaults(func=collate)

    cmd = commands.add_parser("probe", help="list required modules that no one provides")
    cmd.add_argument("--out", required=True, help="file to write")
    cmd.add_argument("--imports", help="manifest of modules provided by requirements")
    cmd.add_argument("ddi", nargs="*", help="P1689 files, or @file listing them")
    cmd.set_defaults(func=probe)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except CollateError as e:
        print("error: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
