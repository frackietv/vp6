"""The CommonDialog: VB's Filter syntax, the Open and Save As dialogs, Color, Font,
Print and Help, cancelling (CancelError, DialogCancelled), the designer's icon."""

import os

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QDialog, QFileDialog

from vp6 import (CommonDialog, DialogCancelled, Form, vpCdlCancel, vpOFNAllowMultiselect,
                 vpOFNOverwritePrompt, vpPDPageNums, vpRed)
from vp6.controls import CONTROL_TYPES, parse_filter
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


@pytest.fixture
def cdl(qapp):
    form = Form()
    cdl = CommonDialog(form, Name="cdl")
    yield cdl
    form._widget.close()


def test_filter():
    assert parse_filter("Text Files (*.txt)|*.txt|All Files (*.*)|*.*") == [
        "Text Files (*.txt)", "All Files (*)"]
    assert parse_filter("Pictures|*.png;*.jpg") == ["Pictures (*.png *.jpg)"]
    assert parse_filter("") == [] and parse_filter("odd|") == ["odd (*)"]


def test_invisible_at_run_time(cdl):
    assert cdl._widget is None and "Width" not in cdl._specs  # (an icon in the designer)
    assert CONTROL_TYPES["CommonDialog"].Events == () and "CommonDialog" in Toolbox().buttons
    assert not icon("CommonDialog").isNull()


def test_open(cdl, monkeypatch, tmp_path):
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text("x")
    seen = {}

    def accept(dialog):
        seen.update(title=dialog.windowTitle(), filters=dialog.nameFilters(),
                    chosen=dialog.selectedNameFilter(), folder=dialog.directory().path(),
                    mode=dialog.fileMode())
        dialog.selectFile(str(tmp_path / "b.txt"))
        dialog.selectNameFilter(dialog.nameFilters()[0])
        return QDialog.Accepted

    monkeypatch.setattr(QFileDialog, "exec", accept)
    cdl.DialogTitle = "Pick"
    cdl.Filter = "Text (*.txt)|*.txt|All (*.*)|*.*"
    cdl.FilterIndex = 2
    cdl.InitDir = str(tmp_path)
    assert cdl.ShowOpen() is True
    assert seen == {"title": "Pick", "filters": ["Text (*.txt)", "All (*)"],
                    "chosen": "All (*)", "folder": str(tmp_path),
                    "mode": QFileDialog.ExistingFile}
    assert cdl.FileName == str(tmp_path / "b.txt") and cdl.FileTitle == "b.txt"
    assert cdl.FileNames == [cdl.FileName] and cdl.FilterIndex == 1
    cdl.Flags = vpOFNAllowMultiselect
    cdl.ShowOpen()
    assert seen["mode"] == QFileDialog.ExistingFiles


def test_save(cdl, monkeypatch, tmp_path):
    seen = {}

    def accept(dialog):
        seen.update(save=dialog.acceptMode() == QFileDialog.AcceptSave,
                    confirm=not dialog.testOption(QFileDialog.DontConfirmOverwrite),
                    suffix=dialog.defaultSuffix())
        dialog.selectFile(str(tmp_path / "out.txt"))
        return QDialog.Accepted

    monkeypatch.setattr(QFileDialog, "exec", accept)
    cdl.DefaultExt = ".txt"
    assert cdl.ShowSave()
    assert seen == {"save": True, "confirm": False, "suffix": "txt"}  # (VB: no prompt)
    cdl.Flags = vpOFNOverwritePrompt
    cdl.ShowSave()
    assert seen["confirm"] and cdl.FileTitle == "out.txt"


def test_cancelling(cdl, monkeypatch):
    monkeypatch.setattr(QFileDialog, "exec", lambda dialog: QDialog.Rejected)
    cdl.FileName = "/kept.txt"
    assert cdl.ShowOpen() is False and cdl.FileName == "/kept.txt"
    cdl.CancelError = True
    with pytest.raises(DialogCancelled) as error:
        cdl.ShowSave()
    assert error.value.Number == vpCdlCancel == 32755


def test_color(cdl, monkeypatch):
    seen = {}

    def accept(dialog):
        seen["start"] = dialog.currentColor().name()
        dialog.setCurrentColor(QColor("#00ff00"))
        return QDialog.Accepted

    monkeypatch.setattr("vp6.controls.QColorDialog.exec", accept)
    cdl.Color = vpRed
    assert cdl.ShowColor() and seen["start"] == "#ff0000" and cdl.Color == 0x00FF00


def test_font(cdl, monkeypatch):
    seen = {}

    def accept(dialog):
        seen["start"] = (dialog.currentFont().family(), dialog.currentFont().bold())
        font = QFont("Courier New", 18)
        font.setItalic(True)
        font.setStrikeOut(True)
        dialog.setCurrentFont(font)
        return QDialog.Accepted

    monkeypatch.setattr("vp6.controls.QFontDialog.exec", accept)
    cdl.FontName, cdl.FontBold = "Arial", True
    assert cdl.ShowFont() and seen["start"] == ("Arial", True)
    assert (cdl.FontName, cdl.FontSize, cdl.FontBold, cdl.FontItalic, cdl.FontStrikethru) == (
        "Courier New", 18, False, True, True)


def test_printer(cdl, monkeypatch):
    from PySide6.QtPrintSupport import QPrintDialog

    seen = {}

    def accept(dialog):
        seen.update(range=(dialog.fromPage(), dialog.toPage()),
                    limits=(dialog.minPage(), dialog.maxPage()),
                    copies=dialog.printer().copyCount())
        dialog.printer().setCopyCount(3)
        dialog.setFromTo(2, 4)
        return QDialog.Accepted

    monkeypatch.setattr(QPrintDialog, "exec", accept)
    cdl.Flags = vpPDPageNums
    cdl.Min, cdl.Max, cdl.FromPage, cdl.ToPage, cdl.Copies = 1, 9, 1, 2, 2
    assert cdl.ShowPrinter()
    assert seen == {"range": (1, 2), "limits": (1, 9), "copies": 2}
    assert (cdl.Copies, cdl.FromPage, cdl.ToPage, cdl.Orientation) == (3, 2, 4, 1)


def test_help(cdl, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("vp6.controls.QDesktopServices.openUrl",
                        lambda url: opened.append(url.toString()) or True)
    with pytest.raises(ValueError, match="no HelpFile"):
        cdl.ShowHelp()
    cdl.HelpFile = "https://example.com/help"
    assert cdl.ShowHelp() and opened == ["https://example.com/help"]
    cdl.HelpFile = str(tmp_path / "help.html")
    cdl.ShowHelp()
    assert opened[-1] == QUrl.fromLocalFile(str(tmp_path / "help.html")).toString()


def test_in_the_designer(qapp, tmp_path):
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument

    path = tmp_path / "Form1.py"
    from vp6 import formfile

    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    designer.create_control("CommonDialog", None, None)
    designer.select(["CommonDialog1"])
    designer.nudge(8, 0)
    designer.nudge(8, 8, resize=True)  # (an icon: no size of its own)
    line = next(l for l in designer.document.text.splitlines() if "CommonDialog(" in l)
    assert "Width" not in line and "Height" not in line
    assert designer.controls["CommonDialog1"]._widget.width() == 32
