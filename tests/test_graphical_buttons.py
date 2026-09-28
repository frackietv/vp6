"""Style = Graphical: CommandButton pictures, and CheckBox and OptionButton toggle buttons."""

import os
import sys

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QToolButton

from vp6 import formfile, vpChecked, vpUnchecked
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


@pytest.fixture
def form(qapp, tmp_path, monkeypatch):
    for name, color in (("up", "red"), ("down", "green"), ("off", "gray")):
        image = QImage(24, 24, QImage.Format_ARGB32)
        image.fill(QColor(color))
        image.save(str(tmp_path / f"{name}.png"))
    (tmp_path / "Buttons.py").write_text(
        "from vp6 import *\n\n\n"
        "class Buttons(Form):\n"
        "    def InitializeComponent(self):\n"
        "        self.cmd = CommandButton(self, Caption='&Go', Style=1, Picture='up.png', "
        "DownPicture='down.png', DisabledPicture='off.png', Default=True)\n"
        "        self.cmdPlain = CommandButton(self, Caption='Plain', Picture='up.png')\n"
        "        self.chk = CheckBox(self, Caption='Bold', Style=1, Value=1)\n"
        "        self.opt = ControlArray()\n"
        "        self.opt[0] = OptionButton(self, Caption='A', Style=1, Value=True)\n"
        "        self.opt[1] = OptionButton(self, Caption='B', Style=1)\n"
        "        self.optPlain = OptionButton(self, Caption='C')\n"
        "        self.log = []\n\n"
        "    def cmd_Click(self):\n"
        "        self.log.append('cmd')\n\n"
        "    def chk_Click(self):\n"
        "        self.log.append(('chk', self.chk.Value))\n\n"
        "    def opt_Click(self, Index):\n"
        "        self.log.append(('opt', Index))\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    from Buttons import Buttons
    f = Buttons()
    f.Show()
    yield f
    f.Unload()
    sys.modules.pop("Buttons", None)


def _color(button):
    return button.icon().pixmap(24).toImage().pixelColor(5, 5).name()


def test_a_picture_button(form):
    cmd = form.cmd._widget
    assert isinstance(cmd, QToolButton) and isinstance(form.cmdPlain._widget, QPushButton)
    assert form.cmdPlain._widget.icon().isNull()  # Standard: no picture, as in VB
    assert cmd.toolButtonStyle() == Qt.ToolButtonTextUnderIcon  # the picture above
    assert _color(cmd) == "#ff0000" and cmd.text() == "&Go"
    cmd.setDown(True)  # pressed: the DownPicture
    form.cmd._update_picture()
    assert _color(cmd) == "#008000"
    cmd.setDown(False)
    form.cmd._update_picture()
    form.cmd.Value = True  # clicks it, like a Standard one
    assert form.log == ["cmd"]
    form.cmd.Enabled = False
    assert _color(cmd) == "#808080"  # the DisabledPicture
    form.cmd.Enabled = True
    form.cmd.Caption = ""
    assert cmd.toolButtonStyle() == Qt.ToolButtonIconOnly
    form.cmd.Picture = ""
    assert cmd.icon().isNull() and cmd.toolButtonStyle() == Qt.ToolButtonTextOnly
    # Enter on the form clicks the Default button, Graphical or not
    form._handle_default_cancel(form.chk, type("Key", (), {"key": lambda self: Qt.Key_Return})())
    assert form.log == ["cmd", "cmd"]


def test_toggle_buttons(form):
    chk = form.chk._widget
    assert isinstance(chk, QToolButton) and chk.isCheckable() and chk.isChecked()
    chk.click()  # pressed -> not
    assert form.chk.Value == vpUnchecked and form.log[-1] == ("chk", 0)
    form.chk.Value = vpChecked  # code: pressed (and Click, as for any CheckBox)
    assert chk.isChecked() and form.log[-1] == ("chk", 1)
    form.chk.Value = 2  # Grayed: not pressed
    assert not chk.isChecked()
    # Graphical OptionButtons: exclusive with the container's others, Graphical or not
    assert form.opt[0].Value and form.opt[0]._widget.isChecked()
    form.opt[1]._widget.click()
    assert (form.opt[0].Value, form.opt[1].Value, form.optPlain.Value) == (False, True, False)
    assert form.log[-1] == ("opt", 1)
    form.opt[1]._widget.click()  # clicking the pressed one: it stays pressed
    assert form.opt[1].Value
    form.optPlain._widget.click()
    assert (form.opt[0].Value, form.opt[1].Value, form.optPlain.Value) == (False, False, True)


def test_changing_the_style(form):
    form.log.clear()
    form.chk.Value = vpChecked
    form.log.clear()
    form.chk.Style = 0  # Standard again: a check box, still checked, no Click
    assert isinstance(form.chk._widget, QCheckBox) and form.chk.Value == vpChecked
    form.chk.Style = 1
    assert isinstance(form.chk._widget, QToolButton) and form.chk._widget.isChecked()
    assert form.log == []
    form.chk.FontSize = 20  # a FontSize of its own is kept
    assert form.chk._widget.font().pointSize() == 20
    form.chk.FontSize = None  # else an ordinary button's size (not a tool button's)
    assert form.chk._widget.font().pointSizeF() == \
        QApplication.font("QPushButton").pointSizeF()


def test_form_file_and_designer(qapp, tmp_path):
    body = ("def InitializeComponent(self):\n"
            "    self.cmd = CommandButton(self, Caption='Go', Left=8, Top=8, Width=97, "
            "Height=60, Style=1, Picture='go.png')\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("cmd").props["Style"] == 1
    region = formfile.generate_region(form)
    assert "Style=1," in region and "Picture='go.png'" in region
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("CheckBox", QRect(origin + QPoint(16, 16), origin + QPoint(120, 50)),
                            None)
    d.select([name])
    assert d.set_property("Style", 1) is None  # rebuilt as a toggle button while designing
    assert isinstance(d.controls[name]._widget, QToolButton) and "Style=1" in d.document.text
    d.close()
