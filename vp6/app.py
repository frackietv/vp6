"""Application level services: the Qt application, App/Screen/Clipboard
objects, DoEvents, End and the VB style run-time error handling."""

from __future__ import annotations

import inspect
import os
import signal
import socket
import sys
import threading
import traceback

from PySide6.QtCore import QEventLoop, QObject, QSocketNotifier, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

_interrupt_handler = None  # installed by ensure_app() for VP6 programs


def ensure_app() -> QApplication:
    """Return the QApplication, creating it on first use. A VP6 program
    creates it here, so this is also where Ctrl+C gets wired to closing the
    program's forms, and where it gets the VP6 icon (until the project's own
    icon replaces it, see set_program_icon). (The IDE and the tests create
    their own QApplication and keep their own Ctrl+C behavior.)"""
    global _interrupt_handler
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
        _interrupt_handler = install_interrupt_handler(close_all_windows)
        app.setWindowIcon(vp6_icon())
    return app


# --- icons -----------------------------------------------------------------------------------

# The VP6 icon (project.VP6_ICON_FILES, several sizes): the IDE's icon, and
# every program's until its project names its own


def icon_from(paths) -> QIcon:
    """An icon from image files (the sizes of one picture); missing files are
    skipped, so the icon may be null."""
    icon = QIcon()
    for path in paths:
        if os.path.isfile(path):
            icon.addFile(path)
    return icon


def vp6_icon() -> QIcon:
    from .project import VP6_ICON_FILES

    return icon_from(VP6_ICON_FILES)


def set_program_icon(paths) -> bool:
    """Make these image files the program's icon (its windows, and the Dock or
    taskbar). Returns False, keeping the icon it had, if none can be read."""
    app = ensure_app()  # first: Qt can't read images before there is an application
    icon = icon_from(paths)
    if icon.isNull():
        return False
    app.setWindowIcon(icon)
    return True


# --- Ctrl+C -----------------------------------------------------------------------------

class InterruptHandler(QObject):
    """Makes Ctrl+C (SIGINT) in the terminal run ``action`` in a Qt program.

    Python runs signal handlers only when it gets control back, and Qt's
    event loop can stay in C++ indefinitely, so SIGINT would be ignored. The
    signal module writes to a socket on every signal (``set_wakeup_fd``); a
    socket notifier on it returns control to Python, which then runs the
    handler. Before ``action``, any open modal window (a MsgBox, a dialog, a
    form shown with vpModal) is closed, since it would block. A repeated
    Ctrl+C while ``action`` is still running (e.g. a Form_Unload asking
    "Close?") is ignored."""

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self._action = action
        self._busy = False
        self._receive, self._send = socket.socketpair()
        for sock in (self._receive, self._send):
            sock.setblocking(False)
        signal.set_wakeup_fd(self._send.fileno())
        signal.signal(signal.SIGINT, self._on_interrupt)
        self._notifier = QSocketNotifier(self._receive.fileno(), QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._drain)

    def _drain(self, *_):
        try:
            self._receive.recv(64)
        except OSError:
            pass
        # Back in Python: the pending SIGINT handler runs now

    def _on_interrupt(self, signum, frame):
        QTimer.singleShot(0, self, self._run)

    def _run(self):
        if self._busy:
            return
        modal = QApplication.activeModalWidget()
        if modal is not None:
            # Close it, then continue once its event loop has returned
            modal.reject() if isinstance(modal, QDialog) else modal.close()
            QTimer.singleShot(0, self, self._run)
            return
        self._busy = True
        try:
            self._action()
        finally:
            self._busy = False


def install_interrupt_handler(action, parent=None) -> InterruptHandler | None:
    """Run ``action`` on Ctrl+C. Returns None where signals can't be handled
    (not the main thread)."""
    if threading.current_thread() is not threading.main_thread():
        return None
    try:
        return InterruptHandler(action, parent)
    except (ValueError, OSError):
        return None


