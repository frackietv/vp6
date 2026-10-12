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


def _drivelistbox(p):
    _combobox(p)
    p.setBrush(C.face)  # a drive in the box
    p.drawRect(QRectF(4, 9.5, 9, 5))
    p.fillRect(QRectF(10.5, 11.5, 1.5, 1.5), QColor("#3cb043"))


def _folder_shape(p, x, y, color):
    p.setBrush(color)
    p.drawPolygon([QPointF(x, y), QPointF(x + 3, y), QPointF(x + 4, y + 1.5),
                   QPointF(x + 8, y + 1.5), QPointF(x + 8, y + 6), QPointF(x, y + 6)])


def _dirlistbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    folder = QColor("#e8b730")
    _folder_shape(p, 5, 5, folder)  # an open folder and one in it
    p.drawLine(QPointF(7, 11), QPointF(7, 16))
    p.drawLine(QPointF(7, 16), QPointF(10, 16))
    _folder_shape(p, 10, 13, folder)


def _filelistbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    for y in (6, 11.5, 17):  # files, each a page with a folded corner, and its name
        p.drawPolygon([QPointF(5, y - 1.5), QPointF(7.5, y - 1.5), QPointF(9, y),
                       QPointF(9, y + 2.5), QPointF(5, y + 2.5)])
        p.drawLine(QPointF(11, y + 0.5), QPointF(18.5, y + 0.5))


def _richtextbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    _text(p, QRectF(4, 3, 9, 10), "A", 9, True, QColor("#d03030"))  # formatted text
    _text(p, QRectF(11, 3, 9, 10), "b", 9, False, C.blue)
    p.drawLine(QPointF(6, 14), QPointF(18, 14))
    p.drawLine(QPointF(6, 17.5), QPointF(15, 17.5))


def _codebox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    p.fillRect(QRectF(3.5, 3.5, 5, 17), C.face)  # the gutter
    for y in (7, 11, 15, 19):  # its line numbers
        p.drawLine(QPointF(5, y - 1), QPointF(7, y - 1))
    for x, y, w, color in ((10, 6, 6, C.blue), (12, 10, 7, QColor("#d03030")),
                           (12, 14, 5, QColor("#2e9e40")), (10, 18, 4, C.ink)):
        p.fillRect(QRectF(x, y, w, 1.6), color)  # colored code


def _markdownbox(p):
    p.setBrush(C.paper)
    p.drawRoundedRect(QRectF(2, 5, 20, 14), 2, 2)
    _text(p, QRectF(3, 5, 11, 14), "M", 10, True)  # the Markdown mark: M and a down arrow
    p.fillRect(QRectF(16, 8, 2, 5), C.ink)
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(14, 12.5), QPointF(20, 12.5), QPointF(17, 16)])


def _flexgrid(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 4, 18, 16))
    p.fillRect(QRectF(3.5, 4.5, 17, 3.5), C.face)  # the fixed row
    p.fillRect(QRectF(3.5, 4.5, 4, 15), C.face)  # and column
    for x in (7.5, 14):
        p.drawLine(QPointF(x, 4), QPointF(x, 20))
    for y in (8, 12, 16):
        p.drawLine(QPointF(3, y), QPointF(21, y))
    p.fillRect(QRectF(8, 12.5, 5.5, 3), C.blue)  # the current cell


def _data(p):  # VB's Data control: |< < > >| under a database
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 13, 20, 8))
    p.setBrush(QColor("#f2d17b") if C is _LIGHT else QColor("#8a7230"))
    p.drawRect(QRectF(6, 4, 12, 6))  # the database: a cylinder
    p.drawEllipse(QRectF(6, 2, 12, 4))
    p.setBrush(C.ink)
    p.setPen(Qt.NoPen)
    p.drawPolygon([QPointF(8, 14.5), QPointF(8, 19.5), QPointF(4.5, 17)])  # previous
    p.drawPolygon([QPointF(16, 14.5), QPointF(16, 19.5), QPointF(19.5, 17)])  # next


