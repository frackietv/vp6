"""Picture objects: Picture (in memory, drawn on), LoadPicture, SavePicture, a
form's or PictureBox's Image, PaintPicture, Picture objects as picture
properties and icons, a form's background Picture, and pictures on the
clipboard (and in drops from other programs)."""

import os

import pytest
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtTest import QTest

import vp6
from vp6 import (Clipboard, CommandButton, Form, Image, ImageList, LoadPicture, Picture,
                 PictureBox, SavePicture, formfile, vpBlue, vpCFBitmap, vpCFDIB, vpCFFiles,
                 vpCFRTF, vpCFText, vpCustom, vpFSSolid, vpGreen, vpPicTypeBitmap,
                 vpPicTypeNone, vpRed, vpWhite, vpYellow)
from vp6.controls import DataObject

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


def png(path, color, size=(40, 30)) -> str:
    image = QImage(*size, QImage.Format_RGB32)
    image.fill(color)
    image.save(str(path))
    return str(path)


def test_a_picture_in_memory(qapp):
    picture = Picture(50, 40)
    assert (picture.Width, picture.Height, picture.Type) == (50, 40, vpPicTypeBitmap)
    assert picture.Point(10, 10) == -1  # transparent
    picture.Line(0, 0, 20, 20, vpRed, "BF")  # the graphics methods
    picture.FillStyle, picture.FillColor = vpFSSolid, vpYellow
    picture.Circle(35, 30, 8, vpBlue)
    picture.CurrentX, picture.CurrentY = 0, 25
    picture.FontBold = True
    picture.Print("x")
    assert picture.Point(10, 10) == vpRed and picture.Point(35, 30) == vpYellow
    assert picture.Point(50, 0) == -1 and picture.CurrentY > 25
    filled = Picture(10, 10, BackColor=vpGreen)
    assert filled.Point(5, 5) == vpGreen
    filled.PSet(5, 5, vpRed)
    filled.Cls()  # back to its BackColor
    assert filled.Point(5, 5) == vpGreen and (filled.CurrentX, filled.CurrentY) == (0, 0)
    copy = picture.Image  # (a copy)
    copy.Cls()
    assert picture.Point(10, 10) == vpRed
    with pytest.raises(AttributeError):
        picture.Colour = 1


def test_load_and_save(qapp, tmp_path):
    path = png(tmp_path / "a.png", 0xFF0000)  # red, as 0xRRGGBB
    picture = LoadPicture(path)
    assert (picture.Width, picture.Height) == (40, 30) and picture.Point(1, 1) == vpRed
    empty = LoadPicture()
    assert empty.Type == vpPicTypeNone and (empty.Width, empty.Height) == (0, 0)
    with pytest.raises(FileNotFoundError):
        LoadPicture(str(tmp_path / "missing.png"))
    (tmp_path / "not.png").write_text("text")
    with pytest.raises(ValueError):
        LoadPicture(str(tmp_path / "not.png"))
    picture.PSet(2, 2, vpBlue)
    SavePicture(picture, str(tmp_path / "b.jpg"))  # the format from the extension
    assert QImage(str(tmp_path / "b.jpg")).width() == 40
    SavePicture(picture, str(tmp_path / "c"))  # none: BMP, as in VB
    assert open(tmp_path / "c", "rb").read(2) == b"BM"
    SavePicture(path, str(tmp_path / "d.png"))  # a file's picture
    assert LoadPicture(str(tmp_path / "d.png")).Point(1, 1) == vpRed
    with pytest.raises(OSError):
        SavePicture(empty, str(tmp_path / "e.png"))


