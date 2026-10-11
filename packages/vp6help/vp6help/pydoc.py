"""Help pages for Python packages, javadoc-style: a page per module with its
classes (their methods, properties and attributes, and what they inherit),
functions and constants, linked to each other.

Modules with source are read with ``ast``, without being imported (nothing
runs, and the same source makes the same pages on every system); compiled
modules (extension modules such as PySide6's) are imported and inspected.

    pages = package_pages(["vp6"], follow=False)

``follow`` documents the packages the given ones import as well (one level:
not the packages those import), leaving out Python's standard library unless
``follow_stdlib``.

Each page is a ``Page(path, title, html, parent)``; its path is
``python/<module>.html``, under ``python/index.html``, the list of packages.
Classes, functions and constants are headings with ids (``#Form``,
``#Form.Show``) so the index and links can point at them; a ``# --- Title ---``
comment in a module groups the constants after it.
"""

from __future__ import annotations

import ast
import copy
import importlib
import importlib.util
import inspect
import pkgutil
import re
import sys
from dataclasses import dataclass, field

from .markdown import escape, to_html

__all__ = ["Page", "package_pages", "PREFIX"]

PREFIX = "python/"
INDEX = PREFIX + "index.html"
_VALUE_LENGTH = 100
_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")


@dataclass
class Page:
    path: str
    title: str
    html: str
    parent: str | None = None  # the page it comes under in the contents


@dataclass
class Member:
    name: str
    kind: str  # method, classmethod, staticmethod, property, attribute, function, constant
    signature: str = ""
    doc: str = ""
    value: str = ""
    group: str = ""  # constants: the "# --- group ---" they come under


@dataclass
class ClassDoc:
    name: str
    module: str
    bases: list[str]  # as written
    doc: str = ""
    signature: str = ""  # the constructor's parameters
    members: list[Member] = field(default_factory=list)
    resolved: list[tuple[str, str] | None] = field(default_factory=list)  # (module, name)


@dataclass
class ModuleDoc:
    name: str
    doc: str = ""
    package: bool = False
    classes: list[ClassDoc] = field(default_factory=list)
    functions: list[Member] = field(default_factory=list)
    constants: list[Member] = field(default_factory=list)
    exports: list[tuple[str, str]] = field(default_factory=list)  # (name, from module)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)  # local -> (mod, name)
    references: set[str] = field(default_factory=set)  # top-level packages imported
    submodules: list[str] = field(default_factory=list)
    error: str = ""


# --- finding modules ---------------------------------------------------------------------------

def _modules(name: str, private: bool) -> list[tuple[str, object]]:
    """A package's modules (or a lone module) as (name, spec), not importing them."""
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        spec = None
    if spec is None:
        raise ImportError(f"No Python package or module named {name!r}")
    found = [(name, spec)]
    if spec.submodule_search_locations:
        def walk(locations, prefix):
            for info in sorted(pkgutil.iter_modules(locations, prefix), key=lambda i: i.name):
                last = info.name.rpartition(".")[2]
                if last == "__main__" or (last.startswith("_") and not private):
                    continue
                sub = info.module_finder.find_spec(info.name)
                if sub is None:
                    continue
                found.append((info.name, sub))
                if info.ispkg and sub.submodule_search_locations:
                    walk(list(sub.submodule_search_locations), info.name + ".")

        walk(list(spec.submodule_search_locations), name + ".")
    return found


def _public(name: str, private: bool) -> bool:
    return private or not name.startswith("_")


# --- reading source ------------------------------------------------------------------------------

def _signature(args: ast.arguments, drop_first: bool, returns) -> str:
    args = copy.deepcopy(args)
    if drop_first:
        if args.posonlyargs:
            args.posonlyargs.pop(0)
        elif args.args:
            args.args.pop(0)
            if len(args.defaults) > len(args.args):
                args.defaults.pop(0)
    text = f"({ast.unparse(args)})"
    if returns is not None:
        text += f" -> {ast.unparse(returns)}"
    return text


def _value(node) -> str:
    try:
        text = ast.unparse(node)
    except Exception:  # noqa: BLE001
        return "…"
    text = " ".join(text.split())
    return text if len(text) <= _VALUE_LENGTH else text[:_VALUE_LENGTH - 1] + "…"


def _decorators(node) -> list[str]:
    names = []
    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        names.append(ast.unparse(target))
    return names


def _attribute_doc(body: list, index: int) -> str:
    """A string right after an assignment documents it (as Sphinx reads it)."""
    if index + 1 < len(body):
        after = body[index + 1]
        if isinstance(after, ast.Expr) and isinstance(after.value, ast.Constant) \
                and isinstance(after.value.value, str):
            return inspect.cleandoc(after.value.value)
    return ""


