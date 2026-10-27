"""
Sphinx extension documenting the packages in jolt.pkgs.

Every package module is imported when the documentation is built, so that
versions and parameters never go out of date. The ``jolt-packages``
directive generates a table of the package tasks, and the
``jolt-packages-reference`` directive generates class documentation for
each task, which the table links to.

Attributes are described by their docstrings in the package or in one of
its base classes. Requirement attributes, which are rarely documented, are
described by their name.
"""

import ast
import functools
import importlib
import inspect
import pkgutil
import sys

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import StringList
from sphinx.util.nodes import nested_parse_with_titles

import jolt.pkgs
from jolt.tasks import BooleanParameter, Parameter, TaskRegistry


# Types of class attributes that are documented
_ATTRIBUTE_TYPES = (str, int, float, bool, list, tuple, dict)

# Attributes that are internal to Jolt
_INTERNAL_ATTRIBUTES = {"abstract", "name"}

_SYSTEMS = {"darwin": "macOS", "linux": "Linux", "windows": "Windows"}


def _module_label(module):
    return "pkgmodule-" + module.rsplit(".", 1)[-1].replace("_", "-")


def _qualified_name(cls):
    return "{}.{}".format(cls.__module__, cls.__name__)


@functools.lru_cache(maxsize=None)
def _attribute_docs(module):
    """ Docstrings of the class attributes in a module, by class and attribute name. """
    try:
        tree = ast.parse(inspect.getsource(sys.modules[module]))
    except (KeyError, OSError, TypeError):
        return {}
    docs = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt, following in zip(node.body, node.body[1:]):
            if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                continue
            if not (isinstance(following, ast.Expr) and isinstance(following.value, ast.Constant)
                    and isinstance(following.value.value, str)):
                continue
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    docs[(node.name, target.id)] = inspect.cleandoc(following.value.value)
    return docs


def _requirement_doc(attr):
    """ Description of a requirement attribute, derived from its name. """
    words = attr[len("requires_"):].split("_")
    if words[0] in ("git", "src"):
        return "Sources of the package."
    systems = [_SYSTEMS[word] for word in words if word in _SYSTEMS]
    words = [word for word in words if word not in _SYSTEMS]
    if len(words) > 1 and words[-1] in ("on", "off"):
        condition = " when the ``{}`` parameter is {}".format(
            "_".join(words[:-1]), "enabled" if words[-1] == "on" else "disabled")
    else:
        condition = ""
    if systems:
        condition += " on {}".format(" and ".join(systems))
    return "Tasks required by the package{}.".format(condition)


def _attribute_doc(cls, attr):
    for base in cls.__mro__:
        doc = _attribute_docs(base.__module__).get((base.__name__, attr))
        if doc:
            return doc
    if attr.startswith("requires_"):
        return _requirement_doc(attr)
    return ""


def _attributes(cls):
    """ Documented class attributes, from the class and its package base classes. """
    attrs = {}
    for base in cls.__mro__:
        if base is not cls and not base.__module__.startswith("jolt.pkgs."):
            continue
        for key, value in base.__dict__.items():
            if key.startswith("_") or key in attrs or key in _INTERNAL_ATTRIBUTES:
                continue
            if isinstance(value, Parameter) or isinstance(value, _ATTRIBUTE_TYPES):
                attrs[key] = getattr(cls, key)
    # Parameters first, in the order they are declared
    return dict(sorted(attrs.items(), key=lambda item: not isinstance(item[1], Parameter)))


def _version(cls):
    version = getattr(cls, "version", None)
    if isinstance(version, Parameter):
        version = version.default
    return str(version) if isinstance(version, str) else ""


def _inline(text):
    """ Escape text for use in a table cell or paragraph. """
    return " ".join(str(text).split()).replace("*", r"\*").replace("`", r"\`")


def _indent(text, indent):
    return [indent + line if line else "" for line in text.splitlines()]


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
                "   * - :py:class:`{} <{}>`".format(cls.name, _qualified_name(cls)),
                "     - {}".format(_version(cls) or "—"),
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
                    lines += self._class(cls)
        return lines

    def _class(self, cls):
        bases = ", ".join(":py:class:`{}`".format(_qualified_name(base)) for base in cls.__bases__)
        lines = [
            ".. py:class:: {}".format(cls.__name__),
            "   :module: {}".format(cls.__module__),
            "",
            "   Bases: {}".format(bases),
            "",
        ]
        doc = cls.__dict__.get("__doc__")
        if doc:
            lines += _indent(inspect.cleandoc(doc), "   ") + [""]
        lines += [
            "   .. code-block:: python",
            "",
            "       from {} import {}".format(*cls.__module__.rsplit(".", 1)),
            "",
            "       requires = [\"{}\"]".format(cls.name),
            "",
            "   .. py:attribute:: name",
            "      :value: {!r}".format(cls.name),
            "",
            "      Name of the task.",
            "",
        ]
        for attr, value in _attributes(cls).items():
            lines += self._attribute(cls, attr, value)
        return lines

    def _attribute(self, cls, attr, value):
        doc = _attribute_doc(cls, attr)
        if isinstance(value, Parameter):
            lines = [
                "   .. py:attribute:: {}".format(attr),
                "      :type: {}".format(type(value).__name__),
            ]
            if value.default not in (None, ""):
                lines += ["      :value: {!r}".format(value.default)]
            doc = value._help or doc
            if value._accepted_values and not isinstance(value, BooleanParameter):
                values = ", ".join("``{}``".format(v) for v in value._accepted_values)
                doc = "{} Values: {}".format(_inline(doc), values).strip()
        else:
            lines = [
                "   .. py:attribute:: {}".format(attr),
                "      :value: {!r}".format(value),
            ]
        lines += [""] + _indent(doc or "", "      ") + [""]
        return lines


def setup(app):
    app.add_directive("jolt-packages", JoltPackages)
    app.add_directive("jolt-packages-reference", JoltPackagesReference)
    return {"parallel_read_safe": True}
