"""The IDE's side of the debugger (the program's is ``vp6/debugagent.py``).

``DebugSession`` listens on a localhost port the program is told of
(``VP6_DEBUG_PORT``) and speaks the agent's protocol: it sends the
breakpoints first (``start``), then pauses, steps, continues and evaluates;
``paused``, ``resumed`` and results come back as signals and callbacks.

``WatchWindow`` is the Watches panel: expressions evaluated in the current
frame each time the program stops.
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette
from PySide6.QtNetwork import QHostAddress, QTcpServer
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QMenu, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..debugagent import canonical
from .theme import theme_manager

class DebugSession(QObject):
    """One run of the program under the debugger."""

    connected = Signal()
    paused = Signal(dict)  # the agent's "paused" message: reason, file, line, stack, error
    resumed = Signal()

    def __init__(self, breakpoints: dict[str, list[int]], step: bool = False, parent=None):
        super().__init__(parent)
        self._breakpoints = breakpoints
        self._step = step
        self._socket = None
        self._buffer = b""
        self._next_id = 0
        self._callbacks: dict[int, object] = {}
        self.location: dict | None = None  # where it is paused (None: running)
        self.frame = 0  # the frame of the stack expressions are evaluated in
        self.server = QTcpServer(self)
        if not self.server.listen(QHostAddress.LocalHost, 0):
            raise OSError(self.server.errorString())
        self.server.newConnection.connect(self._on_connection)

    @property
    def port(self) -> int:
        return self.server.serverPort()

    @property
    def is_paused(self) -> bool:
        return self.location is not None

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    # -- the connection ----------------------------------------------------------------------
    def _on_connection(self):
        socket = self.server.nextPendingConnection()
        if self._socket is not None:  # (one program: a later one is refused)
            socket.close()
            return
        self._socket = socket
        socket.readyRead.connect(self._on_ready_read)
        socket.disconnected.connect(self._on_disconnected)
        self.server.close()
        self._send({"cmd": "start", "breakpoints": self._breakpoints, "step": self._step})
        self.connected.emit()

    def _send(self, message: dict) -> None:
        if self._socket is not None:
            self._socket.write((json.dumps(message) + "\n").encode("utf-8"))
            self._socket.flush()

    def _on_ready_read(self):
        self._buffer += bytes(self._socket.readAll())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                message = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            self._dispatch(message)

    def _dispatch(self, message: dict) -> None:
        event = message.get("event")
        if event == "paused":
            self.location = message
            self.frame = 0
            self.paused.emit(message)
        elif event == "running":
            self.location = None
            self.resumed.emit()
        elif event == "result":
            callback = self._callbacks.pop(message.get("id"), None)
            if callback is not None:
                callback(message)

    def _on_disconnected(self):
        was_paused = self.is_paused
        self.location = None
        self._socket = None
        self._callbacks.clear()
        if was_paused:
            self.resumed.emit()

    def close(self) -> None:
        if self._socket is not None:
            self._socket.abort()
            self._socket = None
        self.server.close()
        self.location = None

    # -- commands ------------------------------------------------------------------------------
    def set_breakpoints(self, breakpoints: dict[str, list[int]]) -> None:
        self._breakpoints = breakpoints
        self._send({"cmd": "breakpoints", "breakpoints": breakpoints})

    def pause(self) -> None:
        if not self.is_paused:
            self._send({"cmd": "pause"})

    def resume(self, how: str = "continue") -> None:
        """continue, step (into), next (over) or return (out)."""
        if self.is_paused:
            self._send({"cmd": how})

    def apply_changes(self, files: dict[str, str], callback) -> None:
        """Edit and Continue: send the files' new text (path → text) to the
        paused program; ``callback`` gets what was changed (``changed``,
        ``added``, ``removed``, ``running``, ``errors``, ``files``)."""
        if not self.is_paused:
            callback({"errors": ["The program isn't paused"], "files": []})
            return
        self._next_id += 1
        self._callbacks[self._next_id] = callback
        self._send({"cmd": "apply", "id": self._next_id, "files": files})

    def evaluate(self, expression: str, callback, statements: bool = False) -> None:
        """Evaluate an expression (or, with ``statements``, run a statement) in
        the current frame while paused; ``callback`` gets the result (``value``
        and ``type``, or ``error``)."""
        if not self.is_paused:
            callback({"error": "The program isn't paused"})
            return
        self._next_id += 1
        self._callbacks[self._next_id] = callback
        self._send({"cmd": "eval", "id": self._next_id, "expr": expression,
                    "frame": self.frame, "exec": statements})


class WatchWindow(QWidget):
    """The Watches panel: an expression a row, with its value and type each
    time the program stops (Debug > Add Watch; double-click to edit, Delete to
    remove)."""

    changed = Signal()  # the expressions changed: evaluate them again

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Expression", "Value", "Type"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked |
                                  QAbstractItemView.EditKeyPressed)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        self.tree.setColumnWidth(0, 200)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.installEventFilter(self)  # Delete (and Backspace) remove the selected ones
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)
        self._filling = False
        self.apply_theme()
        theme_manager().changed.connect(self.apply_theme)

    def apply_theme(self) -> None:
        colors = theme_manager().current().colors
        palette = self.tree.palette()
        for group in (QPalette.Active, QPalette.Inactive):
            palette.setColor(group, QPalette.Base, QColor(colors["background"]))
            palette.setColor(group, QPalette.Text, QColor(colors["foreground"]))
        self.tree.setPalette(palette)
        self.tree.setFont(theme_manager().font())

    # -- the expressions -------------------------------------------------------------------------
    def expressions(self) -> list[str]:
        return [item.text(0) for item in self.items()]

    def items(self) -> list[QTreeWidgetItem]:
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    def add(self, expression: str) -> None:
        expression = expression.strip()
        if not expression:
            return
        self._filling = True
        item = QTreeWidgetItem([expression, "", ""])
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.tree.addTopLevelItem(item)
        self._filling = False
        self.changed.emit()

    def remove_selected(self) -> None:
        for item in self.tree.selectedItems():
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))

    def clear(self) -> None:
        self.tree.clear()

    def _on_item_changed(self, item, column):
        if self._filling or column != 0:
            return
        if not item.text(0).strip():  # (emptied: gone)
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
            return
        self.set_value(item, "", "")
        self.changed.emit()

    def set_value(self, item: QTreeWidgetItem, value: str, type_name: str,
                  error: bool = False) -> None:
        if self.tree.indexOfTopLevelItem(item) < 0:  # (removed since it was asked)
            return
        self._filling = True
        item.setText(1, value)
        item.setText(2, type_name)
        color = QColor(theme_manager().current().colors["output_error"]) if error else None
        item.setForeground(1, color if color is not None else self.tree.palette().text())
        self._filling = False

    def show_result(self, item: QTreeWidgetItem, expression: str, result: dict) -> None:
        """Show what evaluating an item's expression gave (unless it was edited
        or removed since)."""
        if item.text(0) != expression:
            return
        if "error" in result:
            self.set_value(item, f"<{result['error']}>", "", error=True)
        else:
            self.set_value(item, result.get("value") or "", result.get("type", ""))

    def out_of_context(self) -> None:
        """The program isn't running: no values."""
        for item in self.items():
            self.set_value(item, "<not running>", "")

    def eventFilter(self, watched, event):
        if watched is self.tree and event.type() == QEvent.KeyPress and \
                self.tree.state() != QAbstractItemView.EditingState and \
                (event.matches(QKeySequence.Delete) or event.key() == Qt.Key_Backspace):
            self.remove_selected()
            return True
        return super().eventFilter(watched, event)

    def _context_menu(self) -> QMenu:
        menu = QMenu(self.tree)
        selected = bool(self.tree.selectedItems())
        edit = menu.addAction("Edit Watch", lambda: self.tree.editItem(
            self.tree.currentItem(), 0))
        edit.setEnabled(self.tree.currentItem() is not None)
        menu.addAction("Delete Watch", self.remove_selected).setEnabled(selected)
        menu.addSeparator()
        menu.addAction("Clear All", self.clear).setEnabled(self.tree.topLevelItemCount() > 0)
        return menu

    def _on_context_menu(self, pos) -> None:
        menu = self._context_menu()
        menu.exec(self.tree.viewport().mapToGlobal(pos))
        menu.deleteLater()


def same_file(a: str, b: str) -> bool:
    return canonical(a) == canonical(b) if a and b else False


def describe(location: dict) -> str:
    """Where the program is paused, for the status bar."""
    if not location.get("file"):
        return "Paused between events"
    where = f"{os.path.basename(location['file'])}, line {location['line']}"
    return {"breakpoint": f"Breakpoint at {where}", "error": f"Error at {where}",
            "pause": f"Paused at {where}"}.get(location.get("reason"), f"Paused at {where}")