def _dockpanel(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 3, 20, 18))  # the form
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 8, 18))  # a panel docked to its left
    p.fillRect(QRectF(2.5, 3.5, 7, 3.5), C.blue)  # its caption bar
    p.drawRect(QRectF(12, 8, 8, 9))  # and one floating
    p.fillRect(QRectF(12.5, 8.5, 7, 3), C.blue)


def _shape(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 4, 12, 10))  # a rectangle
    p.setBrush(C.blue)
    p.drawEllipse(QRectF(9, 9, 12, 12))  # and a circle over it


def _usercontrol(p):
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 4, 20, 16))  # a control of your own: a surface...
    p.setBrush(C.paper)
    p.drawRect(QRectF(5, 7, 9, 5))  # ...with controls on it
    p.setBrush(C.button_bottom)
    p.drawRect(QRectF(5, 14, 6, 4))
    p.setBrush(C.blue)
    p.drawEllipse(QRectF(14, 11, 6, 6))


def _commondialog(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 4, 18, 16))  # a dialog window
    p.fillRect(QRectF(3.5, 4.5, 17, 3.5), C.blue)  # its title bar
    p.setBrush(QColor("#e8b730"))
    p.drawRect(QRectF(6, 11, 6, 5))  # a folder
    p.setBrush(C.face)
    p.drawRect(QRectF(14, 15, 5, 3))  # a button


def _webview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))  # a page...
    p.fillRect(QRectF(2.5, 3.5, 19, 4), C.face)  # ...with an address bar
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(C.blue, 1.2))
    p.drawEllipse(QRectF(7, 9, 10, 10))  # a globe
    p.drawEllipse(QRectF(10, 9, 4, 10))
    p.drawLine(QPointF(7, 14), QPointF(17, 14))


def _webbrowser(p):
    _webview(p)
    p.setPen(QPen(C.ink, 1))
    p.setBrush(C.paper)
    p.drawRect(QRectF(4, 4.5, 3, 2))  # its back and forward buttons
    p.drawRect(QRectF(8, 4.5, 3, 2))


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


def _process(p):  # a console window
    p.setBrush(QColor("#2b2b2b"))
    p.drawRect(QRectF(3, 5, 18, 14))
    p.setPen(QPen(QColor("#5fd35f"), 1.6))
    p.drawLine(QPointF(6, 9), QPointF(9, 12))
    p.drawLine(QPointF(9, 12), QPointF(6, 15))
    p.drawLine(QPointF(11, 15), QPointF(16, 15))


def _winsock(p):  # two computers, connected
    p.setBrush(QColor("#5b9bd5"))
    p.drawRect(QRectF(2.5, 3.5, 9, 7))
    p.drawRect(QRectF(12.5, 13.5, 9, 7))
    p.setPen(QPen(QColor("#2e9d4a"), 1.6))
    p.setBrush(Qt.NoBrush)
    p.drawPolyline([QPointF(7, 11), QPointF(7, 17), QPointF(12, 17)])


def _filewatcher(p):  # a page with an eye on it
    p.setBrush(C.paper)
    p.drawRect(QRectF(4.5, 2.5, 13, 18))
    p.setPen(QPen(C.ink, 0.8))
    for y in (6.5, 9.5, 12.5):
        p.drawLine(QPointF(7, y), QPointF(15, y))
    p.setPen(QPen(C.ink, 1))
    p.setBrush(QColor("#5b9bd5"))
    p.drawEllipse(QRectF(10.5, 14.5, 11, 7))
    p.setBrush(QColor("#1e1e1e"))
    p.drawEllipse(QRectF(14.5, 16.5, 3, 3))


def _designerview(p):  # a form with a selected control: grab handles
    p.setBrush(C.paper)
    p.drawRect(QRectF(2.5, 3.5, 19, 17))
    p.setBrush(QColor("#5b9bd5"))
    p.drawRect(QRectF(2.5, 3.5, 19, 3))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(C.ink, 0.8, Qt.DashLine))
    p.drawRect(QRectF(6.5, 9.5, 11, 7))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1f6fd1"))
    for x, y in ((5.5, 8.5), (16.5, 8.5), (5.5, 15.5), (16.5, 15.5)):
        p.drawRect(QRectF(x, y, 2.5, 2.5))
    p.setPen(QPen(C.ink, 1))


