"""GraphicsView: shapes as objects."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

import vp6
from vp6 import Form, GraphicsView
from vp6.graphicsview import svg_path


@pytest.fixture
def form(qapp):
    class Plan(Form):
        def InitializeComponent(self):
            self.events = []
            self.gvwPlan = GraphicsView(self, Left=0, Top=0, Width=400, Height=300,
                                        BorderStyle=0)

        def gvwPlan_ItemClick(self, Item):
            self.events.append(("Click", Item.Key))

        def gvwPlan_ItemMoved(self, Item):
            self.events.append(("Moved", Item.Key))

    f = Plan()
    f.Show()
    QTest.qWait(10)
    yield f
    f.Unload()


def test_svg_path():
    path = svg_path("M 10 10 L 50 10 l 0 40 H 10 V 10 Z")
    assert path.boundingRect().getRect() == (10, 10, 40, 40)
    curve = svg_path("M0,0 C 10 0 20 10 20 20 Q 30 30 40 20")
    assert curve.elementCount() > 3
    with pytest.raises(ValueError):
        svg_path("M 0 0 A 5 5 0 0 1 10 10")
    with pytest.raises(ValueError):
        svg_path("M 0 0 L 5")


def test_items(form):
    items = form.gvwPlan.Items
    box = items.AddRect(20, 20, 100, 50, FillColor=vp6.vpYellow, Key="box")
    ring = items.AddEllipse(150, 20, 60, 60, BorderWidth=3, Key="ring")
    items.AddLine(0, 200, 300, 200, ForeColor=vp6.vpRed)
    items.AddPolygon([(250, 100), (300, 150), (220, 160)], FillColor=vp6.vpGreen)
    items.AddPath("M 10 250 Q 60 220 110 250")
    label = items.AddText("Kitchen", 20, 100, FontBold=True, Key="label")
    picture = items.AddPicture(vp6.Picture(10, 10, BackColor=vp6.vpBlue), 300, 20)
    group = items.AddGroup(items.AddRect(320, 220, 20, 20), items.AddRect(345, 220, 20, 20),
                           Key="chairs")
    assert items.Count == 10 and items("box") is box and items(1) is box
    assert [i.Kind for i in items][:3] == ["Rect", "Ellipse", "Line"]
    assert (box.Left, box.Top, box.Width) == (20, 20, 101) and box.FillColor == vp6.vpYellow
    assert label.Text == "Kitchen" and picture.Kind == "Picture" and group.Kind == "Group"
    box.Rotation, box.Scale, box.ZOrder = 30, 2, 5
    assert (box.Rotation, box.Scale, box.ZOrder) == (30, 2, 5)
    box.Move(40, 50)
    assert (box.Left, box.Top) == (40, 50)
    label.Text = "Dining"
    assert label.Text == "Dining"
    with pytest.raises(AttributeError):
        ring.Text = "x"
    ring.ForeColor, ring.FillColor = None, vp6.vpCyan
    assert ring.ForeColor is None and ring.FillColor == vp6.vpCyan
    with pytest.raises(ValueError):
        items.AddRect(0, 0, 1, 1, Key="box")
    ring.Remove()
    assert items.Count == 9 and "ring" not in items._by_key
    items.Clear()
    assert items.Count == 0


def test_click_and_drag(form):
    view = form.gvwPlan
    table = view.Items.AddRect(50, 50, 80, 60, FillColor=vp6.vpYellow, Key="table")
    table.Movable = table.Selectable = True
    view.Items.AddRect(200, 50, 80, 60, Key="wall")
    viewport = view._widget.viewport()
    assert view.HitTest(90, 80) is table and view.HitTest(5, 5) is None
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(240, 80))
    assert form.events == [("Click", "wall")]
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(90, 80))
    QTest.mouseMove(viewport, QPoint(130, 110))
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(130, 110))
    assert form.events[-1] == ("Moved", "table") and (table.Left, table.Top) == (90, 80)
    assert view.SelectedItems == [table]


def test_view(form):
    view = form.gvwPlan
    view.Items.AddRect(0, 0, 800, 600, Key="big")
    view.Zoom = 2
    assert view.Zoom == 2
    view.ZoomToFit()
    assert view.Zoom < 1
    view.SceneWidth = 1000
    assert view._scene.sceneRect().width() == 1000
    view.MouseMode = 1
    assert view._widget.dragMode() == view._widget.DragMode.ScrollHandDrag
    assert view.SceneX(0) >= 0
    picture = view.Picture
    assert picture.Width == 1000 and picture.Height in (600, 601)  # (the outline's half pixel)


def test_print_out(form, tmp_path):
    form.gvwPlan.Items.AddEllipse(10, 10, 100, 100, FillColor=vp6.vpRed)
    from vp6 import printer

    folder = printer.REDIRECT_DIR  # (the tests print to PDF files there)
    before = set(os.listdir(folder))
    form.gvwPlan.PrintOut()
    assert set(os.listdir(folder)) - before
