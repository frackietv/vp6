"""The Object Browser (View > Object Browser, F2), as VB's: the classes,
members, events and constants of VP6 and of the open project.

The model is plain Python: ``vp6_library()`` lists VP6's classes (the controls
and Form, the classes such as Picture and ControlArray, the global objects
App, Screen, Clipboard, Debug, Printer, Printers and Forms, a "Globals" class
of its functions, and one class per group of constants), and
``project_library(name, documents)`` the project's forms, user controls and
modules, read from their code as it is in the IDE (``ast``; a file with a
syntax error shows what came before). A ``ClassInfo`` has its ``members()``,
each a ``Member`` with its kind (Property, Method, Event, Constant,
Variable, Control, Class), a declaration and a description; project members
know their file and line. ``search(classes, text)`` finds classes and
members by name.

``ObjectBrowser`` is the window: a library combo (All Libraries, VP6, the
project), a search field, the search results, the Classes and Members lists
and the details pane. Double-clicking a project member asks the IDE to show
it (``goto(path, line, control)``).
"""

from __future__ import annotations

import ast
import inspect
import os
import re
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget)

VP6_LIBRARY = "VP6"
ALL_LIBRARIES = "<All Libraries>"

# What a property's kind is called in a declaration
_KIND_TYPES = {"str": "String", "text": "String", "font": "String (font name)",
               "file": "String (picture file) or Picture", "shortcut": "String (shortcut)",
               "int": "Integer", "bool": "Boolean", "enum": "Integer", "color": "Color",
               "list": "list of String", "outline": "list of String (an outline)",
               "panels": "Panels", "tabs": "Tabs", "images": "ListImages",
               "buttons": "Buttons", "columns": "ColumnHeaders", "listitems": "ListItems"}
# Class attributes that are a class's description, not members
_NOT_MEMBERS = {"TypeName", "DefaultEvent", "DefaultSize", "Events", "Properties",
                "IsContainer", "InToolbox", "properties", "Run"}


@dataclass
class Member:
    name: str
    kind: str  # Property, Method, Event, Constant, Variable, Control, Class
    declaration: str
    description: str = ""
    path: str | None = None  # (project members: where it is)
    line: int | None = None
    type_name: str | None = None  # a Control's type (its Toolbox icon)


@dataclass
class ClassInfo:
    name: str
    kind: str  # Class, Object, Globals, Constants, Form, UserControl, Module
    library: str
    description: str = ""
    _members: Callable[[], list[Member]] = field(default=lambda: [], repr=False)
    path: str | None = None
    line: int | None = None
    type_name: str | None = None  # a control class's type (its Toolbox icon)

    def members(self) -> list[Member]:
        """Its members, alphabetically (made when first asked for)."""
        cached = self.__dict__.get("_cache")
        if cached is None:
            cached = sorted(self._members(), key=lambda m: m.name.lower())
            self.__dict__["_cache"] = cached
        return cached


def _first_paragraph(text: str | None) -> str:
    return (text or "").strip().split("\n\n")[0].replace("\n", " ").strip()


def _signature(name: str, function) -> str:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return f"{name}(...)"
    parameters = [p for p in signature.parameters.values() if p.name != "self"]
    text = ", ".join(str(p).replace(" ", "") if p.default is inspect.Parameter.empty
                     else f"{p.name}={p.default!r}" for p in parameters)
    return f"{name}({text})"


# --- VP6 ---------------------------------------------------------------------------------------

def _property_member(cls, name: str) -> Member:
    spec = getattr(cls, "_specs", {}).get(name)
    if spec is not None:
        kind = _KIND_TYPES.get(spec.kind, spec.kind)
        notes = spec.description
        if spec.choices:
            notes = (notes + ". " if notes else "") + ", ".join(label for _, label
                                                                 in spec.choices)
        if spec.default not in (None, "", [], ()):
            notes += f" (default: {spec.default!r})"
        return Member(name, "Property", f"Property {name} As {kind}", notes.strip())
    attribute = inspect.getattr_static(cls, name, None)
    doc = attribute.__doc__ if isinstance(attribute, property) else ""
    read_only = isinstance(attribute, property) and attribute.fset is None
    return Member(name, "Property", f"Property {name}" + (" (read-only)" if read_only else ""),
                  _first_paragraph(doc))


