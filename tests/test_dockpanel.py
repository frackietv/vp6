"""DockPanels: docked to the form's edges, floating in their own windows, dragged to
another edge, resized, closed and shown again, and the form's DockLayout."""

import json
import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vp6 import (CommandButton, DockPanel, Form, Label, PictureBox, vpAlignBottom, vpAlignLeft,
                 vpAlignRight, vpAlignTop)
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Docks(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 600, 400
        self.events = []
        self.keep_open = False
        self.dckLeft = DockPanel(self, Caption="Left", Align=3, Width=150)
        self.cmdInside = CommandButton(self.dckLeft, Caption="In", Left=8, Top=8, Width=60,
                                       Height=26)
        self.dckBottom = DockPanel(self, Caption="Bottom", Align=2, Height=100)
        self.picMiddle = PictureBox(self, Align=5, BorderStyle=0)

    def dckLeft_DockChange(self):
        self.events.append(("DockChange", self.dckLeft.Floating, self.dckLeft.Align))

    def dckLeft_Close(self):
        self.events.append("Close")
        return self.keep_open

    def dckLeft_Resize(self):
        self.events.append("Resize")


@pytest.fixture
def form(qapp):
    form = Docks()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def geometry(control):
    g = control._widget.geometry()
    return g.x(), g.y(), g.width(), g.height()


def test_docked_layout(form):
    left, bottom = form.dckLeft, form.dckBottom
    assert geometry(left) == (0, 0, 150, 400)
    assert geometry(bottom) == (150, 300, 450, 100)  # (beside the earlier one)
    assert geometry(form.picMiddle) == (150, 0, 450, 300)  # Fill: what they leave
    assert form.cmdInside._widget.parent() is left._widget.content  # a container
    content = left._widget.content.geometry()
    assert content.top() >= 22 and content.width() < 150  # under its caption, beside its edge
    left.Width = 200
    assert geometry(left)[2] == 200 and geometry(form.picMiddle)[0] == 200
    left.Align = vpAlignRight
    assert geometry(left) == (400, 0, 200, 400) and geometry(bottom) == (0, 300, 400, 100)


def test_floating_and_docking(form):
    left = form.dckLeft
    left.Float()
    window = left._float_window
    assert left.Floating and window.isVisible() and window.isWindow()
    assert form.events[-1] == ("DockChange", True, vpAlignLeft)
    assert geometry(form.dckBottom) == (0, 300, 600, 100)  # its space goes to the others
    assert form.cmdInside._widget.window() is window  # its controls go with it
    left.FloatMove(50, 60, 220, 180)
    assert (left.FloatLeft, left.FloatTop, left.FloatWidth, left.FloatHeight) == (50, 60, 220,
                                                                                    180)
    left.Width = 999  # (floating: no effect on its window or the form)
    assert left.FloatWidth == 220
    left.Dock(vpAlignTop)
    assert not left.Floating and left._float_window is None and left.Align == vpAlignTop
    assert form.events[-1] == ("DockChange", False, vpAlignTop)
    assert geometry(left)[:2] == (0, 0) and geometry(left)[2] == 600
    left.Floating = True  # where it last floated
    assert (left.FloatLeft, left.FloatTop, left.FloatWidth) == (50, 60, 220)
    left.Floating = False
    assert left.Align == vpAlignTop  # back to the edge it had
    left.Dock(vpAlignBottom)  # docked: moved to another edge
    assert left.Align == vpAlignBottom and form.events[-1] == ("DockChange", False,
                                                               vpAlignBottom)


def test_closing_and_showing_again(form, monkeypatch):
    left = form.dckLeft
    caption = left._widget.caption
    close = caption.button_rects()["close"].center()
    QTest.mouseClick(caption, Qt.LeftButton, Qt.NoModifier, close)
    assert form.events[-2:] == ["Close", ("DockChange", False, vpAlignLeft)]
    assert not left.Visible and not left._widget.isVisible()
    assert geometry(form.dckBottom)[0] == 0  # its space goes to the others
    left.Visible = True
    assert left._widget.isVisible() and geometry(left)[0] == 0
    form.keep_open = True  # Close cancelling
    QTest.mouseClick(caption, Qt.LeftButton, Qt.NoModifier, close)
    assert left.Visible
    form.keep_open = False
    left.Float()  # floating: closing hides its window, Visible shows it again
    window = left._float_window
    QTest.mouseClick(left._widget.caption, Qt.LeftButton, Qt.NoModifier,
                     left._widget.caption.button_rects()["close"].center())
    assert not left.Visible and not window.isVisible() and left.Floating
    left.Visible = True
    assert window.isVisible()
    form.keep_open = True
    window.close()  # the window manager's close: as the button
    assert window.isVisible() and left.Visible
    form.keep_open = False
    window.close()
    assert not left.Visible


def test_caption_buttons_and_double_click(form):
    left = form.dckLeft
    caption = left._widget.caption
    QTest.mouseClick(caption, Qt.LeftButton, Qt.NoModifier,
                     caption.button_rects()["float"].center())
    assert left.Floating
    caption = left._widget.caption
    QTest.mouseDClick(caption, Qt.LeftButton, Qt.NoModifier, QPoint(20, 10))
    assert not left.Floating
    left.Floatable = False
    left.Closable = False
    assert caption.button_rects() == {}
    QTest.mouseDClick(caption, Qt.LeftButton, Qt.NoModifier, QPoint(20, 10))
    assert not left.Floating


def test_dragging_to_another_edge(form):
    left, area = form.dckLeft, form._container_widget()
    grab = QPoint(20, 10)  # where the caption bar is held
    start = left._widget.caption.mapToGlobal(grab)
    assert left._drag_start(start + QPoint(40, 40), grab)
    assert left.Floating
    left._drag_move(area.mapToGlobal(QPoint(300, 200)))  # the middle: no edge
    assert left._float_window.pos() == area.mapToGlobal(QPoint(300, 200)) - grab
    assert left._band is None or not left._band.isVisible()
    left._drag_move(area.mapToGlobal(QPoint(590, 200)))  # near the right edge
    assert left._band.isVisible() and left._band.geometry().right() == 599
    left._drag_end(area.mapToGlobal(QPoint(590, 200)))
    assert not left.Floating and left.Align == vpAlignRight and not left._band.isVisible()
    assert geometry(left)[0] + geometry(left)[2] == 600
    # Dropped in the middle: it stays floating
    left._drag_start(left._widget.caption.mapToGlobal(grab), grab)
    left._drag_end(area.mapToGlobal(QPoint(300, 150)))
    assert left.Floating
    # Dropped panels go next to the edge, outside the form's other DockPanels
    left._drag_end(area.mapToGlobal(QPoint(300, 395)))
    assert left.Align == vpAlignBottom and form._controls.index(left) < form._controls.index(
        form.dckBottom)
    assert geometry(left)[1] + geometry(left)[3] == 400  # at the bottom edge
    left.Floatable = False
    assert not left._drag_start(left._widget.caption.mapToGlobal(grab), grab)


def test_resizing_by_the_edge(form):
    left = form.dckLeft
    sizer = left._widget.sizer
    assert sizer.isVisible() and sizer.geometry().right() >= 140
    form.events.clear()
    QTest.mousePress(sizer, Qt.LeftButton, Qt.NoModifier, QPoint(2, 100))
    QTest.mouseMove(sizer, QPoint(52, 100))
    QTest.mouseRelease(sizer, Qt.LeftButton, Qt.NoModifier, QPoint(52, 100))
    assert left.Width == 200 and "Resize" in form.events
    left._resize_docked(5)  # (not smaller than its caption and a little)
    assert left.Width >= 40
    left._resize_docked(10000)  # nor larger than the form leaves
    assert left.Width <= 560
    left.Resizable = False
    assert not sizer.isVisible()


def test_floating_windows_follow_the_form(form):
    left = form.dckLeft
    left.Float()
    window = left._float_window
    form.Hide()
    assert not window.isVisible()
    form.Show()
    assert window.isVisible()


def test_dock_layout(form):
    left, bottom = form.dckLeft, form.dckBottom
    left.Width = 180
    bottom.Float()
    bottom.FloatMove(30, 40, 300, 150)
    saved = form.DockLayout
    entries = json.loads(saved)["dock_panels"]
    assert [e["name"] for e in entries] == ["dckLeft", "dckBottom"]
    assert entries[1]["floating"] and entries[1]["float"] == [30, 40, 300, 150]
    # Everything moved, then put back
    bottom.Dock(vpAlignTop)
    left.Align = vpAlignRight
    left.Width = 120
    left.Visible = False
    form._controls.remove(bottom)
    form._controls.insert(form._controls.index(left), bottom)
    form.DockLayout = saved
    assert left.Align == vpAlignLeft and left.Width == 180 and left.Visible
    assert bottom.Floating and (bottom.FloatLeft, bottom.FloatTop) == (30, 40)
    assert bottom.Align == vpAlignBottom  # where it docks back to
    assert form._controls.index(left) < form._controls.index(bottom)
    form.DockLayout = ""  # (nothing to change)
    with pytest.raises(ValueError, match="not a DockLayout"):
        form.DockLayout = "nonsense"


def test_floating_from_the_start(qapp):
    class Starts(Form):
        def InitializeComponent(self):
            self.dck = DockPanel(self, Caption="Floats", Floating=True)
            self.lbl = Label(self, Caption="x")

    form = Starts()
    assert form.dck.Floating and not form.dck._float_window.isVisible()  # (form hidden)
    form.Show()
    assert form.dck._float_window.isVisible()
    form.Unload()


def test_toolbox_icon_and_events(qapp):
    assert "DockPanel" in Toolbox().buttons and "DockPanel" in CONTROL_TYPES
    assert not icon("DockPanel").isNull()
    assert CONTROL_TYPES["DockPanel"].DefaultEvent == "DockChange"
    assert EVENT_ARGS["DockChange"] == EVENT_ARGS["Close"] == ""


class Groups(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 600, 400
        self.dckProject = DockPanel(self, Caption="Project", Align=4, Width=160, Height=300)
        self.dckProps = DockPanel(self, Caption="Properties", Align=4, Width=100, Height=100)
        self.dckImmediate = DockPanel(self, Caption="Immediate", Align=2, Height=120)
        self.dckOutput = DockPanel(self, Caption="Output", Align=2, Height=80)
        self.dckTerminal = DockPanel(self, Caption="Terminal", Align=2, Height=80,
                                     Visible=False)
        self.picMiddle = PictureBox(self, Align=5, BorderStyle=0)


@pytest.fixture
def groups(qapp):
    form = Groups()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def test_tabbed_together(groups):
    immediate, output, terminal = groups.dckImmediate, groups.dckOutput, groups.dckTerminal
    output.TabWith(immediate)
    assert output.TabPanels == [immediate, output] == immediate.TabPanels
    assert output._values["Height"] == 120  # (the place's size: the tabs take some)
    assert immediate.ActiveTab is output and output._widget.isVisible()
    assert not immediate._widget.isVisible()
    bar = groups.dckImmediate._slot.items[0].bar
    assert bar.isVisible() and [bar.tabText(i) for i in range(bar.count())] == \
        ["Immediate", "Output"]
    panel, tabs = geometry(output), bar.geometry()
    assert panel[1] + panel[3] == tabs.y() and tabs.bottom() == 399  # the tabs under it
    assert panel[2] == 340 and geometry(groups.picMiddle)[3] == 280  # one place: 120 high
    bar.setCurrentIndex(0)  # a click on a tab
    assert immediate.ActiveTab is immediate and immediate._widget.isVisible()
    # A hidden panel in the group has no tab; shown, it joins them in front
    terminal.TabWith(immediate)
    terminal.Visible = False
    assert bar.count() == 2 and immediate.ActiveTab is immediate
    terminal.Visible = True
    assert bar.count() == 3 and immediate.ActiveTab is terminal
    terminal.Visible = False
    output.Visible = False
    assert not bar.isVisible() and immediate._widget.isVisible()  # one left: no tabs
    assert geometry(immediate)[3] == 120
    output.Visible = True
    output.Separate()
    assert output.TabPanels == [output] and immediate.TabPanels == [immediate, terminal]
    assert output._widget.isVisible() and geometry(groups.picMiddle)[3] == 160  # (120 each)
    terminal.Separate()
    assert immediate._slot is None and terminal._slot is None


def test_side_by_side(groups):
    project, props = groups.dckProject, groups.dckProps
    props.SplitWith(project)
    assert props._values["Width"] == 160 and project.SplitPanels == [project, props]
    top, bottom = geometry(project), geometry(props)
    assert top[0] == bottom[0] == 440 and top[2] == bottom[2] == 160
    handle = project._slot.handles[0]
    assert top[1] == 0 and handle.geometry().top() == top[3]
    assert bottom[1] == handle.geometry().bottom() + 1 and bottom[1] + bottom[3] == 400
    assert abs(top[3] - 3 * bottom[3]) < 4  # their Heights: 300 to 100
    project.Width = 200  # the place's width: both
    assert geometry(props)[2] == 200 and props._values["Width"] == 200
    # Dragging the edge between them
    start = handle.mapToGlobal(QPoint(5, 2))
    QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, QPoint(5, 2))
    handle.mouseMoveEvent(_move_event(handle, start + QPoint(0, -50)))
    QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, QPoint(5, 2))
    assert geometry(project)[3] == top[3] - 50
    # Tabs inside a place shared side by side
    groups.dckOutput.TabWith(props)
    assert groups.dckOutput.Align == vpAlignRight and props.TabPanels == [props,
                                                                           groups.dckOutput]
    assert geometry(groups.dckOutput)[0] == 400 and not props._widget.isVisible()
    # Moved to another edge: on its own there
    props.Align = vpAlignLeft
    assert props._slot is None and geometry(props)[0] == 0


