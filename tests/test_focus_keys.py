"""Focus and keyboard: Validate and CausesValidation, Form.ActiveControl and
Screen.ActiveControl, SendKeys."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from vp6 import (CommandButton, Form, Label, Menu, Screen, SendKeys, TextBox, UserControl,
                 vpShiftMask)
from vp6.app import parse_keys
from vp6.controls import CONTROL_TYPES, EVENT_ARGS

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class ctlBox(UserControl):
    def InitializeComponent(self):
        self.Surface.Width = 120
        self.Surface.Height = 30
        self.txtInside = TextBox(self, Left=0, Top=0, Width=120, Height=25)


class Entry(Form):
    def InitializeComponent(self):
        self.events = []
        self.KeyPreview = True
        self.lblCity = Label(self, Caption="Ci&ty:", Left=10, Top=160, Width=50, Height=20,
                             TabIndex=5)  # (its access key: the control after it, txtCode)
        self.txtAge = TextBox(self, Left=10, Top=10, TabIndex=1)
        self.txtCity = TextBox(self, Left=10, Top=40, TabIndex=2)
        self.cmdOK = CommandButton(self, Left=10, Top=70, Default=True, TabIndex=3)
        self.cmdHelp = CommandButton(self, Left=10, Top=110, CausesValidation=False, TabIndex=4)
        self.txtCode = TextBox(self, Left=200, Top=10, TabIndex=6)
        self.ctl = ctlBox(self, Left=200, Top=50, TabIndex=7)
        self.mnuFile = Menu(self, Caption="&File")
        self.mnuFileSave = Menu(self.mnuFile, Caption="&Save", Shortcut="Ctrl+S")

    def txtAge_Validate(self):
        self.events.append("Validate")
        return not self.txtAge.Text.isdigit()  # True: the focus stays

    def txtAge_LostFocus(self):
        self.events.append("txtAge_LostFocus")

    def txtAge_GotFocus(self):
        self.events.append("txtAge_GotFocus")

    def txtCity_GotFocus(self):
        self.events.append("txtCity_GotFocus")

    def cmdOK_Click(self):
        self.events.append("OK")

    def cmdHelp_Click(self):
        self.events.append("Help")

    def mnuFileSave_Click(self):
        self.events.append("Save")

    def Form_KeyDown(self, KeyCode, Shift):
        if Shift & vpShiftMask:
            self.events.append(("Shift", KeyCode))


@pytest.fixture
def form(qapp):
    form = Entry()
    form.Show()
    form._widget.activateWindow()
    QTest.qWait(20)
    form.txtAge.SetFocus()
    QTest.qWait(10)
    form.events.clear()
    yield form
    form.txtAge.Text = "1"
    form.Unload()


def focus(control):
    control.SetFocus()
    QTest.qWait(20)


# --- Validate ------------------------------------------------------------------------------------

def test_validate_keeps_the_focus(form):
    form.txtAge.Text = "old"
    focus(form.txtCity)
    assert form.events == ["Validate"]  # no LostFocus, no GotFocus anywhere
    assert form.ActiveControl is form.txtAge
    form.txtAge.Text = "42"
    focus(form.txtCity)
    assert form.events[1:] == ["Validate", "txtAge_LostFocus", "txtCity_GotFocus"]
    assert form.ActiveControl is form.txtCity
    form.events.clear()
    focus(form.txtAge)
    assert "Validate" not in form.events  # (only the control left has it)


def test_causes_validation(form):
    form.txtAge.Text = "old"
    focus(form.cmdHelp)  # CausesValidation = False: no Validate
    assert "Validate" not in form.events and form.ActiveControl is form.cmdHelp
    assert form.cmdHelp.CausesValidation is False and form.txtCity.CausesValidation is True


def test_a_button_clicked_while_invalid_doesnt_click(form):
    form.txtAge.Text = "old"
    QTest.mouseClick(form.cmdOK._widget, Qt.LeftButton)
    QTest.qWait(20)
    assert "OK" not in form.events and form.ActiveControl is form.txtAge
    QTest.mouseClick(form.cmdHelp._widget, Qt.LeftButton)  # not waiting for validity
    assert "Help" in form.events
    form.txtAge.Text = "5"
    focus(form.txtAge)
    QTest.mouseClick(form.cmdOK._widget, Qt.LeftButton)
    assert "OK" in form.events


def test_validate_for_controls_that_take_the_focus():
    for name in ("TextBox", "CommandButton", "ComboBox", "ListBox", "FlexGrid", "CodeBox"):
        cls = CONTROL_TYPES[name]
        assert "Validate" in cls.Events and cls._specs["CausesValidation"].default is True
    for name in ("Label", "Frame", "Timer", "Line", "PictureBox"):
        assert "Validate" not in CONTROL_TYPES[name].Events
    assert EVENT_ARGS["Validate"] == ""


# --- ActiveControl --------------------------------------------------------------------------------

def test_active_control(form):
    assert form.ActiveControl is form.txtAge and Screen.ActiveControl is form.txtAge
    form.txtAge.Text = "7"  # (valid: the focus may leave)
    focus(form.ctl.txtInside)  # in a user control: the user control
    assert form.ActiveControl is form.ctl and Screen.ActiveControl is form.ctl
    other = Form()
    assert other.ActiveControl is None
    other._widget.close()


# --- SendKeys -------------------------------------------------------------------------------------

def test_parsing():
    def keys(text):
        return [(int(k), m.value, t) for k, m, t in parse_keys(text)]

    shift, ctrl, alt = (m.value for m in (Qt.ShiftModifier, Qt.ControlModifier, Qt.AltModifier))
    assert keys("aB") == [(int(Qt.Key_A), 0, "a"), (int(Qt.Key_B), shift, "B")]
    assert keys("+c") == [(int(Qt.Key_C), shift, "C")]
    assert keys("^(xy)") == [(int(Qt.Key_X), ctrl, "x"), (int(Qt.Key_Y), ctrl, "y")]
    assert keys("%{F4}") == [(int(Qt.Key_F4), alt, "")]
    assert keys("~{ENTER}{TAB}") == [(int(Qt.Key_Return), 0, "\r")] * 2 + [
        (int(Qt.Key_Tab), 0, "\t")]
    assert keys("{LEFT 3}") == [(int(Qt.Key_Left), 0, "")] * 3
    assert keys("{x 2}") == [(int(Qt.Key_X), 0, "x")] * 2
    assert [t for _k, _m, t in keys("{+}{^}{%}{~}{(}{)}{{}{}}")] == list("+^%~(){}")
    assert keys("{bs}") == [(int(Qt.Key_Backspace), 0, "\b")]  # (any case)
    for bad in ("{NOPE}", "{ENTER", "(ab", "a)"):
        with pytest.raises(ValueError, match="SendKeys"):
            parse_keys(bad)


def test_send_keys(form):
    form.txtAge.Text = ""
    SendKeys("12{TAB}", Wait=True)  # at once, to whatever has the focus
    assert form.txtAge.Text == "12" and form.ActiveControl is form.txtCity
    SendKeys("Paris~")  # later: once this code is done
    assert form.txtCity.Text == ""
    QTest.qWait(50)
    assert form.txtCity.Text == "Paris" and form.events[-1] == "OK"  # Enter: Default button
    assert ("Shift", 80) in form.events  # (the P: Shift, as typed)
    form.events.clear()
    SendKeys("^s", Wait=True)  # a menu's Shortcut
    assert form.events == ["Save"]
    SendKeys("%t", Wait=True)  # a Label's access key: the box after it
    assert form.ActiveControl is form.txtCode
    SendKeys("{BS}+x{HOME}", Wait=True)
    assert form.txtCode.Text == "X" and form.txtCode.SelStart == 0
