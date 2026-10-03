"""The IDE's Terminal panel: a shell in the project's folder, as the Terminal
control (``vp6/terminal.py``) runs it, in the editor theme's colors and font.

The shell starts when the panel is first shown. When it ends, Enter starts a
new one; the panel's menu (a right click) copies, pastes, clears, and starts a
new shell or ends the one running.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QMenu, QVBoxLayout, QWidget

from ..terminal import Terminal
from .theme import theme_manager


class _PanelHost:
    """What a Terminal needs of its form, for the one in the panel: its widget
    is the container, its events come to the panel."""

    _design_mode = False
    KeyPreview = False

    def __init__(self, panel: "TerminalPanel"):
        self._panel = panel
        self._controls: list = []

    def _owner_form(self):
        return self

    def _container_widget(self) -> QWidget:
        return self._panel

    def _base_dir(self) -> str:
        return self._panel.folder()

    def _register_control(self, control) -> None:
        self._controls.append(control)

    def _style_widget(self, widget) -> None:
        pass  # (the IDE's own look)

    def _layout_aligned(self) -> None:
        pass

    def _apply_tab_order(self) -> None:
        pass

    def _preview_key(self, *_) -> bool:
        return False

    def _handle_default_cancel(self, *_) -> bool:
        return False

    def _fire(self, *_):
        return None

    # The Terminal's events (as a form's handlers: Name_Event)
    def Shell_Exited(self, ExitCode):
        self._panel._exited(ExitCode)

    def Shell_TitleChange(self, Title):
        self._panel.titleChanged.emit(Title)


class TerminalPanel(QWidget):
    """A shell in the IDE (View > Terminal Window). ``folder`` gives the
    folder a new shell starts in (the project's, else the home folder)."""

    titleChanged = Signal(str)  # the title the shell gave its terminal

    def __init__(self, folder=None, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._replacing = False  # (new_shell ending the one before)
        self._host = _PanelHost(self)
        self.terminal = Terminal(self._host, "Shell", AutoStart=False)  # (showEvent)
        self.view = self.terminal._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        self.view.installEventFilter(self)
        self.apply_theme()
        theme_manager().changed.connect(self.apply_theme)

    def folder(self) -> str:
        """Where a new shell starts."""
        folder = self._folder() if self._folder is not None else None
        return folder if folder and os.path.isdir(folder) else os.path.expanduser("~")

    @property
    def running(self) -> bool:
        return self.terminal.Running

    # -- the shell ----------------------------------------------------------------------------
    def new_shell(self) -> None:
        """End the shell running (if any) and start another in the folder."""
        terminal = self.terminal
        if terminal.Running:
            self._replacing = True  # (its end doesn't say "Enter")
            try:
                self.end_shell()
            finally:
                self._replacing = False
        terminal.Clear()
        terminal.WorkingDirectory = self.folder()
        terminal.Start()
        self.view.setFocus()

    def end_shell(self) -> None:
        """End the shell at once (also when the IDE closes), and wait for it."""
        if self.terminal.Running:
            self.terminal._program.end()

    def _exited(self, code: int) -> None:
        if self._replacing:
            return
        self.terminal._screen.feed(f"\r\n\x1b[2m[The shell ended with code {code}. "
                                   f"Press Enter for a new one.]\x1b[0m\r\n")
        self.terminal._redraw()

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == QEvent.KeyPress and \
                event.key() in (Qt.Key_Return, Qt.Key_Enter) and not self.running:
            self.new_shell()
            return True
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.terminal._started:  # the first time it is shown
            self.new_shell()

    # -- look ---------------------------------------------------------------------------------
    def apply_theme(self) -> None:
        """The editor theme's colors and font (a point smaller, as the Immediate
        window's)."""
        colors = theme_manager().current().colors
        terminal = self.terminal
        terminal.BackColor = colors["background"]
        terminal.ForeColor = colors["foreground"]
        font = theme_manager().font()
        terminal.FontName = font.family()
        terminal.FontSize = max(font.pointSize() - 1, 6)

    # -- the menu -----------------------------------------------------------------------------
    def _context_menu(self) -> QMenu:
        menu = QMenu(self.view)
        copy = menu.addAction("Copy", self.terminal.Copy)
        copy.setEnabled(self.view.selection is not None)
        menu.addAction("Paste", self.terminal.Paste).setEnabled(self.running)
        menu.addSeparator()
        menu.addAction("Clear", self.terminal.Clear)
        menu.addSeparator()
        menu.addAction("New Shell", self.new_shell)
        menu.addAction("End Shell", self.end_shell).setEnabled(self.running)
        return menu

    def _on_context_menu(self, pos) -> None:
        screen = self.terminal._screen
        if screen.mouse_mode and self.running:
            return  # (the program has the mouse: its right button is its own)
        menu = self._context_menu()
        menu.exec(self.view.mapToGlobal(pos))
        menu.deleteLater()
