"""Showing a form inside a container of another form (Form.ShowIn)."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from vp6 import CommandButton, Form, Frame, Label, PictureBox, vpFixedSingle

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Host(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 500, 400
        self.picPane = PictureBox(self, Left=10, Top=10, Width=200, Height=150, BorderStyle=0)
        self.fraPane = Frame(self, Caption="Frame", Left=220, Top=10, Width=200, Height=150)
        self.lblHost = Label(self, Caption="host", Left=10, Top=300)

    def Form_Load(self):
        self.events = []

    def Form_Unload(self):
        self.events.append("host unload")


class Page(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 120, 90
        self.cmdGo = CommandButton(self, Caption="Go", Left=4, Top=4, Width=60, Height=30,
                                   Default=True)

    def Form_Load(self):
        self.events = ["load"]

    def Form_Resize(self):
        self.events.append(("resize", self.ScaleWidth, self.ScaleHeight))

    def Form_Unload(self):
        self.events.append("unload")
        return getattr(self, "refuse", False)

    def cmdGo_Click(self):
        self.events.append("go")


@pytest.fixture
def host(qapp):
    form = Host()
    form.Show()
    yield form
    form.Unload()


def test_fills_the_container_and_follows_its_size(host):
    page = Page()
    page.ShowIn(host.picPane)
    assert page.Container is host.picPane and page.Visible
    assert not page._widget.isWindow() and page._widget.parentWidget() is host.picPane._widget
    assert page.events == ["load", ("resize", 200, 150)]  # Load first, then the size
    host.picPane.Width, host.picPane.Height = 260, 180
    assert page.events[-1] == ("resize", 260, 180) and page.ScaleWidth == 260
    page.cmdGo._widget.click()  # its controls work as usual
    assert page.events[-1] == "go"
    page.BorderStyle = vpFixedSingle  # window-only properties don't pop it out
    page.Caption = "Page"
    assert not page._widget.isWindow()


def test_frame_form_and_fixed_position(host):
    page = Page()
    page.ShowIn(host.fraPane)  # inside a Frame: below its caption
    assert page._widget.geometry() == host.fraPane._widget.contentsRect()
    other = Page()
    other.Left, other.Top = 30, 200
    other.ShowIn(host, Fill=False)  # in the form itself, keeping its size and place
    assert other.Container is host
    assert (other._widget.x(), other._widget.y(), other.ScaleWidth) == (30, 200, 120)


def test_popping_out_and_moving(host):
    page = Page()
    page.ShowIn(host.picPane)
    page.ShowIn(None)  # a window of its own
    assert page.Container is None and page._widget.isWindow() and page.Visible
    page.ShowIn(host.fraPane)
    assert page._widget.parentWidget() is host.fraPane._widget
    page.ShowIn(host.picPane)  # from one container to another
    assert page._widget.parentWidget() is host.picPane._widget and page in host._embedded
    assert page.events.count("load") == 1
    page.Hide()
    assert not page.Visible
    page.Show()  # still in its container
    assert page.Visible and page.Container is host.picPane


def test_unloading(host):
    page, other = Page(), Page()
    page.ShowIn(host.picPane)
    other.ShowIn(host.fraPane)
    page.Unload()  # only itself
    assert page.events[-1] == "unload" and not page._loaded and other._loaded
    page.ShowIn(host.picPane)  # load it again (Form_Load starts a new events list)
    assert page._loaded and page.events[0] == "load" and "unload" not in page.events
    page.refuse = True  # its Form_Unload would cancel...
    assert host.Unload() is True  # ...but it goes with its host
    assert host.events == ["host unload"]
    assert page.events[-1] == "unload" and not page._loaded and not other._loaded
    assert page.Container is None  # a window again (hidden), so it outlives the host


def test_a_host_that_cancels_keeps_its_forms(host):
    page = Page()
    page.ShowIn(host.picPane)
    host.Form_Unload = lambda: True  # like answering No to "Close?"
    assert host.Unload() is False
    assert page._loaded and page.Visible
    del host.Form_Unload


def test_invalid_containers(host):
    page = Page()
    with pytest.raises(TypeError, match="container"):
        page.ShowIn(host.lblHost)  # a Label can't hold anything
    with pytest.raises(ValueError, match="inside itself"):
        page.ShowIn(page)
    page.ShowIn(host.picPane)
    with pytest.raises(ValueError, match="inside itself"):
        host.ShowIn(page)  # host holds page: page can't hold host


def test_nested_and_keys(host):
    outer, inner = Page(), Page()
    outer.ShowIn(host.picPane)
    inner.ShowIn(outer)
    assert inner._widget.parentWidget() is outer._widget
    QTest.keyClick(inner.cmdGo._widget, Qt.Key_Return)  # its Default button
    assert inner.events[-1] == "go" and "go" not in outer.events
    host.Unload()
    assert not inner._loaded and not outer._loaded
