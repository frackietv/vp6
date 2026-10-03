"""VB's ``Printer`` object and ``Printers`` collection.

``Printer`` prints with the graphics methods (``Print``, ``Line``,
``Circle``, ``PSet``, ``PaintPicture``, ``TextWidth`` / ``TextHeight``) and
the drawing properties, on pages: ``NewPage`` starts the next one,
``EndDoc`` sends the document to the printer (or the PDF file named by
``OutputFile``), ``KillDoc`` throws it away. The first graphics method
starts a document; one still open when the program ends is sent then, as in
VB.

Coordinates are VP6's pixels: 1/96 inch, the size of a pixel on a standard
screen (so 96 is an inch), from the top left of the page's printable area;
``ScaleWidth`` and ``ScaleHeight`` are that area's size, ``Width`` and
``Height`` the paper's. Font sizes are points, as on screen.

``Printers`` lists the system's printers (``Printers(0)``, ``Printers.Count``);
``Printer.DeviceName = Printers(1).DeviceName`` chooses one (VB's ``Set
Printer = Printers(1)``). A CommonDialog's ShowPrinter sets the Printer's
printer, Copies and Orientation (its PrinterDefault).

``REDIRECT_DIR`` (or the environment variable ``VP6_PRINT_TO_PDF``): a
folder where documents for a printer go as PDF files instead (the tests use
it, so nothing is printed).
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

from PySide6.QtCore import QMarginsF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter
from PySide6.QtWidgets import QApplication

from ._props import P, PropertyHost, enum_choices
from .drawing import DRAWING_PROPERTIES, Drawing

UNITS_PER_INCH = 96  # VP6's pixels

REDIRECT_DIR: str | None = os.environ.get("VP6_PRINT_TO_PDF") or None

# PaperSize: VB's vbPRPS... numbers
PAPER_SIZES = {1: QPageSize.Letter, 3: QPageSize.Tabloid, 4: QPageSize.Ledger,
               5: QPageSize.Legal, 7: QPageSize.Executive, 8: QPageSize.A3, 9: QPageSize.A4,
               11: QPageSize.A5, 13: QPageSize.B5, 20: QPageSize.Comm10E,
               27: QPageSize.DLE}
_PAPER_CHOICES = ((1, "1 - Letter"), (3, "3 - Tabloid"), (4, "4 - Ledger"), (5, "5 - Legal"),
                  (7, "7 - Executive"), (8, "8 - A3"), (9, "9 - A4"), (11, "11 - A5"),
                  (13, "13 - B5"), (20, "20 - Envelope #10"), (27, "27 - Envelope DL"))


def _printer_infos():
    from PySide6.QtPrintSupport import QPrinterInfo

    return QPrinterInfo.availablePrinters()


def _default_paper() -> int:
    """Letter where the system's locale measures in inches, else A4."""
    from PySide6.QtCore import QLocale

    return 1 if QLocale.system().measurementSystem() != QLocale.MetricSystem else 9


class PrinterInfo:
    """One of the system's printers (an item of ``Printers``)."""

    def __init__(self, info):
        self.DeviceName = info.printerName()
        self.DriverName = info.makeAndModel()
        self.Port = info.location()
        self.IsDefault = info.isDefault()

    def __repr__(self):
        return f"<Printer {self.DeviceName!r}>"


class _Printers:
    """The system's printers: ``Printers(0)`` or ``Printers[0]``, ``Count``,
    ``len(Printers)``, ``for p in Printers``."""

    def _list(self) -> list[PrinterInfo]:
        return [PrinterInfo(info) for info in _printer_infos()]

    def __call__(self, Index: int) -> PrinterInfo:
        return self._list()[int(Index)]

    __getitem__ = __call__

    def __len__(self) -> int:
        return len(self._list())

    def __iter__(self):
        return iter(self._list())

    @property
    def Count(self) -> int:
        return len(self)

    def __repr__(self):
        return f"<Printers {[p.DeviceName for p in self]}>"


