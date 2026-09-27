import os

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

from conftest import wait_for
from PySide6.QtWidgets import QApplication, QMessageBox

from vp6 import *  # noqa: F403
from vp6 import app as vp6_app


class SampleForm(Form):
    def InitializeComponent(self):
        self.Caption = "Sample"
        self.Frame1 = Frame(self, Caption="Group", Left=8, Top=8, Width=200, Height=120)
        self.Option1 = OptionButton(self.Frame1, Caption="A", Left=8, Top=24, Value=True)
        self.Option2 = OptionButton(self.Frame1, Caption="B", Left=8, Top=48)
        self.Command1 = CommandButton(self, Caption="&OK", Left=220, Top=8, Default=True)
        self.Command2 = CommandButton(self, Caption="Cancel", Left=220, Top=48, Cancel=True)
        self.Text1 = TextBox(self, Text="", Left=8, Top=140)
        self.Check1 = CheckBox(self, Caption="Check", Left=8, Top=170)
        self.List1 = ListBox(self, List=["pear", "apple"], Left=8, Top=200, Sorted=True)
        self.Combo1 = ComboBox(self, Style=2, List=["x", "y", "z"], Text="y", Left=140, Top=200)
        self.Timer1 = Timer(self, Interval=0)

    def __init__(self):
        self.log = []
        super().__init__()

    def Form_Load(self):
        self.log.append("Load")

    def Form_Unload(self):
        self.log.append("Unload")
        return self.Tag == "keep"

    def Command1_Click(self):
        self.log.append("OK")

    def Command2_Click(self):
        self.log.append("Cancel")

    def Text1_Change(self):
        self.log.append("Change:" + self.Text1.Text)

    def Text1_KeyPress(self, KeyAscii):
        if chr(KeyAscii).isdigit():
            return 0  # reject digits
        return ord(chr(KeyAscii).upper())

    def Check1_Click(self):
        self.log.append(f"Check:{self.Check1.Value}")

    def Timer1_Timer(self):
        self.log.append("Tick")
        self.Timer1.Enabled = False

    def List1_Click(self):
        self.log.append("List:" + self.List1.Text)

    def Option2_Click(self):
        self.log.append("Option2")


@pytest.fixture
def form(qapp):
    f = SampleForm()
    f.Show()
    yield f
    f.Tag = ""
    f.Unload()


def test_controls_are_named_and_nested(form):
    assert [c.Name for c in form.Controls][:3] == ["Frame1", "Option1", "Option2"]
    assert form.Option1.Parent is form.Frame1
    assert form.Option1.Container is form.Frame1
    assert form.log == ["Load"]
    assert form.Caption == "Sample"


def test_click_and_default_cancel_buttons(form):
    form.Command1._widget.click()
    QTest.keyClick(form.Text1._widget, Qt.Key_Return)
    QTest.keyClick(form.Text1._widget, Qt.Key_Escape)
    assert form.log[1:] == ["OK", "OK", "Cancel"]


def test_keypress_can_transform_and_cancel(form):
    QTest.keyClicks(form.Text1._widget, "ab1c")
    assert form.Text1.Text == "ABC"
    assert form.log[-1] == "Change:ABC"


def test_value_properties_fire_click(form):
    form.Check1.Value = vpChecked
    assert form.Check1.Value == 1
    form.Option2.Value = True
    assert form.Option1.Value is False
    assert form.log[1:] == ["Check:1", "Option2"]


def test_list_and_combo(form):
    assert form.List1.List == ["apple", "pear"]
    form.List1.AddItem("banana")
    assert form.List1.List == ["apple", "banana", "pear"]
    form.List1.ListIndex = 1
    assert form.List1.Text == "banana"
    assert form.log[-1] == "List:banana"
    form.List1.RemoveItem(0)
    assert form.List1.ListCount == 2
    assert form.Combo1.Text == "y" and form.Combo1.ListIndex == 1


def test_timer(form):
    form.Timer1.Interval = 10
    wait_for(lambda: "Tick" in form.log, 1000)
    QTest.qWait(50)
    assert form.log.count("Tick") == 1


def test_unload_can_be_cancelled(form):
    form.Tag = "keep"
    assert form.Unload() is False
    assert form.Visible
    form.Tag = ""
    assert form.Unload() is True
    assert form.log[-2:] == ["Unload", "Unload"]
    assert form not in list(Forms)


def test_misspelled_property_raises(form):
    with pytest.raises(AttributeError):
        form.Command1.Captoin = "x"
    with pytest.raises(AttributeError):
        CommandButton(form, Captoin="x")


def test_multiline_textbox_switch_keeps_text(form):
    form.Text1.Text = "hello"
    form.Text1.MultiLine = True
    assert form.Text1.Text == "hello"
    form.Text1.Text = "a\nb"
    assert form.Text1.Text == "a\nb"