def _class_from_source(node: ast.ClassDef, module: str, private: bool) -> ClassDoc:
    cls = ClassDoc(node.name, module, [ast.unparse(b) for b in node.bases],
                   ast.get_docstring(node) or "")
    seen = set()
    for index, item in enumerate(node.body):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = _decorators(item)
            if item.name == "__init__":
                cls.signature = _signature(item.args, True, None)
                continue
            if not _public(item.name, private) or item.name in seen:
                continue
            if any(d.endswith((".setter", ".deleter")) for d in decorators):
                continue
            kind = ("property" if "property" in decorators or
                    any(d.endswith("cached_property") for d in decorators) else
                    "staticmethod" if "staticmethod" in decorators else
                    "classmethod" if "classmethod" in decorators else "method")
            signature = "" if kind == "property" else \
                _signature(item.args, kind != "staticmethod", item.returns)
            if kind == "property" and item.returns is not None:
                signature = f": {ast.unparse(item.returns)}"
            seen.add(item.name)
            cls.members.append(Member(item.name, kind, signature, ast.get_docstring(item) or ""))
        elif isinstance(item, (ast.Assign, ast.AnnAssign)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            names = []
            for target in targets:
                elements = target.elts if isinstance(target, ast.Tuple) else [target]
                names += [e.id for e in elements if isinstance(e, ast.Name)]
            for name in names:
                if not _public(name, private) or name in seen:
                    continue
                seen.add(name)
                value = _value(item.value) if item.value is not None and len(names) == 1 else ""
                annotation = f": {ast.unparse(item.annotation)}" \
                    if isinstance(item, ast.AnnAssign) else ""
                cls.members.append(Member(name, "attribute", annotation,
                                          _attribute_doc(node.body, index), value))
    return cls


def _module_from_source(name: str, spec, private: bool) -> ModuleDoc:
    package = bool(spec.submodule_search_locations)
    doc = ModuleDoc(name, package=package)
    try:
        with open(spec.origin, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError) as error:
        doc.error = f"{type(error).__name__}: {error}"
        return doc
    doc.doc = ast.get_docstring(tree) or ""
    here = name if package else name.rpartition(".")[0]

    def absolute(module: str | None, level: int) -> str:
        if not level:
            return module or ""
        base = here.split(".")
        base = base[:len(base) - (level - 1)] if level > 1 else base
        return ".".join(base + ([module] if module else []))

    # What it imports: names it can re-export, and the packages it uses
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                doc.references.add(alias.name.partition(".")[0])
                doc.imports[alias.asname or alias.name.partition(".")[0]] = (alias.name, "")
        elif isinstance(node, ast.ImportFrom):
            source_module = absolute(node.module, node.level)
            if source_module:
                doc.references.add(source_module.partition(".")[0])
            for alias in node.names:
                if alias.name != "*":
                    doc.imports[alias.asname or alias.name] = (source_module, alias.name)

    # __all__, when it says which names are public: all of them when it lists
    # only names (``[*OTHERS, "Name"]`` is computed: then the names it lists, and
    # the public names)
    listed: list[str] = []
    complete = None
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets) and \
                    isinstance(node.value, (ast.List, ast.Tuple)):
                literal = [isinstance(e, ast.Constant) and isinstance(e.value, str)
                           for e in node.value.elts]
                names = [e.value for e, ok in zip(node.value.elts, literal) if ok]
                listed = listed + names if isinstance(node, ast.AugAssign) else names
                complete = all(literal) and complete is not False

    def public(member_name: str) -> bool:
        if complete:
            return member_name in listed
        return member_name in listed or _public(member_name, private)

    lines = source.splitlines()
    group, last_line = "", 0
    defined = set()
    for index, node in enumerate(tree.body):
        # "# --- Title ---" comments above a statement start a group of constants
        for line in lines[last_line:node.lineno - 1]:
            m = re.match(r"\s*#\s*-{2,}\s*(.+?)\s*-{2,}\s*$", line)
            if m:
                group = m.group(1)
        last_line = getattr(node, "end_lineno", node.lineno)
        if isinstance(node, ast.ClassDef):
            defined.add(node.name)
            if public(node.name):
                doc.classes.append(_class_from_source(node, name, private))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
            if public(node.name):
                doc.functions.append(Member(node.name, "function",
                                            _signature(node.args, False, node.returns),
                                            ast.get_docstring(node) or ""))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = []
            for target in targets:
                elements = target.elts if isinstance(target, ast.Tuple) else [target]
                names += [e.id for e in elements if isinstance(e, ast.Name)]
            for member_name in names:
                defined.add(member_name)
                if member_name == "__all__" or not public(member_name):
                    continue
                if any(c.name == member_name for c in doc.constants):
                    continue
                value = _value(node.value) if node.value is not None and len(names) == 1 \
                    else ""
                doc.constants.append(Member(member_name, "constant", "",
                                            _attribute_doc(tree.body, index), value, group))
    # Names it makes public from other modules
    for member_name in listed:
        if member_name not in defined and member_name in doc.imports:
            module, original = doc.imports[member_name]
            doc.exports.append((member_name, module))
    return doc


