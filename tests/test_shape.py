"""The Shape control: its kinds, fills, border and back style, drawn as asked; no events,
clicks going through; the constants, Toolbox and icon."""

import os

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor

from vp6 import (Form, Shape, vpBSDash, vpBSInsideSolid, vpBSSolid, vpBSTransparent, vpBlue,
                 vpCross, vpDiagonalCross, vpDownwardDiagonal, vpFSSolid, vpFSTransparent,
                 vpGreen, vpHorizontalLine, vpOpaque, vpRed, vpShapeCircle, vpShapeOval,
                 vpShapeRectangle, vpShapeRoundedRectangle, vpShapeRoundedSquare,
                 vpShapeSquare, vpTransparent, vpUpwardDiagonal, vpVerticalLine, vpYellow)
from vp6.controls import CONTROL_TYPES
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


@pytest.fixture
def shape(qapp):
    form = Form()
    form.BackColor = vpBlue  # (what shows through a transparent shape)
    shape = Shape(form, Name="shp", Left=10, Top=10, Width=100, Height=60, FillStyle=vpFSSolid,
                  FillColor=vpRed, BorderColor=vpGreen, BorderWidth=4)
    form.Show()
    yield shape
    form.Unload()


def pixel(shape, x, y) -> str:
    """A pixel's color in the shape's own coordinates, as drawn on the form."""
    image = shape._form._widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return QColor(image.pixel(int((shape.Left + x) * ratio),
                              int((shape.Top + y) * ratio))).name()


def test_defaults():
    form = Form()
    shape = Shape(form, Name="shp")
    assert (shape.Width, shape.Height) == (81, 81)
    assert (shape.Shape, shape.BackStyle, shape.FillStyle, shape.BorderStyle,
            shape.BorderWidth) == (vpShapeRectangle, vpTransparent, vpFSTransparent, vpBSSolid, 1)
    assert shape.FillColor is None and shape.BorderColor is None and shape.BackColor is None
    assert CONTROL_TYPES["Shape"].Events == () and CONTROL_TYPES["Shape"].DefaultEvent == ""
    form.Unload()


def test_rectangle_fill_and_border(shape):
    assert pixel(shape, 50, 30) == "#ff0000"  # filled
    assert pixel(shape, 1, 30) == "#00ff00"  # its border, inside its box
    shape.BorderStyle = vpBSTransparent
    assert pixel(shape, 1, 30) == "#ff0000"
    shape.FillStyle = vpFSTransparent  # what is behind shows through
    assert pixel(shape, 50, 30) == "#0000ff"
    shape.BackStyle = vpOpaque  # its BackColor (unset: the window's)
    shape.BackColor = vpYellow
    assert pixel(shape, 50, 30) == "#ffff00"


def test_round_kinds(shape):
    shape.BorderStyle = vpBSTransparent
    for kind in (vpShapeOval, vpShapeCircle, vpShapeRoundedRectangle, vpShapeRoundedSquare):
        shape.Shape = kind
        assert pixel(shape, 1, 1) == "#0000ff", kind  # (the corner: outside it)
        assert pixel(shape, 50, 30) == "#ff0000", kind
    shape.Shape = vpShapeCircle  # as wide as high, centered: the sides are outside
    assert pixel(shape, 50, 2) == "#ff0000" and pixel(shape, 5, 30) == "#0000ff"
    shape.Shape = vpShapeSquare
    assert pixel(shape, 25, 30) == "#ff0000" and pixel(shape, 15, 30) == "#0000ff"
    shape.Shape = vpShapeOval  # the whole box
    assert pixel(shape, 5, 30) == "#ff0000"


def test_hatched_fills(shape):
    shape.BorderStyle = vpBSTransparent
    for style in (vpHorizontalLine, vpVerticalLine, vpUpwardDiagonal, vpDownwardDiagonal,
                  vpCross, vpDiagonalCross):
        shape.FillStyle = style
        image = shape._form._widget.grab().toImage()
        ratio = image.devicePixelRatio()
        colors = {QColor(image.pixel(int((shape.Left + x) * ratio),
                                     int((shape.Top + y) * ratio))).name()
                  for x in range(20, 80) for y in range(20, 40)}
        assert "#0000ff" in colors and any(c != "#0000ff" for c in colors), style  # lines
    shape.FillStyle = vpHorizontalLine  # lines at y = 4, 12, 20...: between them, behind
    assert pixel(shape, 50, 8) == "#0000ff"


def test_border_styles_and_widths(shape):
    shape.FillStyle = vpFSTransparent
    shape.BorderStyle = vpBSInsideSolid
    shape.BorderWidth = 6
    assert pixel(shape, 3, 30) == "#00ff00" and pixel(shape, 8, 30) == "#0000ff"
    shape.BorderStyle = vpBSDash  # some of the border's pixels: gaps
    image = shape._form._widget.grab().toImage()
    ratio = image.devicePixelRatio()
    top = {QColor(image.pixel(int((shape.Left + x) * ratio), int((shape.Top + 2) * ratio)))
           .name() for x in range(10, 90)}
    assert top == {"#00ff00", "#0000ff"}


def test_no_events_and_clicks_go_through(shape):
    widget = shape._form._widget
    assert widget.childAt(QPoint(shape.Left + 50, shape.Top + 30)) is None  # (transparent)
    assert shape._widget.focusPolicy() == shape._widget.focusPolicy().NoFocus
    with pytest.raises(AttributeError):
        shape.Caption = "x"


def test_toolbox_icon_and_constants(qapp):
    assert "Shape" in Toolbox().buttons and "Shape" in CONTROL_TYPES
    order = list(CONTROL_TYPES)
    assert order.index("Shape") == order.index("Line") - 1  # VB's Toolbox: Shape, Line
    assert not icon("Shape").isNull()
    assert (vpShapeRectangle, vpShapeSquare, vpShapeOval, vpShapeCircle,
            vpShapeRoundedRectangle, vpShapeRoundedSquare) == tuple(range(6))
    assert (vpFSSolid, vpFSTransparent, vpHorizontalLine, vpVerticalLine, vpUpwardDiagonal,
            vpDownwardDiagonal, vpCross, vpDiagonalCross) == tuple(range(8))
    assert (vpBSTransparent, vpBSSolid, vpBSDash, vpBSInsideSolid) == (0, 1, 2, 6)
