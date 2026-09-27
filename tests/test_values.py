"""ProgressBar, Slider and UpDown: controls with a Value between Min and Max."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QSlider

from vp6 import (Form, Label, ProgressBar, Slider, TextBox, UpDown, formfile,
                 vpOrientationHorizontal, vpOrientationVertical, vpTickBoth, vpTickBottomRight,
                 vpTickNone, vpTickTopLeft)
from vp6.controls import CONTROL_TYPES
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Values(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 400, 300
        self.prg = ProgressBar(self, Left=8, Top=8, Value=40)
        self.sld = Slider(self, Left=8, Top=40, Max=20, Value=5)
        self.txt = TextBox(self, Left=8, Top=100, Width=48, Height=25, Text="3")
        self.ud = UpDown(self, Left=56, Top=100, Height=25, Min=1, Max=5, Value=3,
                         BuddyControl="txt", SyncBuddy=True)
        self.lbl = Label(self, Left=8, Top=140, Caption="1")
        self.udDay = UpDown(self, Left=40, Top=140, Width=40, Height=25, Min=1, Max=7, Value=1,
                            Wrap=True, Orientation=vpOrientationHorizontal,
                            BuddyControl="lbl", SyncBuddy=True)
        self.events = []

    def sld_Scroll(self):
        self.events.append(("Scroll", self.sld.Value))

    def sld_Change(self):
        self.events.append(("Change", self.sld.Value))

    def ud_Change(self):
        self.events.append(("udChange", self.ud.Value))

    def ud_UpClick(self):
        self.events.append("UpClick")

    def ud_DownClick(self):
        self.events.append("DownClick")

    def prg_Click(self):
        self.events.append("prgClick")


@pytest.fixture
def form(qapp):
    f = Values()
    f.Show()
    yield f
    f.Unload()


def test_progressbar(form):
    prg = form.prg
    assert (prg.Min, prg.Max, prg.Value) == (0, 100, 40)
    assert not prg._widget.isTextVisible() and prg._widget.focusPolicy() == Qt.NoFocus
    prg.Value = 250  # kept at the nearer end
    assert prg.Value == 100
    prg.Value = -5
    assert prg.Value == 0
    prg.Value = 80
    prg.Max = 50  # a smaller Max keeps Value inside
    assert prg.Value == 50 and prg._widget.value() == 50
    prg.Min = 60
    assert prg.Value == 60
    prg.Orientation = vpOrientationVertical
    assert prg._widget.orientation() == Qt.Vertical
    QTest.mouseClick(prg._widget, Qt.LeftButton)  # Click, from the mouse
    assert "prgClick" in form.events


def test_slider_scroll_while_dragging_change_after(form):
    sld, widget = form.sld, form.sld._widget
    sld.Value = 8  # code: Change
    assert form.events == [("Change", 8)]
    form.events.clear()
    widget.setSliderDown(True)  # the user drags the thumb
    widget.setValue(9)
    widget.setValue(10)
    assert form.events == [("Scroll", 9), ("Scroll", 10)]
    widget.setSliderDown(False)  # and lets go: one Change
    assert form.events[-1] == ("Change", 10) and len(form.events) == 3
    form.events.clear()
    widget.setFocus()
    QTest.keyClick(widget, Qt.Key_Right)  # a key: Change at once
    assert form.events == [("Change", 11)]
    QTest.keyClick(widget, Qt.Key_PageUp)  # LargeChange
    assert sld.Value == 16


def test_slider_properties(form):
    sld, widget = form.sld, form.sld._widget
    assert (sld.SmallChange, sld.LargeChange, sld.TickFrequency) == (1, 5, 1)
    for style, position in ((vpTickBottomRight, QSlider.TicksBelow),
                            (vpTickTopLeft, QSlider.TicksAbove),
                            (vpTickBoth, QSlider.TicksBothSides), (vpTickNone, QSlider.NoTicks)):
        sld.TickStyle = style
        assert widget.tickPosition() == position
    sld.TickFrequency = 4
    sld.Orientation = vpOrientationVertical
    assert widget.tickInterval() == 4 and widget.orientation() == Qt.Vertical
    sld.Value = 99
    assert sld.Value == 20  # Max


def test_updown_steps_and_its_buddy(form):
    ud, up, down = form.ud, form.ud._widget.up, form.ud._widget.down
    assert up.focusPolicy() == Qt.NoFocus  # the buddy keeps the focus
    up.click()
    assert ud.Value == 4 and form.txt.Text == "4"  # the buddy shows it
    assert form.events == [("udChange", 4), "UpClick"]
    up.click()
    up.click()  # stops at Max (no Wrap): UpClick, but no Change
    assert ud.Value == 5 and form.events[-3:] == [("udChange", 5), "UpClick", "UpClick"]
    form.txt.Text = "2"  # typed into the buddy: the next click starts there
    down.click()
    assert ud.Value == 1 and form.txt.Text == "1" and form.events[-1] == "DownClick"
    form.txt.Text = "99"
    up.click()  # a typed number over Max: kept at Max, and shown
    assert ud.Value == 5 and form.txt.Text == "5"
    form.txt.Text = "many"
    down.click()  # not a number: from the Value
    assert ud.Value == 4 and form.txt.Text == "4"
    ud.Value = 2  # code: Change, and the buddy follows
    assert form.events[-1] == ("udChange", 2) and form.txt.Text == "2"
    ud.Increment = 2
    up.click()
    assert ud.Value == 4
    assert ud.Buddy is form.txt


def test_updown_wraps_and_label_buddy(form):
    ud = form.udDay
    assert ud._widget.up.arrowType() == Qt.RightArrow  # horizontal: left and right
    ud._widget.down.click()  # below Min: from Max
    assert ud.Value == 7 and form.lbl.Caption == "7"  # a Label buddy: its Caption
    ud._widget.up.click()
    assert ud.Value == 1 and form.lbl.Caption == "1"
    ud.Orientation = vpOrientationVertical
    assert ud._widget.up.arrowType() == Qt.UpArrow
    ud.BuddyProperty = "Tag"
    ud._widget.up.click()
    assert form.lbl.Tag == "2" and form.lbl.Caption == "1"
    ud.BuddyControl = "nothing"  # no such control: no buddy
    assert ud.Buddy is None
    ud._widget.up.click()
    assert ud.Value == 3
    ud.SyncBuddy = False
    ud.BuddyControl = "lbl"
    ud._widget.up.click()
    assert form.lbl.Tag == "2"  # not synchronized


def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.ud = UpDown(self, Left=8, Top=8, Width=17, Height=33, Max=99, "
            "BuddyControl='txt', SyncBuddy=True)\n"
            "    self.sld = Slider(self, Left=8, Top=50, Width=161, Height=41, TickStyle=2)\n"
            "    self.prg = ProgressBar(self, Left=8, Top=100, Width=161, Height=25, Value=30)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("ud").props["BuddyControl"] == "txt"
    region = formfile.generate_region(form)
    assert "BuddyControl='txt'" in region and "TickStyle=2" in region and "Value=30" in region


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    names = [d.create_control(kind, QRect(origin + QPoint(16, 16 + 60 * i),
                                          origin + QPoint(180, 50 + 60 * i)), None)
             for i, kind in enumerate(("ProgressBar", "Slider", "UpDown"))]
    assert names == ["ProgressBar1", "Slider1", "UpDown1"]
    updown = d.controls["UpDown1"]
    updown._widget.up.click()  # arrows do nothing while designing
    assert updown.Value == 0
    d.select(["Slider1"])
    assert d.set_property("TickStyle", vpTickBoth) is None
    assert "TickStyle=2" in d.document.text
    d.close()


def test_toolbox_icons_and_constants(qapp):
    for name, default_event in (("ProgressBar", "Click"), ("Slider", "Scroll"),
                                ("UpDown", "Change")):
        assert name in Toolbox().buttons and name in CONTROL_TYPES
        assert CONTROL_TYPES[name].DefaultEvent == default_event
        assert not icons.icon(name).isNull()
    assert (vpOrientationHorizontal, vpOrientationVertical) == (0, 1)
    assert (vpTickBottomRight, vpTickTopLeft, vpTickBoth, vpTickNone) == (0, 1, 2, 3)