def _terminal(p):  # a terminal window with a prompt
    p.setBrush(QColor("#1e1e1e"))
    p.drawRect(QRectF(2.5, 4, 19, 16))
    p.setPen(QPen(QColor("#e5e5e5"), 1.5))
    p.drawLine(QPointF(5.5, 8.5), QPointF(8.5, 11.5))
    p.drawLine(QPointF(8.5, 11.5), QPointF(5.5, 14.5))
    p.setPen(QPen(QColor("#5fd35f"), 1.5))
    p.drawLine(QPointF(10.5, 15), QPointF(15.5, 15))


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


def _listview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.setBrush(C.face)
    p.drawRect(QRectF(2, 3, 20, 4))  # the column titles
    for y, color in ((9.5, "#9ec5fe"), (13.5, "#ffe08a"), (17.5, "#a3e4a8")):  # three rows
        p.setBrush(QColor(color))
        p.drawRect(QRectF(4, y - 1, 2.5, 2.5))
        p.drawLine(QPointF(8, y), QPointF(13, y))
        p.drawLine(QPointF(15, y), QPointF(20, y))


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


def _pause(p):  # (Run > Break: two bars, as a pause button)
    p.setPen(QPen(QColor("#1f5fbf"), 1))
    p.setBrush(QColor("#4c8dff"))
    p.drawRoundedRect(QRectF(6, 5, 4.5, 14), 1, 1)
    p.drawRoundedRect(QRectF(13.5, 5, 4.5, 14), 1, 1)


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


def _isometric(p):
    # A cube in isometric projection: three shaded faces, 120 degrees apart
    top, left, right = QColor("#9fb8ec"), QColor("#4f74c8"), QColor("#2f4f9a")
    w = 10.4  # (a face's width: its edges at 30 degrees)
    p.setPen(QPen(QColor("#1d2b4f"), 0.8))
    for color, corners in ((top, ((12, 3), (12 + w, 6), (12, 9), (12 - w, 6))),
                           (left, ((12 - w, 6), (12, 9), (12, 21), (12 - w, 18))),
                           (right, ((12, 9), (12 + w, 6), (12 + w, 18), (12, 21)))):
        p.setBrush(color)
        p.drawPolygon([QPointF(x, y) for x, y in corners])


def _perspective(p):
    # A box in two-point perspective: its edges heading for vanishing points on the
    # horizon at the sides, the horizon dashed
    top, left, right = QColor("#f2c879"), QColor("#d9822b"), QColor("#a8541c")
    p.setPen(QPen(QColor("#888888"), 0.6, Qt.DashLine))
    p.drawLine(QPointF(1, 4), QPointF(23, 4))
    p.setPen(QPen(QColor("#4a2a10"), 0.8))
    for color, corners in ((top, ((12, 7.5), (21, 8.8), (12, 10.8), (3, 8.8))),
                           (left, ((3, 8.8), (12, 10.8), (12, 22), (3, 17.6))),
                           (right, ((12, 10.8), (21, 8.8), (21, 17.6), (12, 22)))):
        p.setBrush(color)
        p.drawPolygon([QPointF(x, y) for x, y in corners])


def _toolbox_list(p):  # the Toolbox's list view: rows of an icon and a name
    for y in (4, 10.5, 17):
        p.setBrush(C.blue)
        p.drawRect(QRectF(3, y, 4.5, 4.5))
        p.fillRect(QRectF(10, y + 1.5, 11, 1.6), C.ink)


def _toolbox_groups(p):  # the Toolbox by category: two headings, each over its tools
    for y in (3, 13):
        p.fillRect(QRectF(2, y, 20, 2.2), C.ink)
        p.setBrush(C.paper)
        for x in (4, 10, 16):
            p.drawRect(QRectF(x, y + 4, 4, 4))