# --- inspecting compiled modules -------------------------------------------------------------------

def _clean(text: str) -> str:
    return _ADDRESS.sub("", text)


def _inspected_signature(obj, drop_first: bool) -> str:
    try:
        signature = inspect.signature(obj)
    except (TypeError, ValueError):
        first = (getattr(obj, "__doc__", None) or "").strip().splitlines()[:1]
        m = re.match(r"[\w.]+(\(.*\).*)$", first[0]) if first else None
        return m.group(1) if m else "(…)"
    params = list(signature.parameters.values())
    if drop_first and params and params[0].name in ("self", "cls"):
        signature = signature.replace(parameters=params[1:])
    return _clean(str(signature))


def _own_doc(obj) -> str:
    text = obj.__dict__.get("__doc__") if isinstance(obj, type) else \
        getattr(obj, "__doc__", None)
    return inspect.cleandoc(text) if isinstance(text, str) else ""


def _module_by_import(name: str, spec, private: bool) -> ModuleDoc:
    doc = ModuleDoc(name, package=bool(spec.submodule_search_locations))
    try:
        module = importlib.import_module(name)
    except Exception as error:  # noqa: BLE001
        doc.error = f"{type(error).__name__}: {error}"
        return doc
    doc.doc = _own_doc(module) if isinstance(module.__doc__, str) else ""
    declared = getattr(module, "__all__", None)
    for member_name in sorted(declared if declared is not None else dir(module)):
        if declared is None and not _public(member_name, private):
            continue
        obj = getattr(module, member_name, None)
        if inspect.ismodule(obj):
            continue
        if inspect.isclass(obj):
            if getattr(obj, "__module__", name) != name:
                if declared is not None:
                    doc.exports.append((member_name, obj.__module__))
                continue
            cls = ClassDoc(member_name, name,
                           [b.__qualname__ for b in obj.__bases__ if b is not object],
                           _own_doc(obj))
            cls.resolved = [(b.__module__, b.__qualname__) for b in obj.__bases__
                            if b is not object]
            for base in obj.__bases__:
                top = base.__module__.partition(".")[0]
                if top not in ("builtins", name.partition(".")[0]):
                    doc.references.add(top)
            try:
                cls.signature = _inspected_signature(obj, False)
            except Exception:  # noqa: BLE001
                cls.signature = ""
            for attr, value in sorted(obj.__dict__.items()):
                if not _public(attr, private):
                    continue
                if isinstance(value, (staticmethod, classmethod)):
                    kind = type(value).__name__
                    value = value.__func__
                    cls.members.append(Member(attr, kind, _inspected_signature(
                        value, kind == "classmethod"), _own_doc(value)))
                elif isinstance(value, property) or inspect.isdatadescriptor(value):
                    cls.members.append(Member(attr, "property", "", _own_doc(value)))
                elif callable(value):
                    cls.members.append(Member(attr, "method",
                                              _inspected_signature(value, True), _own_doc(value)))
                else:
                    cls.members.append(Member(attr, "attribute", "", "",
                                              _clean(_short(repr(value)))))
            doc.classes.append(cls)
        elif inspect.isroutine(obj):
            if getattr(obj, "__module__", name) not in (name, None) and declared is None:
                continue
            doc.functions.append(Member(member_name, "function",
                                        _inspected_signature(obj, False), _own_doc(obj)))
        elif declared is not None or not callable(obj):
            doc.constants.append(Member(member_name, "constant", "", "",
                                        _clean(_short(repr(obj)))))
    return doc


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _VALUE_LENGTH else text[:_VALUE_LENGTH - 1] + "…"


def _read(name: str, spec, private: bool) -> ModuleDoc:
    origin = getattr(spec, "origin", None) or ""
    if origin.endswith(".py"):
        return _module_from_source(name, spec, private)
    return _module_by_import(name, spec, private)


# --- the pages -----------------------------------------------------------------------------