def test_colors():
    assert RGB(255, 0, 0) == vpRed == 0x0000FF
    assert QBColor(12) == vpRed
    from vp6 import colors

    assert colors.normalize("#0000ff") == vpBlue


def test_handler_arity_and_errors(qapp, capsys):
    calls = []

    class F(Form):
        def InitializeComponent(self):
            self.Picture1 = PictureBox(self)

        def Picture1_MouseDown(self, Button):  # declares fewer args than VB passes
            calls.append(Button)

        def Picture1_Click(self):
            raise ValueError("boom")

    f = F()
    f.Show()
    QTest.mouseClick(f.Picture1._widget, Qt.LeftButton, pos=f.Picture1._widget.rect().center())
    assert calls == [vpLeftButton]
    assert "ValueError: boom" in capsys.readouterr().err
    f.Unload()


def test_msgbox_returns_vp_constants(qapp):
    def answer():
        box = QApplication.activeModalWidget()
        box.button(QMessageBox.No).click()

    QTimer.singleShot(50, answer)
    assert MsgBox("Continue?", vpYesNo + vpQuestion) == vpNo


def test_handler_call_passes_only_declared_args():
    received = []
    vp6_app.call_handler(lambda a, b: received.append((a, b)), 1, 2, 3, 4)
    vp6_app.call_handler(lambda *args: received.append(args), 1, 2)
    assert received == [(1, 2), (1, 2)]


# --- ZIndex (stacking order) ------------------------------------------------------------

def _stack(container_widget):
    """Child widgets bottom to top (Qt keeps children in stacking order)."""
    return [w._vp_control.Name for w in container_widget.children()
            if getattr(w, "_vp_control", None) is not None]


class StackForm(Form):
    def InitializeComponent(self):
        self.Label1 = Label(self, Caption="one", Left=0, Top=0, ZIndex=2)
        self.Label2 = Label(self, Caption="two", Left=10, Top=10)
        self.Label3 = Label(self, Caption="three", Left=20, Top=20)
        self.Frame1 = Frame(self, Caption="f", Left=0, Top=40, ZIndex=-1)
        self.Check1 = CheckBox(self.Frame1, Caption="in frame", ZIndex=5)
        self.Check2 = CheckBox(self.Frame1, Caption="also in frame")
        self.Timer1 = Timer(self, Interval=0)


def test_zindex_orders_controls_at_creation(qapp):
    form = StackForm()
    # Equal ZIndex keeps creation order; higher is on top; containers stack separately
    assert _stack(form._widget) == ["Frame1", "Label2", "Label3", "Label1"]
    assert _stack(form.Frame1._widget) == ["Check2", "Check1"]
    assert not hasattr(form.Timer1, "ZIndex") or "ZIndex" not in form.Timer1._specs


def test_zindex_changes_take_effect_immediately(qapp):
    form = StackForm()
    form.Show()
    form.Label2.ZIndex = 10
    assert _stack(form._widget)[-1] == "Label2"
    form.Label2.ZIndex = -10
    assert _stack(form._widget)[0] == "Label2"
    top_at = form._widget.childAt(15, 15)  # where Label1-3 overlap
    assert top_at._vp_control is form.Label1  # ZIndex 2 beats Label3's 0
    form.Unload()


def test_zorder_method_sets_zindex(qapp):
    form = StackForm()
    form.Label2.ZOrder(0)  # bring to front
    assert form.Label2.ZIndex == 3 and _stack(form._widget)[-1] == "Label2"
    form.Label2.ZOrder(0)  # already on top: unchanged
    assert form.Label2.ZIndex == 3
    form.Label2.ZOrder(1)  # send to back
    assert form.Label2.ZIndex == -2 and _stack(form._widget)[0] == "Label2"


def test_rebuilt_widget_keeps_its_place(qapp):
    class F(Form):
        def InitializeComponent(self):
            self.Text1 = TextBox(self, ZIndex=-1)
            self.Label1 = Label(self)

    form = F()
    form.Text1.MultiLine = True  # replaces the widget
    assert _stack(form._widget) == ["Text1", "Label1"]


def test_end_stops_without_unload_events(tmp_path):
    """End() ends the program at once: no Form_Unload (e.g. no "Close?"
    question), like VB's End statement. It ends the process, so the program
    runs in one of its own."""
    import subprocess
    import sys

    marker = tmp_path / "unloaded.txt"
    script = tmp_path / "ender.py"
    script.write_text(f"""
from vp6 import *


class frmMain(Form):
    def Form_Load(self):
        self.tmrEnd = Timer(self, Interval=50)

    def tmrEnd_Timer(self):
        print("ending", flush=True)
        End()

    def Form_Unload(self):
        open({str(marker)!r}, "w").write("Form_Unload ran")
        return True  # would cancel a normal close


run(frmMain)
print("after run", flush=True)
""")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=root,
               VP6_NO_ERROR_DIALOG="1")
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ending\n"  # nothing after End()
    assert not marker.exists()  # Form_Unload didn't run