def _toolbox_sort(p):  # the Toolbox in its own order: rows of different lengths
    for y, width in ((4, 12), (10.5, 18), (17, 8)):
        p.fillRect(QRectF(3, y + 1, width, 2.2), C.ink)


def _toolbox_sorted(p, first: str, last: str):  # by name: two letters and an arrow down
    _text(p, QRectF(1, 0, 11, 12), first, 10, True)
    _text(p, QRectF(1, 12, 11, 12), last, 10, True)
    p.fillRect(QRectF(16, 3, 2, 14), C.blue)
    p.setBrush(C.blue)
    p.drawPolygon([QPointF(13, 15), QPointF(21, 15), QPointF(17, 21)])


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


# --- the newer controls -------------------------------------------------------------------

def _spinbox(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 6, 20, 12))  # a number box...
    _text(p, QRectF(3, 6, 12, 12), "42", 8, align=Qt.AlignVCenter | Qt.AlignLeft)
    p.setBrush(C.face)
    p.drawRect(QRectF(15, 6, 7, 6))  # ...with its arrows in it
    p.drawRect(QRectF(15, 12, 7, 6))
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(18.5, 7.5), QPointF(16.8, 10.5), QPointF(20.2, 10.5)])
    p.drawPolygon([QPointF(18.5, 16.5), QPointF(16.8, 13.5), QPointF(20.2, 13.5)])


def _dtpicker(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))  # a calendar page
    p.fillRect(QRectF(2.5, 3.5, 19, 4.5), QColor("#d03030"))
    for x in (6, 11, 16):
        p.drawLine(QPointF(x, 1.5), QPointF(x, 5))  # its rings
    _text(p, QRectF(2, 8, 20, 13), "31", 9, True)


def _monthview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.fillRect(QRectF(2.5, 3.5, 19, 4), C.blue)  # the month's header, and a grid of days
    for row in range(3):
        for col in range(5):
            p.fillRect(QRectF(4 + col * 3.6, 10 + row * 3.6, 2, 2),
                       QColor("#d03030") if (row, col) == (1, 2) else C.ink)


def _dial(p):
    p.setBrush(C.face)
    p.drawEllipse(QRectF(4, 4, 16, 16))  # a knob, its notches around it
    for angle in range(-120, 121, 40):
        rad = math.radians(angle - 90)
        p.drawLine(QPointF(12 + 9.5 * math.cos(rad), 12 + 9.5 * math.sin(rad)),
                   QPointF(12 + 11.5 * math.cos(rad), 12 + 11.5 * math.sin(rad)))
    p.setBrush(C.blue)
    p.drawEllipse(QRectF(13, 6.5, 3.5, 3.5))  # its mark


def _lcdnumber(p):
    p.setBrush(QColor("#1e1e1e"))
    p.drawRect(QRectF(2, 5, 20, 14))
    p.setPen(QPen(QColor("#ff4040"), 1.6))  # a seven-segment 8 and a 1
    for x in (5, 13):
        p.drawLine(QPointF(x + 1, 8), QPointF(x + 4, 8))
        p.drawLine(QPointF(x + 1, 12), QPointF(x + 4, 12))
        p.drawLine(QPointF(x + 1, 16), QPointF(x + 4, 16))
        p.drawLine(QPointF(x, 9), QPointF(x, 11))
        p.drawLine(QPointF(x + 5, 9), QPointF(x + 5, 11))
        p.drawLine(QPointF(x, 13), QPointF(x, 15))
        p.drawLine(QPointF(x + 5, 13), QPointF(x + 5, 15))
    p.setPen(QPen(C.ink, 1))


def _fontcombobox(p):
    _combobox(p)
    _text(p, QRectF(3, 7, 12, 10), "Aa", 8, False, None, Qt.AlignVCenter | Qt.AlignLeft)


