"""MsgBox and InputBox."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

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


__all__ = ["MsgBox", "InputBox"]
