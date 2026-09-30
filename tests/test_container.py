"""Moving a control to another container at run time (VB's
Set Command1.Container = Frame1)."""

import os

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest

from vp6 import (CommandButton, DockPanel, Form, Frame, Label, Menu, OptionButton, PictureBox,
                 TextBox)

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Boxes(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 600, 400
        self.clicks = []
        self.fra1 = Frame(self, Caption="One", Left=10, Top=10, Width=200, Height=120)
        self.fra2 = Frame(self, Caption="Two", Left=220, Top=10, Width=200, Height=120)
        self.opt1 = OptionButton(self.fra1, Left=10, Top=20, Value=True)
        self.opt2 = OptionButton(self.fra1, Left=10, Top=50)
        self.opt3 = OptionButton(self.fra2, Left=10, Top=20, Value=True)
        self.pic = PictureBox(self, Left=10, Top=150, Width=200, Height=120)
        self.lblInner = Label(self.fra2, Caption="inner", Left=10, Top=80, Width=60, Height=20)
        self.cmd = CommandButton(self, Left=300, Top=300, Width=80, Height=30, TabIndex=1)
        self.txt = TextBox(self, Left=400, Top=300, TabIndex=2)
        self.dck = DockPanel(self, Caption="Dock", Align=4, Width=120)
        self.mnu = Menu(self, Caption="M")

    def cmd_Click(self):
        self.clicks.append("cmd")


@pytest.fixture
def form(qapp):
    form = Boxes()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def at(control) -> QPoint:
    """Where a control is in the form."""
    return control._widget.mapTo(control._form._widget, QPoint(0, 0))


def test_moving_keeps_left_and_top_in_the_new_container(form):
    form.cmd.Container = form.fra1
    assert form.cmd.Container is form.fra1 and form.cmd.Parent is form.fra1
    assert (form.cmd.Left, form.cmd.Top) == (300, 300)  # (now in the frame: clipped there)
    form.cmd.Move(20, 80)
    assert form.cmd._widget.parent() is form.fra1._container_widget()
    assert at(form.cmd).x() > at(form.fra1).x() and form.cmd._widget.isVisible()
    form.cmd._widget.click()  # its events still come here
    assert form.clicks == ["cmd"]
    form.cmd.Container = form.pic  # a PictureBox
    assert form.cmd._widget.parent() is form.pic._container_widget()
    form.cmd.Container = form.dck  # a DockPanel
    assert form.cmd._widget.parent() is form.dck._container_widget()
    form.cmd.Container = form  # and back to the form
    assert form.cmd.Parent is form and form.cmd._widget.parent() is form._container_widget()
    form.cmd.Container = form  # (where it is: nothing to do)


def test_hidden_stays_hidden_and_z_order(form):
    form.txt.Visible = False
    form.txt.Container = form.fra1
    assert not form.txt._widget.isVisible() and not form.txt.Visible
    form.txt.Visible = True
    assert form.txt._widget.isVisible()
    form.cmd.ZIndex = -1  # below the frame's other controls once it is there
    form.cmd.Container = form.fra2
    form.cmd.Move(5, 75)
    siblings = form.fra2._container_widget().children()
    assert siblings.index(form.cmd._widget) < siblings.index(form.lblInner._widget)


def test_option_buttons_join_the_new_containers_group(form):
    form.opt2.Container = form.fra2
    form.opt2.Value = True
    assert form.opt2.Value and not form.opt3.Value  # the Two group now
    assert form.opt1.Value  # (the One group kept its choice)


def test_containers_move_with_their_controls(form):
    form.fra2.Container = form.pic
    assert form.lblInner.Parent is form.fra2  # (still in its frame, which moved)
    assert form.lblInner._widget.parent().window() is form._widget


def test_a_docked_control_leaves_the_form_layout(form):
    form.pic.Width = 150
    form.pic.Align = 3  # docked to the form's left: the rest starts after it
    assert form._free_area[0] == 150
    form.pic.Container = form.fra1  # in a frame: not docked to the form any more
    assert form.pic.Parent is form.fra1 and form._free_area[0] == 0


def test_tab_order_follows(form):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    form._widget.activateWindow()
    form.txt.Container = form.fra1  # in a frame now, still after cmd by TabIndex
    form.cmd.SetFocus()
    QTest.qWait(10)
    QTest.keyClick(form.cmd._widget, Qt.Key_Tab)
    assert QApplication.focusWidget() is form.txt._widget


def test_errors(form):
    with pytest.raises(ValueError, match="container control"):
        form.cmd.Container = form.txt  # not a container
    other = Boxes()
    with pytest.raises(ValueError, match="container control"):
        form.cmd.Container = other.fra1  # another form's
    with pytest.raises(ValueError, match="into itself"):
        form.fra1.Container = form.fra1
    form.fra2.Container = form.fra1
    with pytest.raises(ValueError, match="into itself"):
        form.fra1.Container = form.fra2  # (fra2 is in fra1)
    with pytest.raises(TypeError, match="can't be moved"):
        form.mnu.Container = form.fra1
    with pytest.raises(ValueError):
        form.cmd.Container = None
    other._widget.close()
