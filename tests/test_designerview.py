"""The DesignerView control: a form's file designed in a program (selecting,
adding, moving, resizing and deleting controls, properties, undo, the Tool,
Locked, saving) with its events; a placeholder in the IDE's designer."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vp6 import DesignerView, Form, formfile
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.ide.mainwindow import create_project

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Studio(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 640, 480
        self.dsg = DesignerView(self, Left=0, Top=0, Width=640, Height=480)
        self.log = []

    def dsg_SelChange(self):
        self.log.append(("SelChange", tuple(self.dsg.SelectedControls)))

    def dsg_Change(self):
        self.log.append("Change")

    def dsg_ControlAdded(self, Name):
        self.log.append(("added", Name))

    def dsg_ControlDeleted(self, Name):
        self.log.append(("deleted", Name))

    def dsg_ControlMoved(self, Name):
        self.log.append(("moved", Name))

    def dsg_ControlResized(self, Name):
        self.log.append(("resized", Name))

    def dsg_PropertyChanged(self, Name, Property):
        self.log.append(("property", Name, Property))

    def dsg_GoToCode(self, Name, Event):
        self.log.append(("code", Name, Event))


@pytest.fixture
def studio(qapp, tmp_path):
    create_project(str(tmp_path), "Proj", "exe")
    form = Studio()
    form.Show()
    form.dsg.FileName = str(tmp_path / "Proj" / "Form1.py")
    QTest.qWait(10)
    yield form
    form.Unload()


def test_designing(studio, tmp_path):
    dsg, log = studio.dsg, studio.log
    assert dsg.ControlNames == [] and dsg.SelectedControls == [] and not dsg.Modified
    name = dsg.AddControl("CommandButton", 16, 24, 120, 40)
    assert name == "Command1" and dsg.SelectedControls == ["Command1"]
    assert ("added", "Command1") in log and log[-1] == "Change"
    assert dsg.ControlType("Command1") == "CommandButton" and dsg.ControlType("") == "Form"
    assert dsg.GetProperty("Command1", "Width") == 120 and dsg.Modified
    log.clear()
    dsg.SetProperty("Caption", "OK")
    assert ("property", "Command1", "Caption") in log and \
        dsg.GetProperty("Command1", "Caption") == "OK"
    with pytest.raises(ValueError, match="Invalid"):
        dsg.SetProperty("Width", "wide")
    log.clear()
    designer = dsg._designer
    designer.nudge(8, 0)  # (an arrow key)
    assert ("moved", "Command1") in log
    log.clear()
    designer.nudge(8, 8, resize=True)
    assert ("resized", "Command1") in log
    dsg.AddControl("Label")  # (in the middle)
    assert dsg.ControlNames == ["Command1", "Label1"]
    dsg.SelectControls(["Command1", "Label1"])
    assert dsg.SelectedControls == ["Command1", "Label1"]
    with pytest.raises(KeyError):
        dsg.SelectControls("Nonesuch")
    log.clear()
    dsg.DeleteSelection()
    assert ("deleted", "Command1") in log and ("deleted", "Label1") in log
    assert dsg.CanUndo and not dsg.CanRedo
    dsg.Undo()
    assert dsg.ControlNames == ["Command1", "Label1"] and dsg.CanRedo
    dsg.Redo()
    assert dsg.ControlNames == []
    dsg.Undo()
    dsg.SelectControls([])
    dsg.SetProperty("Caption", "Designed")
    assert ("property", "", "Caption") in log
    # Saved: the form file has the changes
    dsg.Save()
    assert not dsg.Modified
    saved = (tmp_path / "Proj" / "Form1.py").read_text()
    definition = formfile.parse(saved)
    assert [c.name for c in definition.controls] == ["Command1", "Label1"]
    assert definition.props["Caption"] == "Designed" and dsg.Source == saved
    dsg.Save(str(tmp_path / "Proj" / "Copy.py"))  # (saved as another file: designing it)
    assert dsg.FileName.endswith("Copy.py") and dsg.ControlNames == ["Command1", "Label1"]


def test_tool_locked_and_double_click(studio):
    dsg, log = studio.dsg, studio.log
    designer = dsg._designer
    dsg.Tool = "TextBox"
    assert designer.tool == "TextBox"
    with pytest.raises(ValueError):
        dsg.Tool = "Nonesuch"
    origin = designer.form_canvas_rect().topLeft()
    overlay = designer.overlay
    QTest.mousePress(overlay, Qt.LeftButton, Qt.NoModifier, origin + QPoint(20, 20))
    QTest.mouseMove(overlay, origin + QPoint(120, 50))
    QTest.mouseRelease(overlay, Qt.LeftButton, Qt.NoModifier, origin + QPoint(120, 50))
    assert dsg.ControlNames == ["Text1"] and dsg.Tool == ""  # (used: the pointer again)
    dsg.Locked = True
    assert designer.locked
    log.clear()
    rect = designer.canvas_rect("Text1")
    QTest.mouseDClick(overlay, Qt.LeftButton, Qt.NoModifier, rect.center())
    assert ("code", "Text1", "Change") in log
    assert EVENT_ARGS["GoToCode"] == "Name, Event"


def test_without_a_form_and_in_the_ide(qapp, tmp_path):
    form = Studio()
    with pytest.raises(RuntimeError, match="no form"):
        form.dsg.Source
    with pytest.raises(FileNotFoundError):
        form.dsg.LoadForm(str(tmp_path / "missing.py"))
    assert not form.dsg.Modified and form.dsg.SelectedControls == []
    form._widget.close()
    assert CONTROL_TYPES["DesignerView"] is DesignerView and list(CONTROL_TYPES)[-1] == "Menu"
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument

    create_project(str(tmp_path), "P", "exe")
    path = tmp_path / "P" / "Form1.py"
    source = path.read_text()
    definition = formfile.parse(source)
    definition.controls.append(formfile.ControlDef("DesignerView", "Designer1", None,
                                                   {"Left": 8, "Top": 8}))
    path.write_text(formfile.replace_region(source, definition))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path / "P"))
    assert "DesignerView" in designer.controls["Designer1"]._widget.text()  # (a placeholder)
