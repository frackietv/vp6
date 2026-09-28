"""ListBox and ComboBox per-item properties: ItemData, ItemImage, ItemBold,
ItemItalic and ItemForeColor."""

import os
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from vp6 import ComboBox, Form, ListBox, vpBlue, vpRed

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Lists(Form):
    def InitializeComponent(self):
        self.lst = ListBox(self, List=["Bravo", "Charlie"], Sorted=True)
        self.cbo = ComboBox(self, Style=2, List=["Red", "Blue"])


@pytest.fixture(params=["lst", "cbo"])
def control(qapp, request):
    return getattr(Lists(), request.param)


def test_item_data(control):
    control.ItemData[0] = 10
    control.ItemData[1] = "anything"  # (VB's ItemData was a number; here any value)
    assert control.ItemData(0) == 10 and control.ItemData[1] == "anything"
    assert len(control.ItemData) == control.ListCount == 2
    control.AddItem("New")
    assert control.ItemData[control.List.index("New")] is None  # none yet
    for bad in (-1, 3):
        with pytest.raises(IndexError, match="ListCount is 3"):
            control.ItemData[bad] = 1
        with pytest.raises(IndexError):
            control.ItemData(bad)


def test_values_move_with_their_items(qapp):
    lst = Lists().lst
    lst.ItemData[0], lst.ItemData[1] = "b", "c"  # Bravo, Charlie
    lst.ItemBold[1] = True
    lst.AddItem("Alpha")  # sorted in at 0: the others move, with their values
    assert lst.List == ["Alpha", "Bravo", "Charlie"]
    assert [lst.ItemData[i] for i in range(3)] == [None, "b", "c"]
    assert [lst.ItemBold[i] for i in range(3)] == [False, False, True]
    lst.RemoveItem(1)
    assert [lst.ItemData[i] for i in range(2)] == [None, "c"] and lst.ItemBold[1]
    cbo = Lists().cbo
    cbo.ItemData[0], cbo.ItemData[1] = vpRed, vpBlue
    cbo.Sorted = True  # Blue, Red
    assert cbo.List == ["Blue", "Red"] and cbo.ItemData[0] == vpBlue
    cbo.ListIndex = 1
    assert cbo.ItemData[cbo.ListIndex] == vpRed  # VB's ItemData(ListIndex)


def test_fonts_and_colors(control):
    widget_role = control._role
    control.ItemBold[0] = True
    control.ItemItalic[1] = True
    assert (control.ItemBold[0], control.ItemItalic[0]) == (True, False)
    assert (control.ItemBold[1], control.ItemItalic[1]) == (False, True)
    assert widget_role(0, Qt.FontRole).bold() and widget_role(1, Qt.FontRole).italic()
    control.ItemItalic[1] = False
    assert not control.ItemItalic(1)
    assert control.ItemForeColor[0] is None  # the control's
    control.ItemForeColor[0] = vpRed
    assert control.ItemForeColor[0] == vpRed
    assert widget_role(0, Qt.ForegroundRole).color() == QColor(255, 0, 0)
    control.ItemForeColor[0] = None
    assert control.ItemForeColor[0] is None


@pytest.fixture
def pictures(qapp, tmp_path, monkeypatch):
    for name, color in (("a", "red"), ("b", "green")):
        image = QImage(16, 16, QImage.Format_ARGB32)
        image.fill(QColor(color))
        image.save(str(tmp_path / f"{name}.png"))
    (tmp_path / "Pics.py").write_text(
        "from vp6 import *\n\n\n"
        "class Pics(Form):\n"
        "    def InitializeComponent(self):\n"
        "        self.lst = ListBox(self, List=['One', 'Two'], ImageList='iml')\n"
        "        self.cbo = ComboBox(self, Style=2, List=['One'])\n"
        "        self.iml = ImageList(self, ListImages=['a.png|a', 'b.png|b'])\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    sys.modules.pop("Pics", None)


def test_item_images(pictures):
    from Pics import Pics
    form = Pics()
    lst = form.lst

    def shown(index):
        icon = lst._role(index, Qt.DecorationRole)
        return icon is not None and not icon.isNull()

    lst.ItemImage[0] = "a"  # by Key
    lst.ItemImage[1] = 2  # by Index
    assert lst.ItemImage[0] == "a" and shown(0) and shown(1)
    with pytest.raises(KeyError):
        lst.ItemImage[0] = "nothing"
    form.iml.ListImages.Clear()  # the ImageList's changes show at once
    assert not shown(0) and not shown(1) and lst.ItemImage[0] == "a"
    form.iml.ListImages.Add(Key="a", Picture="a.png")
    assert shown(0)
    lst.ItemImage[0] = ""
    assert not shown(0)
    form.cbo.ItemImage[0] = "b.png"  # without an ImageList: a picture file
    assert not form.cbo._role(0, Qt.DecorationRole).isNull()
