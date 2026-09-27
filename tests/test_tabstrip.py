"""The TabStrip control, its Tabs collection and Tab objects."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from vp6 import (Form, Frame, TabStrip, formfile, vpTabPlacementBottom, vpTabPlacementLeft,
                 vpTabPlacementRight, vpTabPlacementTop)
from vp6.controls import CONTROL_TYPES, parse_tab
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

TABS = ["&General|general|Name and size", "Colors|colors", "About"]


def test_parse_tab():
    assert parse_tab("&General|general|Name and size") == {
        "Caption": "&General", "Key": "general", "ToolTipText": "Name and size", "Image": ""}
    assert parse_tab(" About ") == {"Caption": "About", "Key": "", "ToolTipText": "",
                                    "Image": ""}
    assert parse_tab("A|a||gear")["Image"] == "gear" and parse_tab("B|b||2")["Image"] == 2


class Window(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 500, 320
        self.tbs = TabStrip(self, Left=16, Top=16, Width=300, Height=200, Tabs=TABS)
        self.fra = Frame(self, Left=0, Top=0, Width=10, Height=10)
        self.events = []
        self.locked = False
        self.client_at_load = None

    def Form_Load(self):
        # Before the form is shown: the client area is already right
        t = self.tbs
        self.client_at_load = (t.ClientLeft, t.ClientTop, t.ClientWidth, t.ClientHeight)

    def tbs_Click(self):
        self.events.append(("Click", self.tbs.SelectedItem.Key))

    def tbs_BeforeClick(self):
        self.events.append("BeforeClick")
        return self.locked


@pytest.fixture
def window(qapp):
    w = Window()
    w.Show()
    QTest.qWait(10)
    yield w
    w.Unload()


def _click_tab(strip, index):
    bar = strip._widget.tabBar()
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(index).center())


def test_tabs_and_selection(window):
    tbs = window.tbs
    assert tbs.Tabs.Count == 3 and [t.Index for t in tbs.Tabs] == [1, 2, 3]
    assert [tbs._widget.tabText(i) for i in range(3)] == ["&General", "Colors", "About"]
    assert tbs._widget.tabToolTip(0) == "Name and size"
    general = tbs.Tabs("general")
    assert tbs.SelectedItem is general and general.Selected  # the first to begin with
    assert window.events == []  # no Click while loading
    tbs.SelectedItem = "colors"  # by Key (or Index, or the Tab): Click, as in VB
    assert window.events == [("Click", "colors")] and tbs.Tabs(2).Selected
    tbs.Tabs(3).Selected = True
    assert tbs.SelectedItem.Caption == "About"
    tbs.SelectedItem = 1
    assert tbs.SelectedItem is general


def test_the_user_clicks_and_before_click_cancels(window):
    tbs = window.tbs
    _click_tab(tbs, 1)
    assert window.events == ["BeforeClick", ("Click", "colors")]
    window.locked = True  # BeforeClick returns True: the tab stays
    _click_tab(tbs, 2)
    assert tbs.SelectedItem.Key == "colors" and window.events[-1] == "BeforeClick"
    window.events.clear()
    _click_tab(tbs, 1)  # the selected tab: nothing to decide
    assert window.events == []


def test_changing_the_tabs(window):
    tbs = window.tbs
    tbs.SelectedItem = "colors"
    window.events.clear()
    first = tbs.Tabs.Add(1, "first", "First")  # before the others: the selection stays
    assert [t.Caption for t in tbs.Tabs] == ["First", "&General", "Colors", "About"]
    assert first.Index == 1 and tbs.SelectedItem.Key == "colors"
    assert window.events == []  # rebuilding the tabs fires no Click
    first.Caption = "Start"
    first.ToolTipText = "Where it begins"
    assert tbs._widget.tabText(0) == "Start" and tbs._widget.tabToolTip(0) == "Where it begins"
    with pytest.raises(KeyError):
        tbs.Tabs.Add(Key="first")
    with pytest.raises(IndexError):
        tbs.Tabs(9)
    tbs.Tabs.Remove("first")
    assert tbs.Tabs.Count == 3 and tbs.SelectedItem.Key == "colors"
    tbs.Tabs("colors").Key = "palette"
    assert tbs.Tabs("palette").Index == 2
    tbs.Tabs.Clear()
    assert tbs.Tabs.Count == 0 and tbs.SelectedItem is None
    added = tbs.Tabs.Add(Caption="Only")
    assert tbs.SelectedItem is added


def test_client_area(window):
    tbs = window.tbs
    widget = tbs._widget
    for placement in (vpTabPlacementTop, vpTabPlacementBottom, vpTabPlacementLeft,
                      vpTabPlacementRight):
        tbs.Placement = placement
        QTest.qWait(5)
        page = widget.currentWidget()
        top_left = page.mapTo(widget, QPoint(0, 0)) + widget.pos()
        assert (tbs.ClientLeft, tbs.ClientTop, tbs.ClientWidth, tbs.ClientHeight) == \
            (top_left.x(), top_left.y(), page.width(), page.height()), placement
    tbs.Placement = vpTabPlacementTop
    QTest.qWait(5)
    assert window.client_at_load == (tbs.ClientLeft, tbs.ClientTop, tbs.ClientWidth,
                                     tbs.ClientHeight)  # computed before it was shown
    assert tbs.ClientTop > tbs.Top and tbs.ClientLeft >= tbs.Left  # inside the tabs' frame
    # A Frame over the client area is on top of the TabStrip (created after it)
    window.fra.Move(tbs.ClientLeft, tbs.ClientTop, tbs.ClientWidth, tbs.ClientHeight)
    hit = window._container_widget().childAt(window.fra._widget.geometry().center())
    assert hit is window.fra._widget or window.fra._widget.isAncestorOf(hit)


def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.tbs = TabStrip(self, Left=8, Top=8, Width=257, Height=177, "
            "Tabs=['&General|general', 'About'], Placement=1)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("tbs").props["Tabs"] == ["&General|general", "About"]
    region = formfile.generate_region(form)
    assert "Tabs=['&General|general', 'About']" in region and "Placement=1" in region


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("TabStrip", QRect(origin + QPoint(16, 16), origin + QPoint(280, 200)),
                            None)
    assert name == "TabStrip1"
    strip = d.controls[name]
    assert strip.Tabs.Count == 1 and strip.Tabs(1).Caption == "Tab1"
    d.select([name])
    assert d.set_property("Tabs", TABS) is None
    assert strip.Tabs.Count == 3 and "Tabs=['&General|general|Name and size'," in d.document.text
    window = PropertiesWindow()
    window.set_designer(d)
    row = next(r for r in range(window.table.rowCount())
               if window.table.item(r, 0).text() == "Tabs")
    assert window.table.cellWidget(row, 1).text() == "(Tabs: 3)"
    d.close()


def test_toolbox_icon_and_constants(qapp):
    assert "TabStrip" in Toolbox().buttons and "TabStrip" in CONTROL_TYPES
    assert TabStrip.DefaultEvent == "Click"
    assert not icons.icon("TabStrip").isNull()
    assert (vpTabPlacementTop, vpTabPlacementBottom, vpTabPlacementLeft,
            vpTabPlacementRight) == (0, 1, 2, 3)