def close_all_windows() -> None:
    """Ctrl+C in a VP6 program: close its windows like their close buttons
    would, so each Form_Unload runs (and may cancel). When the last one
    closes, the program ends."""
    app = QApplication.instance()
    windows = [w for w in app.topLevelWidgets() if w.isVisible()]
    if not windows:
        app.quit()  # an event loop without windows: just stop it
        return
    for window in windows:
        form = getattr(window, "_vp_form", None)
        if form is not None:  # (its Form_QueryUnload's UnloadMode: vpAppTaskManager)
            form.__dict__["_unload_mode"] = 3
        window.close()


def DoEvents() -> None:
    """Process pending GUI events, like VB6's DoEvents."""
    app = QApplication.instance()
    if app is not None:
        app.processEvents(QEventLoop.AllEvents)


def Beep() -> None:
    ensure_app()
    QApplication.beep()


def End() -> None:
    """Terminate the program immediately, like VB6's End statement: no form
    gets Form_Unload (closing the windows would run it, so they aren't
    closed; the process just ends)."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


class _App:
    """The VB ``App`` object."""

    Title = ""

    @property
    def Path(self) -> str:
        main = sys.modules.get("__main__")
        path = getattr(main, "__file__", None)
        return os.path.dirname(os.path.abspath(path)) if path else os.getcwd()

    @property
    def EXEName(self) -> str:
        return self.Title or os.path.splitext(os.path.basename(sys.argv[0] or "app"))[0]


class _Screen:
    """The VB ``Screen`` object (sizes in pixels)."""

    @property
    def Width(self) -> int:
        ensure_app()
        return QGuiApplication.primaryScreen().size().width()

    @property
    def Height(self) -> int:
        ensure_app()
        return QGuiApplication.primaryScreen().size().height()

    @property
    def ActiveForm(self):
        widget = QApplication.activeWindow()
        return getattr(widget, "_vp_form", None)


class _Clipboard:
    """The VB ``Clipboard`` object."""

    def GetText(self) -> str:
        ensure_app()
        return QGuiApplication.clipboard().text()

    def SetText(self, text: str) -> None:
        ensure_app()
        QGuiApplication.clipboard().setText(str(text))

    def Clear(self) -> None:
        ensure_app()
        QGuiApplication.clipboard().clear()


class _Debug:
    """``Debug.Print`` writes to the IDE's Immediate window (stdout)."""

    @staticmethod
    def Print(*values) -> None:
        print(*values, flush=True)


App = _App()
Screen = _Screen()
Clipboard = _Clipboard()
Debug = _Debug()


# --- event handler invocation -------------------------------------------------

_arity_cache: dict = {}


def _positional_capacity(func) -> int | None:
    """How many positional arguments ``func`` (a bound method) accepts;
    None means unlimited."""
    key = getattr(func, "__func__", func)
    if key in _arity_cache:
        return _arity_cache[key]
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        result = None
    else:
        if any(p.kind == p.VAR_POSITIONAL for p in params):
            result = None
        else:
            result = sum(1 for p in params
                         if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))
    _arity_cache[key] = result
    return result


def call_handler(handler, *args):
    """Call an event handler, passing only as many arguments as it declares.

    ``def Command1_MouseDown(self, Button, Shift, X, Y)`` and
    ``def Command1_MouseDown(self)`` both work. Exceptions are reported as VB
    style run-time errors instead of silently vanishing inside Qt.
    """
    capacity = _positional_capacity(handler)
    if capacity is not None:
        args = args[:capacity]
    try:
        return handler(*args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - this is the top-level error trap
        report_runtime_error(exc)
        return None


def report_runtime_error(exc: BaseException) -> None:
    traceback.print_exception(exc, file=sys.stderr)
    sys.stderr.flush()
    if os.environ.get("VP6_NO_ERROR_DIALOG"):
        return
    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(App.EXEName or "VP6")
    box.setText(f"Run-time error:\n\n{type(exc).__name__}: {exc}")
    box.setDetailedText("".join(traceback.format_exception(exc)))
    end_button = box.addButton("End", QMessageBox.DestructiveRole)
    box.addButton("Continue", QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is end_button:
        End()


def run_event_loop() -> int:
    """Run the GUI event loop while any window is open."""
    app = QApplication.instance()
    if app is None or not any(w.isVisible() for w in app.topLevelWidgets()):
        return 0
    return app.exec()


__all__ = ["App", "Screen", "Clipboard", "Debug", "DoEvents", "Beep", "End"]