def package_pages(names: list[str], follow: bool = False, follow_stdlib: bool = False,
                  private: bool = False, exclude: tuple[str, ...] = ()) -> list[Page]:
    """The help pages of Python packages (and their modules), and of the
    packages they import when ``follow``."""
    modules: dict[str, ModuleDoc] = {}
    order: list[str] = []

    def document(name: str) -> None:
        for module_name, spec in _modules(name, private):
            if module_name in modules or _excluded(module_name, exclude):
                continue
            modules[module_name] = _read(module_name, spec, private)
            order.append(module_name)

    for name in names:
        document(name)
    tops = [n for n in names]
    if follow:
        referenced = set()
        for module in list(modules.values()):
            referenced |= module.references
        stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__", "builtins"}
        documented = {n.partition(".")[0] for n in modules}
        for top in sorted(referenced - documented):
            if (top in stdlib and not follow_stdlib) or _excluded(top, exclude):
                continue
            try:
                document(top)
                tops.append(top)
            except ImportError:
                continue
    for name, module in modules.items():
        parent = name.rpartition(".")[0]
        if parent in modules:
            modules[parent].submodules.append(name)
    _resolve_bases(modules)
    return [_index_page(tops, modules)] + [_module_page(modules[n], modules) for n in order]


def _excluded(name: str, patterns) -> bool:
    import fnmatch

    return any(fnmatch.fnmatchcase(name, p) or name.startswith(p + ".") for p in patterns)


def _resolve_bases(modules: dict[str, ModuleDoc]) -> None:
    """Where each class's bases are defined, when that is a module documented
    here (following re-exports such as a package's ``from .x import Name``)."""
    def locate(module_name: str, name: str, depth: int = 0):
        module = modules.get(module_name)
        if module is None or depth > 5:
            return None
        if any(c.name == name for c in module.classes):
            return module_name, name
        if name in module.imports:
            source, original = module.imports[name]
            if original:
                return locate(source, original, depth + 1) or (source, original)
        return None

    for module in modules.values():
        for cls in module.classes:
            if cls.resolved:
                continue
            for base in cls.bases:
                head, _, rest = base.partition(".")
                found = None
                if not rest:
                    found = locate(module.name, base)
                elif head in module.imports and not module.imports[head][1]:
                    found = locate(module.imports[head][0], rest)
                cls.resolved.append(found)


def _url(module: str, anchor: str = "") -> str:
    return f"/{PREFIX}{module}.html" + (f"#{anchor}" if anchor else "")


def _docstring(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"``(.+?)``", r"`\1`", text)
    return to_html(text)


def _index_page(tops: list[str], modules: dict[str, ModuleDoc]) -> Page:
    rows = []
    for name in sorted(modules):
        summary = (modules[name].doc.strip().splitlines() or [""])[0]
        rows.append(f'<tr><td><a href="{_url(name)}"><code>{escape(name)}</code></a></td>'
                    f"<td>{escape(summary)}</td></tr>")
    html = ("<h1>Python reference</h1>\n"
            f"<p>The modules of {', '.join(f'<code>{escape(t)}</code>' for t in tops)}: "
            "their classes, functions and constants.</p>\n"
            "<table>\n<tr><th>Module</th><th>Summary</th></tr>\n" + "\n".join(rows) +
            "\n</table>\n")
    return Page(INDEX, "Python reference", html)