def _hotkey(p):
    p.setBrush(C.paper)
    p.drawRoundedRect(QRectF(2, 6, 10, 12), 2, 2)  # two keys
    p.drawRoundedRect(QRectF(13, 6, 9, 12), 2, 2)
    _text(p, QRectF(2, 6, 10, 12), "^", 9, True)
    _text(p, QRectF(13, 6, 9, 12), "S", 8, True)


def _commandlink(p):
    p.setBrush(C.paper)
    p.drawRoundedRect(QRectF(2, 5, 20, 14), 2, 2)
    p.setBrush(QColor("#2e9e40"))
    p.setPen(Qt.NoPen)
    p.drawPolygon([QPointF(4.5, 8), QPointF(9, 11), QPointF(4.5, 14)])  # the arrow
    p.setPen(QPen(C.ink, 1))
    p.fillRect(QRectF(10.5, 8.5, 9, 2), C.blue)  # its caption
    p.fillRect(QRectF(10.5, 13, 7, 1.2), C.ink)  # and description


def _toolbutton(p):
    p.setBrush(C.face)
    p.drawRoundedRect(QRectF(3, 4, 15, 16), 2, 2)
    p.setBrush(QColor("#f5c542"))
    p.drawEllipse(QRectF(6, 7, 9, 9))  # a picture
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(18.5, 13), QPointF(22, 13), QPointF(20.25, 15.5)])  # its menu


def _buttonbox(p):
    for x, accept in ((2, False), (12.5, True)):
        p.setBrush(C.blue if accept else C.button_top)
        p.drawRoundedRect(QRectF(x, 8, 9.5, 8), 2, 2)
    _text(p, QRectF(12.5, 8, 9.5, 8), "OK", 6, True, QColor("#ffffff"))


def _toolbox_control(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 2, 18, 20))
    for y in (2, 6, 17):  # the pages' headers, one of them open
        p.fillRect(QRectF(3.5, y + 0.5, 17, 3.5), C.face)
        p.drawLine(QPointF(3, y + 4), QPointF(21, y + 4))
    p.fillRect(QRectF(6, 12, 9, 2), C.blue)


def _pageframe(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(7, 2, 14, 14))  # pages, one behind another
    p.drawRect(QRectF(5, 4, 14, 14))
    p.drawRect(QRectF(3, 6, 14, 14))
    p.fillRect(QRectF(5, 9, 9, 2), C.blue)
    p.fillRect(QRectF(5, 13, 6, 2), C.blue)


def _scrollpanel(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.setBrush(C.face)
    p.drawRect(QRectF(17, 3, 5, 18))  # its scroll bar
    p.setBrush(C.blue)
    p.drawRect(QRectF(18, 6, 3, 6))
    p.setBrush(C.button_top)
    p.drawRect(QRectF(5, 7, 9, 5))  # a control in it, cut at the edge
    p.drawRect(QRectF(5, 15, 11, 6))


def _columnview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 4, 20, 16))
    p.drawLine(QPointF(8.5, 4), QPointF(8.5, 20))
    p.drawLine(QPointF(15, 4), QPointF(15, 20))
    p.fillRect(QRectF(3, 7, 5, 2.5), C.blue)  # chosen in each column
    p.fillRect(QRectF(9.5, 11, 5, 2.5), C.blue)
    p.setBrush(C.face)
    p.drawRect(QRectF(16.5, 7, 4, 6))  # the preview


def _dbgrid(p):
    _flexgrid(p)
    p.setBrush(QColor("#f2d17b") if C is _LIGHT else QColor("#8a7230"))
    p.drawRect(QRectF(14, 15, 8, 5))  # a database
    p.drawEllipse(QRectF(14, 13.5, 8, 3))


def _graphicsview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.setBrush(QColor("#f5c542"))
    p.save()
    p.translate(8, 10)
    p.rotate(-15)
    p.drawRect(QRectF(-4, -3, 8, 6))  # shapes, turned
    p.restore()
    p.setBrush(C.blue)
    p.drawEllipse(QRectF(12, 12, 7, 7))
    p.drawLine(QPointF(4, 18), QPointF(11, 14))


