"""A source file's outline, read with ``ast`` (the code is never run):
constants and variables at file scope, classes with their members, functions,
and ``*global code*`` (the top-level statements that aren't imports,
definitions or assignments) as one item. Each item knows the lines it covers
(``spans``), so an IDE can show the item the code's cursor is in
(``item_path_at``); ``sorted_outline`` sorts it by order, name or type.

The IDE's Outline window (``vp6.ide.outline``) shows it.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

GLOBAL_CODE = "*global code*"

# Item kinds, in the order "sort by type" uses
KINDS = ("constant", "variable", "class", "function", "method", "attribute", "code")
KIND_LABELS = {"constant": "Constant", "variable": "Variable", "class": "Class",
               "function": "Function", "method": "Method", "attribute": "Attribute",
               "code": "Top-level code"}
KIND_ICONS = {kind: "Outline" + kind.capitalize() for kind in KINDS}

_CONSTANT_RE = re.compile(r"_?[A-Z][A-Z0-9_]*")


@dataclass
class OutlineItem:
    name: str
    kind: str  # one of KINDS
    line: int  # 1-based line of the definition
    children: list["OutlineItem"] = field(default_factory=list)
    detail: str = ""  # e.g. the first line of top-level code
    # (first, last) 1-based lines it covers: a definition from its first
    # decorator to its last line; top-level code, every statement of it
    spans: list[tuple[int, int]] = field(default_factory=list)


def _span(node) -> tuple[int, int]:
    decorators = [d.lineno for d in getattr(node, "decorator_list", [])]
    return min([node.lineno] + decorators), node.end_lineno or node.lineno


def _names(target) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _names(element)]
    return []


def _assigned_names(node) -> list[str]:
    if isinstance(node, ast.Assign):
        return [name for target in node.targets for name in _names(target)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return _names(node.target)
    return []


def _is_docstring(node, index: int) -> bool:
    return (index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def _members(cls: ast.ClassDef) -> list[OutlineItem]:
    members = []
    for index, node in enumerate(cls.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            members.append(OutlineItem(node.name, "method", node.lineno, spans=[_span(node)]))
        elif isinstance(node, ast.ClassDef):
            members.append(OutlineItem(node.name, "class", node.lineno, _members(node),
                                       spans=[_span(node)]))
        elif not _is_docstring(node, index):
            members += [OutlineItem(name, "attribute", node.lineno, spans=[_span(node)])
                        for name in _assigned_names(node)]
    return members


def outline(source: str) -> list[OutlineItem]:
    """The outline of a Python source, in file order. Raises SyntaxError."""
    tree = ast.parse(source)
    lines = source.splitlines()
    items, code = [], []
    for index, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)) or _is_docstring(node, index):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append(OutlineItem(node.name, "function", node.lineno, spans=[_span(node)]))
        elif isinstance(node, ast.ClassDef):
            items.append(OutlineItem(node.name, "class", node.lineno, _members(node),
                                     spans=[_span(node)]))
        elif _assigned_names(node):
            for name in _assigned_names(node):
                kind = "constant" if _CONSTANT_RE.fullmatch(name) else "variable"
                items.append(OutlineItem(name, kind, node.lineno, spans=[_span(node)]))
        else:
            code.append(_span(node))
    if code:
        first_code = code[0][0]
        items.append(OutlineItem(GLOBAL_CODE, "code", first_code,
                                 detail=lines[first_code - 1].strip(), spans=code))
    return items


def item_path_at(items: list[OutlineItem], line: int) -> list[OutlineItem]:
    """The items covering ``line``, outermost first (e.g. [class, method]);
    empty if none does (a blank line between functions, an import)."""
    for item in items:
        if any(first <= line <= last for first, last in item.spans):
            return [item] + item_path_at(item.children, line)
    return []


# --- sorting ------------------------------------------------------------------------------

SORT_KEYS = {
    "order": lambda item: item.line,
    "name": lambda item: (item.name.lower(), item.line),
    "type": lambda item: (KINDS.index(item.kind), item.line),
}


def sorted_outline(items: list[OutlineItem], key: str = "order",
                   descending: bool = False) -> list[OutlineItem]:
    """A sorted copy; class members are sorted the same way."""
    result = []
    for item in sorted(items, key=SORT_KEYS[key], reverse=descending):
        result.append(OutlineItem(item.name, item.kind, item.line,
                                  sorted_outline(item.children, key, descending), item.detail,
                                  item.spans))
    return result
