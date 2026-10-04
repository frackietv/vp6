"""The Debug panel: the Watches, the Call Stack and the Breakpoints, side by
side at the bottom of the IDE (View > Debug Window).

``CallStackView`` lists the paused program's frames, innermost first;
choosing one makes it the frame the Immediate window and the watches
evaluate in. ``BreakpointList`` lists the breakpoints of every open file,
with a check box to enable or disable each; double-clicking goes to it.
The main window connects them to the documents and the debugger.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QMenu, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..project import EXTENSION
from .debugger import WatchWindow
from .theme import theme_manager

_PATH, _LINE = Qt.UserRole, Qt.UserRole + 1  # (where an item points: its file and line)
_FRAME = Qt.UserRole + 2  # (a call stack item's frame: its index in the program's stack)


def _themed(tree: QTreeWidget) -> None:
    colors = theme_manager().current().colors
    palette = tree.palette()
    for group in (QPalette.Active, QPalette.Inactive):
        palette.setColor(group, QPalette.Base, QColor(colors["background"]))
        palette.setColor(group, QPalette.Text, QColor(colors["foreground"]))
    tree.setPalette(palette)
    tree.setFont(theme_manager().font())


def _section(title: str, body: QWidget) -> QWidget:
    """A part of the panel: its title over it."""
    label = QLabel(title)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    label.setContentsMargins(4, 2, 4, 2)
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(label)
    layout.addWidget(body)
    widget.title = label
    return widget


class CallStackView(QTreeWidget):
    """The paused program's procedures, innermost first (VB's Call Stack).
    Choosing one (``frameChosen``) evaluates in it and shows its line."""

    frameChosen = Signal(int, str, int)  # index (0: innermost), file, line

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["Procedure", "Where"])
        self.setRootIsDecorated(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setStretchLastSection(True)
        self.itemActivated.connect(self._on_activated)
        self.itemClicked.connect(self._on_activated)
        self.current = 0

    def show_stack(self, stack: list[dict]) -> None:
        """The frames of a pause (none: running, or paused between events)."""
        self.clear()
        self.current = 0
        for index, frame in enumerate(stack):
            if frame["file"].endswith(EXTENSION):
                continue  # (the project file, which started it: not a procedure of its own)
            name = os.path.splitext(os.path.basename(frame["file"]))[0]
            item = QTreeWidgetItem([f"{name}.{frame['function']}",
                                    f"line {frame['line']}"])
            item.setData(0, _PATH, frame["file"])
            item.setData(0, _LINE, frame["line"])
            item.setData(0, _FRAME, index)
            self.addTopLevelItem(item)
        self._mark()

    def _mark(self) -> None:
        for index in range(self.topLevelItemCount()):
            item = self.topLevelItem(index)
            font = item.font(0)
            font.setBold(index == self.current)  # (the frame evaluated in)
            item.setFont(0, font)
            item.setFont(1, font)

    def choose(self, index: int) -> None:
        item = self.topLevelItem(index)
        if item is None:
            return
        self.current = index
        self._mark()
        self.setCurrentItem(item)
        self.frameChosen.emit(item.data(0, _FRAME), item.data(0, _PATH), item.data(0, _LINE))

    def _on_activated(self, item, _column=0):
        self.choose(self.indexOfTopLevelItem(item))


class BreakpointList(QTreeWidget):
    """Every breakpoint of the open files: a check box to enable it, its file
    and line, and the line's code. Double-click (or Enter) goes to it; Delete
    removes it."""

    goTo = Signal(str, int)  # file, line
    enableRequested = Signal(str, int, bool)
    removeRequested = Signal(str, int)
    removeAllRequested = Signal()
    enableAllRequested = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["Breakpoint", "Code"])
        self.setRootIsDecorated(False)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setStretchLastSection(True)
        self.itemActivated.connect(lambda item, _c: self.goTo.emit(
            item.data(0, _PATH), item.data(0, _LINE)))
        self.itemChanged.connect(self._on_item_changed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.installEventFilter(self)
        self._filling = False

    def show_breakpoints(self, breakpoints: list[tuple[str, int, bool, str]]) -> None:
        """(file, line, enabled, the line's code) of each, in order."""
        selected = {(i.data(0, _PATH), i.data(0, _LINE)) for i in self.selectedItems()}
        self._filling = True
        self.clear()
        for path, line, enabled, code in breakpoints:
            item = QTreeWidgetItem([f"{os.path.basename(path)}:{line}", code.strip()])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if enabled else Qt.Unchecked)
            item.setData(0, _PATH, path)
            item.setData(0, _LINE, line)
            item.setToolTip(0, f"{path}, line {line}")
            self.addTopLevelItem(item)
            item.setSelected((path, line) in selected)
        self._filling = False

    def entries(self) -> list[tuple[str, int, bool]]:
        return [(item.data(0, _PATH), item.data(0, _LINE),
                 item.checkState(0) == Qt.Checked)
                for item in (self.topLevelItem(i) for i in range(self.topLevelItemCount()))]

    def _on_item_changed(self, item, column):
        if not self._filling and column == 0:
            self.enableRequested.emit(item.data(0, _PATH), item.data(0, _LINE),
                                      item.checkState(0) == Qt.Checked)

    def remove_selected(self) -> None:
        for item in list(self.selectedItems()):
            self.removeRequested.emit(item.data(0, _PATH), item.data(0, _LINE))

    def eventFilter(self, watched, event):
        if watched is self and event.type() == QEvent.KeyPress and \
                (event.matches(QKeySequence.Delete) or event.key() == Qt.Key_Backspace):
            self.remove_selected()
            return True
        return super().eventFilter(watched, event)

    def _context_menu(self) -> QMenu:
        menu = QMenu(self)
        item = self.currentItem()
        go = menu.addAction("Go to Breakpoint", lambda: self.goTo.emit(
            item.data(0, _PATH), item.data(0, _LINE)))
        go.setEnabled(item is not None)
        menu.addAction("Delete Breakpoint", self.remove_selected).setEnabled(
            bool(self.selectedItems()))
        menu.addSeparator()
        some = self.topLevelItemCount() > 0
        menu.addAction("Enable All", lambda: self.enableAllRequested.emit(True)).setEnabled(some)
        menu.addAction("Disable All",
                       lambda: self.enableAllRequested.emit(False)).setEnabled(some)
        menu.addAction("Delete All", self.removeAllRequested.emit).setEnabled(some)
        return menu

    def _on_context_menu(self, pos) -> None:
        menu = self._context_menu()
        menu.exec(self.viewport().mapToGlobal(pos))
        menu.deleteLater()


class DebugPanel(QWidget):
    """The Watches, the Call Stack and the Breakpoints, side by side."""

    def __init__(self, watches: WatchWindow | None = None, parent=None):
        super().__init__(parent)
        self.watches = watches or WatchWindow()
        self.call_stack = CallStackView()
        self.breakpoints = BreakpointList()
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.sections = [_section("Watches", self.watches),
                         _section("Call Stack", self.call_stack),
                         _section("Breakpoints", self.breakpoints)]
        for section in self.sections:
            self.splitter.addWidget(section)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
        self.apply_theme()
        theme_manager().changed.connect(self.apply_theme)

    def apply_theme(self) -> None:
        for tree in (self.call_stack, self.breakpoints):
            _themed(tree)

    def not_paused(self) -> None:
        """Running (or ended): no stack."""
        self.call_stack.show_stack([])