class Gallery(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 300, 200
        self.BackColor = vpWhite
        self.picBox = PictureBox(self, Left=150, Top=10, Width=100, Height=80, AutoRedraw=True,
                                 BackColor=vpWhite)
        self.imgOne = Image(self, Left=10, Top=150)
        self.cmdIcon = CommandButton(self, Left=200, Top=150, Width=80, Height=40, Style=1)
        self.imlPictures = ImageList(self)


@pytest.fixture
def gallery(qapp):
    form = Gallery()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def test_pictures_as_picture_properties(gallery, tmp_path):
    badge = Picture(30, 20, BackColor=vpRed)
    gallery.picBox.Picture = badge  # PictureBox
    assert gallery.picBox.Point(5, 5) == vpRed and gallery.picBox.Picture is badge
    gallery.imgOne.Picture = badge  # Image: its size
    assert (gallery.imgOne.Width, gallery.imgOne.Height) == (30, 20)
    gallery.cmdIcon.Picture = badge  # a graphical button
    assert not gallery.cmdIcon._widget.icon().isNull()
    gallery.Icon = badge  # the window's icon
    assert not gallery._widget.windowIcon().isNull()
    gallery.picBox.MouseIcon = Picture(16, 16, BackColor=vpBlue)  # a pointer
    gallery.picBox.MousePointer = vpCustom
    assert gallery.picBox._widget.cursor().shape() == Qt.BitmapCursor
    image = gallery.imlPictures.ListImages.Add(1, "badge", badge)  # an ImageList's
    assert image.Picture is badge and gallery.imlPictures.ListImages(1).Width == 30
    gallery.picBox.Picture = LoadPicture()  # (empty: none)
    assert gallery.picBox.Point(5, 5) == vpWhite
    gallery.picBox.Picture = png(tmp_path / "g.png", 0x00FF00)  # (files still work)
    assert gallery.picBox.Point(5, 5) == vpGreen


def test_image_and_paint_picture(gallery, tmp_path):
    box = gallery.picBox
    box.Picture = Picture(20, 20, BackColor=vpGreen)
    box.Line(30, 30, 50, 50, vpRed, "BF")
    shot = box.Image  # background, Picture and drawing, inside the border
    assert (shot.Width, shot.Height) == (box.ScaleWidth, box.ScaleHeight)
    assert shot.Point(5, 5) == vpGreen and shot.Point(40, 40) == vpRed
    assert shot.Point(80, 10) == vpWhite
    gallery.imgOne.Picture = shot  # e.g. another control's Picture
    assert gallery.imgOne.Width == box.ScaleWidth
    # PaintPicture: a Picture or a file, at its size, scaled, or a part of it
    gallery.AutoRedraw = True
    gallery.PaintPicture(shot, 0, 0)
    assert gallery.Point(40, 40) == vpRed and gallery.Point(5, 5) == vpGreen
    gallery.PaintPicture(shot, 0, 100, 20, 20, 30, 30, 21, 21)  # its red part, scaled
    assert gallery.Point(10, 110) == vpRed
    gallery.PaintPicture(png(tmp_path / "b.png", 0x0000FF), 100, 100, 10, 10)  # a file
    assert gallery.Point(105, 105) == vpBlue
    gallery.PaintPicture(LoadPicture(), 0, 0)  # (empty: nothing)
    assert gallery.Image.Point(105, 105) == vpBlue  # a form's Image too


def test_a_forms_background_picture(qapp, tmp_path):
    png(tmp_path / "back.png", 0x0000FF, (60, 40))

    class Backdrop(Form):
        def InitializeComponent(self):
            self.BackColor = vpWhite
            self.Picture = "back.png"  # (relative to the form's folder)

        def _base_dir(self):
            return str(tmp_path)

    form = Backdrop()
    form.Show()
    QTest.qWait(10)
    assert form.Point(30, 20) == vpBlue and form.Point(70, 20) == vpWhite  # top left
    form.AutoRedraw = True
    form.Line(0, 0, 10, 10, vpRed, "BF")  # the drawing over it
    assert form.Point(5, 5) == vpRed and form.Point(30, 20) == vpBlue
    form.Picture = Picture(20, 20, BackColor=vpGreen)
    assert form.Point(15, 15) == vpGreen and form.Point(30, 20) == vpWhite
    form.Picture = ""
    assert form.Point(15, 15) == vpWhite
    assert "Picture" in Form._specs
    body = "def InitializeComponent(self):\n    self.Picture = 'back.png'\n"
    assert "self.Picture = 'back.png'" in \
        formfile.generate_region(formfile.parse_region_body(body, "Form1"))
    form.Unload()


def test_the_clipboard(qapp, tmp_path):
    Clipboard.Clear()
    assert not Clipboard.GetFormat(vpCFBitmap) and Clipboard.GetData() is None
    Clipboard.SetData(Picture(12, 8, BackColor=vpRed))
    assert Clipboard.GetFormat(vpCFBitmap) and Clipboard.GetFormat(vpCFDIB)
    picture = Clipboard.GetData()
    assert (picture.Width, picture.Height) == (12, 8) and picture.Point(1, 1) == vpRed
    assert Clipboard.GetData(vpCFText) is None
    Clipboard.SetData(png(tmp_path / "p.png", 0x00FF00))  # a file's picture
    assert Clipboard.GetData(vpCFDIB).Point(1, 1) == vpGreen
    Clipboard.SetText("words")
    assert Clipboard.GetFormat(vpCFText) and not Clipboard.GetFormat(vpCFBitmap)
    Clipboard.SetText(r"{\rtf1 bold}", vpCFRTF)  # rich text
    assert Clipboard.GetFormat(vpCFRTF) and Clipboard.GetText(vpCFRTF) == r"{\rtf1 bold}"
    mime = QMimeData()  # files, from another program
    from PySide6.QtCore import QUrl

    mime.setUrls([QUrl.fromLocalFile("/tmp/a.txt")])
    QGuiApplication.clipboard().setMimeData(mime)
    assert Clipboard.GetFormat(vpCFFiles) and Clipboard.GetData(vpCFFiles) == ["/tmp/a.txt"]
    assert Clipboard.GetText(vpCFRTF) == ""
    Clipboard.Clear()


def test_a_dropped_picture(qapp):
    mime = QMimeData()
    image = QImage(6, 4, QImage.Format_RGB32)
    image.fill(0xFF0000)
    mime.setImageData(image)
    data = DataObject(mime)
    assert data.GetFormat(vpCFBitmap) and data.GetFormat(vpCFDIB)
    assert data.GetData(vpCFBitmap).Point(1, 1) == vpRed
    assert DataObject(QMimeData()).GetData(vpCFBitmap) is None


def test_exported():
    for name in ("Picture", "LoadPicture", "SavePicture", "vpCFBitmap", "vpPicTypeBitmap"):
        assert name in vp6.__all__
