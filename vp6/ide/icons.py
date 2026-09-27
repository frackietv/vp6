"""Toolbox, toolbar and project icons, drawn with QPainter so the IDE ships no
icon files. Every icon has a light and a dark variant so it stays visible in
both IDE color schemes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)

SIZE = 24


@dataclass(frozen=True)
class _Colors:
    ink: QColor  # outlines and glyphs
    face: QColor  # 3D control faces
    paper: QColor  # text fields, pages, list backgrounds
    blue: QColor
    button_top: QColor
    button_bottom: QColor


_LIGHT = _Colors(QColor("#2b2b2b"), QColor("#e8e8e8"), QColor("#ffffff"), QColor("#1f5fbf"),
                 QColor("#ffffff"), QColor("#c9c9c9"))
_DARK = _Colors(QColor("#e6e6e6"), QColor("#5a5a5e"), QColor("#2f2f33"), QColor("#4c9bff"),
                QColor("#77777c"), QColor("#4a4a4e"))
C = _LIGHT  # the palette used by the drawing functions below


def _text(p, rect, text, size=9, bold=False, color=None, align=Qt.AlignCenter):
    font = QFont()
    font.setPixelSize(size)
    font.setBold(bold)
    p.setFont(font)
    p.setPen(color or C.ink)
    p.drawText(rect, align, text)
    p.setPen(QPen(C.ink, 1))


# --- toolbox --------------------------------------------------------------------------

def _pointer(p):
    p.setBrush(C.paper)
    p.drawPolygon([QPointF(7, 3), QPointF(7, 19), QPointF(11, 15), QPointF(14, 21),
                   QPointF(16, 20), QPointF(13, 14), QPointF(18, 14)])


def _picturebox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 4, 18, 16))
    p.setBrush(QColor("#7fc36b"))
    p.drawPolygon([QPointF(4, 19), QPointF(10, 11), QPointF(14, 16), QPointF(17, 13),
                   QPointF(20, 19)])
    p.setBrush(QColor("#f5c542"))
    p.drawEllipse(QRectF(15, 6, 4, 4))


def _label(p):
    _text(p, QRectF(0, 0, SIZE, SIZE), "A", 17, True)


def _textbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 6, 20, 12))
    _text(p, QRectF(3, 6, 14, 12), "ab", 9, align=Qt.AlignVCenter | Qt.AlignLeft)
    p.drawLine(QPointF(17, 8.5), QPointF(17, 15.5))


def _frame(p):
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(3, 7, 18, 13))
    _text(p, QRectF(5, 2, 11, 9), "xy", 8)


def _commandbutton(p):
    gradient = QLinearGradient(0, 6, 0, 18)
    gradient.setColorAt(0, C.button_top)
    gradient.setColorAt(1, C.button_bottom)
    p.setBrush(gradient)
    p.drawRoundedRect(QRectF(2, 6, 20, 12), 2, 2)


def _checkbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(4, 5, 14, 14))
    p.setPen(QPen(C.blue, 2.2))
    p.drawPolyline([QPointF(7, 12), QPointF(10, 15.5), QPointF(16, 7)])


def _optionbutton(p):
    p.setBrush(C.paper)
    p.drawEllipse(QRectF(4, 4, 16, 16))
    p.setBrush(C.ink)
    p.drawEllipse(QRectF(9, 9, 6, 6))


def _combobox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 7, 20, 10))
    p.setBrush(C.face)
    p.drawRect(QRectF(15, 7, 7, 10))
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(16.5, 11), QPointF(20.5, 11), QPointF(18.5, 13.5)])


def _listbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    for y in (7, 11, 15):
        p.drawLine(QPointF(6, y), QPointF(18, y))
    p.fillRect(QRectF(4, 9.5, 16, 3), C.blue)


def _hscroll(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 8, 20, 8))
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(3.5, 12), QPointF(6.5, 9.5), QPointF(6.5, 14.5)])
    p.drawPolygon([QPointF(20.5, 12), QPointF(17.5, 9.5), QPointF(17.5, 14.5)])
    p.setBrush(C.paper)
    p.drawRect(QRectF(9, 9, 5, 6))


def _vscroll(p):
    p.save()
    p.translate(SIZE, 0)
    p.rotate(90)
    _hscroll(p)
    p.restore()


def _timer(p):
    p.setBrush(QColor("#fff4c2") if C is _LIGHT else QColor("#6b5d2a"))
    p.drawEllipse(QRectF(4, 5, 16, 16))
    p.drawRect(QRectF(10, 1.5, 4, 3))
    p.drawLine(QPointF(12, 13), QPointF(12, 8))
    p.drawLine(QPointF(12, 13), QPointF(16, 13))


def _image(p):
    p.setPen(QPen(C.ink, 1, Qt.DashLine))  # no frame of its own, like VB's Image icon
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(3, 4, 18, 16))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#7fc36b"))
    p.drawPolygon([QPointF(5, 18), QPointF(10, 11), QPointF(14, 16), QPointF(16, 14),
                   QPointF(19, 18)])
    p.setBrush(QColor("#f5c542"))
    p.drawEllipse(QRectF(14, 7, 4, 4))
    p.setPen(QPen(C.ink, 1))


def _treeview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    p.setPen(QPen(C.ink, 1))
    p.drawLine(QPointF(7, 8), QPointF(7, 17))  # the tree's lines
    p.drawLine(QPointF(7, 12), QPointF(10, 12))
    p.drawLine(QPointF(7, 17), QPointF(10, 17))
    p.setBrush(C.blue)
    p.setPen(Qt.NoPen)
    for x, y, w in ((5, 5, 11), (11, 10.5, 8), (11, 15.5, 8)):
        p.drawRect(QRectF(x, y, w, 3))
    p.setPen(QPen(C.ink, 1))


def _splitter(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 4, 8, 16))  # two panes and the bar between them
    p.drawRect(QRectF(14, 4, 8, 16))
    p.setBrush(C.face)
    p.drawRect(QRectF(10, 4, 4, 16))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))  # the two-headed drag arrow
    for x, dx in ((5, 2), (19, -2)):
        p.drawLine(QPointF(x, 12), QPointF(x + dx, 10))
        p.drawLine(QPointF(x, 12), QPointF(x + dx, 14))


def _progressbar(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 8, 20, 8))
    p.setBrush(QColor("#3fb950") if C is _LIGHT else QColor("#2ea043"))
    p.drawRect(QRectF(2, 8, 12, 8))  # filled part way


def _slider(p):
    p.drawLine(QPointF(3, 10), QPointF(21, 10))  # the scale
    for x in (3, 7.5, 12, 16.5, 21):  # tick marks below it
        p.drawLine(QPointF(x, 17), QPointF(x, 20))
    p.setBrush(C.face)
    p.drawPolygon([QPointF(12, 4), QPointF(15, 4), QPointF(15, 12), QPointF(13.5, 15),
                   QPointF(12, 12)])  # the thumb, pointing at the ticks


def _updown(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(7, 2, 10, 10))
    p.drawRect(QRectF(7, 12, 10, 10))
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(12, 4.5), QPointF(9.5, 9), QPointF(14.5, 9)])
    p.drawPolygon([QPointF(12, 19.5), QPointF(9.5, 15), QPointF(14.5, 15)])


def _statusbar(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 4, 20, 16))  # a window...
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 14, 20, 6))  # ...and its status bar, in three panels
    p.drawLine(QPointF(12, 14), QPointF(12, 20))
    p.drawLine(QPointF(17, 14), QPointF(17, 20))
    p.setBrush(C.blue)
    p.drawRect(QRectF(4, 16.5, 5, 1))


def _tabstrip(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(9, 4, 7, 5))  # a tab behind
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 8, 20, 13))  # the page
    p.save()
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(2.5, 3.5, 6, 5))  # the selected tab, open into its page
    p.restore()
    path = QPainterPath()
    path.moveTo(2, 8)
    path.lineTo(2, 3)
    path.lineTo(9, 3)
    path.lineTo(9, 8)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setBrush(C.blue)
    p.drawRect(QRectF(5, 12, 12, 1.5))
    p.drawRect(QRectF(5, 16, 8, 1.5))


def _imagelist(p):
    for offset, color in ((0, "#9ec5fe"), (4, "#ffe08a"), (8, "#a3e4a8")):  # a pile of pictures
        p.setBrush(QColor(color))
        p.drawRect(QRectF(2 + offset, 10 - offset, 12, 10))
    p.setBrush(QColor("#3fb950") if C is _LIGHT else QColor("#2ea043"))
    p.drawPolygon([QPointF(11, 18), QPointF(15, 12), QPointF(20, 18)])  # a hill in the top one


def _toolbar(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 6, 20, 11))  # the bar, with three buttons
    for x, color in ((4, "#9ec5fe"), (10, "#ffe08a"), (16, "#a3e4a8")):
        p.setBrush(QColor(color))
        p.drawRect(QRectF(x, 8.5, 4, 6))


def _line(p):
    p.setPen(QPen(C.ink, 2))
    p.drawLine(QPointF(5, 19), QPointF(19, 5))
    p.setPen(QPen(C.ink, 1))
    p.setBrush(C.paper)
    for x, y in ((5, 19), (19, 5)):
        p.drawRect(QRectF(x - 2, y - 2, 4, 4))


# --- project / toolbar ---------------------------------------------------------------

def _form(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.fillRect(QRectF(2.5, 3.5, 19, 4), C.blue)


def _page(p):
    p.setBrush(C.paper)
    p.drawPolygon([QPointF(5, 2), QPointF(15, 2), QPointF(19, 6), QPointF(19, 22),
                   QPointF(5, 22)])
    p.drawPolyline([QPointF(15, 2), QPointF(15, 6), QPointF(19, 6)])


def _module(p):
    _page(p)
    for y in (10, 13, 16, 19):
        p.drawLine(QPointF(8, y), QPointF(16, y))


def _new(p):
    _page(p)
    p.setPen(QPen(QColor("#e0a800"), 1.6))
    for a, b in (((16, 12), (16, 20)), ((12, 16), (20, 16))):
        p.drawLine(QPointF(*a), QPointF(*b))


def _folder(p):
    p.setBrush(QColor("#f3d27a") if C is _LIGHT else QColor("#c9a54a"))
    p.drawPolygon([QPointF(2, 6), QPointF(9, 6), QPointF(11, 8), QPointF(22, 8),
                   QPointF(22, 20), QPointF(2, 20)])


def _open(p):
    _folder(p)
    p.setBrush(QColor("#f8e2a2") if C is _LIGHT else QColor("#e0bf66"))
    p.drawPolygon([QPointF(4, 11), QPointF(23, 11), QPointF(21, 20), QPointF(2, 20)])


def _save(p):
    p.setBrush(C.blue)
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 2, 2)
    p.setBrush(C.paper)
    p.drawRect(QRectF(7, 3, 10, 6))
    p.drawRect(QRectF(6, 13, 12, 8))


def _run(p):
    p.setPen(QPen(QColor("#1d7a32"), 1))
    p.setBrush(QColor("#34c759"))
    p.drawPolygon([QPointF(6, 3.5), QPointF(20, 12), QPointF(6, 20.5)])


def _stop(p):
    p.setPen(QPen(QColor("#a3261f"), 1))
    p.setBrush(QColor("#ff453a"))
    p.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)


def _sun(p):
    p.setPen(QPen(QColor("#f5a623"), 1.6, Qt.SolidLine, Qt.RoundCap))
    center = QPointF(12, 12)
    for i in range(8):
        angle = i * math.pi / 4
        direction = QPointF(math.cos(angle), math.sin(angle))
        p.drawLine(center + direction * 7, center + direction * 10)
    p.setPen(QPen(QColor("#e8930c"), 1))
    p.setBrush(QColor("#ffc94a"))
    p.drawEllipse(center, 4.5, 4.5)


def _moon(p):
    disc = QPainterPath()
    disc.addEllipse(QRectF(4, 4, 16, 16))
    bite = QPainterPath()
    bite.addEllipse(QRectF(9, 1, 14, 14))
    color = QColor("#5b5fc7") if C is _LIGHT else QColor("#c9ccff")
    p.setPen(QPen(color.darker(130), 1))
    p.setBrush(color)
    p.drawPath(disc.subtracted(bite))


def _kitchensink(p):
    # A 2 x 2 sampler of controls
    for (x, y), drawer in zip(((0, 0), (12, 0), (0, 12), (12, 12)),
                              (_commandbutton, _checkbox, _optionbutton, _listbox)):
        p.save()
        p.translate(x, y)
        p.scale(0.5, 0.5)
        drawer(p)
        p.restore()


def _badge(p, color: str, letter: str, size: int = 13):
    """Outline item icon: a colored rounded square with a white letter."""
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 4, 4)
    _text(p, QRectF(3, 2, 18, 19), letter, size, True, QColor("#ffffff"))


_OUTLINE_BADGES = {
    "OutlineConstant": ("#0f8f8c", "K"),
    "OutlineVariable": ("#2f6fd6", "v"),
    "OutlineClass": ("#d9800f", "C"),
    "OutlineFunction": ("#8e44ad", "\u0192"),  # ƒ
    "OutlineMethod": ("#a45ad8", "m"),
    "OutlineAttribute": ("#50708f", "a"),
    "OutlineCode": ("#6d6d6d", "\u25b6"),  # ▶
}


def _console(p):
    p.setBrush(QColor("#1e1e1e"))
    p.setPen(QPen(C.ink, 1))
    p.drawRect(QRectF(2, 4, 20, 16))
    _text(p, QRectF(3, 5, 18, 14), ">_", 9, True, QColor("#7CFC00"),
          Qt.AlignLeft | Qt.AlignVCenter)


_DRAWERS = {
    "Pointer": _pointer, "PictureBox": _picturebox, "Label": _label, "TextBox": _textbox,
    "Frame": _frame, "CommandButton": _commandbutton, "CheckBox": _checkbox,
    "OptionButton": _optionbutton, "ComboBox": _combobox, "ListBox": _listbox,
    "HScrollBar": _hscroll, "VScrollBar": _vscroll, "Timer": _timer, "Line": _line, "Image": _image, "TreeView": _treeview, "Splitter": _splitter,
    "ProgressBar": _progressbar, "Slider": _slider, "UpDown": _updown, "StatusBar": _statusbar,
    "TabStrip": _tabstrip, "ImageList": _imagelist, "Toolbar": _toolbar,
    "Form": _form, "Module": _module, "Project": _folder, "Console": _console,
    "New": _new, "Open": _open, "Save": _save, "Run": _run, "Stop": _stop,
    "Sun": _sun, "Moon": _moon, "KitchenSink": _kitchensink,
    **{name: (lambda p, c=color, l=letter: _badge(p, c, l, 10 if l == "\u25b6" else 13))
       for name, (color, letter) in _OUTLINE_BADGES.items()},
}

_dark = False


def set_dark(dark: bool) -> None:
    """Choose the variant returned by icon() / large_icon()."""
    global _dark
    _dark = bool(dark)


def is_dark() -> bool:
    return _dark


def _render(name: str, dark: bool, scale: int) -> QPixmap:
    global C
    pixmap = QPixmap(SIZE * scale, SIZE * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(scale, scale)
    C = _DARK if dark else _LIGHT
    painter.setPen(QPen(C.ink, 1 if scale <= 2 else 0.8))
    _DRAWERS.get(name, _module)(painter)
    painter.end()
    C = _LIGHT
    pixmap.setDevicePixelRatio(2)
    return pixmap


def _faded(pixmap: QPixmap) -> QPixmap:
    faded = QPixmap(pixmap.size())
    faded.setDevicePixelRatio(pixmap.devicePixelRatio())
    faded.fill(Qt.transparent)
    painter = QPainter(faded)
    painter.setOpacity(0.35)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return faded


@lru_cache(maxsize=None)
def _icon(name: str, dark: bool, scale: int) -> QIcon:
    pixmap = _render(name, dark, scale)
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Normal)
    icon.addPixmap(_faded(pixmap), QIcon.Disabled)  # visible but clearly inactive
    return icon


def icon(name: str) -> QIcon:
    """24px icon (drawn at 2x for HiDPI) in the current light/dark variant."""
    return _icon(name, _dark, 2)


def large_icon(name: str) -> QIcon:
    """48px icons for the New Project dialog."""
    return _icon(name, _dark, 4)
