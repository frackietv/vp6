"""The Toolbar control, its Buttons collection and Button objects."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from vp6 import (Form, PictureBox, StatusBar, Toolbar, formfile, vpAlignFill, vpAlignLeft,
                 vpTbrButtonGroup, vpTbrCheck, vpTbrDefault, vpTbrPressed, vpTbrSeparator,
                 vpTbrTextAlignBottom, vpTbrTextAlignRight, vpTbrUnpressed)
from vp6.controls import CONTROL_TYPES, parse_button
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

BUTTONS = ["New|new", "Open|open||Open a file", "-", "Bold|bold||Bold|check",
           "-", "Left|left|||group pressed", "Center|center|||group", "Right|right|||group",
           "Secret|secret|||hidden", "Off|off|||disabled"]


def test_parse_button():
    assert parse_button("Open|open|open|Open a file") == {
        "Caption": "Open", "Key": "open", "Image": "open", "ToolTipText": "Open a file",
        "Style": vpTbrDefault, "Value": 0, "Enabled": True, "Visible": True}
    assert parse_button("|bold|2|Bold|check pressed")["Style"] == vpTbrCheck
    assert parse_button("|bold|2|Bold|check pressed")["Image"] == 2  # an Index
    assert parse_button(" - ")["Style"] == vpTbrSeparator
    group = parse_button("L|l|||group disabled hidden")
    assert (group["Style"], group["Enabled"], group["Visible"]) == (vpTbrButtonGroup, False,
                                                                    False)


class Window(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 520, 300
        self.sbMain = StatusBar(self)
        self.tbrMain = Toolbar(self, Buttons=BUTTONS)
        self.picRest = PictureBox(self, Align=vpAlignFill)
        self.clicks = []

    def tbrMain_ButtonClick(self, Button):
        self.clicks.append((Button.Key, Button.Value))


@pytest.fixture
def window(qapp):
    w = Window()
    w.Show()
    QTest.qWait(10)
    yield w
    w.Unload()


def _click(button):
    tool = button._bar._widget.widgetForAction(button._action)
    QTest.mouseClick(tool, Qt.LeftButton)


def test_docked_at_the_top(window):
    bar = window.tbrMain
    assert (bar.Left, bar.Top, bar.Width) == (0, 0, 520)
    assert bar.Height == bar._widget.sizeHint().height()  # as tall as its buttons
    assert window.picRest.Top == bar.Height  # the rest below it (and above the StatusBar)
    window.Width = 600
    QTest.qWait(10)
    assert bar.Width == 600
    bar.Align = vpAlignLeft  # a vertical toolbar
    assert bar._widget.orientation() == Qt.Vertical and window.picRest.Left == bar.Width
    assert window.picRest.Top == 0


def test_buttons(window):
    buttons = window.tbrMain.Buttons
    assert buttons.Count == 10 and buttons("open").Index == 2
    assert [b._action is not None for b in buttons] == [True] * 8 + [False, True]  # hidden
    assert buttons(3).Style == vpTbrSeparator and buttons(3)._action.isSeparator()
    assert buttons("open")._action.toolTip() == "Open a file"
    assert buttons("new")._action.toolTip() == "New"  # the Caption, without a tip
    assert not buttons("off")._action.isEnabled()
    assert buttons("left").Value == vpTbrPressed and buttons("left")._action.isChecked()
    added = buttons.Add(2, "save", "Save")
    assert added.Index == 2 and buttons("open").Index == 3
    added.Caption, added.ToolTipText = "Save all", "Save everything"
    assert added._action.text() == "Save all" and added._action.toolTip() == "Save everything"
    with pytest.raises(KeyError):
        buttons.Add(Key="save")
    buttons("secret").Visible = True
    assert buttons("secret")._action is not None
    buttons.Remove("save")
    assert buttons.Count == 10 and buttons("open").Index == 2
    geometry = buttons("open")
    assert geometry.Width > 0 and geometry.Left > buttons("new").Left  # read-only placement


def test_clicks_check_and_group_buttons(window):
    buttons = window.tbrMain.Buttons
    _click(buttons("open"))
    assert window.clicks == [("open", 0)]
    _click(buttons("bold"))  # a Check button: pressed, then not
    _click(buttons("bold"))
    assert window.clicks[1:] == [("bold", vpTbrPressed), ("bold", vpTbrUnpressed)]
    _click(buttons("center"))  # a ButtonGroup: one of them pressed
    assert [buttons(k).Value for k in ("left", "center", "right")] == [0, 1, 0]
    _click(buttons("center"))  # the pressed one stays pressed (as in VB)
    assert buttons("center").Value == vpTbrPressed and buttons("center")._action.isChecked()
    assert window.clicks[-1] == ("center", vpTbrPressed)
    buttons("right").Value = vpTbrPressed  # code: the group follows, no ButtonClick
    assert [buttons(k).Value for k in ("left", "center", "right")] == [0, 0, 1]
    assert [buttons(k)._action.isChecked() for k in ("left", "center", "right")] == \
        [False, False, True]
    assert window.clicks[-1] == ("center", vpTbrPressed)
    buttons("right").Value = vpTbrUnpressed  # code may leave none pressed
    assert not any(buttons(k)._action.isChecked() for k in ("left", "center", "right"))


def test_pictures_and_text_alignment(qapp, tmp_path, monkeypatch):
    (tmp_path / "open.png").write_bytes(b"")
    image = QImage(24, 24, QImage.Format_ARGB32)
    image.fill(QColor("orange"))
    image.save(str(tmp_path / "open.png"))
    (tmp_path / "Bar.py").write_text(
        "from vp6 import *\n\n\n"
        "class Bar(Form):\n"
        "    def InitializeComponent(self):\n"
        "        self.tbr = Toolbar(self, ImageList='iml', "
        "Buttons=['Open|open|open', 'Two|two|1'])\n"
        "        self.iml = ImageList(self, ListImages=['open.png|open'])\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    from Bar import Bar
    form = Bar()
    bar = form.tbr
    assert all(not b._action.icon().isNull() for b in bar.Buttons)  # by key and by Index
    assert bar._widget.iconSize().toTuple() == (24, 24)  # the ImageList's size
    assert bar._widget.toolButtonStyle() == Qt.ToolButtonTextUnderIcon
    bar.TextAlignment = vpTbrTextAlignRight
    assert bar._widget.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
    with pytest.raises(KeyError):
        bar.Buttons("open").Image = "nothing"
    bar.Buttons.Add(Key="more", Caption="More", Image="open")
    assert not bar.Buttons("more")._action.icon().isNull()
    assert vpTbrTextAlignBottom == 0


def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.tbr = Toolbar(self, Left=0, Top=0, Width=400, Height=40, "
            "Buttons=['Open|open|open|Open a file', '-', '|bold|bold|Bold|check'], "
            "TextAlignment=1)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("tbr").props["Buttons"][1] == "-"
    region = formfile.generate_region(form)
    assert "Buttons=['Open|open|open|Open a file', '-', '|bold|bold|Bold|check']" in region


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("Toolbar", QRect(origin + QPoint(16, 100), origin + QPoint(300, 140)),
                            None)
    assert name == "Toolbar1"
    bar = d.controls[name]
    assert bar.Top == 0 and bar.Buttons.Count == 1  # docked at the top; one button
    d.select([name])
    assert d.set_property("Buttons", BUTTONS) is None
    assert bar.Buttons.Count == 10 and "Buttons=['New|new'," in d.document.text
    bar.Buttons("new")._action.trigger()  # no ButtonClick while designing (no handler runs)
    window = PropertiesWindow()
    window.set_designer(d)
    row = next(r for r in range(window.table.rowCount())
               if window.table.item(r, 0).text() == "Buttons")
    assert window.table.cellWidget(row, 1).text() == "(Buttons: 10)"
    d.close()


def test_toolbox_icon_and_constants(qapp):
    assert "Toolbar" in Toolbox().buttons and "Toolbar" in CONTROL_TYPES
    assert Toolbar.DefaultEvent == "ButtonClick"
    assert not icons.icon("Toolbar").isNull()
    assert (vpTbrDefault, vpTbrCheck, vpTbrButtonGroup, vpTbrSeparator) == (0, 1, 2, 3)
    assert (vpTbrUnpressed, vpTbrPressed) == (0, 1)
