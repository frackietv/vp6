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


# --- NewIndex, TopIndex, SelCount, Selected, Checkbox ListBox, Simple Combo, DropDown ---------

class More(Form):
    def InitializeComponent(self):
        self.lst = ListBox(self, Left=0, Top=0, Width=120, Height=60,
                           List=[f"Item {n:02}" for n in range(20)])
        self.chk = ListBox(self, Style=1, List=["Cheese", "Ham", "Pineapple"])
        self.cbo = ComboBox(self, List=["b", "c"], Sorted=True)
        self.simple = ComboBox(self, Style=1, Width=120, Height=100, List=["one", "two"])
        self.events = []

    def chk_ItemCheck(self, Item):
        self.events.append(("ItemCheck", Item, self.chk.Selected(Item)))

    def cbo_DropDown(self):
        self.events.append("DropDown")

    def simple_Click(self):
        self.events.append(("Click", self.simple.ListIndex))


@pytest.fixture
def more(qapp):
    form = More()
    form.Show()
    yield form
    form.Unload()


def test_new_index(more):
    for control in (more.lst, more.cbo):
        assert control.NewIndex == -1  # the designer's List: none added
    more.lst.AddItem("At 3", 3)
    assert more.lst.NewIndex == 3 and more.lst.List[3] == "At 3"
    more.cbo.AddItem("a")  # sorted in at the front
    assert more.cbo.NewIndex == 0 and more.cbo.List == ["a", "b", "c"]
    more.cbo.AddItem("bb")
    assert more.cbo.List[more.cbo.NewIndex] == "bb"
    assert more.cbo._role(more.cbo.NewIndex, Qt.UserRole + 2) is None  # the mark is gone
    more.cbo.RemoveItem(0)
    assert more.cbo.NewIndex == -1
    more.lst.AddItem("x")
    more.lst.Clear()
    assert more.lst.NewIndex == -1


def test_top_index_and_selection(more):
    lst = more.lst
    assert lst.TopIndex == 0
    lst.TopIndex = 10  # scrolls
    assert lst.TopIndex == 10
    assert lst.SelCount == 0
    lst.MultiSelect = 2
    lst.Selected[2] = True  # VB's List1.Selected(2) = True
    lst.Selected[5] = True
    assert lst.Selected(2) and lst.SelCount == 2
    lst.Selected[2] = False
    assert lst.SelCount == 1
    more.cbo.TopIndex = 1
    assert more.cbo.TopIndex == 1  # (the list isn't open: as set)


def test_checkbox_list_box(more):
    chk = more.chk
    item = chk._widget.item(1)
    assert item.flags() & Qt.ItemIsUserCheckable and not chk.Selected(1)
    item.setCheckState(Qt.Checked)  # the user checks Ham
    assert more.events == [("ItemCheck", 1, True)] and chk.SelCount == 1
    chk.Selected[2] = True  # code: checked, no ItemCheck
    chk.ItemBold[0] = True  # nor for other changes of an item
    assert chk.SelCount == 2 and len(more.events) == 1
    chk.AddItem("Olives")  # new items get a check box too
    assert chk._widget.item(chk.NewIndex).flags() & Qt.ItemIsUserCheckable
    chk.Style = 0  # Standard again: no check boxes; Selected is selected again
    assert not chk._widget.item(1).flags() & Qt.ItemIsUserCheckable
    assert chk.SelCount == 0


def test_simple_combo(more):
    simple = more.simple
    widget = simple._widget
    assert widget.list.isVisible() and widget.edit.isVisible()  # the list is always shown
    simple.ListIndex = 1  # choosing an item: its text, and Click
    assert simple.Text == "two" and more.events[-1] == ("Click", 1)
    simple.Text = "three"  # free text, as in a Dropdown Combo
    assert simple.Text == "three" and simple.ListIndex == 1
    simple.AddItem("three")
    simple.ItemData[simple.NewIndex] = 3
    assert simple.List == ["one", "two", "three"] and simple.ItemData(2) == 3
    count = len(more.events)
    simple.Style = 0  # a Dropdown Combo now: the items, the text and the choice kept
    assert simple.List == ["one", "two", "three"] and simple.ListIndex == 1
    assert len(more.events) == count  # no Click for refilling the new widget


def test_drop_down(more):
    more.cbo._widget.showPopup()
    more.cbo._widget.hidePopup()
    assert more.events == ["DropDown"]
