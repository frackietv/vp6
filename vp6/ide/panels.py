"""Toolbox, Project Explorer, Immediate window and Output window."""

from __future__ import annotations

import os
import re

from PySide6.QtCore import QProcess, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QButtonGroup, QGridLayout, QLineEdit, QMenu, QPlainTextEdit, QToolButton, QTreeWidget,
    QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout, QWidget,
)

from ..controls import CONTROL_TYPES
from ..project import SUB_MAIN, Project
from . import icons
from .theme import theme_manager


class Toolbox(QWidget):
    """The General tab of the VB toolbox."""

    toolSelected = Signal(object)  # control type name or None for the pointer
    toolActivated = Signal(str)  # double-click: add the control to the form

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(4, 4, 4, 4)
        self.buttons: dict[str | None, QToolButton] = {}
        tools = [None, *(name for name, cls in CONTROL_TYPES.items() if cls.InToolbox)]
        for index, type_name in enumerate(tools):
            button = QToolButton()
            button.setIcon(icons.icon(type_name or "Pointer"))
            button.setIconSize(QSize(24, 24))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(type_name or "Pointer")
            button.setFixedSize(34, 34)
            button.clicked.connect(lambda _=False, t=type_name: self.toolSelected.emit(t))
            if type_name:
                button.mouseDoubleClickEvent = \
                    lambda event, t=type_name: self.toolActivated.emit(t)
            self.group.addButton(button)
            self.buttons[type_name] = button
            grid.addWidget(button, index // 2, index % 2)
        self.buttons[None].setChecked(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(grid)
        layout.addStretch(1)

    def refresh_icons(self) -> None:
        """Redraw the icons after switching between light and dark."""
        for type_name, button in self.buttons.items():
            button.setIcon(icons.icon(type_name or "Pointer"))

    def reset(self) -> None:
        self.buttons[None].setChecked(True)
        self.toolSelected.emit(None)


class ProjectExplorer(QWidget):
    openObject = Signal(str)  # path -> designer
    openCode = Signal(str)  # path -> code window
    removeFile = Signal(str)
    setStartup = Signal(str)
    addForm = Signal()
    addModule = Signal()
    projectSelected = Signal()  # the project (root) item became current
    fileSelected = Signal(str)  # a form or module item became current

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_code = QToolButton()
        self.view_code.setText("View Code")
        self.view_object = QToolButton()
        self.view_object.setText("View Object")
        self.view_code.clicked.connect(self._on_view_code)
        self.view_object.clicked.connect(self._on_view_object)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.currentItemChanged.connect(self._update_buttons)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        buttons = QGridLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.view_code, 0, 0)
        buttons.addWidget(self.view_object, 0, 1)
        buttons.setColumnStretch(2, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(buttons)
        layout.addWidget(self.tree)
        self._update_buttons()

    def populate(self, project: Project | None, names: dict[str, str]) -> None:
        """names maps absolute path -> display name (form class / module name)."""
        self.tree.clear()
        if project is None:
            return
        root = QTreeWidgetItem([f"{project.name} ({os.path.basename(project.path)})"])
        root.setIcon(0, icons.icon("Project"))
        self.tree.addTopLevelItem(root)
        for title, files, kind in (("Forms", project.forms, "form"),
                                   ("Modules", project.modules, "module")):
            if not files:
                continue
            folder = QTreeWidgetItem([title])
            folder.setIcon(0, icons.icon("Project"))
            root.addChild(folder)
            for relative in files:
                path = project.abspath(relative)
                name = names.get(path, os.path.splitext(relative)[0])
                item = QTreeWidgetItem([f"{name} ({relative})"])
                item.setIcon(0, icons.icon("Form" if kind == "form" else "Module"))
                item.setData(0, Qt.UserRole, path)
                item.setData(0, Qt.UserRole + 1, kind)
                item.setData(0, Qt.UserRole + 2, name)
                is_startup = (kind == "form" and name == project.startup) or \
                    (project.startup == SUB_MAIN and kind == "module"
                     and re.search(r"^def Main\(", open(path, encoding="utf-8").read(), re.M)
                     if os.path.exists(path) else False)
                if is_startup:
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                folder.addChild(item)
        self.tree.expandAll()

    def select_path(self, path: str | None) -> None:
        """Select the item of a file (e.g. the one in the active window)
        without opening anything."""
        if path is None:
            return
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value() is not None:
            item = iterator.value()
            if item.data(0, Qt.UserRole) == path:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                return
            iterator += 1

    def select_project(self) -> None:
        root = self.tree.topLevelItem(0)
        if root is not None:
            self.tree.setCurrentItem(root)

    def project_selected(self) -> bool:
        item = self.tree.currentItem()
        return item is not None and item.parent() is None

    def _on_current_changed(self, item, _previous) -> None:
        if item is None:
            return
        if item.parent() is None:
            self.projectSelected.emit()
        elif item.data(0, Qt.UserRole):
            self.fileSelected.emit(item.data(0, Qt.UserRole))

    def _current(self):
        item = self.tree.currentItem()
        if item is None or item.data(0, Qt.UserRole) is None:
            return None, None
        return item.data(0, Qt.UserRole), item.data(0, Qt.UserRole + 1)

    def _update_buttons(self, *_):
        path, kind = self._current()
        self.view_code.setEnabled(path is not None)
        self.view_object.setEnabled(kind == "form")

    def _on_view_code(self):
        path, _ = self._current()
        if path:
            self.openCode.emit(path)

    def _on_view_object(self):
        path, kind = self._current()
        if path and kind == "form":
            self.openObject.emit(path)

    def _on_double_click(self, item, _column):
        path, kind = item.data(0, Qt.UserRole), item.data(0, Qt.UserRole + 1)
        if path:
            (self.openObject if kind == "form" else self.openCode).emit(path)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item is not None and item.data(0, Qt.UserRole):
            self.tree.setCurrentItem(item)
            path, kind = item.data(0, Qt.UserRole), item.data(0, Qt.UserRole + 1)
            menu.addAction("View Code", lambda: self.openCode.emit(path))
            if kind == "form":
                menu.addAction("View Object", lambda: self.openObject.emit(path))
                menu.addAction("Set as Start Up",
                               lambda: self.setStartup.emit(item.data(0, Qt.UserRole + 2)))
            menu.addSeparator()
            menu.addAction(f"Remove {os.path.basename(path)}", lambda: self.removeFile.emit(path))
            menu.addSeparator()
        menu.addAction("Add Form", self.addForm.emit)
        menu.addAction("Add Module", self.addModule.emit)
        menu.exec(self.tree.viewport().mapToGlobal(pos))


class _OutputPane(QWidget):
    """A read-only, themed text pane for program output. Text is appended with
    a kind (out, err, info, in) that picks its color; the kind is stored on
    the text, so a theme change recolors what's already there."""

    _KIND = QTextFormat.UserProperty + 1  # char format property: output kind

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(20000)
        self.output.setContextMenuPolicy(Qt.CustomContextMenu)
        self.output.customContextMenuRequested.connect(self._on_context_menu)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self.output)

    def _start_theming(self) -> None:
        """Call at the end of the subclass constructor."""
        self.apply_theme()
        theme_manager().changed.connect(self.apply_theme)

    def _themed_widgets(self) -> list[QWidget]:
        return [self.output]

    def apply_theme(self) -> None:
        theme = theme_manager().current()
        colors = theme.colors
        font = theme_manager().font()
        font.setPointSize(max(font.pointSize() - 1, 6))
        for widget in self._themed_widgets():
            palette = widget.palette()
            for group in (QPalette.Active, QPalette.Inactive):
                palette.setColor(group, QPalette.Base, QColor(colors["background"]))
                palette.setColor(group, QPalette.Text, QColor(colors["foreground"]))
                palette.setColor(group, QPalette.Highlight,
                                 QColor(colors["selection_background"]))
                palette.setColor(group, QPalette.HighlightedText,
                                 QColor(colors["selection_foreground"]))
            dimmed = QColor(colors["foreground"])
            dimmed.setAlpha(130)
            palette.setColor(QPalette.Disabled, QPalette.Base, QColor(colors["background"]))
            palette.setColor(QPalette.Disabled, QPalette.Text, dimmed)
            for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
                palette.setColor(group, QPalette.PlaceholderText, dimmed)
            widget.setPalette(palette)
            widget.setFont(font)
        # Recolor what's already in the window
        document = self.output.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                kind = fragment.charFormat().property(self._KIND)
                if kind:
                    cursor = QTextCursor(document)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(),
                                       QTextCursor.KeepAnchor)
                    cursor.setCharFormat(self._format(kind))
                iterator += 1
            block = block.next()

    def _format(self, kind: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        role = {"err": "output_error", "info": "output_info", "in": "output_input"}.get(kind)
        if role:
            fmt.setForeground(QColor(theme_manager().current().colors[role]))
            fmt.setProperty(self._KIND, kind)
        if kind == "info":
            fmt.setFontItalic(True)
        return fmt

    def clear(self) -> None:
        self.output.clear()

    def append(self, text: str, kind: str = "out") -> None:
        # Keep following the end only if the user was already there
        scrollbar = self.output.verticalScrollBar()
        at_end = scrollbar.value() >= scrollbar.maximum() - 2
        cursor = QTextCursor(self.output.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text, self._format(kind))
        if at_end:
            scrollbar.setValue(scrollbar.maximum())

    def _context_menu(self) -> QMenu:
        raise NotImplementedError

    def _on_context_menu(self, pos) -> None:
        menu = self._context_menu()
        menu.exec(self.output.viewport().mapToGlobal(pos))
        menu.deleteLater()


class ImmediateWindow(_OutputPane):
    """Program output (stdout/stderr, Debug.Print) plus a line for stdin."""

    openLocation = Signal(str, int)  # path, line
    inputSubmitted = Signal(str)

    _LOCATION_RE = re.compile(r'File "([^"]+)", line (\d+)')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output.mouseDoubleClickEvent = self._on_double_click
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type input for the running program and press Enter")
        self.input.returnPressed.connect(self._submit)
        self.input.setEnabled(False)
        self._layout.addWidget(self.input)
        self._start_theming()

    def _themed_widgets(self) -> list[QWidget]:
        return [self.output, self.input]

    def set_running(self, running: bool) -> None:
        self.input.setEnabled(running)
        if running:
            self.input.setFocus()

    def _submit(self) -> None:
        text = self.input.text()
        self.input.clear()
        self.append(text + "\n", "in")
        self.inputSubmitted.emit(text)

    def _context_menu(self) -> QMenu:
        """Qt's standard text menu (Copy, Select All) plus Clear."""
        menu = self.output.createStandardContextMenu()
        menu.addSeparator()
        clear = menu.addAction("Clear", self.clear)
        clear.setEnabled(not self.output.document().isEmpty())
        return menu

    def _on_double_click(self, event) -> None:
        cursor = self.output.cursorForPosition(event.position().toPoint())
        line = cursor.block().text()
        match = self._LOCATION_RE.search(line)
        if match:
            self.openLocation.emit(match.group(1), int(match.group(2)))
        else:
            QPlainTextEdit.mouseDoubleClickEvent(self.output, event)


class OutputWindow(_OutputPane):
    """The IDE's own stdout and stderr, including libraries such as Qt (see
    ``outputcapture.OutputCapture``). Hidden by default; View > Output Window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_theming()

    def _context_menu(self) -> QMenu:
        menu = QMenu(self.output)
        select_all = menu.addAction("Select All", self.output.selectAll)
        copy = menu.addAction("Copy", self.output.copy)
        menu.addSeparator()
        clear = menu.addAction("Clear", self.clear)
        empty = self.output.document().isEmpty()
        select_all.setEnabled(not empty)
        copy.setEnabled(self.output.textCursor().hasSelection())
        clear.setEnabled(not empty)
        return menu


def pump_process_output(process: QProcess, window: ImmediateWindow) -> None:
    process.readyReadStandardOutput.connect(
        lambda: window.append(bytes(process.readAllStandardOutput()).decode("utf-8", "replace")))
    process.readyReadStandardError.connect(
        lambda: window.append(bytes(process.readAllStandardError()).decode("utf-8", "replace"),
                              "err"))