def _class_members(cls) -> list[Member]:
    """A VP6 class's properties, methods and events (its own and inherited)."""
    from ..controls import EVENT_ARGS

    members: dict[str, Member] = {}
    for name in getattr(cls, "_specs", {}):
        members[name] = _property_member(cls, name)
    for name in dir(cls):
        if name.startswith("_") or name in members or name in _NOT_MEMBERS:
            continue
        attribute = inspect.getattr_static(cls, name, None)
        for klass in cls.__mro__:  # (as defined, not bound)
            if name in vars(klass):
                attribute = vars(klass)[name]
                break
        if isinstance(attribute, property):
            members[name] = _property_member(cls, name)
        elif isinstance(attribute, (staticmethod, classmethod)):
            function = attribute.__func__
            members[name] = Member(name, "Method", _signature(name, function),
                                   _first_paragraph(inspect.getdoc(function)))
        elif inspect.isfunction(attribute):
            members[name] = Member(name, "Method", _signature(name, attribute),
                                   _first_paragraph(inspect.getdoc(attribute)))
        elif not callable(attribute) and not inspect.isclass(attribute) and \
                not inspect.ismodule(attribute):  # (e.g. App.Major: a plain attribute)
            members[name] = Member(name, "Property", f"Property {name} = {attribute!r}")
    for event in getattr(cls, "Events", ()):
        arguments = EVENT_ARGS.get(event, "")
        handler = f"Name_{event}(self" + (f", {arguments})" if arguments else ")")
        members[event] = Member(event, "Event", f"Event {event}({arguments})",
                                f"Handled in the form by {handler}, Name being the "
                                "control's (Form_... for the form's)")
    return list(members.values())


def _constant_groups() -> list[tuple[str, list[str]]]:
    """constants.py's groups: (title, names), from its "# --- title ---" lines."""
    from .. import constants

    groups, title = [], None
    with open(constants.__file__, encoding="utf-8") as f:
        for line in f:
            heading = re.match(r"#\s*---\s*(.+?)\s*-{3,}\s*$", line)
            if heading:
                title = heading.group(1)
                groups.append((title, []))
                continue
            assignment = re.match(r"(vp\w+)\s*=", line)
            if assignment and groups:
                groups[-1][1].append(assignment.group(1))
    return groups


def _constants_class(title: str, names: list[str]) -> ClassInfo:
    import vp6

    def members():
        return [Member(name, "Constant", f"Const {name} = {getattr(vp6, name)!r}")
                for name in names if hasattr(vp6, name)]

    return ClassInfo(title, "Constants", VP6_LIBRARY, f"Constants: {title}", members)


def vp6_library() -> list[ClassInfo]:
    """VP6's classes, objects, functions and constants (made once)."""
    cached = globals().get("_VP6_CLASSES")
    if cached is not None:
        return cached
    import vp6

    classes = []
    globals_members = []
    for name in vp6.__all__:
        if name.startswith("vp"):
            continue
        value = getattr(vp6, name)
        if inspect.isclass(value):
            from ..controls import CONTROL_TYPES

            classes.append(ClassInfo(name, "Class", VP6_LIBRARY,
                                     _first_paragraph(inspect.getdoc(value)),
                                     lambda cls=value: _class_members(cls),
                                     type_name=name if name in CONTROL_TYPES else None))
        elif inspect.isfunction(value) or inspect.isbuiltin(value):
            globals_members.append(Member(name, "Method", _signature(name, value),
                                          _first_paragraph(inspect.getdoc(value))))
        else:  # App, Screen, Clipboard, Debug, Printer, Printers, Forms
            classes.append(ClassInfo(name, "Object", VP6_LIBRARY,
                                     _first_paragraph(inspect.getdoc(type(value))),
                                     lambda cls=type(value): _class_members(cls)))
    classes.append(ClassInfo("Globals", "Globals", VP6_LIBRARY,
                             "VP6's functions, used without an object (from vp6 import *)",
                             lambda: globals_members))
    for title, names in _constant_groups():
        classes.append(_constants_class(title, names))
    colors = [n for n in vp6.__all__ if n.startswith("vp") and n in
              ("vpBlack", "vpBlue", "vpCyan", "vpGreen", "vpMagenta", "vpRed", "vpWhite",
               "vpYellow")]
    schemes = [n for n in vp6.__all__ if n.startswith("vpScheme")]
    classes.append(_constants_class("Colors", colors))
    classes.append(_constants_class("Color schemes", schemes))
    classes.sort(key=lambda c: c.name.lower())
    globals()["_VP6_CLASSES"] = classes
    return classes


