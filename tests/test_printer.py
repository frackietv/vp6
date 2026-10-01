"""The Printer object and Printers collection: printing with the graphics
methods to pages (to PDF files here: conftest redirects every document, so
nothing reaches a real printer), NewPage, EndDoc, KillDoc, the page's size,
fonts in points, the system's printers and CommonDialog.ShowPrinter's
choices (PrinterDefault)."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QDialog

import vp6
from vp6 import (CommonDialog, Form, Picture, Printer, Printers, vpBlue, vpFSSolid,
                 vpPRORLandscape, vpPRPSA4, vpPRPSLetter, vpRed, vpYellow)
from vp6 import printer as printer_module

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


def pdf(path):
    document = QPdfDocument()
    document.load(str(path))
    return document


def page_image(document, index=0):
    """A page at 96 dots an inch: VP6's units (plus the PDF's half-inch margins)."""
    size = document.pagePointSize(index)
    return document.render(index, QSize(round(size.width() * 96 / 72),
                                        round(size.height() * 96 / 72)))


def color_at(image, x, y) -> str:
    """The color printed at x, y (the margins: half an inch); white where nothing is."""
    color = image.pixelColor(x + 48, y + 48)
    return "#ffffff" if color.alpha() == 0 else color.name()


def test_printing_to_a_pdf_file(qapp, tmp_path):
    Printer.OutputFile = str(tmp_path / "out.pdf")
    Printer.PaperSize = vpPRPSLetter
    assert (Printer.Width, Printer.Height) == (816, 1056)  # 8.5 x 11 inches, 96 an inch
    assert (Printer.ScaleWidth, Printer.ScaleHeight) == (816 - 96, 1056 - 96)  # its margins
    assert Printer.Page == 1
    Printer.Line(0, 0, 96, 96, vpRed, "BF")  # an inch square
    Printer.FillStyle, Printer.FillColor = vpFSSolid, vpYellow
    Printer.Circle(300, 300, 50, vpBlue)
    Printer.PaintPicture(Picture(40, 40, BackColor=vpBlue), 500, 100)
    Printer.CurrentX, Printer.CurrentY = 0, 600
    Printer.FontSize = 36
    Printer.Print("Big")
    assert Printer.CurrentY > 600 + 36 * 96 / 72  # (points: 36 points is half an inch)
    assert Printer.TextHeight("x") == pytest.approx(Printer.TextHeight("x"))
    Printer.EndDoc()
    document = pdf(tmp_path / "out.pdf")
    assert document.pageCount() == 1 and document.pagePointSize(0).width() == 612
    image = page_image(document)
    assert color_at(image, 48, 48) == "#ff0000" and color_at(image, 120, 48) == "#ffffff"
    assert color_at(image, 300, 300) == "#ffff00"
    picture = color_at(image, 520, 120)  # (a picture in a PDF: nearly its colors)
    assert int(picture[5:7], 16) > 0xF0 and int(picture[1:5], 16) < 0x1010
    big = [color_at(image, x, y) for x in range(0, 110) for y in range(600, 650)]
    assert "#000000" in big  # the text, black
    assert Printer.Page == 1 and (Printer.CurrentX, Printer.CurrentY) == (0, 0)


def test_pages_and_orientation(qapp, tmp_path):
    Printer.OutputFile = str(tmp_path / "pages.pdf")
    Printer.PaperSize = vpPRPSA4
    Printer.Print("one")
    Printer.NewPage()
    assert Printer.Page == 2 and Printer.CurrentY == 0
    Printer.Orientation = vpPRORLandscape  # (from the next page)
    Printer.NewPage()
    assert Printer.Width > Printer.Height
    Printer.Print("three")
    Printer.EndDoc()
    document = pdf(tmp_path / "pages.pdf")
    sizes = [document.pagePointSize(i) for i in range(document.pageCount())]
    assert len(sizes) == 3 and round(sizes[0].width()) == 595  # A4
    assert sizes[2].width() > sizes[2].height()


def test_new_page_first_and_kill_doc(qapp, tmp_path):
    Printer.OutputFile = str(tmp_path / "blank.pdf")
    Printer.NewPage()  # (starts the document: a blank first page)
    Printer.Print("two")
    Printer.EndDoc()
    assert pdf(tmp_path / "blank.pdf").pageCount() == 2
    Printer.OutputFile = str(tmp_path / "killed.pdf")
    Printer.Print("never printed")
    Printer.KillDoc()
    assert not (tmp_path / "killed.pdf").exists() and Printer._painter is None


def test_redirected_and_ended_when_the_program_ends(qapp):
    # (conftest: a document for a printer goes to a PDF in REDIRECT_DIR)
    if not Printers.Count:
        pytest.skip("no printer")
    Printer.Print("to the printer")
    Printer._end_at_exit()  # (what aboutToQuit does)
    printed = list(Path(printer_module.REDIRECT_DIR).glob("*.pdf"))
    assert len(printed) == 1 and pdf(printed[0]).pageCount() == 1


def test_no_printer(qapp, monkeypatch):
    monkeypatch.setattr(printer_module, "_printer_infos", lambda: [])
    monkeypatch.setattr(printer_module, "REDIRECT_DIR", None)
    assert Printers.Count == 0 and Printer.DriverName == ""
    with pytest.raises(RuntimeError, match="no printer"):
        Printer.Print("x")


def test_not_on_a_printer(qapp):
    with pytest.raises(AttributeError):
        Printer.Cls()
    with pytest.raises(AttributeError):
        Printer.Point(1, 1)
    with pytest.raises(AttributeError):
        Printer.Image
    with pytest.raises(AttributeError):
        Printer.Colour = 1


def test_printers(qapp):
    names = [p.DeviceName for p in Printers]
    assert len(names) == Printers.Count == len(Printers)
    if names:
        assert Printers(0).DeviceName == Printers[0].DeviceName == names[0]
        assert Printer.DeviceName in names  # the default one
        Printer.DeviceName = names[-1]  # VB's Set Printer = Printers(...)
        assert Printer.DeviceName == names[-1]
        assert any(p.IsDefault for p in Printers)
    with pytest.raises(ValueError):
        Printer.DeviceName = "No such printer"
    Printer.DeviceName = ""  # the default again
    assert Printer.PaperSize in (1, 9, 256) or Printer.PaperSize in printer_module.PAPER_SIZES


def test_show_printer_sets_the_printer(qapp, monkeypatch):
    from PySide6.QtGui import QPageLayout
    from PySide6.QtPrintSupport import QPrintDialog

    def accept(dialog):
        dialog.printer().setCopyCount(4)
        dialog.printer().setPageOrientation(QPageLayout.Landscape)
        return QDialog.Accepted

    monkeypatch.setattr(QPrintDialog, "exec", accept)

    class Host(Form):
        def InitializeComponent(self):
            self.cdl = CommonDialog(self)

    form = Host()
    form.cdl.PrinterDefault = False  # (only the dialog's own properties)
    assert form.cdl.ShowPrinter() and Printer.Copies == 1
    form.cdl.PrinterDefault = True
    assert form.cdl.ShowPrinter()
    assert (Printer.Copies, Printer.Orientation) == (4, vpPRORLandscape)
    form.Unload()


def test_exported():
    for name in ("Printer", "Printers", "vpPRORPortrait", "vpPRPSA4", "vpPRDPVertical"):
        assert name in vp6.__all__
