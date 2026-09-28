"""The ListView control: ListItems, ColumnHeaders, SubItems, views, sorting, events."""

import os
import sys

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QListView

from vp6 import (Form, ListView, formfile, vpLvwAscending, vpLvwColumnCenter, vpLvwColumnLeft,
                 vpLvwColumnRight, vpLvwDescending, vpLvwIcon, vpLvwList, vpLvwReport,
                 vpLvwSmallIcon)
from vp6.controls import CONTROL_TYPES, parse_column, parse_list_item
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

COLUMNS = ["Name|name|120", "Size|size|80|right", "Moons|moons|60|center"]
ITEMS = ["Earth|earth|||12756|1", "Mars|mars|||6792|2", "Jupiter|jupiter|||142984|95"]


def test_parse_column_and_item():
    assert parse_column("Size|size|80|right") == {"Text": "Size", "Key": "size", "Width": 80,
                                                  "Alignment": vpLvwColumnRight}
    assert parse_column("Name") == {"Text": "Name", "Key": "", "Width": 100,
                                    "Alignment": vpLvwColumnLeft}
    assert parse_list_item("Earth|earth|planet|2|12756 km|1 moon") == {
        "Text": "Earth", "Key": "earth", "Icon": "planet", "SmallIcon": 2,
        "SubItems": ["12756 km", "1 moon"]}
    assert parse_list_item("Just text")["SubItems"] == []