# --- the project ----------------------------------------------------------------------------

def _parse(text: str) -> ast.Module:
    """The code's syntax tree; with a syntax error, the code before it."""
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        lines = text.splitlines()[:max((exc.lineno or 1) - 1, 0)]
        while lines:
            try:
                return ast.parse("\n".join(lines))
            except SyntaxError as again:
                lines = lines[:max((again.lineno or 1) - 1, 0)]
        return ast.parse("")


def _function_member(node, path: str) -> Member:
    arguments = [a.arg for a in node.args.args if a.arg != "self"]
    return Member(node.name, "Method", f"{node.name}({', '.join(arguments)})",
                  _first_paragraph(ast.get_docstring(node)), path, node.lineno)


def _module_members(tree: ast.Module, path: str) -> list[Member]:
    members = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            members.append(_function_member(node, path))
        elif isinstance(node, ast.ClassDef):
            members.append(Member(node.name, "Class", f"Class {node.name}",
                                  _first_paragraph(ast.get_docstring(node)), path,
                                  node.lineno))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    kind = "Constant" if target.id.isupper() else "Variable"
                    value = ast.get_source_segment(_SOURCE.get(path, ""), node.value) \
                        if node.value is not None else ""
                    word = "Const" if kind == "Constant" else "Dim"
                    members.append(Member(target.id, kind, f"{word} {target.id} = {value}"
                                          if value else f"{word} {target.id}", "", path,
                                          node.lineno))
    return members


_SOURCE: dict[str, str] = {}  # (the text being parsed, for the variables' values)


def _form_class(tree: ast.Module, document, path: str, kind: str, library: str) -> ClassInfo:
    from ..controls import CONTROL_TYPES

    class_name = document.form_def.class_name
    node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name),
                None)

    def members():
        found = []
        seen = set()
        for control in document.form_def.controls:  # its controls (an array once)
            if control.name in seen:
                continue
            seen.add(control.name)
            array = control.index is not None
            found.append(Member(control.name, "Control",
                                f"{control.name} As {control.type}"
                                + (" (a control array)" if array else ""),
                                "A control on the " + ("user control" if kind == "UserControl"
                                                       else "form"),
                                path, None, control.type))
        if kind == "UserControl":  # its Properties and Events, as on a form
            cls = CONTROL_TYPES.get(class_name)
            if cls is not None:
                for name in cls._specs:
                    if name not in ("Left", "Top", "Width", "Height"):
                        found.append(_property_member(cls, name))
                for member in _class_members(cls):
                    if member.kind == "Event" and member.name in getattr(cls, "Events", ()):
                        found.append(member)
        if node is not None:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        item.name != "InitializeComponent":
                    found.append(_function_member(item, path))
        return found

    return ClassInfo(class_name, kind, library,
                     _first_paragraph(ast.get_docstring(node)) if node else "", members, path,
                     node.lineno if node else None)


def project_library(name: str, documents) -> list[ClassInfo]:
    """The project's forms, user controls and modules: ``documents`` are the
    IDE's (a module's ``kind`` is "module"; a form's or user control's has its
    ``form_def``)."""
    classes = []
    for document in documents:
        text = document.text
        path = document.path
        _SOURCE[path] = text
        tree = _parse(text)
        kind = {"form": "Form", "usercontrol": "UserControl"}.get(document.kind, "Module")
        if kind == "Module":
            classes.append(ClassInfo(os.path.splitext(os.path.basename(path))[0], "Module",
                                     name, _first_paragraph(ast.get_docstring(tree)),
                                     lambda t=tree, p=path: _module_members(t, p), path, 1))
        else:
            classes.append(_form_class(tree, document, path, kind, name))
    classes.sort(key=lambda c: c.name.lower())
    return classes


