"""Application level services: the Qt application, App/Screen/Clipboard
objects, DoEvents, End and the VB style run-time error handling."""

from __future__ import annotations

import inspect
import os
import sys
import traceback

from PySide6.QtCore import QEventLoop
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox


def ensure_app() -> QApplication:
    """Return the QApplication, creating it on first use."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def DoEvents() -> None:
    """Process pending GUI events, like VB6's DoEvents."""
    app = QApplication.instance()
    if app is not None:
        app.processEvents(QEventLoop.AllEvents)


def Beep() -> None:
    ensure_app()
    QApplication.beep()


def End() -> None:
    """Terminate the program immediately, like VB6's End statement."""
    app = QApplication.instance()
    if app is not None:
        app.closeAllWindows()
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
