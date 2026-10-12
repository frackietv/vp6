"""MsgBox and InputBox; ProgressBox (a progress dialog) and ShowError (an
error message with "Show this message again")."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QErrorMessage, QInputDialog, QMessageBox,
                               QProgressDialog)

from . import constants as c
from .app import App, ensure_app
from .appearance import match_dialog

_BUTTON_SETS = {
    c.vpOKOnly: [(QMessageBox.Ok, c.vpOK)],
    c.vpOKCancel: [(QMessageBox.Ok, c.vpOK), (QMessageBox.Cancel, c.vpCancel)],
    c.vpAbortRetryIgnore: [(QMessageBox.Abort, c.vpAbort), (QMessageBox.Retry, c.vpRetry),
                           (QMessageBox.Ignore, c.vpIgnore)],
    c.vpYesNoCancel: [(QMessageBox.Yes, c.vpYes), (QMessageBox.No, c.vpNo),
                      (QMessageBox.Cancel, c.vpCancel)],
    c.vpYesNo: [(QMessageBox.Yes, c.vpYes), (QMessageBox.No, c.vpNo)],
    c.vpRetryCancel: [(QMessageBox.Retry, c.vpRetry), (QMessageBox.Cancel, c.vpCancel)],
}

_ICONS = {
    c.vpCritical: QMessageBox.Critical,
    c.vpQuestion: QMessageBox.Question,
    c.vpExclamation: QMessageBox.Warning,
    c.vpInformation: QMessageBox.Information,
}


def MsgBox(prompt, buttons: int = c.vpOKOnly, title: str | None = None) -> int:
    """Show a message box and return vpOK, vpCancel, vpYes, ...

    >>> if MsgBox("Save changes?", vpYesNo + vpQuestion) == vpYes: ...
    """
    ensure_app()
    parent = QApplication.activeWindow()
    box = QMessageBox(parent)
    box.setWindowTitle(title if title is not None else (App.EXEName or "VP6"))
    box.setText(str(prompt))
    box.setIcon(_ICONS.get(buttons & 0x70, QMessageBox.NoIcon))

    pairs = _BUTTON_SETS.get(buttons & 0x7, _BUTTON_SETS[c.vpOKOnly])
    std = QMessageBox.StandardButton(0)
    for qt_button, _ in pairs:
        std |= qt_button
    box.setStandardButtons(std)
    default_index = (buttons & 0xF00) // 256
    if default_index < len(pairs):
        box.setDefaultButton(pairs[default_index][0])
    match_dialog(box, parent)

    clicked = QMessageBox.StandardButton(box.exec())
    for qt_button, result in pairs:
        if clicked == qt_button:
            return result
    # Closed with Escape / the window close button
    return c.vpCancel if any(r == c.vpCancel for _, r in pairs) else pairs[-1][1]


def InputBox(prompt, title: str | None = None, default: str = "") -> str:
    """Ask the user for a line of text. Returns "" when cancelled (like VB6)."""
    ensure_app()
    parent = QApplication.activeWindow()
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title if title is not None else (App.EXEName or "VP6"))
    dialog.setLabelText(str(prompt))
    dialog.setTextValue(str(default))
    match_dialog(dialog, parent)
    return dialog.textValue() if dialog.exec() else ""


class _ProgressBox:
    """What ProgressBox returns: set its Value as the work goes on."""

    def __init__(self, dialog: QProgressDialog):
        self._dialog = dialog

    def __repr__(self):
        return f"<ProgressBox {self.Value}/{self.Max}>"

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.Close()

    @property
    def Value(self) -> int:
        """How far the work is, from 0 to Max; reaching Max closes it."""
        return max(self._dialog.value(), 0)

    @Value.setter
    def Value(self, value):
        self._dialog.setValue(int(value))
        QApplication.processEvents()  # (it is drawn, and its Cancel button works)

    @property
    def Max(self) -> int:
        return self._dialog.maximum()

    @Max.setter
    def Max(self, value):
        self._dialog.setMaximum(int(value))

    @property
    def Text(self) -> str:
        """The text above the bar (e.g. what is being done now)."""
        return self._dialog.labelText()

    @Text.setter
    def Text(self, value):
        self._dialog.setLabelText(str(value))
        QApplication.processEvents()

    @property
    def Cancelled(self) -> bool:
        """Whether the user clicked Cancel (stop the work then)."""
        return self._dialog.wasCanceled()

    @property
    def Visible(self) -> bool:
        return self._dialog.isVisible()

    def Close(self) -> None:
        """Close it (the work is done, or was stopped)."""
        self._dialog.reset()
        self._dialog.close()
        self._dialog.deleteLater()


def ProgressBox(Prompt, Max: int = 100, Title: str | None = None, Modal: bool = True,
                Delay: int = 500, CancelText: str = "Cancel") -> _ProgressBox:
    """A progress dialog for long work, shown once it has taken Delay ms (and
    looks like it will go on): set the returned object's ``Value`` (0 to Max)
    and ``Text`` as the work goes on, and stop when ``Cancelled``. Modal: the
    program's windows don't respond meanwhile. CancelText "" has no Cancel
    button. It closes when Value reaches Max (or with Close())::

        progress = ProgressBox("Copying files...", len(files))
        for number, name in enumerate(files, 1):
            copy(name)
            progress.Value = number
            if progress.Cancelled:
                break
    """
    ensure_app()
    parent = QApplication.activeWindow()
    dialog = QProgressDialog(str(Prompt), str(CancelText) if CancelText else None, 0,
                             int(Max), parent)
    dialog.setWindowTitle(Title if Title is not None else (App.EXEName or "VP6"))
    dialog.setWindowModality(Qt.ApplicationModal if Modal else Qt.NonModal)
    dialog.setMinimumDuration(max(0, int(Delay)))
    dialog.setAutoClose(True)
    dialog.setAutoReset(False)
    match_dialog(dialog, parent)
    dialog.setValue(0)
    return _ProgressBox(dialog)


_error_box: list = []  # (the one ShowError uses: it remembers what not to show again)


def ShowError(Message, Kind: str = "") -> None:
    """Show an error message that the user can choose not to see again (the
    "Show this message again" check box): of this Kind (any text), or this
    Message when there is no Kind. It doesn't wait; more messages queue up."""
    ensure_app()
    if not _error_box:
        box = QErrorMessage()
        box.setWindowTitle(App.EXEName or "VP6")
        _error_box.append(box)
    box = _error_box[0]
    match_dialog(box, QApplication.activeWindow())
    if Kind:
        box.showMessage(str(Message), str(Kind))
    else:
        box.showMessage(str(Message))


__all__ = ["MsgBox", "InputBox", "ProgressBox", "ShowError"]
