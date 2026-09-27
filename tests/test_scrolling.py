"""PictureBox ScrollBars: a container that scrolls its contents."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from conftest import wait_for

from vp6 import (CommandButton, Form, Label, PictureBox, formfile, vpBoth, vpHorizontal,
                 vpSBNone, vpVertical)
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Pane(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 400, 300
        self.picPane = PictureBox(self, Left=10, Top=10, Width=200, Height=150, ScrollBars=3,
                                  BorderStyle=0)
        self.lblFar = Label(self.picPane, Caption="far", Left=10, Top=400, Width=80, Height=20)
        self.cmdWide = CommandButton(self.picPane, Caption="wide", Left=300, Top=10,
                                     Width=60, Height=30)

    def Form_Load(self):
        self.events = []

    def picPane_Scroll(self):
        self.events.append(("scroll", self.picPane.ScrollLeft, self.picPane.ScrollTop))

    def picPane_Click(self):
        self.events.append("click")

    def cmdWide_Click(self):
        self.events.append("wide")


@pytest.fixture
def pane(qapp):
    form = Pane()
    form.Show()
    QTest.qWait(20)
    yield form
    form.Unload()


def _bars(picture):
    area = picture._scroll_area
    return area.horizontalScrollBar(), area.verticalScrollBar()


def test_bars_appear_when_controls_reach_beyond_the_edges(pane):
    horizontal, vertical = _bars(pane.picPane)
    assert horizontal.isVisible() and vertical.isVisible()
    view = pane.picPane._scroll_area.viewport().size()
    assert vertical.maximum() == 420 - view.height()  # lblFar ends at 420
    assert horizontal.maximum() == 360 - view.width()  # cmdWide ends at 360
    assert pane.lblFar.Parent is pane.picPane and pane.lblFar.Top == 400  # positions as set


def test_scroll_position_and_event(pane):
    pane.picPane.ScrollTop = 100
    pane.picPane.ScrollLeft = 50
    assert (pane.picPane.ScrollLeft, pane.picPane.ScrollTop) == (50, 100)
    assert pane.events == [("scroll", 0, 100), ("scroll", 50, 100)]
    offset = pane.lblFar._widget.mapTo(pane.picPane._widget, QPoint(0, 0))
    assert offset == QPoint(10 - 50, 400 - 100)  # the contents moved


def test_bars_follow_the_contents(pane):
    pane.lblFar.Top = 20
    pane.cmdWide.Left = 20
    horizontal, vertical = _bars(pane.picPane)
    # The scroll area hides its bars a pass or two of the event loop later
    wait_for(lambda: not horizontal.isVisible() and not vertical.isVisible(), 1000)
    late = Label(pane.picPane, Caption="added", Left=0, Top=600, Width=50, Height=20)
    pane.picPane.ScrollTop = 10_000  # counts controls added just now
    assert pane.picPane.ScrollTop == 620 - pane.picPane._scroll_area.viewport().height()
    late._widget.hide()
    wait_for(lambda: not vertical.isVisible(), 1000)  # hidden controls don't count


def test_only_the_chosen_directions(pane):
    assert (vpSBNone, vpHorizontal, vpVertical, vpBoth) == (0, 1, 2, 3)
    pane.picPane.ScrollBars = vpVertical
    horizontal, vertical = _bars(pane.picPane)
    wait_for(lambda: not horizontal.isVisible() and vertical.isVisible(), 1000)
    pane.picPane.ScrollBars = 0  # off: the controls go back on the PictureBox itself
    assert pane.picPane._scroll_area is None
    assert pane.lblFar._widget.parentWidget() is pane.picPane._widget
    assert (pane.picPane.ScrollLeft, pane.picPane.ScrollTop) == (0, 0)


def test_controls_and_clicks_still_work(pane):
    pane.cmdWide._widget.click()
    viewport = pane.picPane._scroll_area.viewport()
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(150, 100))  # empty space
    assert pane.events == ["wide", "click"]


def test_a_taller_form_inside_scrolls(qapp):
    class Host(Form):
        def InitializeComponent(self):
            self.picPane = PictureBox(self, Left=0, Top=0, Width=200, Height=150, ScrollBars=2,
                                      BorderStyle=0)

    class Tall(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 100, 500

    host, tall = Host(), Tall()
    host.Show()
    tall.ShowIn(host.picPane)
    QTest.qWait(30)
    view = host.picPane._scroll_area.viewport()
    assert tall.ScaleWidth == view.width()  # fills the width
    assert tall.ScaleHeight == 500  # keeps its height, so the pane scrolls
    assert host.picPane._scroll_area.verticalScrollBar().maximum() == 500 - view.height()
    host.Unload()


def test_designer_shows_controls_in_place(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("PictureBox", QRect(origin + QPoint(16, 16), origin + QPoint(200, 150)),
                            None)
    d.select([name])
    assert d.set_property("ScrollBars", 3) is None
    assert "ScrollBars=3" in d.document.text
    assert d.controls[name]._scroll_area is None  # the designer doesn't scroll
    d.close()