def search(classes: list[ClassInfo], text: str) -> list[tuple[ClassInfo, Member | None]]:
    """The classes and members whose names contain ``text`` (any case)."""
    needle = text.strip().lower()
    if not needle:
        return []
    found = []
    for info in classes:
        if needle in info.name.lower():
            found.append((info, None))
        found += [(info, m) for m in info.members() if needle in m.name.lower()]
    return found


# --- the window --------------------------------------------------------------------------------

_ICON_COLORS = {"Property": "#4a7bd0", "Method": "#c0392b", "Event": "#e2a700",
                "Constant": "#7f8c8d", "Variable": "#16a085", "Control": "#8e44ad",
                "Class": "#2c6fbb", "Object": "#2c6fbb", "Globals": "#555555",
                "Constants": "#7f8c8d", "Form": "#27ae60", "UserControl": "#d35400",
                "Module": "#16a085"}


def kind_icon(kind: str, type_name: str | None = None) -> QIcon:
    """A control's Toolbox icon; else a small badge with the kind's first
    letter, in its color."""
    if type_name is not None:
        from . import icons

        icon = icons.icon(type_name)
        if not icon.isNull():
            return icon
    pixmap = QPixmap(32, 32)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(_ICON_COLORS.get(kind, "#555555")))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRect(1, 1, 14, 14), 3, 3)
    font = QFont()
    font.setPixelSize(10)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(Qt.white)
    painter.drawText(QRect(1, 1, 14, 14), Qt.AlignCenter, {"Constants": "#", "Globals": "G",
                                                           "UserControl": "U"}.get(kind,
                                                                                   kind[0]))
    painter.end()
    return QIcon(pixmap)


