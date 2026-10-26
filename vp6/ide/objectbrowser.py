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

from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget)

from .logic.library import (ALL_LIBRARIES, VP6_LIBRARY, ClassInfo, Member,  # noqa: F401
                            project_library, search, vp6_library)

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

    def help_topic(self) -> tuple[str, str]:
        """What F1 asks the help about here: the member chosen (and its class),
        else the class."""
        row = self.class_list.currentRow()
        if not 0 <= row < len(self.classes):
            return "", ""
        info = self.classes[row]
        member = self.member_list.currentRow()
        if self.member_list.hasFocus() and 0 <= member < len(self.shown_members):
            return self.shown_members[member].name, info.name
        return info.name, ""

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
