"""Form.PopupMenu: a form's menu shown as a context menu, where and how, what was
chosen."""

import os

import pytest
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtTest import QTest

from vp6 import (CommandButton, Form, Menu, vpPopupMenuCenterAlign, vpPopupMenuLeftAlign,
                 vpPopupMenuRightAlign, vpPopupMenuRightButton)

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Popups(Form):
    def InitializeComponent(self):
        self.log = []
        self.mnuFile = Menu(self, Caption="&File")
        self.mnuFileOpen = Menu(self.mnuFile, Caption="&Open")
        self.mnuPop = Menu(self, Caption="Pop", Visible=False)
        self.mnuCut = Menu(self.mnuPop, Caption="Cu&t")
        self.mnuCopy = Menu(self.mnuPop, Caption="&Copy")
        self.mnuEmpty = Menu(self, Caption="Empty")
        self.cmd = CommandButton(self, Left=10, Top=10)

    def mnuPop_Click(self):
        self.log.append("Pop")  # (the menu's own Click: just before it opens)

    def mnuCopy_Click(self):
        self.log.append("Copy")


@pytest.fixture
def form(qapp):
    form = Popups()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def later(form, action):
    """Do something with the menu while PopupMenu waits."""
    seen = {}

    def run():
        menu = form.mnuPop._submenu
        seen.update(visible=menu.isVisible(), pos=menu.pos(), width=menu.width(),
                    default=menu.defaultAction())
        action(menu)

    QTimer.singleShot(30, run)
    return seen


def test_choosing_an_item(form):
    seen = later(form, lambda menu: (form.mnuCopy._action.trigger(), menu.close()))
    chosen = form.PopupMenu(form.mnuPop, DefaultMenu=form.mnuCut)
    assert chosen is form.mnuCopy and form.log == ["Pop", "Copy"]  # (Click before it returns)
    assert seen["visible"] and seen["default"] is form.mnuCut._action  # bold
    assert form.mnuPop._submenu.defaultAction() is None  # (only for that time)
    later(form, lambda menu: menu.close())  # closed without a choice
    assert form.PopupMenu(form.mnuPop) is None
    assert "_popup_chosen" not in form.__dict__
    form.mnuCopy._action.trigger()  # (a Click outside PopupMenu: nothing waits)
    assert "_popup_chosen" not in form.__dict__


def test_where(form):
    area = form._container_widget()
    point = area.mapToGlobal(QPoint(100, 50))
    seen = later(form, lambda menu: menu.close())
    form.PopupMenu(form.mnuPop, vpPopupMenuLeftAlign + vpPopupMenuRightButton, 100, 50)
    assert seen["pos"] == point
    seen = later(form, lambda menu: menu.close())
    form.PopupMenu(form.mnuPop, vpPopupMenuRightAlign, 100, 50)
    assert seen["pos"].x() + seen["width"] == pytest.approx(point.x(), abs=2)
    seen = later(form, lambda menu: menu.close())
    form.PopupMenu(form.mnuPop, vpPopupMenuCenterAlign, 100, 50)
    assert seen["pos"].x() + seen["width"] // 2 == pytest.approx(point.x(), abs=2)
    QCursor.setPos(area.mapToGlobal(QPoint(30, 40)))  # without X, Y: at the mouse
    seen = later(form, lambda menu: menu.close())
    form.PopupMenu(form.mnuPop, Y=60)
    assert seen["pos"].y() == area.mapToGlobal(QPoint(0, 60)).y()


def test_errors_and_the_menu_bar(form):
    assert not form.mnuPop.Visible and form.mnuFile.Visible
    with pytest.raises(TypeError, match="not a Menu"):
        form.PopupMenu(form.cmd)
    with pytest.raises(ValueError, match="no items"):
        form.PopupMenu(form.mnuEmpty)
    seen = {}  # (a menu-bar menu can pop up too)
    QTimer.singleShot(30, lambda: (seen.update(v=form.mnuFile._submenu.isVisible()),
                                   form.mnuFile._submenu.close()))
    form.PopupMenu(form.mnuFile)
    assert seen["v"]


def test_at_design_time(qapp):
    class Designing(Form):
        _design_mode = True

        def InitializeComponent(self):
            self.mnuPop = Menu(self, Caption="Pop")
            self.mnuA = Menu(self.mnuPop, Caption="A")

    form = Designing()
    assert form.PopupMenu(form.mnuPop) is None
    form._widget.close()
