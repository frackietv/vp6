"""The Outline window: the structure of a source file.

``outline(source)`` reads a file with ``ast`` (it never runs it) and returns
its outline:

* constants (``HELP``) and variables at file scope,
* classes with their members (methods, class attributes, nested classes),
* functions,
* ``*global code*``: the file's top-level statements that aren't imports,
  definitions or assignments (e.g. ``if __name__ == "__main__":``), as one
  item pointing at the first of them.

Imports and the module docstring aren't listed. The designer region's
``InitializeComponent`` is listed like any method, but nothing inside it.

Each item knows the lines it covers (``spans``), so the window can highlight
the item the code editor's cursor is in (``OutlineWindow.set_line``): the
innermost one, e.g. a method rather than its class.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import icons
from .theme import theme_manager

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


# --- the panel --------------------------------------------------------------------------------

class OutlineWindow(QWidget):
    """Shows the outline of one document; clicking an item emits ``lineChosen``."""

    lineChosen = Signal(int)  # 1-based line in the shown document

    SORT_BUTTONS = (("order", "File order", "Sort in the order of the file"),
                    ("name", "Name", "Sort by name"),
                    ("type", "Type", "Sort by type"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.items: list[OutlineItem] = []
        self.line: int | None = None  # the code editor's cursor line: its item is highlighted
        self.sort_key, self.descending = "order", False

        self.buttons: dict[str, QToolButton] = {}
        bar = QHBoxLayout()
        bar.setContentsMargins(2, 2, 2, 2)
        bar.setSpacing(2)
        for key, text, tip in self.SORT_BUTTONS:
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(tip + " (click again to reverse)")
            button.clicked.connect(lambda _=False, k=key: self.sort_by(k))
            self.buttons[key] = button
            bar.addWidget(button)
            button.setProperty("label", text)
        bar.addStretch(1)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.hide()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item_chosen)
        self.tree.itemActivated.connect(self._on_item_chosen)  # Enter / double-click
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.problem)
        layout.addWidget(self.tree)

        self._timer = QTimer(self)  # re-parse shortly after the text changes
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)
        theme_manager().changed.connect(self._show)  # icons have light/dark variants
        self._update_buttons()

    # -- which document ------------------------------------------------------------------
    def set_document(self, document) -> None:
        if document is self.document:
            return
        if self.document is not None:
            try:
                self.document.text_document.contentsChanged.disconnect(self._timer.start)
            except (RuntimeError, TypeError):
                pass
        self.document = document
        if document is not None:
            document.text_document.contentsChanged.connect(self._timer.start)
        self.refresh()

    def set_line(self, line: int | None) -> None:
        """Highlight the innermost item covering this 1-based line (the code
        editor's cursor), or none."""
        self.line = line
        self._highlight()

    def _highlight(self) -> None:
        node = None
        if self.line is not None:
            path = item_path_at(self.items, self.line)
            node = self._node_for(path)
        if node is None:
            self.tree.setCurrentItem(None)
            self.tree.clearSelection()
        else:
            self.tree.setCurrentItem(node)
            self.tree.scrollToItem(node)

    def _node_for(self, path: list[OutlineItem]):
        """The tree's node for an item path (the tree may be sorted), by kind,
        name and line at each level."""
        parent, node = self.tree.invisibleRootItem(), None
        for item in path:
            node = next((parent.child(i) for i in range(parent.childCount())
                         if parent.child(i).data(0, Qt.UserRole) == item.line and
                         parent.child(i).data(0, Qt.UserRole + 1) == item.kind and
                         parent.child(i).text(0) == item.name), None)
            if node is None:
                return None
            parent = node
        return node

    def refresh(self) -> None:
        """Re-read the document. On a syntax error, keep the last outline."""
        self._timer.stop()
        if self.document is None:
            self.items = []
            self.problem.hide()
        else:
            try:
                self.items = outline(self.document.text)
                self.problem.hide()
            except SyntaxError as exc:
                self.problem.setText(f"Syntax error on line {exc.lineno}: "
                                     "showing the last outline")
                self.problem.show()
        self._show()

    # -- sorting -------------------------------------------------------------------------------
    def sort_by(self, key: str) -> None:
        """Choose the sort; choosing the current one again reverses it."""
        if key == self.sort_key:
            self.descending = not self.descending
        else:
            self.sort_key, self.descending = key, False
        self._update_buttons()
        self._show()

    def _update_buttons(self) -> None:
        for key, button in self.buttons.items():
            label = button.property("label")
            active = key == self.sort_key
            button.setChecked(active)
            button.setText(f"{label} {'▼' if self.descending else '▲'}" if active else label)

    # -- the tree ----------------------------------------------------------------------------------
    def _show(self) -> None:
        self.tree.clear()
        self._add(self.tree.invisibleRootItem(),
                  sorted_outline(self.items, self.sort_key, self.descending))
        self.tree.expandAll()
        self._highlight()

    def _add(self, parent: QTreeWidgetItem, items: list[OutlineItem]) -> None:
        for item in items:
            node = QTreeWidgetItem([item.name])
            node.setIcon(0, icons.icon(KIND_ICONS[item.kind]))
            node.setData(0, Qt.UserRole, item.line)
            node.setData(0, Qt.UserRole + 1, item.kind)
            tip = f"{KIND_LABELS[item.kind]}, line {item.line}"
            node.setToolTip(0, f"{tip}: {item.detail}" if item.detail else tip)
            parent.addChild(node)
            self._add(node, item.children)

    def _on_item_chosen(self, node: QTreeWidgetItem, _column: int = 0) -> None:
        line = node.data(0, Qt.UserRole)
        if line:
            self.lineChosen.emit(int(line))