class ObjectBrowser(QWidget):
    """The Object Browser window. ``get_project()`` gives (the project's name,
    its documents), or None without a project; ``goto(path, line, control)``
    shows a project member (its line, or a control on a form)."""

    def __init__(self, get_project: Callable[[], tuple[str, list] | None] = lambda: None,
                 goto: Callable[[str, int | None, str | None], None] = lambda *a: None,
                 parent: QWidget | None = None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Object Browser")
        self._get_project = get_project
        self._goto = goto
        self.classes: list[ClassInfo] = []
        self.shown_members: list[Member] = []
        self.found: list[tuple[ClassInfo, Member | None]] = []

        self.library = QComboBox()
        self.library.currentIndexChanged.connect(lambda *_: self._fill_classes())
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search")
        self.search_edit.returnPressed.connect(self.run_search)
        search_button = QPushButton("&Search")
        search_button.clicked.connect(self.run_search)
        top = QHBoxLayout()
        top.addWidget(self.library, 1)
        top.addWidget(self.search_edit, 1)
        top.addWidget(search_button)

        self.results = QListWidget()  # Search Results
        self.results.setVisible(False)
        self.results.currentRowChanged.connect(self._on_result_chosen)
        self.results.itemActivated.connect(lambda *_: self._activate_member())
        self.class_list = QListWidget()
        self.class_list.currentRowChanged.connect(self._on_class_chosen)
        self.member_list = QListWidget()
        self.member_list.currentRowChanged.connect(self._on_member_chosen)
        self.member_list.itemActivated.connect(lambda *_: self._activate_member())
        lists = QSplitter(Qt.Horizontal)
        lists.addWidget(self._labelled("Classes", self.class_list))
        lists.addWidget(self._labelled("Members", self.member_list))
        lists.setSizes([220, 380])
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.RichText)
        self.details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.setMinimumHeight(70)
        self.details.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        self.details.setMargin(6)
        body = QSplitter(Qt.Vertical)
        body.addWidget(self.results)
        body.addWidget(lists)
        body.addWidget(self.details)
        body.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(body, 1)
        self.resize(640, 520)
        self.refresh()

    @staticmethod
    def _labelled(title: str, widget: QWidget) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        layout.addWidget(widget)
        return box

    # -- what it shows -------------------------------------------------------------------------
    def _project_classes(self) -> list[ClassInfo]:
        project = self._get_project()
        return project_library(*project) if project is not None else []

    def refresh(self) -> None:
        """Read the project again (its code may have changed) and fill the lists."""
        chosen = self.library.currentText()
        project = self._get_project()
        self._project = self._project_classes()
        self.library.blockSignals(True)
        self.library.clear()
        self.library.addItem(ALL_LIBRARIES)
        self.library.addItem(VP6_LIBRARY)
        if project is not None:
            self.library.addItem(project[0])
        index = self.library.findText(chosen)
        self.library.setCurrentIndex(index if index >= 0 else 0)
        self.library.blockSignals(False)
        self._fill_classes()

    def library_classes(self) -> list[ClassInfo]:
        chosen = self.library.currentText()
        if chosen == VP6_LIBRARY:
            return vp6_library()
        if chosen == ALL_LIBRARIES:
            return sorted(self._project + vp6_library(), key=lambda c: c.name.lower())
        return list(self._project)

    def _fill_classes(self) -> None:
        self.classes = self.library_classes()
        self.class_list.clear()
        for info in self.classes:
            self.class_list.addItem(QListWidgetItem(kind_icon(info.kind, info.type_name),
                                                    info.name))
        if self.classes:
            self.class_list.setCurrentRow(0)
        else:
            self.member_list.clear()
            self.details.clear()

    def show_class(self, name: str, member: str | None = None) -> bool:
        """Select a class (and one of its members) by name."""
        for row, info in enumerate(self.classes):
            if info.name == name:
                self.class_list.setCurrentRow(row)
                self.class_list.scrollToItem(self.class_list.item(row))
                if member is not None:
                    for index, item in enumerate(self.shown_members):
                        if item.name == member:
                            self.member_list.setCurrentRow(index)
                            self.member_list.scrollToItem(self.member_list.item(index))
                            return True
                    return False
                return True
        return False

    def _on_class_chosen(self, row: int) -> None:
        self.member_list.clear()
        if not 0 <= row < len(self.classes):
            self.shown_members = []
            return
        info = self.classes[row]
        self.shown_members = info.members()
        for member in self.shown_members:
            self.member_list.addItem(QListWidgetItem(kind_icon(member.kind, member.type_name),
                                                     member.name))
        self._show_class_details(info)

    def _show_class_details(self, info: ClassInfo) -> None:
        kind = {"Constants": "Constants", "Globals": "Functions"}.get(info.kind, info.kind)
        self.details.setText(f"<b>{kind} {_html(info.name)}</b><br>"
                             f"Member of <b>{_html(info.library)}</b><br>"
                             f"{_html(info.description)}")

    def _on_member_chosen(self, row: int) -> None:
        if not 0 <= row < len(self.shown_members):
            return
        info = self.classes[self.class_list.currentRow()]
        self._show_member_details(info, self.shown_members[row])

    def _show_member_details(self, info: ClassInfo, member: Member) -> None:
        where = f"Member of <b>{_html(info.library)}.{_html(info.name)}</b>"
        self.details.setText(f"<b>{_html(member.declaration)}</b><br>{where}<br>"
                             f"{_html(member.description)}")

    # -- search -------------------------------------------------------------------------------
    def run_search(self) -> None:
        """List the classes and members whose names contain the search text."""
        self.found = search(self.library_classes(), self.search_edit.text())
        self.results.clear()
        for info, member in self.found:
            text = f"{info.library}  {info.name}" + (f".{member.name}" if member else "")
            icon = kind_icon(member.kind, member.type_name) if member else \
                kind_icon(info.kind, info.type_name)
            self.results.addItem(QListWidgetItem(icon, text))
        self.results.setVisible(bool(self.search_edit.text().strip()))
        if not self.found and self.search_edit.text().strip():
            self.results.addItem("(nothing found)")

    def _on_result_chosen(self, row: int) -> None:
        if 0 <= row < len(self.found):
            info, member = self.found[row]
            self.show_class(info.name, member.name if member else None)

    # -- going to a project member -------------------------------------------------------------
    def _activate_member(self) -> None:
        row = self.member_list.currentRow()
        if 0 <= row < len(self.shown_members):
            member = self.shown_members[row]
            if member.path is not None:
                self._goto(member.path, member.line,
                           member.name if member.kind == "Control" else None)
                return
        info = self.classes[self.class_list.currentRow()] \
            if 0 <= self.class_list.currentRow() < len(self.classes) else None
        if info is not None and info.path is not None and row < 0:
            self._goto(info.path, info.line, None)

    def sizeHint(self) -> QSize:
        return QSize(640, 520)


def _html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
