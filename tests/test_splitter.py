"""The Splitter control, and the PictureBox Resize event it relies on."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from vp6 import (Form, Label, PictureBox, Splitter, formfile, vpAlignBottom, vpAlignLeft,
                 vpAlignRight, vpAlignTop)
from vp6.controls import CONTROL_TYPES
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Explorer(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 500, 300
        self.picNav = PictureBox(self, Align=vpAlignLeft, Width=150)
        self.splNav = Splitter(self, Align=vpAlignLeft, MinSize=50)
        self.picLog = PictureBox(self, Align=vpAlignBottom, Height=60)
        self.splLog = Splitter(self, Align=vpAlignBottom, Height=5)
        self.lblMain = Label(self, Caption="main", Left=200, Top=10)

    def Form_Load(self):
        self.events = []

    def splNav_Moved(self):
        self.events.append(("moved", self.picNav.Width))

    def picNav_Resize(self):
        # every docked control is in place when a pane's Resize runs
        self.events.append(("resize", self.picNav.Width, self.splNav.Left))


@pytest.fixture
def explorer(qapp):
    form = Explorer()
    form.Show()
    yield form
    form.Unload()


def _place(control):
    return control.Left, control.Top, control.Width, control.Height


def _drag(splitter, dx, dy):
    """Drag the bar in one move (it moves along while dragged)."""
    bar = splitter._widget
    start = QPoint(2, 2)
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(bar, start + QPoint(dx, dy))
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, start)


def test_splitters_dock_beside_their_panes(explorer):
    assert _place(explorer.picNav) == (0, 0, 150, 300)
    assert _place(explorer.splNav) == (150, 0, 6, 300)
    assert _place(explorer.picLog) == (156, 240, 344, 60)
    assert _place(explorer.splLog) == (156, 235, 344, 5)
    assert explorer.splNav._widget.cursor().shape() == Qt.SplitHCursor
    assert explorer.splLog._widget.cursor().shape() == Qt.SplitVCursor


def test_dragging_resizes_the_pane(explorer):
    explorer.events.clear()
    _drag(explorer.splNav, 40, 0)
    assert explorer.picNav.Width == 190 and explorer.splNav.Left == 190
    assert explorer.events == [("resize", 190, 190), ("moved", 190)]  # Resize sees the bar moved
    _drag(explorer.splLog, 0, -20)  # a Bottom pane grows upwards
    assert explorer.picLog.Height == 80 and explorer.splLog.Top == 300 - 80 - 5


def test_minimum_sizes(explorer):
    _drag(explorer.splNav, -500, 0)
    assert explorer.picNav.Width == 50  # MinSize
    _drag(explorer.splNav, 1000, 0)
    free = explorer._free_area
    assert free[2] - free[0] == 50  # MinSize left beside it too
    explorer.splNav.Enabled = False
    width = explorer.picNav.Width
    _drag(explorer.splNav, -100, 0)
    assert explorer.picNav.Width == width  # a disabled splitter doesn't move
    assert Splitter.Events == ("Moved",) and Splitter.DefaultEvent == "Moved"


def test_right_and_top_splitters_and_no_pane(qapp):
    class Other(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 400, 300
            self.spl0 = Splitter(self, Align=vpAlignTop)  # nothing docked before it
            self.picTop = PictureBox(self, Align=vpAlignTop, Height=50)
            self.splTop = Splitter(self, Align=vpAlignTop, Height=6)
            self.picSide = PictureBox(self, Align=vpAlignRight, Width=100)
            self.splSide = Splitter(self, Align=vpAlignRight)

    form = Other()
    form.Show()
    _drag(form.spl0, 0, 30)
    assert form.picTop.Height == 50  # no pane: nothing happens
    _drag(form.splTop, 0, 30)
    assert form.picTop.Height == 80
    _drag(form.splSide, -25, 0)  # a Right pane grows to the left
    assert form.picSide.Width == 125 and form.picSide.Left == 400 - 125
    form.Unload()


def test_picturebox_resize_event(qapp):
    class Plain(Form):
        def InitializeComponent(self):
            self.picBox = PictureBox(self, Left=0, Top=0, Width=100, Height=80)

        def Form_Load(self):
            self.sizes = []

        def picBox_Resize(self):
            self.sizes.append((self.picBox.Width, self.picBox.Height))

    form = Plain()
    form.Show()
    form.sizes.clear()
    form.picBox.Width = 140
    assert form.sizes == [(140, 80)]
    assert "Resize" in PictureBox.Events
    form.Unload()


def test_file_designer_and_toolbox(qapp, tmp_path):
    body = ("def InitializeComponent(self):\n"
            "    self.picA = PictureBox(self, Left=0, Top=0, Width=120, Height=360, Align=3)\n"
            "    self.splA = Splitter(self, Left=120, Top=0, Width=6, Height=360, MinSize=40)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert "self.splA = Splitter(self, Left=120, Top=0, Width=6, Height=360, MinSize=40)" in \
        formfile.generate_region(form)  # Align=3 (Left) is the default
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))  # 480 x 360
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(900, 700)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    pane = d.create_control("PictureBox", QRect(origin + QPoint(16, 16), origin + QPoint(96, 96)),
                            None)
    d.select([pane])
    d.set_property("Align", vpAlignLeft)
    bar = d.create_control("Splitter", QRect(origin + QPoint(200, 16), origin + QPoint(206, 96)),
                           None)
    props = d.form_def.control(bar).props
    assert bar == "Splitter1" and (props["Left"], props["Top"], props["Height"]) == (80, 0, 360)
    assert d.controls[bar]._widget.cursor().shape() == Qt.SplitHCursor
    d.close()
    assert "Splitter" in Toolbox().buttons and "Splitter" in CONTROL_TYPES
    assert not icons.icon("Splitter").isNull()
