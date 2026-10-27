"""
Sphinx extension documenting the packages in jolt.pkgs.

Every package module is imported when the documentation is built, so that
versions and parameters never go out of date. The ``jolt-packages``
directive generates a table of the package tasks, and the
``jolt-packages-reference`` directive generates a reference entry for each
task, which the table links to.
"""

import importlib
import inspect
import pkgutil
import re

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import StringList
from sphinx.util.nodes import nested_parse_with_titles

import jolt.pkgs
from jolt.tasks import BooleanParameter, Parameter, TaskRegistry


def _label(name):
    # Docutils strips trailing hyphens from ids, which would make grpc/c++ and grpc/c equal
    name = name.lower().replace("+", "plus")
    return "pkg-" + re.sub(r"[^a-z0-9]+", "-", name)


def _module_label(module):
    return "pkgmodule-" + module.rsplit(".", 1)[-1].replace("_", "-")


def _parameters(cls):
    params = {}
    for mro in reversed(cls.__mro__):
        for key in getattr(mro, "__param_list", {}):
            attr = getattr(cls, key, None)
            if isinstance(attr, Parameter) and not key.startswith("_"):
                params[key] = attr
    return params


def _version(cls):
    version = getattr(cls, "version", None)
    if isinstance(version, Parameter):
        version = version.default
    return str(version) if isinstance(version, str) else ""


def _sources(cls):
    """ URLs that the task fetches its sources from. """
    urls = []
    for name, value in inspect.getmembers(cls):
        if name != "url" and not name.startswith("requires"):
            continue
        for item in value if isinstance(value, (list, tuple)) else [value]:
            if isinstance(item, str):
                urls += re.findall(r"url=([^,\"]+)", item) or re.findall(r"^(https?://\S+)$", item)
    return list(dict.fromkeys(urls))


def _inline(text):
    """ Escape text for use in a table cell or paragraph. """
    return " ".join(str(text).split()).replace("*", r"\*").replace("`", r"\`")


def _package_tasks():
    for module in pkgutil.iter_modules(jolt.pkgs.__path__):
        importlib.import_module("jolt.pkgs." + module.name)
    tasks = [
        cls for cls in TaskRegistry.get().tasks.values()
        if cls.__module__.startswith("jolt.pkgs.")
    ]
    return sorted(tasks, key=lambda cls: cls.name)


class _GeneratedDirective(Directive):
    has_content = False

    def run(self):
        node = nodes.section()
        node.document = self.state.document
        lines = StringList(self.lines(_package_tasks()), source=self.name)
        nested_parse_with_titles(self.state, lines, node)
        return node.children


class JoltPackages(_GeneratedDirective):
    def lines(self, tasks):
        lines = [
            ".. list-table::",
            "   :header-rows: 1",
            "   :widths: 30 20 50",
            "",
            "   * - Task",
            "     - Version",
            "     - Module",
        ]
        for cls in tasks:
            lines += [
                "   * - :ref:`{} <{}>`".format(cls.name, _label(cls.name)),
                "     - {}".format(_version(cls) or "\u2014"),
                "     - :ref:`{} <{}>`".format(cls.__module__, _module_label(cls.__module__)),
            ]
        return lines


class JoltPackagesReference(_GeneratedDirective):
    def lines(self, tasks):
        lines = []
        for module in sorted({cls.__module__ for cls in tasks}):
            lines += [
                ".. _{}:".format(_module_label(module)),
                "",
                module,
                "^" * len(module),
                "",
            ]
            for cls in tasks:
                if cls.__module__ == module:
                    lines += self._reference(cls)
        return lines

    def _reference(self, cls):
        lines = [
            ".. _{}:".format(_label(cls.name)),
            "",
            cls.__name__,
            "~" * len(cls.__name__),
            "",
        ]
        doc = cls.__dict__.get("__doc__")
        if doc:
            lines += [_inline(doc), ""]
        lines += [
            ".. code-block:: python",
            "",
            "    from {} import {}".format(*cls.__module__.rsplit(".", 1)),
            "",
            "    requires = [\"{}\"]".format(cls.name),
            "",
        ]
        for url in _sources(cls):
            lines += ["Source: ``{}``".format(url), ""]
        params = _parameters(cls)
        if params:
            lines += [
                ".. list-table::",
                "   :header-rows: 1",
                "   :widths: 20 20 60",
                "",
                "   * - Parameter",
                "     - Default",
                "     - Description",
            ]
            for name, param in params.items():
                default = param.default
                if isinstance(default, (list, tuple)):
                    default = ", ".join(str(value) for value in default)
                description = _inline(param._help or "")
                if param._accepted_values and not isinstance(param, BooleanParameter):
                    values = ", ".join("``{}``".format(value) for value in param._accepted_values)
                    description = "{} Values: {}".format(description, values).strip()
                lines += [
                    "   * - ``{}``".format(name),
                    "     - {}".format("``{}``".format(default) if default not in (None, "") else "\u2014"),
                    "     - {}".format(description or "\u2014"),
                ]
            lines += [""]
        return lines


def setup(app):
    app.add_directive("jolt-packages", JoltPackages)
    app.add_directive("jolt-packages-reference", JoltPackagesReference)
    return {"parallel_read_safe": True}
