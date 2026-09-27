"""The StatusBar control, its Panels collection and Panel objects."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from vp6 import (Form, PictureBox, StatusBar, formfile, vpAlignLeft, vpSbrCaps, vpSbrCenter,
                 vpSbrContents, vpSbrDate, vpSbrNormal, vpSbrRight, vpSbrSimple, vpSbrSpring,
                 vpSbrText, vpSbrTime)
from vp6 import controls
from vp6.controls import CONTROL_TYPES, parse_panel
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

PANELS = ["Ready|status|spring", "|caps|caps 50 center", "|clock|time 80 right"]


def test_parse_panel():
    assert parse_panel("Ready|status|spring") == {"Text": "Ready", "Key": "status",
                                                  "AutoSize": 1}
    assert parse_panel(" | clock | TIME 80 right") == {"Text": "", "Key": "clock", "Style": 5,
                                                       "Width": 80, "Alignment": 2}
    assert parse_panel("Just text") == {"Text": "Just text", "Key": ""}
    assert parse_panel("x|k|contents date center")["AutoSize"] == 2


class Window(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 500, 300
        self.sbMain = StatusBar(self, Panels=PANELS)
        self.picNav = PictureBox(self, Align=vpAlignLeft, Width=100)
        self.events = []

    def sbMain_PanelClick(self, Panel):
        self.events.append(("PanelClick", Panel.Key))

    def sbMain_PanelDblClick(self, Panel):
        self.events.append(("PanelDblClick", Panel.Key))

    def sbMain_Click(self):
        self.events.append("Click")


@pytest.fixture
def window(qapp):
    w = Window()
    w.Show()
    QTest.qWait(10)
    yield w
    w.Unload()


def _widths(bar):
    return [panel._label.width() for panel in bar.Panels if panel._label is not None]


def test_docked_at_the_bottom(window):
    bar = window.sbMain
    assert (bar.Left, bar.Top, bar.Width, bar.Height) == (0, 275, 500, 25)
    assert (window.picNav.Top, window.picNav.Height) == (0, 275)  # beside it: above the bar
    window.Width = 600
    QTest.qWait(10)
    assert bar.Width == 600 and _widths(bar)[1:] == [50, 80]  # the Spring panel grows
    assert _widths(bar)[0] > 400
    bar.Align = 1  # Top
    assert bar.Top == 0 and window.picNav.Top == 25
    bar.Visible = False  # hidden: no space
    assert window.picNav.Top == 0 and window.picNav.Height == window.ScaleHeight


def test_panels_collection(window):
    panels = window.sbMain.Panels
    assert panels.Count == 3 and [p.Index for p in panels] == [1, 2, 3]
    assert panels(1) is panels("status") is panels.Item("status")
    status = panels("status")
    assert (status.Text, status.AutoSize, status.Style) == ("Ready", vpSbrSpring, vpSbrText)
    status.Text = "Working"
    assert status._label.text() == "Working"
    mode = panels.Add(2, "mode", "EDIT")  # at Index 2
    assert [p.Key for p in panels] == ["status", "mode", "caps", "clock"]
    assert mode.Index == 2 and mode.Width == 96  # the default width
    mode.AutoSize = vpSbrContents
    mode.Text = "A much longer mode text"
    assert mode._label.width() > 96  # as wide as its text
    mode.Width = 40
    mode.AutoSize = 0  # fixed: its Width
    assert mode._label.width() == 40
    mode.Alignment = vpSbrCenter
    assert mode._label.alignment() & Qt.AlignHCenter
    mode.ToolTipText = "The editing mode"
    assert mode._label.toolTip() == "The editing mode"
    with pytest.raises(KeyError):
        panels.Add(Key="mode")  # keys are unique
    with pytest.raises(KeyError):
        panels("nothing")
    with pytest.raises(IndexError):
        panels(9)
    mode.Visible = False  # a hidden panel: no label
    assert mode._label is None and len(_widths(window.sbMain)) == 3
    panels.Remove("mode")
    panels.Remove(1)
    assert [p.Key for p in panels] == ["caps", "clock"]
    added = panels.Add(Text="end")  # at the end
    assert added.Index == 3 and added.Key == ""
    panels("caps").Key = "lock"
    assert panels("lock").Index == 1
    panels.Clear()
    assert panels.Count == 0


def test_time_date_and_lock_keys(window, monkeypatch):
    from PySide6.QtCore import QDate, QLocale, QTime
    panels = window.sbMain.Panels
    clock = panels("clock")
    assert clock._label.text() == QLocale().toString(QTime.currentTime(), QLocale.ShortFormat)
    assert window.sbMain._timer.isActive()  # kept up to date
    clock.Style = vpSbrDate
    assert clock._label.text() == QLocale().toString(QDate.currentDate(), QLocale.ShortFormat)
    assert clock.Text == ""  # its own Text is kept
    caps = panels("caps")
    assert caps._label.text() == "CAPS" and caps.Style == vpSbrCaps
    monkeypatch.setattr(controls, "_lock_key_on", lambda style: True)
    window.sbMain._refresh_live_panels()
    assert caps._label.isEnabled()  # on: shown normally
    monkeypatch.setattr(controls, "_lock_key_on", lambda style: False)
    window.sbMain._refresh_live_panels()
    assert not caps._label.isEnabled()  # off: dimmed
    for panel in list(panels):
        panel.Style = vpSbrText
    assert not window.sbMain._timer.isActive()  # nothing to keep up to date


def test_simple_style(window):
    bar = window.sbMain
    bar.SimpleText = "Saving..."
    bar.Style = vpSbrSimple
    assert bar._simple_label.isVisible() and bar._simple_label.text() == "Saving..."
    assert all(p._label is None for p in bar.Panels)  # the panels are kept, not shown
    bar.Style = vpSbrNormal
    assert not bar._simple_label.isVisible() and bar.Panels("status")._label.isVisible()


def test_panel_click_events(window):
    bar = window.sbMain._widget
    label = window.sbMain.Panels("clock")._label
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, label.geometry().center())
    assert window.events == [("PanelClick", "clock"), "Click"]
    QTest.mouseDClick(bar, Qt.LeftButton, Qt.NoModifier, label.geometry().center())
    assert ("PanelDblClick", "clock") in window.events


def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.sb = StatusBar(self, Left=0, Top=275, Width=500, Height=25, "
            "Panels=['Ready|status|spring', '|clock|time 80'])\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("sb").props["Panels"] == ["Ready|status|spring", "|clock|time 80"]
    assert "Panels=['Ready|status|spring', '|clock|time 80']" in formfile.generate_region(form)


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("StatusBar", QRect(origin + QPoint(16, 16), origin + QPoint(200, 40)),
                            None)
    assert name == "StatusBar1"
    bar = d.controls[name]
    assert bar.Top + bar.Height == d.form.ScaleHeight  # docked to the bottom
    assert bar.Panels.Count == 1  # one Spring panel to start with
    d.select([name])
    assert d.set_property("Panels", PANELS) is None
    assert bar.Panels.Count == 3 and not bar._timer.isActive()  # no clock while designing
    assert "Panels=['Ready|status|spring'," in d.document.text
    window = PropertiesWindow()
    window.set_designer(d)
    row = next(r for r in range(window.table.rowCount())
               if window.table.item(r, 0).text() == "Panels")
    assert window.table.cellWidget(row, 1).text() == "(Panels: 3)"
    d.close()


def test_toolbox_icon_and_constants(qapp):
    assert "StatusBar" in Toolbox().buttons and "StatusBar" in CONTROL_TYPES
    assert StatusBar.DefaultEvent == "PanelClick"
    assert not icons.icon("StatusBar").isNull()
    assert (vpSbrText, vpSbrCaps, vpSbrTime, vpSbrDate) == (0, 1, 5, 6)
    assert (vpSbrSpring, vpSbrContents, vpSbrCenter, vpSbrRight) == (1, 2, 1, 2)