def _move_event(widget, global_point):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    local = widget.mapFromGlobal(global_point)
    return QMouseEvent(QEvent.MouseMove, QPointF(local), QPointF(global_point), Qt.LeftButton,
                       Qt.LeftButton, Qt.NoModifier)


def test_layout_saved_and_loaded(groups):
    immediate, output, project, props = (groups.dckImmediate, groups.dckOutput,
                                         groups.dckProject, groups.dckProps)
    output.TabWith(immediate)
    immediate.Activate()
    props.SplitWith(project)
    groups.Move(50, 60, 640, 420)
    saved = groups.SaveLayout()
    layout = json.loads(saved)
    assert layout["window"]["width"] == 640 and layout["window"]["height"] == 420
    entries = {e["name"]: e for e in layout["dock_panels"]}
    assert entries["dckOutput"]["group"] == "dckImmediate" and entries["dckOutput"]["tab"] == 1
    assert entries["dckProps"]["item"] == 1 and entries["dckImmediate"]["active"]
    output.Separate()
    props.Separate()
    groups.Move(0, 0, 500, 300)
    groups.LoadLayout(saved)
    assert (groups.Width, groups.Height) == (640, 420)
    assert immediate.TabPanels == [immediate, output] and immediate.ActiveTab is immediate
    assert project.SplitPanels == [project, props]
    groups.LoadLayout("")  # (nothing)
    with pytest.raises(ValueError, match="not a layout"):
        groups.LoadLayout("{nonsense")


def test_dock_panels_on_an_mdi_form(qapp):
    from vp6 import MDIForm

    class Workspace(MDIForm):
        def InitializeComponent(self):
            self.Width, self.Height = 600, 400
            self.dckTools = DockPanel(self, Caption="Tools", Align=3, Width=150)
            self.dckOut = DockPanel(self, Caption="Out", Align=2, Height=100)

    form = Workspace()
    form.Show()
    QTest.qWait(10)
    area = form._workspace().geometry()
    assert (area.x(), area.y(), area.width(), area.height()) == (150, 0, 450, 300)
    form.dckOut.TabWith(form.dckTools)
    area = form._workspace().geometry()
    assert (area.x(), area.width(), area.height()) == (150, 450, 400)
    form.Unload()