def _chart(p):
    p.drawLine(QPointF(3, 3), QPointF(3, 21))  # the axes
    p.drawLine(QPointF(3, 21), QPointF(21, 21))
    for x, h, color in ((5, 8, "#1f8fe0"), (10, 14, "#7fc36b"), (15, 11, "#f2a12b")):
        p.setBrush(QColor(color))
        p.drawRect(QRectF(x, 21 - h, 4, h))


def _svgimage(p):
    p.setPen(QPen(C.ink, 1, Qt.DashLine))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.setPen(QPen(C.blue, 1.4))
    path = QPainterPath()  # a curve and its control points: vectors
    path.moveTo(5, 17)
    path.cubicTo(8, 5, 16, 19, 19, 7)
    p.drawPath(path)
    p.setPen(QPen(C.ink, 1))
    p.setBrush(C.paper)
    for x, y in ((5, 17), (19, 7)):
        p.drawRect(QRectF(x - 1.5, y - 1.5, 3, 3))


def _mediaplayer(p):
    p.setBrush(QColor("#1e1e1e"))
    p.drawRect(QRectF(2, 4, 20, 13))  # the video...
    p.setBrush(QColor("#ffffff"))
    p.setPen(Qt.NoPen)
    p.drawPolygon([QPointF(10, 7), QPointF(15, 10.5), QPointF(10, 14)])
    p.setPen(QPen(C.ink, 1))
    p.drawLine(QPointF(2, 20), QPointF(22, 20))  # ...and its position
    p.setBrush(C.blue)
    p.drawEllipse(QRectF(9, 18.5, 3, 3))


def _pdfviewer(p):
    p.setBrush(C.paper)
    p.drawPolygon([QPointF(5, 2), QPointF(15, 2), QPointF(19, 6), QPointF(19, 22),
                   QPointF(5, 22)])  # a page with a folded corner
    p.fillRect(QRectF(3, 11, 15, 6), QColor("#d03030"))
    _text(p, QRectF(3, 11, 15, 6), "PDF", 5, True, QColor("#ffffff"))


def _openglview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(2, 3, 20, 18))
    p.setBrush(QColor("#1f8fe0"))  # a cube in 3D
    p.drawPolygon([QPointF(12, 6), QPointF(18, 9), QPointF(12, 12), QPointF(6, 9)])
    p.setBrush(QColor("#7fc36b"))
    p.drawPolygon([QPointF(6, 9), QPointF(12, 12), QPointF(12, 19), QPointF(6, 16)])
    p.setBrush(QColor("#f2a12b"))
    p.drawPolygon([QPointF(12, 12), QPointF(18, 9), QPointF(18, 16), QPointF(12, 19)])


def _quickview(p):
    p.setBrush(QColor("#41cd52"))  # Qt's green, and QML
    p.drawRoundedRect(QRectF(2, 5, 20, 14), 3, 3)
    _text(p, QRectF(2, 5, 20, 14), "QML", 7, True, QColor("#ffffff"))


def _undoview(p):
    p.setBrush(C.paper)
    p.drawRect(QRectF(3, 3, 18, 18))
    for y in (7, 11, 15):  # a history...
        p.drawLine(QPointF(10, y), QPointF(18, y))
    p.fillRect(QRectF(9, 9.5, 10, 3), C.blue)
    p.setPen(QPen(C.ink, 1.4))  # ...and the undo arrow
    path = QPainterPath()
    path.moveTo(8, 17)
    path.arcTo(QRectF(4, 7, 6, 8), 270, 180)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(QPen(C.ink, 1))
    p.setBrush(C.ink)
    p.drawPolygon([QPointF(5, 7), QPointF(8.5, 5), QPointF(8.5, 9.5)])


def _wizardform(p):
    _form(p)
    p.setBrush(C.blue)  # Back and Next along the bottom
    p.drawRoundedRect(QRectF(13, 16, 7, 3), 1, 1)
    p.setBrush(C.paper)
    p.drawRoundedRect(QRectF(5, 16, 7, 3), 1, 1)