class _PrinterSurface:
    """What the graphics methods need of the surface they draw on, for the
    Printer: the printable area's size and the font (it has no widget)."""

    def __init__(self, printer: "_Printer"):
        self._printer = printer

    def width(self) -> int:
        return self._printer._draw_area_size().width()

    def height(self) -> int:
        return self._printer._draw_area_size().height()

    def devicePixelRatioF(self) -> float:
        return 1.0

    def palette(self):
        app = QApplication.instance()
        return app.palette() if app is not None else None

    def font(self) -> QFont:
        """The Printer's font, its size in VP6's pixels (points * 96 / 72): the
        page's painter is scaled to them, so it prints at its point size."""
        values = self._printer._values
        app = QApplication.instance()
        font = QFont(app.font()) if app is not None else QFont()
        if values.get("FontName"):
            font.setFamily(values["FontName"])
        points = values.get("FontSize") or font.pointSizeF() or 12
        font.setPixelSize(max(1, round(float(points) * UNITS_PER_INCH / 72)))
        font.setBold(bool(values.get("FontBold")))
        font.setItalic(bool(values.get("FontItalic")))
        font.setUnderline(bool(values.get("FontUnderline")))
        return font

    def update(self) -> None:
        pass


class _Printer(Drawing, PropertyHost):
    """VB's ``Printer`` object (see the module's documentation)."""

    TypeName = "Printer"
    _design_mode = False
    Properties = (
        *(spec for spec in DRAWING_PROPERTIES if spec.name != "AutoRedraw"),
        P("ForeColor", "color", None, description="What it prints with; unset: black"),
        P("FontName", "font", None), P("FontSize", "int", None),
        P("FontBold", "bool", False), P("FontItalic", "bool", False),
        P("FontUnderline", "bool", False),
        P("Orientation", "enum", 1, ((1, "1 - Portrait"), (2, "2 - Landscape"))),
        P("PaperSize", "enum", 0, _PAPER_CHOICES),
        P("Copies", "int", 1),
        P("ColorMode", "enum", 2, ((1, "1 - Monochrome"), (2, "2 - Color"))),
        P("Duplex", "enum", 1, enum_choices("", "Simplex", "Horizontal", "Vertical")[1:]),
        P("OutputFile", "str", ""),
    )

    def __init__(self):
        d = self.__dict__
        d["_values"] = {}
        d["_surface"] = _PrinterSurface(self)
        d["_device"] = None  # the printer's name: None = the system's default
        d["_qprinter"] = None  # a document in progress: its QPrinter and QPainter
        d["_painter"] = None
        d["_page"] = 1
        self._init_values({})

    def __setattr__(self, name, value):
        if name in self._specs or isinstance(getattr(type(self), name, None), property):
            object.__setattr__(self, name, value)
        else:
            raise AttributeError(f"Printer has no property '{name}'")

    def __repr__(self):
        return f"<Printer {self.DeviceName!r}>"

    def _fire(self, event, *args):
        return None

    def _read_PaperSize(self):
        """The paper chosen, else the printer's own (256: one VB has no number
        for)."""
        if self._values.get("PaperSize"):
            return self._values["PaperSize"]
        size = self._page_size().id()
        return next((number for number, id_ in PAPER_SIZES.items() if id_ == size), 256)

    def _page_size(self) -> QPageSize:
        """The paper: as chosen, else the printer's default paper, else Letter or A4
        as the system's locale measures."""
        chosen = self._values.get("PaperSize")
        if chosen in PAPER_SIZES:
            return QPageSize(PAPER_SIZES[chosen])
        info = self._info()
        if info is not None and info.defaultPageSize().isValid():
            return info.defaultPageSize()
        return QPageSize(PAPER_SIZES[_default_paper()])

    # -- which printer ----------------------------------------------------------------------
    @property
    def DeviceName(self) -> str:
        """The printer's name (the system's default one unless chosen); set it to
        one of Printers' DeviceName to print there."""
        if self._device is not None:
            return self._device
        from PySide6.QtPrintSupport import QPrinterInfo

        return QPrinterInfo.defaultPrinter().printerName()

    @DeviceName.setter
    def DeviceName(self, value):
        name = str(value or "")
        if name and name not in [info.printerName() for info in _printer_infos()]:
            raise ValueError(f"No printer named {name!r} (see Printers)")
        self.__dict__["_device"] = name or None

    @property
    def DriverName(self) -> str:
        info = self._info()
        return info.makeAndModel() if info is not None else ""

    @property
    def Port(self) -> str:
        info = self._info()
        return info.location() if info is not None else ""

    def _info(self):
        for info in _printer_infos():
            if info.printerName() == self.DeviceName:
                return info
        return None

    # -- the page -------------------------------------------------------------------------
    def _layout(self) -> QPageLayout:
        """The page: its paper, orientation and the printer's margins."""
        page = self._page_size()
        orientation = QPageLayout.Landscape if self._values.get("Orientation") == 2 \
            else QPageLayout.Portrait
        margins = QMarginsF(0, 0, 0, 0)
        info = self._info()
        if info is not None and self._target() is None:
            from PySide6.QtPrintSupport import QPrinter

            probe = QPrinter(info, QPrinter.HighResolution)
            probe.setPageSize(page)
            margins = probe.pageLayout().margins(QPageLayout.Point)
        else:
            margins = QMarginsF(36, 36, 36, 36)  # (a PDF: half an inch)
        return QPageLayout(page, orientation, margins, QPageLayout.Point)

    def _units(self, points: float) -> int:
        return round(points * UNITS_PER_INCH / 72)

    @property
    def Width(self) -> int:
        """The paper's width (VP6's pixels: 96 an inch), as it is turned."""
        return self._units(self._layout().fullRect(QPageLayout.Point).width())

    @property
    def Height(self) -> int:
        return self._units(self._layout().fullRect(QPageLayout.Point).height())


    @property
    def Page(self) -> int:
        """The number of the page being printed (1 for the first)."""
        return self._page

    # -- the document ------------------------------------------------------------------------
    def _target(self) -> str | None:
        """The PDF file the document goes to, or None for the printer."""
        if self._values.get("OutputFile"):
            return str(self._values["OutputFile"])
        if REDIRECT_DIR:
            name = "".join(c if c.isalnum() else "_" for c in self.DeviceName or "printer")
            return os.path.join(REDIRECT_DIR, f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-"
                                              f"{id(self) % 10000}.pdf")
        return None

    def _begin(self) -> QPainter:
        """The document's painter, starting the document if needed."""
        if self._painter is not None:
            return self._painter
        from PySide6.QtPrintSupport import QPrinter

        target = self._target()
        info = self._info()
        if target is None and info is None:
            raise RuntimeError("There is no printer to print on (see Printers); set "
                               "Printer.OutputFile to print to a PDF file")
        printer = QPrinter(info, QPrinter.HighResolution) if target is None and info \
            else QPrinter(QPrinter.HighResolution)
        if target is not None:
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(target)
        values = self._values
        printer.setPageLayout(self._layout())
        printer.setCopyCount(max(1, int(values.get("Copies") or 1)))
        printer.setColorMode(QPrinter.GrayScale if values.get("ColorMode") == 1
                             else QPrinter.Color)
        printer.setDuplex({2: QPrinter.DuplexShortSide, 3: QPrinter.DuplexLongSide}.get(
            values.get("Duplex"), QPrinter.DuplexNone))
        printer.setDocName(QApplication.applicationName() or "VP6")
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError(f"Couldn't start printing on {self.DeviceName or target!r}")
        self._scale(painter, printer)
        self.__dict__.update(_qprinter=printer, _painter=painter, _page=1)
        app = QApplication.instance()
        if app is not None and not self.__dict__.get("_quit_hooked"):
            # A document still open when the program ends is printed then, as in VB
            app.aboutToQuit.connect(self._end_at_exit)
            self.__dict__["_quit_hooked"] = True
        return painter

    def _scale(self, painter: QPainter, printer) -> None:
        """VP6's pixels (1/96 inch) on the printer's resolution."""
        ratio = printer.resolution() / UNITS_PER_INCH
        painter.resetTransform()
        painter.scale(ratio, ratio)

    @contextmanager
    def _draw_painter(self, antialias=False):
        painter = self._begin()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, antialias)
        try:
            yield painter
        finally:
            painter.restore()

    def _draw_area_size(self) -> QSize:
        """The printable area (ScaleWidth, ScaleHeight: it in ScaleMode's units)."""
        rect = self._layout().paintRect(QPageLayout.Point)
        return QSize(self._units(rect.width()), self._units(rect.height()))

    def _draw_text_color(self):
        color = self._values.get("ForeColor")
        from . import colors

        return colors.to_qcolor(color) if color is not None else QColor(Qt.black)

    def NewPage(self) -> None:
        """End this page and start the next one (the current point goes back to
        the top left)."""
        printer = self._qprinter
        if printer is None:
            self._begin()
            printer = self._qprinter
        printer.setPageLayout(self._layout())  # (Orientation, PaperSize: from this page)
        printer.newPage()
        self._scale(self._painter, printer)
        self.__dict__["_page"] += 1
        self.CurrentX = self.CurrentY = 0

    def EndDoc(self) -> None:
        """Send the document to the printer (or its OutputFile)."""
        if self._painter is not None:
            self._painter.end()
        self._reset()

    def KillDoc(self) -> None:
        """Throw the document away: nothing is printed."""
        printer, painter = self._qprinter, self._painter
        if printer is not None:
            printer.abort()
            if painter is not None and painter.isActive():
                painter.end()
            path = printer.outputFileName()
            if path and os.path.isfile(path):
                os.remove(path)
        self._reset()

    def _reset(self) -> None:
        self.__dict__.update(_qprinter=None, _painter=None, _page=1)
        state = self._draw_state()
        state["x"] = state["y"] = 0.0
        state["dash"] = None

    def _end_at_exit(self) -> None:
        if self._painter is not None:
            self.EndDoc()

    # -- not on a printer ---------------------------------------------------------------------
    def _drawing_surface(self):
        return self._surface

    def Cls(self) -> None:
        raise AttributeError("The Printer has no Cls: NewPage starts a new page, KillDoc "
                             "throws the document away")

    def Point(self, X, Y) -> int:
        raise AttributeError("The Printer has no Point")

    @property
    def Image(self):
        raise AttributeError("The Printer has no Image")

    def _paint_drawing(self, widget) -> None:
        pass

    def _adopt(self, qprinter) -> None:
        """A Print dialog's choices (CommonDialog.ShowPrinter, PrinterDefault):
        its printer, copies, orientation, colors, two-sided printing, and a PDF
        file when it was chosen to print to one."""
        from PySide6.QtPrintSupport import QPrinter

        if qprinter.outputFormat() == QPrinter.PdfFormat and qprinter.outputFileName():
            self.OutputFile = qprinter.outputFileName()
        else:
            self.OutputFile = ""
            names = [info.printerName() for info in _printer_infos()]
            if qprinter.printerName() in names:
                self.__dict__["_device"] = qprinter.printerName()
        self.Copies = qprinter.copyCount()
        self.Orientation = 2 if qprinter.pageLayout().orientation() == QPageLayout.Landscape \
            else 1
        self.ColorMode = 1 if qprinter.colorMode() == QPrinter.GrayScale else 2
        self.Duplex = {QPrinter.DuplexShortSide: 2, QPrinter.DuplexLongSide: 3}.get(
            qprinter.duplex(), 1)
        for number, size in PAPER_SIZES.items():
            if qprinter.pageLayout().pageSize().id() == size:
                self.PaperSize = number
                break


Printer = _Printer()
Printers = _Printers()
