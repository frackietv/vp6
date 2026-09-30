"""The Image control: a lightweight picture."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from vp6 import CommandButton, Form, Image, formfile
from vp6.controls import CONTROL_TYPES
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.kitchensink import draw_picture
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


@pytest.fixture
def picture(qapp, tmp_path) -> str:
    path = str(tmp_path / "picture.png")
    draw_picture(path)  # 320 x 240
    return path


def _form(picture, **props):
    class Gallery(Form):
        def InitializeComponent(self):
            self.cmdFirst = CommandButton(self, Left=300, Top=300)
            self.imgPhoto = Image(self, Picture=picture, Left=8, Top=8, **props)

        def Form_Load(self):
            self.events = []

        def imgPhoto_Click(self):
            self.events.append("click")

        def imgPhoto_MouseDown(self, Button, Shift, X, Y):
            self.events.append(("down", Button, X, Y))

    form = Gallery()
    form.Show()
    return form


def test_without_stretch_it_takes_the_pictures_size(picture):
    form = _form(picture)
    image = form.imgPhoto
    assert (image.Width, image.Height) == (320, 240)
    image.BorderStyle = 1  # the border goes around the picture
    assert (image.Width, image.Height) == (322, 242)
    form.Unload()


def test_with_stretch_the_picture_fills_the_control(picture):
    form = _form(picture, Stretch=True, Width=64, Height=48)
    image = form.imgPhoto
    assert (image.Width, image.Height) == (64, 48) and image._widget.hasScaledContents()
    image.Width = 100  # resizing keeps the picture scaled to fit
    assert image.Width == 100
    image.Stretch = False  # back to the picture's size
    assert (image.Width, image.Height) == (320, 240)
    image.Picture = ""
    assert image._widget.pixmap().isNull()
    form.Unload()


def test_events_focus_and_enabled(picture):
    form = _form(picture)
    widget = form.imgPhoto._widget
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, QPoint(10, 20))
    assert form.events == [("down", 1, 10, 20), "click"]
    assert widget.focusPolicy() == Qt.NoFocus  # never focused, no Tab stop
    assert "TabIndex" not in Image._specs and not Image.IsContainer
    form.imgPhoto.Enabled = False
    assert widget.isEnabled()  # not grayed like a disabled PictureBox...
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, QPoint(10, 20))
    assert len(form.events) == 2  # ...but it gets no events
    assert not widget.autoFillBackground()  # transparent: the form shows around a picture
    form.Unload()


def test_properties_and_file(picture):
    assert list(Image._specs) == ["Left", "Top", "Width", "Height", "Stretch", "BorderStyle",
                                  "Picture", "Enabled", "Visible", "ToolTipText", "Tag",
                                  "ZIndex", "MousePointer", "MouseIcon", "DragMode",
                                  "DragIcon", "OLEDropMode"]
    body = ("def InitializeComponent(self):\n"
            "    self.imgA = Image(self, Left=8, Top=8, Width=64, Height=48, Stretch=True, "
            "Picture='a.png')\n")
    form = formfile.parse_region_body(body, "Form1")
    assert "self.imgA = Image(self, Left=8, Top=8, Width=64, Height=48, Stretch=True, " \
           "Picture='a.png')" in formfile.generate_region(form)


def test_in_the_designer(qapp, tmp_path, picture):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("Image", QRect(origin + QPoint(16, 16), origin + QPoint(80, 64)),
                            None)
    assert name == "Image1"
    d.select([name])
    assert d.set_property("Picture", picture) is None
    props = d.form_def.control(name).props
    assert (props["Width"], props["Height"]) == (320, 240)  # sized to the picture
    assert d.set_property("Stretch", True) is None
    d.controls[name]._widget.resize(64, 48)
    d.commit_geometry([name])
    assert (props["Width"], props["Height"]) == (64, 48)
    window = PropertiesWindow()
    window.set_designer(d)
    rows = [window.table.item(r, 0).text() for r in range(window.table.rowCount())]
    assert "Stretch" in rows and "TabIndex" not in rows and "BackColor" not in rows
    d.close()


def test_toolbox_and_icon(qapp):
    assert "Image" in Toolbox().buttons and "Image" in CONTROL_TYPES
    assert not icons.icon("Image").isNull()
