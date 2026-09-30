"""Forms as in VB: default form instances (Form2.Show()), Form_QueryUnload with its
UnloadMode, and a form's own Icon."""

import os

import pytest
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest

from vp6 import (Form, Forms, PictureBox, TextBox, Unload, run, vpAppTaskManager, vpFormCode,
                 vpFormControlMenu, vpFormOwner)
from vp6.app import close_all_windows

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

LIMIT = 10


def make_class():
    """A fresh form class for each test (its default instance is the class's)."""
    class Form2(Form):
        LIMIT = LIMIT  # a class constant

        def InitializeComponent(self):
            self.events = []
            self.txtName = TextBox(self, Text="hi")

        def Form_Load(self):
            self.Total = 5

        def Form_QueryUnload(self, UnloadMode):
            self.events.append(("QueryUnload", UnloadMode))
            return self.txtName.Text == "keep"  # True: stays open

        def Form_Unload(self):
            self.events.append(("Unload",))

        def Hello(self):
            return self

    return Form2


@pytest.fixture
def Form2(qapp):
    cls = make_class()
    yield cls
    default = cls.__dict__.get("_vp_default")
    if default is not None and default._loaded:
        default.txtName.Text = ""
        default.Unload()


def test_default_instance(Form2):
    assert "_vp_default" not in Form2.__dict__  # made the first time it is used
    default = Form2.Hello()  # a method: the default instance's
    assert isinstance(default, Form2) and Form2._vp_default is default
    assert Form2.txtName is default.txtName and Form2.txtName.Text == "hi"  # its controls
    assert Form2.Caption == "Form2"  # its properties
    Form2.Caption = "Options"
    assert default.Caption == "Options" and "Caption" not in Form2.__dict__  # (not the class)
    Form2.Show()  # VB's Form2.Show
    assert default.Visible and default in list(Forms) and Form2.Total == 5
    Form2.Total = 9  # its variables
    assert default.Total == 9
    other = Form2()  # an instance of its own: not the default one
    assert other is not default and other.txtName is not default.txtName
    other._widget.close()
    assert Form2.LIMIT == 10 and Form2.Properties[0].name == "Caption"  # (the class's)
    Form2.LIMIT = 11
    assert "LIMIT" in Form2.__dict__  # (a class attribute stays one)
    assert Form2.Run.__self__ is Form2  # (classmethods are the class's)
    assert Form.Show is Form.__dict__["Show"]  # (Form itself has no default instance)
    Unload(Form2)  # Unload, then Show again: the same instance, loaded again
    assert not default.Visible and not default._loaded
    Form2.Show()
    assert Form2._vp_default is default and default._loaded


def test_run_makes_the_running_form_the_default(Form2, monkeypatch):
    monkeypatch.setattr("vp6.form.run_event_loop", lambda: 0)
    assert run(Form2) == 0
    assert Form2._vp_default.Visible  # run(Form2) showed the default instance


def test_query_unload(Form2):
    form = Form2.Hello()
    form.Show()
    form.txtName.Text = "keep"
    assert form.Unload() is False and form.Visible  # cancelled by Form_QueryUnload
    assert form.events == [("QueryUnload", vpFormCode)]  # (Form_Unload not even asked)
    form._widget.close()  # the user: its close button
    assert form.events[-1] == ("QueryUnload", vpFormControlMenu) and form.Visible
    form.txtName.Text = ""
    form.events.clear()
    form._widget.close()
    assert form.events == [("QueryUnload", vpFormControlMenu), ("Unload",)]
    assert not form.Visible
    form.Show()
    form.events.clear()
    close_all_windows()  # Ctrl+C in the program's terminal
    assert ("QueryUnload", vpAppTaskManager) in form.events
    form.Show()
    form.events.clear()
    form.Unload()  # in code, not shown: still asked
    assert form.events == [("QueryUnload", vpFormCode), ("Unload",)]


def test_query_unload_of_a_form_shown_in_another(qapp):
    Inner = make_class()

    class Host(Form):
        def InitializeComponent(self):
            self.pic = PictureBox(self, Width=200, Height=100)

    host = Host()
    host.Show()
    inner = Inner.Hello()
    inner.ShowIn(host.pic)
    inner.txtName.Text = "keep"  # (it can't keep its host open)
    host.Unload()
    assert ("QueryUnload", vpFormOwner) in inner.events and not inner._loaded


def test_icon(qapp, tmp_path, monkeypatch):
    picture = tmp_path / "icon.png"
    image = QImage(32, 32, QImage.Format_ARGB32)
    image.fill(0xFFFF0000)
    image.save(str(picture))
    form = Form()
    monkeypatch.setattr(form, "_base_dir", lambda: str(tmp_path))
    assert form.Icon == ""
    form.Icon = "icon.png"  # relative to the form's folder
    assert not form._widget.windowIcon().isNull()
    assert form._widget.windowIcon().pixmap(32).toImage().pixelColor(5, 5).red() == 255
    form.Icon = str(picture)  # or a full path
    assert not form._widget.windowIcon().isNull()
    form.Icon = "missing.png"  # can't be read: the program's icon
    assert form._widget.windowIcon().cacheKey() == qapp.windowIcon().cacheKey()
    form.Icon = ""
    assert form._widget.windowIcon().cacheKey() == qapp.windowIcon().cacheKey()
    form._widget.close()
    QTest.qWait(1)
