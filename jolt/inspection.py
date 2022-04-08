"""
Reimplementation of Python's inspect module.

A bugfix was made in Python 3.9 which significantly slowed
down the builtin inspect module's source lookup functions.

Unlike the builtin module, this implementation caches the AST
of already parsed modules in order to speed up those functions.

"""

import ast
import sys


# Cache of parsed modules (ClassFinder objects), indexed by module.
_modules = {}


def _populate_cache(module):
    global _modules

    class _ClassFinder(ast.NodeVisitor):
        """ Collects all classes and functions in an Abstract Syntax Tree. """

        def __init__(self):
            self._stack = []
            self.classes = {}
            self.functions = {}

        def visit_FunctionDef(self, node):
            self._stack.append(node.name)
            self.functions['.'.join(self._stack)] = node
            self._stack.append('<locals>')
            self.generic_visit(node)
            self._stack.pop()
            self._stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            self._stack.append(node.name)
            self.classes['.'.join(self._stack)] = node
            self.generic_visit(node)
            self._stack.pop()

    with open(module.__file__) as modfp:
        tree = ast.parse(modfp.read())
    class_finder = _ClassFinder()
    class_finder.visit(tree)
    _modules[module] = class_finder
    return class_finder


def getmodule(cls_or_func):
    """ Returns module in which a class or function is defined """
    if hasattr(cls_or_func, '__module__'):
        return sys.modules.get(cls_or_func.__module__)
    raise TypeError('{!r} is a built-in object'.format(cls_or_func))


def getfile(cls_or_func):
    """ Returns the name of the file in which a class or function is defined """
    module = getmodule(cls_or_func)
    if getattr(module, '__file__', None):
        return module.__file__
    raise TypeError('{!r} is a built-in object'.format(cls_or_func))


def getlineno(cls_or_func):
    """ Returns the name of the file in which a class or function is defined """
    if isinstance(cls_or_func, type):
        ast = getclassast(cls_or_func)
    else:
        ast = getfuncast(cls_or_func)
    return ast.lineno


def getclassast(cls):
    """ Returns the Abstract Syntax Tree of a class """
    global _modules
    module = getmodule(cls)
    module_ast = _modules.get(module)
    if not module_ast:
        module_ast = _populate_cache(module)
    return module_ast.classes[cls.__qualname__]


def getfuncast(func):
    """ Returns the Abstract Syntax Tree of a function """
    global _modules
    module = getmodule(func)
    module_ast = _modules.get(module)
    if not module_ast:
        module_ast = _populate_cache(module)
    return module_ast.functions[func.__qualname__]


def getclasssource(cls):
    """ Returns the source code of a class """
    tree = getclassast(cls)
    try:
        return ast.unparse(tree)
    except AttributeError:
        # For Python <3.9
        return ast.dump(tree, annotate_fields=False)


def getfuncsource(func):
    """ Returns the source code of a function """
    tree = getfuncast(func)
    return ast.dump(tree, annotate_fields=False)


def getmoduleclasses(module, searchtypes, predicate=None):
    """
    Finds all classes in a module that are subclasses of one of
    the search types.

    Returns a dictionary of class lists, indexed by the search types.
    """
    classes = {searchtype: [] for searchtype in searchtypes}

    for key in dir(module):
        obj = getattr(module, key)

        # Skip non-classes
        if not isinstance(obj, type):
            continue

        # Check if subclass of searched types
        for searchtype in searchtypes:
            if issubclass(obj, searchtype):
                if not predicate or not predicate(obj):
                    classes[searchtype].append(obj)

    return classes
