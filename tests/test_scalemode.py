"""ScaleMode: the graphics methods, CurrentX / CurrentY, ScaleLeft / ScaleTop /
ScaleWidth / ScaleHeight, Scale, ScaleX / ScaleY and mouse events' X, Y in
twips, points, inches, centimeters, millimeters, characters or a User scale,
on forms, PictureBoxes, Picture objects and the Printer; Screen.TwipsPerPixel."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

import vp6
from vp6 import (Form, Picture, PictureBox, Printer, Screen, vpBlue, vpCentimeters,
                 vpCharacters, vpHimetric, vpInches, vpMillimeters, vpPixels, vpPoints, vpRed,
                 vpTwips, vpUser, vpWhite)

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Canvas(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 300, 200
        self.BackColor = vpWhite
        self.AutoRedraw = True
        self.clicks = []

    def Form_MouseDown(self, Button, Shift, X, Y):
        self.clicks.append((X, Y))


@pytest.fixture
def form(qapp):
    form = Canvas()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def test_pixels_by_default(form):
    assert form.ScaleMode == vpPixels and (form.ScaleWidth, form.ScaleHeight) == (300, 200)
    assert (form.ScaleLeft, form.ScaleTop) == (0, 0)
    form.Line(10, 10, 20, 20, vpRed, "BF")
    assert form.Point(15, 15) == vpRed


@pytest.mark.parametrize("mode, per_pixel", [(vpTwips, 15), (vpPoints, 0.75), (vpInches, 1 / 96),
                                             (vpCentimeters, 2.54 / 96),
                                             (vpMillimeters, 25.4 / 96)])
def test_units(form, mode, per_pixel):
    form.ScaleMode = mode
    assert form.ScaleWidth == pytest.approx(300 * per_pixel)
    form.Line(20 * per_pixel, 30 * per_pixel, 60 * per_pixel, 70 * per_pixel, vpBlue, "BF")
    assert form.Point(40 * per_pixel, 50 * per_pixel) == vpBlue
    assert form.Point(10 * per_pixel, 50 * per_pixel) == vpWhite
    assert form.CurrentX == pytest.approx(60 * per_pixel)  # (in its units)
    form.CurrentX = 5 * per_pixel
    form.ScaleMode = vpPixels
    assert form.CurrentX == pytest.approx(5)  # (the same place, in pixels)


def test_characters(form):
    form.ScaleMode = vpCharacters  # 8 x 16 pixels each
    assert (form.ScaleWidth, form.ScaleHeight) == (300 / 8, 200 / 16)
    form.PSet(2, 2, vpRed)
    form.ScaleMode = vpPixels
    assert form.Point(16, 32) == vpRed


def test_a_user_scale(form):
    form.Scale(0, 100, 100, 0)  # 0 to 100 across, upwards
    assert form.ScaleMode == vpUser
    assert (form.ScaleLeft, form.ScaleTop, form.ScaleWidth, form.ScaleHeight) == \
        (0, 100, 100, -100)
    form.Line(10, 10, 20, 30, vpRed, "BF")  # near the bottom left
    form.ScaleMode = vpPixels
    assert form.Point(45, 170) == vpRed and form.Point(45, 30) == vpWhite
    form.ScaleWidth = 3  # setting one: a User scale, the others as they are
    assert form.ScaleMode == vpUser and form.ScaleWidth == 3 and form.ScaleHeight == 200
    form.ScaleLeft, form.ScaleTop = -1, -1
    form.PSet(0, 0, vpBlue)  # (0, 0) is a third across, one pixel down
    form.Scale()  # back to pixels
    assert form.ScaleMode == vpPixels and form.Point(100, 1) == vpBlue
    with pytest.raises(ValueError):
        form.ScaleHeight = 0
    with pytest.raises(ValueError):
        form.Scale(1, 1, 1, 5)
    form.ScaleMode = vpUser  # (User from pixels: the pixels it has)
    assert (form.ScaleWidth, form.ScaleHeight) == (300, 200)


def test_circles_text_and_pictures(form):
    form.ScaleMode = vpInches
    form.FillStyle, form.FillColor = 0, vpRed
    form.Circle(1, 1, 0.5, vpRed)  # radius in units across
    form.CurrentX, form.CurrentY = 0, 0
    width = form.TextWidth("Hello")
    form.ScaleMode = vpPixels
    assert form.Point(96, 96) == vpRed and form.Point(96 + 44, 96) == vpRed
    assert form.Point(96 + 52, 96) == vpWhite
    assert width == pytest.approx(form.TextWidth("Hello") / 96)
    form.ScaleMode = vpCentimeters
    form.PaintPicture(Picture(10, 10, BackColor=vpBlue), 5, 1, 1, 1)  # a centimeter square
    form.ScaleMode = vpPixels
    assert form.Point(round(5 * 96 / 2.54) + 10, round(96 / 2.54) + 10) == vpBlue


def test_conversions():
    assert Screen.TwipsPerPixelX == Screen.TwipsPerPixelY == 15
    box = Picture(10, 10)
    assert box.ScaleX(1440, vpTwips, vpInches) == pytest.approx(1)
    assert box.ScaleY(1, vpInches, vpPixels) == pytest.approx(96)
    assert box.ScaleX(2540, vpHimetric, vpCentimeters) == pytest.approx(2.54)
    assert box.ScaleX(96, vpPixels) == 96  # (to its own: pixels)
    box.ScaleWidth = 100  # User: 10 pixels are 100 across
    assert box.ScaleX(10, vpPixels, vpUser) == pytest.approx(100)
    with pytest.raises(ValueError):
        box.ScaleX(1, 42)


def test_mouse_coordinates(form):
    QTest.mouseClick(form._widget, Qt.LeftButton, Qt.NoModifier, QPoint(150, 100))
    form.ScaleMode = vpTwips
    QTest.mouseClick(form._widget, Qt.LeftButton, Qt.NoModifier, QPoint(150, 100))
    form.Scale(0, 0, 1, 1)
    QTest.mouseClick(form._widget, Qt.LeftButton, Qt.NoModifier, QPoint(150, 100))
    assert form.clicks[0] == (150, 100) and form.clicks[1] == (2250, 1500)
    assert form.clicks[2] == pytest.approx((0.5, 0.5))


def test_a_picture_box(qapp):
    class Boxed(Form):
        def InitializeComponent(self):
            self.pic = PictureBox(self, Left=10, Top=10, Width=104, Height=104, AutoRedraw=True,
                                  BackColor=vpWhite, ScaleMode=vpPoints)
            self.at = None

        def pic_MouseDown(self, Button, Shift, X, Y):
            self.at = (X, Y)

    form = Boxed()
    form.Show()
    QTest.qWait(10)
    pic = form.pic
    inside = pic._widget.contentsRect()
    assert pic.ScaleWidth == pytest.approx(inside.width() * 0.75)  # inside its border
    pic.Line(0, 0, 15, 15, vpRed, "BF")
    pic.ScaleMode = vpPixels
    assert pic.Point(10, 10) == vpRed and pic.Point(30, 30) == vpWhite
    QTest.mouseClick(pic._widget, Qt.LeftButton, Qt.NoModifier,
                     inside.topLeft() + QPoint(40, 20))
    assert form.at == (40, 20)  # (from inside its border)
    pic.ScaleMode = vpPoints
    QTest.mouseClick(pic._widget, Qt.LeftButton, Qt.NoModifier,
                     inside.topLeft() + QPoint(40, 20))
    assert form.at == pytest.approx((30, 15))
    assert "ScaleMode" in PictureBox._specs and "ScaleMode" in Form._specs
    form.Unload()


def test_a_picture_and_the_printer(qapp, tmp_path):
    picture = Picture(100, 50, BackColor=vpWhite)
    picture.Scale(0, 0, 10, 5)
    picture.Line(1, 1, 2, 2, vpRed, "BF")
    assert picture.Point(1.5, 1.5) == vpRed and picture.Point(5, 2) == vpWhite
    Printer.OutputFile = str(tmp_path / "scaled.pdf")
    Printer.ScaleMode = vpInches
    assert Printer.ScaleWidth == pytest.approx(Printer._draw_area_size().width() / 96)
    Printer.Line(1, 1, 2, 2, vpRed, "BF")  # an inch square, an inch in
    Printer.EndDoc()
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    document = QPdfDocument()
    document.load(str(tmp_path / "scaled.pdf"))
    size = document.pagePointSize(0)
    image = document.render(0, QSize(round(size.width() * 96 / 72),
                                     round(size.height() * 96 / 72)))
    color = image.pixelColor(48 + 144, 48 + 144)  # (half-inch margins)
    assert color.name() == "#ff0000"
    assert vp6.vpUser == 0 and vp6.vpCharacters == 4