class Planets(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 500, 320
        self.lvw = ListView(self, Left=8, Top=8, Width=420, Height=280, View=vpLvwReport,
                            ColumnHeaders=COLUMNS, ListItems=ITEMS)
        self.events = []

    def lvw_ItemClick(self, Item):
        self.events.append(("ItemClick", Item.Key))

    def lvw_ColumnClick(self, ColumnHeader):
        self.events.append(("ColumnClick", ColumnHeader.Key))

    def lvw_ItemCheck(self, Item):
        self.events.append(("ItemCheck", Item.Key, Item.Checked))


@pytest.fixture
def form(qapp):
    f = Planets()
    f.Show()
    QTest.qWait(10)
    yield f
    f.Unload()


def _keys(lvw):
    return [item.Key for item in lvw.ListItems]


def test_items_and_sub_items(form):
    lvw = form.lvw
    items = lvw.ListItems
    assert items.Count == 3 and _keys(lvw) == ["earth", "mars", "jupiter"]
    earth = items("earth")
    assert items(1) is earth is items.Item("earth") and "earth" in items
    assert (earth.Text, earth.Index, earth.SubItems(1), earth.SubItems[2]) == \
        ("Earth", 1, "12756", "1")
    earth.SubItems[2] = "1 moon"  # VB's Earth.SubItems(2) = "1 moon"
    assert earth.SubItems(2) == "1 moon"
    with pytest.raises(IndexError):
        earth.SubItems[0] = "no"  # 0 is the Text
    venus = items.Add(2, "venus", "Venus")  # at Index 2
    assert venus.Index == 2 and items("mars").Index == 3 and venus.SubItems(1) == ""
    venus.Text, venus.Tag = "Venus!", "hot"
    assert lvw._model.item(1, 0).text() == "Venus!"
    venus.Key = "morning"
    assert items("morning") is venus and "venus" not in items
    with pytest.raises(KeyError):
        items.Add(Key="earth")
    with pytest.raises(IndexError):
        items(9)
    items.Remove("morning")
    assert _keys(lvw) == ["earth", "mars", "jupiter"] and items("mars").Index == 2
    items.Clear()
    assert items.Count == 0 and "earth" not in items


def test_column_headers(form):
    lvw = form.lvw
    columns = lvw.ColumnHeaders
    assert [c.Text for c in columns] == ["Name", "Size", "Moons"]
    size = columns("size")
    assert (size.Index, size.Width, size.Alignment, size.SubItemIndex) == (2, 80, 1, 1)
    model = lvw._model
    assert model.headerData(1, Qt.Horizontal) == "Size"
    assert model.item(0, 1).textAlignment() & Qt.AlignRight  # the column's alignment
    assert model.item(0, 2).textAlignment() & Qt.AlignHCenter
    size.Width = 120
    assert lvw._tree.columnWidth(1) == 120 and size.Width == 120
    size.Text = "Diameter"
    assert model.headerData(1, Qt.Horizontal) == "Diameter"
    columns.Add(Key="notes", Text="Notes", Alignment=vpLvwColumnCenter)
    assert columns.Count == 4 and not lvw._tree.isColumnHidden(3)
    lvw.ListItems("mars").SubItems[3] = "red"  # a new item cell takes its alignment
    assert model.item(1, 3).textAlignment() & Qt.AlignHCenter
    lvw.HideColumnHeaders = True
    assert lvw._tree.isHeaderHidden()


def test_views_keep_the_selection(form):
    lvw = form.lvw
    assert lvw._stack.currentWidget() is lvw._tree  # Report
    lvw.SelectedItem = "mars"
    assert lvw.SelectedItem.Key == "mars" and lvw.ListItems("mars").Selected
    for view, mode in ((vpLvwIcon, QListView.IconMode), (vpLvwSmallIcon, QListView.ListMode),
                       (vpLvwList, QListView.ListMode)):
        lvw.View = view
        assert lvw._stack.currentWidget() is lvw._icons and lvw._icons.viewMode() == mode
        assert lvw.SelectedItem.Key == "mars"  # one selection for every view
    assert lvw._icons.flow() == QListView.TopToBottom  # List: in columns
    lvw.SelectedItem = None
    assert lvw.SelectedItem is None
    lvw.MultiSelect = True
    assert lvw._tree.selectionMode() == QAbstractItemView.ExtendedSelection
    lvw.ListItems("earth").Selected = True
    lvw.ListItems("jupiter").Selected = True
    assert [i.Key for i in lvw.ListItems if i.Selected] == ["earth", "jupiter"]


def test_sorting(form):
    lvw = form.lvw
    lvw.Sorted = True  # SortKey 0: by the Text
    assert _keys(lvw) == ["earth", "jupiter", "mars"] and lvw.ListItems("mars").Index == 3
    lvw.SortKey, lvw.SortOrder = 2, vpLvwDescending  # by the second SubItem, as text
    assert _keys(lvw) == ["jupiter", "mars", "earth"]  # Z to A as text: "95", "2", "1"
    lvw.SortOrder = vpLvwAscending
    lvw.SortKey = 0
    added = lvw.ListItems.Add(Key="ceres", Text="Ceres")  # where the order puts it
    assert added.Index == 1
    lvw.ListItems("ceres").Text = "Zeta"  # a new Text: sorted again
    assert _keys(lvw)[-1] == "ceres"


def test_events(form):
    lvw = form.lvw
    tree = lvw._tree
    rect = tree.visualRect(lvw.ListItems("mars")._cell0.index())
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    assert form.events[0] == ("ItemClick", "mars") and lvw.SelectedItem.Key == "mars"
    point = tree.viewport().mapTo(lvw._widget, rect.center())
    assert lvw.HitTest(point.x(), point.y()).Key == "mars"
    header = tree.header()
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(header.sectionPosition(1) + 10, header.height() // 2))
    assert ("ColumnClick", "size") in form.events
    lvw.Checkboxes = True
    earth = lvw.ListItems("earth")
    earth._cell0.setCheckState(Qt.Checked)  # the user checks it
    assert form.events[-1] == ("ItemCheck", "earth", True) and earth.Checked
    count = len(form.events)
    earth.Checked = False  # code: no ItemCheck
    assert not earth.Checked and len(form.events) == count
    lvw.Checkboxes = False
    assert earth._cell0.data(Qt.CheckStateRole) is None


@pytest.fixture
def pictures(qapp, tmp_path, monkeypatch):
    for name, size in (("big", 32), ("small", 16)):
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(QColor("green"))
        image.save(str(tmp_path / f"{name}.png"))
    (tmp_path / "Pics.py").write_text(
        "from vp6 import *\n\n\n"
        "class Pics(Form):\n"
        "    def InitializeComponent(self):\n"
        "        self.lvw = ListView(self, Icons='imlBig', SmallIcons='imlSmall', "
        "ListItems=['A|a|big|small', 'B|b|1|1', 'C|c'])\n"
        "        self.imlBig = ImageList(self, ListImages=['big.png|big'])\n"
        "        self.imlSmall = ImageList(self, ListImages=['small.png|small'])\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    sys.modules.pop("Pics", None)


def test_icons_and_small_icons(pictures):
    from Pics import Pics
    form = Pics()
    lvw = form.lvw

    def sizes():
        return [lvw._model.item(row, 0).icon().availableSizes()[0].width()
                if not lvw._model.item(row, 0).icon().isNull() else 0 for row in range(3)]

    assert lvw.View == vpLvwIcon and sizes() == [32, 32, 0]  # Icons in the Icon view
    lvw.View = vpLvwReport
    assert sizes() == [16, 16, 0]  # SmallIcons in the others
    item = lvw.ListItems("c")
    item.SmallIcon = "small"
    assert sizes()[2] == 16
    with pytest.raises(KeyError):
        item.Icon = "nothing"
    form.imlSmall.ListImages.Clear()  # the ImageList's changes show at once
    assert sizes() == [0, 0, 0]


def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.lvw = ListView(self, Left=8, Top=8, Width=257, Height=177, View=3, "
            "ColumnHeaders=['Name|name|120', 'Size|size|80|right'], "
            "ListItems=['Earth|earth|||12756'], Sorted=True, SortKey=1)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("lvw").props["ListItems"] == ["Earth|earth|||12756"]
    region = formfile.generate_region(form)
    assert "ColumnHeaders=['Name|name|120', 'Size|size|80|right']" in region
    assert "SortKey=1" in region


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("ListView", QRect(origin + QPoint(16, 16), origin + QPoint(300, 220)),
                            None)
    assert name == "ListView1"
    d.select([name])
    assert d.set_property("View", vpLvwReport) is None
    assert d.set_property("ColumnHeaders", COLUMNS) is None
    assert d.set_property("ListItems", ITEMS) is None
    lvw = d.controls[name]
    assert lvw.ListItems.Count == 3 and lvw.ColumnHeaders.Count == 3
    assert "ListItems=['Earth|earth|||12756|1'," in d.document.text
    window = PropertiesWindow()
    window.set_designer(d)
    texts = {window.table.item(r, 0).text(): window.table.cellWidget(r, 1)
             for r in range(window.table.rowCount())}
    assert texts["ColumnHeaders"].text() == "(Columns: 3)"
    assert texts["ListItems"].text() == "(Items: 3)"
    d.close()


def test_toolbox_icon_and_constants(qapp):
    assert "ListView" in Toolbox().buttons and "ListView" in CONTROL_TYPES
    assert ListView.DefaultEvent == "ItemClick"
    assert not icons.icon("ListView").isNull()
    assert (vpLvwIcon, vpLvwSmallIcon, vpLvwList, vpLvwReport) == (0, 1, 2, 3)
    assert (vpLvwColumnLeft, vpLvwColumnRight, vpLvwColumnCenter) == (0, 1, 2)