def _module_page(module: ModuleDoc, modules: dict[str, ModuleDoc]) -> Page:
    out = [f'<h1 id="{escape(module.name, True)}">{escape(module.name)}</h1>',
           f'<p class="kind">{"Package" if module.package else "Module"}</p>']
    if module.error:
        out.append(f"<p><em>Couldn't be read: {escape(module.error)}</em></p>")
    out.append(_docstring(module.doc))
    if module.submodules:
        out.append("<h2 id=\"modules\">Modules</h2>\n<ul>" + "".join(
            f'<li><a href="{_url(sub)}"><code>{escape(sub)}</code></a></li>'
            for sub in module.submodules) + "</ul>")
    if module.exports:
        rows = []
        for name, source in sorted(module.exports, key=lambda e: e[0].casefold()):
            target = _find(modules, source, name)
            cell = f'<a href="{target}"><code>{escape(name)}</code></a>' if target else \
                f"<code>{escape(name)}</code>"
            rows.append(f"<tr><td>{cell}</td><td><code>{escape(source)}</code></td></tr>")
        out.append("<h2 id=\"names\">Names</h2>\n<p>Defined elsewhere, made public here.</p>\n"
                   "<table>\n<tr><th>Name</th><th>From</th></tr>\n" + "\n".join(rows) +
                   "\n</table>")
    for cls in module.classes:
        out.append(_class_html(cls, modules))
    if module.functions:
        out.append('<h2 id="functions">Functions</h2>')
        for function in module.functions:
            out.append(f'<h3 id="{escape(function.name, True)}">{escape(function.name)}</h3>\n'
                       f"<pre>{escape(function.name + function.signature)}</pre>\n"
                       + _docstring(function.doc))
    if module.constants:
        out.append('<h2 id="constants">Constants</h2>')
        groups: dict[str, list[Member]] = {}
        for constant in module.constants:
            groups.setdefault(constant.group, []).append(constant)
        for group, members in groups.items():
            if group:
                out.append(f"<h3>{escape(group)}</h3>")
            rows = [f"<tr><td><code>{escape(m.name)}</code></td>"
                    f"<td><code>{escape(m.value)}</code></td><td>{escape(m.doc)}</td></tr>"
                    for m in members]
            out.append("<table>\n<tr><th>Name</th><th>Value</th><th>Notes</th></tr>\n"
                       + "\n".join(rows) + "\n</table>")
    parent = module.name.rpartition(".")[0]
    parent_path = f"{PREFIX}{parent}.html" if parent in modules else INDEX
    return Page(f"{PREFIX}{module.name}.html", module.name, "\n".join(o for o in out if o),
                parent_path)


def _find(modules: dict[str, ModuleDoc], module_name: str, name: str, depth: int = 0) -> str:
    """The url of a name documented in a module (following its re-exports)."""
    module = modules.get(module_name)
    if module is None or depth > 5:
        return ""
    if any(c.name == name for c in module.classes) or \
            any(f.name == name for f in module.functions):
        return _url(module_name, name)
    if any(c.name == name for c in module.constants):
        return _url(module_name, "constants")
    if name in module.imports and module.imports[name][1]:
        source, original = module.imports[name]
        return _find(modules, source, original, depth + 1)
    return ""


def _class_html(cls: ClassDoc, modules: dict[str, ModuleDoc]) -> str:
    bases = []
    for written, where in zip(cls.bases, cls.resolved + [None] * len(cls.bases)):
        bases.append(f'<a href="{_url(*where)}">{escape(written)}</a>'
                     if where and where[0] in modules else escape(written))
    out = [f'<h2 id="{escape(cls.name, True)}">{escape(cls.name)}</h2>',
           f"<pre>class {escape(cls.name)}{escape(cls.signature)}"
           + (f"\n    bases: {', '.join(bases)}" if bases else "") + "</pre>",
           _docstring(cls.doc)]
    order = {"property": 0, "attribute": 1, "classmethod": 2, "staticmethod": 2, "method": 3}
    for member in sorted(cls.members, key=lambda m: (order.get(m.kind, 4), m.name.casefold())):
        qualified = f"{cls.name}.{member.name}"
        kind = {"property": "property", "attribute": "attribute",
                "classmethod": "class method", "staticmethod": "static method"}.get(member.kind)
        declaration = member.name + member.signature
        if member.value:
            declaration += f" = {member.value}"
        out.append(f'<h3 id="{escape(qualified, True)}">{escape(qualified)}</h3>'
                   f"<!-- keywords: {escape(member.name)} -->\n"
                   + (f'<p class="kind">{kind}</p>\n' if kind else "")
                   + f"<pre>{escape(declaration)}</pre>\n" + _docstring(member.doc))
    inherited = _inherited(cls, modules)
    for (module_name, base_name), names in inherited:
        links = ", ".join(f'<a href="{_url(module_name, base_name + "." + n)}">'
                          f"<code>{escape(n)}</code></a>" for n in names)
        out.append(f'<p>Inherited from <a href="{_url(module_name, base_name)}">'
                   f"{escape(base_name)}</a>: {links}</p>")
    return "\n".join(o for o in out if o)


def _inherited(cls: ClassDoc, modules: dict[str, ModuleDoc]):
    """The members it inherits from documented classes, base by base."""
    own = {m.name for m in cls.members}
    result, seen = [], set()

    def visit(where):
        if where is None or where in seen:
            return
        seen.add(where)
        module = modules.get(where[0])
        base = next((c for c in module.classes if c.name == where[1]), None) if module else None
        if base is None:
            return
        names = sorted((m.name for m in base.members if m.name not in own), key=str.casefold)
        own.update(names)
        if names:
            result.append((where, names))
        for parent in base.resolved:
            visit(parent)

    for where in cls.resolved:
        visit(where)
    return result
