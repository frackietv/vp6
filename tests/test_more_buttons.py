"""CommandLink, ToolButton and ButtonBox."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox

import vp6
from vp6 import ButtonBox, CommandLink, Form, Menu, TextBox, ToolButton, formfile
from vp6.buttons import parse_box_button


@pytest.fixture
def form(qapp):
    class Buttons(Form):
        def InitializeComponent(self):
            self.events = []
            self.txtName = TextBox(self, Text="")
            self.lnkGo = CommandLink(self, Caption="&Go", Description="Off we go")
            self.tbnBold = ToolButton(self, Caption="B", Checkable=True)
            self.tbnColor = ToolButton(self, Caption="Color", PopupMenu="mnuColors",
                                       ArrowType=2)
            self.bbxDialog = ButtonBox(self, Buttons=["OK", "Cancel", "&Print|action"])
            self.mnuColors = Menu(self, Caption="Colors", Visible=False)
            self.mnuRed = Menu(self.mnuColors, Caption="&Red")

        def lnkGo_Click(self):
            self.events.append("Go")

        def tbnBold_Click(self):
            self.events.append(("Bold", self.tbnBold.Value))

        def tbnColor_ButtonMenuClick(self, ButtonMenu):
            self.events.append(("Menu", ButtonMenu.Name))

        def mnuRed_Click(self):
            self.events.append("Red")

        def bbxDialog_ButtonClick(self, Index):
            self.events.append(("Button", Index))

        def bbxDialog_Accepted(self):
            self.events.append("Accepted")

        def bbxDialog_Rejected(self):
            self.events.append("Rejected")

    f = Buttons()
    f.Show()
    yield f
    f.Unload()


def test_commandlink(form):
    link = form.lnkGo
    assert link._widget.text() == "&Go" and link._widget.description() == "Off we go"
    link._widget.click()
    link.Value = True
    assert form.events == ["Go", "Go"]
    assert not link._widget.icon().isNull()  # (the platform's arrow)
    link.Description = "Somewhere else"
    assert link._widget.description() == "Somewhere else"


def test_commandlink_is_the_default_button(form):
    form.bbxDialog.Visible = False  # (its OK would be the Default otherwise)
    form.lnkGo.Default = True
    QTest.keyClick(form.txtName._widget, Qt.Key_Return)
    assert form.events == ["Go"]


def test_toolbutton(form):
    bold = form.tbnBold
    bold._widget.click()
    assert bold.Value and form.events == [("Bold", True)]
    bold.Value = False
    assert not bold._widget.isChecked()
    assert bold._widget.toolButtonStyle() == Qt.ToolButtonTextOnly  # (no picture: its text)
    color = form.tbnColor
    assert color._widget.menu() is form.mnuColors._submenu
    assert color._widget.popupMode() == color._widget.ToolButtonPopupMode.MenuButtonPopup
    assert color._widget.arrowType() == Qt.DownArrow
    form.events.clear()
    color._widget.setDown(True)  # (chosen from the button's menu)
    form.mnuRed._action.trigger()
    color._widget.setDown(False)
    assert form.events == ["Red", ("Menu", "mnuRed")]
    form.events.clear()
    form.mnuRed._action.trigger()  # (from elsewhere: no ButtonMenuClick)
    assert form.events == ["Red"]
    assert form.tbnBold._widget.popupMode() == color._widget.ToolButtonPopupMode.DelayedPopup


def test_toolbutton_picture(qapp, tmp_path):
    picture = vp6.Picture(16, 16, BackColor=vp6.vpRed)

    class Pics(Form):
        def InitializeComponent(self):
            self.tbnPic = ToolButton(self, Caption="Red", Picture=picture, ButtonStyle=3)

    f = Pics()
    try:
        assert not f.tbnPic._widget.icon().isNull()
        assert f.tbnPic._widget.toolButtonStyle() == Qt.ToolButtonTextUnderIcon
    finally:
        f.Unload()


def test_parse_box_button():
    assert parse_box_button("OK")[2] == QDialogButtonBox.Ok
    assert parse_box_button("Restore Defaults")[2] == QDialogButtonBox.RestoreDefaults
    assert parse_box_button("&Print|action") == ("&Print", 3, None)
    assert parse_box_button("Go|accept") == ("Go", 0, None)
    assert parse_box_button("Wipe|2") == ("Wipe", 2, None)
    assert parse_box_button("Whatever") == ("Whatever", 3, None)


def test_buttonbox(form):
    box = form.bbxDialog
    assert box.ListCount == 3
    assert [box.ButtonRole(i) for i in range(3)] == [vp6.vpRoleAccept, vp6.vpRoleReject,
                                                    vp6.vpRoleAction]
    box._buttons[2][0].click()
    box._buttons[0][0].click()
    box._buttons[1][0].click()
    assert form.events == [("Button", 2), ("Button", 0), "Accepted", ("Button", 1), "Rejected"]
    form.events.clear()
    QTest.keyClick(form.txtName._widget, Qt.Key_Return)  # its OK is the Default
    QTest.keyClick(form.txtName._widget, Qt.Key_Escape)  # and its Cancel the Cancel
    assert form.events == [("Button", 0), "Accepted", ("Button", 1), "Rejected"]
    box.ButtonCaption[2] = "&Print all"
    assert box.ButtonCaption(2) == "&Print all"
    box.ButtonEnabled[0] = False
    assert not box.ButtonEnabled(0)
    with pytest.raises(IndexError):
        box.ButtonCaption(9)
    index = box.AddButton("&Help me", vp6.vpRoleHelp)
    assert index == 3 and box.ButtonRole(3) == vp6.vpRoleHelp
    box.RemoveButton(2)
    assert box.ListCount == 3 and box.Buttons == ["OK", "Cancel", "&Help me|4"]
    box.Orientation = vp6.vpOrientationVertical
    assert box._widget.orientation() == Qt.Vertical


def test_designer_writes_them(qapp, tmp_path):
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument

    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    for type_name in ("CommandLink", "ToolButton", "ButtonBox"):
        designer.create_control(type_name, None, None)
    text = designer.document.text
    assert "self.Link1 = CommandLink(self, Caption='Link1'" in text
    assert "self.ToolButton1 = ToolButton(self" in text and "self.ButtonBox1 = ButtonBox(" in text