def _console(p):
    p.setBrush(QColor("#1e1e1e"))
    p.setPen(QPen(C.ink, 1))
    p.drawRect(QRectF(2, 4, 20, 16))
    _text(p, QRectF(3, 5, 18, 14), ">_", 9, True, QColor("#7CFC00"),
          Qt.AlignLeft | Qt.AlignVCenter)


def _chat(p):  # a speech bubble with a spark: Claude's sessions
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 3, 20, 14), 4, 4)
    tail = QPainterPath()
    tail.moveTo(6, 16)
    tail.lineTo(5, 21)
    tail.lineTo(11, 16.5)
    p.setBrush(C.paper)
    p.drawPath(path.united(tail))
    p.setPen(QPen(QColor("#d97757"), 1.6))
    for angle in range(0, 180, 45):
        dx, dy = 4 * math.cos(math.radians(angle)), 4 * math.sin(math.radians(angle))
        p.drawLine(QPointF(12 - dx, 10 - dy), QPointF(12 + dx, 10 + dy))
    p.setPen(QPen(C.ink, 1))


_DRAWERS = {
    "Pointer": _pointer, "PictureBox": _picturebox, "Label": _label, "TextBox": _textbox,
    "Frame": _frame, "CommandButton": _commandbutton, "CheckBox": _checkbox,
    "OptionButton": _optionbutton, "ComboBox": _combobox, "ListBox": _listbox,
    "HScrollBar": _hscroll, "VScrollBar": _vscroll, "Timer": _timer, "Process": _process, "Terminal": _terminal,
    "Winsock": _winsock, "FileWatcher": _filewatcher, "DesignerView": _designerview, "Data": _data, "Shape": _shape,
    "Line": _line, "Image": _image,
    "DriveListBox": _drivelistbox, "DirListBox": _dirlistbox, "FileListBox": _filelistbox,
    "TreeView": _treeview, "Splitter": _splitter,
    "ProgressBar": _progressbar, "Slider": _slider, "UpDown": _updown, "StatusBar": _statusbar,
    "TabStrip": _tabstrip, "ImageList": _imagelist, "Toolbar": _toolbar,
    "ListView": _listview, "RichTextBox": _richtextbox,
    "CodeBox": _codebox, "MarkdownBox": _markdownbox, "FlexGrid": _flexgrid,
    "DockPanel": _dockpanel, "UserControl": _usercontrol,
    "CommonDialog": _commondialog, "WebView": _webview, "WebBrowser": _webbrowser,
    "Form": _form, "Module": _module, "Project": _folder, "Console": _console, "Chat": _chat,
    "New": _new, "Open": _open, "Save": _save, "Run": _run, "Stop": _stop, "Pause": _pause,
    "Sun": _sun, "Moon": _moon, "KitchenSink": _kitchensink, "Isometric": _isometric,
    "SpinBox": _spinbox, "DTPicker": _dtpicker, "MonthView": _monthview, "Dial": _dial,
    "LCDNumber": _lcdnumber, "FontComboBox": _fontcombobox, "HotKey": _hotkey,
    "CommandLink": _commandlink, "ToolButton": _toolbutton, "ButtonBox": _buttonbox,
    "ToolBox": _toolbox_control, "PageFrame": _pageframe, "ScrollPanel": _scrollpanel,
    "ColumnView": _columnview, "DBGrid": _dbgrid, "GraphicsView": _graphicsview,
    "Chart": _chart, "SvgImage": _svgimage, "MediaPlayer": _mediaplayer,
    "PdfViewer": _pdfviewer, "OpenGLView": _openglview, "QuickView": _quickview,
    "UndoView": _undoview, "WizardForm": _wizardform,
    "Perspective": _perspective, "ToolboxList": _toolbox_list,
    "ToolboxGroups": _toolbox_groups, "ToolboxSort": _toolbox_sort,
    "ToolboxSortAscending": lambda p: _toolbox_sorted(p, "A", "Z"),
    "ToolboxSortDescending": lambda p: _toolbox_sorted(p, "Z", "A"),
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
