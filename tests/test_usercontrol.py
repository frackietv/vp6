"""User controls (VB's UserControl): the runtime (properties, events, its own controls
and events, its surface), form files, the registry of a project's user controls, the
project file, and the IDE (adding one, the Toolbox, placing it on a form, the code
window, reloading after edits)."""

import os
import sys

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vp6 import (CommandButton, ControlArray, Form, Forms, Label, Property, UserControl,
                 formfile)
from vp6.controls import CONTROL_TYPES
from vp6.ide.codeeditor import CodeWindow
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.project import Project
from vp6.usercontrol import (OWN_EVENTS, load_user_control, parse_events,
                             register_user_control, unregister_user_controls,
                             user_control_types)

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class ctlCounter(UserControl):
    Properties = (Property("Value", "int", 0, description="The count"),
                  Property("Step", "int", 1),
                  Property("Mode", "enum", 0, choices=("Up", "Down")))
    Events = ("Change(Value)", "Overflow")

    def InitializeComponent(self):
        self.calls = []
        self.Surface.Width = 160
        self.Surface.Height = 40
        self.Surface.BackColor = 0xC0FFC0
        self.lblValue = Label(self, Caption="0", Left=8, Top=8, Width=60, Height=25)
        self.cmdUp = CommandButton(self, Caption="+", Left=76, Top=4, Width=36, Height=30)
        self.cmdKey = ControlArray()
        self.cmdKey[0] = CommandButton(self, Caption="a", Left=116, Top=4, Width=20, Height=30)
        self.cmdKey[1] = CommandButton(self, Caption="b", Left=136, Top=4, Width=20, Height=30)

    def UserControl_Initialize(self):
        self.calls.append(("Initialize", self.lblValue.Caption))

    def UserControl_Resize(self):
        self.calls.append(("Resize", self.Width))

    def UserControl_PropertyChanged(self, PropertyName):
        self.calls.append(("PropertyChanged", PropertyName))
        if PropertyName == "Value":
            self.lblValue.Caption = str(self.Value)
            if self.RaiseEvent("Change", self.Value) is True:  # the form cancels
                self.Value = 0

    def cmdUp_Click(self):
        self.Value += self.Step

    def cmdKey_Click(self, Index):
        self.calls.append(("cmdKey", Index))

    def UserControl_Click(self):
        self.calls.append(("Click",))


class Host(Form):
    def InitializeComponent(self):
        self.changes = []
        self.ctl1 = ctlCounter(self, Left=10, Top=10, Value=3, Step=2)
        self.ctl2 = ctlCounter(self, Left=10, Top=60, Width=200)

    def ctl1_Change(self, Value):
        self.changes.append(Value)
        return Value > 100  # cancel: back to 0


@pytest.fixture
def host(qapp):
    form = Host()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


# --- the runtime ----------------------------------------------------------------------------------

def test_declarations():
    assert parse_events(("Change(OldValue, NewValue)", "Click", " Done ( ) ")) == (
        ("Change", "Click", "Done"), {"Change": "OldValue, NewValue", "Click": "", "Done": ""})
    with pytest.raises(ValueError):
        parse_events(("not an event!",))
    assert ctlCounter.Events == ("Change", "Overflow") and ctlCounter.DefaultEvent == "Change"
    assert ctlCounter.EventArgs == {"Change": "Value", "Overflow": ""}
    assert ctlCounter.TypeName == "ctlCounter" and ctlCounter.InToolbox
    names = [spec.name for spec in ctlCounter.Properties]
    assert names[:4] == ["Left", "Top", "Width", "Height"] and names[-3:] == ["Value", "Step",
                                                                              "Mode"]
    mode = ctlCounter._specs["Mode"]
    assert mode.choices == ((0, "0 - Up"), (1, "1 - Down")) and mode.default == 0
    assert Property("Name").default == "" and Property("On", "bool").default is False


def test_properties_controls_and_events(host):
    ctl = host.ctl1
    assert (ctl.Width, ctl.Height) == (160, 40)  # its designed size
    assert host.ctl2.Width == 200  # unless given
    assert ctl.Value == 3 and ctl.Step == 2 and ctl.lblValue.Caption == "3"
    # Initialize after its controls exist, before the property values; then each one
    assert ctl.calls[0] == ("Initialize", "0")
    assert [c for c in ctl.calls if c[0] == "PropertyChanged"][:2] == [
        ("PropertyChanged", "Value"), ("PropertyChanged", "Step")]
    assert host.changes == []  # (not while it is made)
    ctl.cmdUp._widget.click()  # its own control's event: its own method
    assert ctl.Value == 5 and host.changes == [5] and ctl.lblValue.Caption == "5"
    ctl.Value = 200  # the form's handler returns True: cancelled
    assert host.changes[-2:] == [200, 0] and ctl.Value == 0
    ctl.cmdKey[1]._widget.click()  # control arrays on it
    assert ctl.calls[-1] == ("cmdKey", 1)
    with pytest.raises(ValueError, match="no event 'Nope'"):
        ctl.RaiseEvent("Nope")
    ctl.Width = 220
    assert ctl.calls[-1] == ("Resize", 220)
    QTest.mouseClick(ctl._widget, Qt.LeftButton, Qt.NoModifier, QPoint(70, 37))  # (no control)
    assert ("Click",) in ctl.calls  # its surface's events are its own
    assert ctl.UserMode and len(ctl.Controls) == 4
    assert ctl.Surface.BackColor == 0xC0FFC0
    assert ctl.lblValue._widget.parent() is ctl._widget
    assert ctl.Surface not in list(Forms) and host in list(Forms)  # (not a loaded form)
    with pytest.raises(AttributeError):
        ctl.Caption = "x"  # (not one of its properties)


def test_at_design_time(qapp):
    class Designing(Form):
        _design_mode = True

        def InitializeComponent(self):
            self.ctl = ctlCounter(self, Name="ctl", Value=7)

    form = Designing()
    form._widget.show()  # (as the designer shows it: a hidden widget gets no Resize)
    QTest.qWait(10)
    ctl = form.ctl
    assert not ctl.UserMode
    assert ctl.lblValue.Caption == "7"  # PropertyChanged runs: it shows its values
    ctl.cmdUp._widget.click()  # its controls' events don't
    assert ctl.Value == 7
    ctl.Width = 300
    assert ("Resize", 300) in ctl.calls  # Resize does
    form._widget.close()


# --- form files -------------------------------------------------------------------------------

SOURCE = formfile.new_user_control_source("ctlNew")


def test_user_control_files():
    assert formfile.find_form_kind(SOURCE) == "usercontrol"
    assert formfile.find_form_kind("class Form1(Form):\n    pass\n") == "form"
    assert formfile.find_form_kind("x = 1\n") is None
    form_def = formfile.parse(SOURCE)
    assert form_def.kind == "usercontrol" and form_def.class_name == "ctlNew"
    assert form_def.props == {"Width": 161, "Height": 97}
    assert "self.Surface.Width = 161" in SOURCE
    form_def.props["BackColor"] = 0xFF0000
    form_def.controls.append(formfile.ControlDef("Label", "Label1", None,
                                                 {"Left": 1, "Top": 2, "Width": 3,
                                                  "Height": 4, "Caption": "x"}))
    text = formfile.replace_region(SOURCE, form_def)
    assert "self.Surface.BackColor = 0xFF0000" in text
    assert formfile.parse(text) == form_def
    cls = load_user_control("ctlNew.py", text)  # a new one works as it is
    assert issubclass(cls, UserControl) and cls.DefaultSize == (161, 97)
    assert cls.Events == ("Click",) and "Caption" in cls._specs
    with pytest.raises(TypeError, match="no UserControl class"):
        load_user_control("other.py", "from vp6 import *\n\n\nclass ctlNew(Form):\n"
                                      "    # region VP6 Designer\n"
                                      "    def InitializeComponent(self):\n"
                                      "        pass\n    # endregion\n")


def test_imports_and_unknown_properties():
    form = "from vp6 import *\nimport os\n\n\nclass Form1(Form):\n    pass\n"
    assert formfile.import_insertion(form, "ctlA", "ctlA") == (2, "from ctlA import ctlA")
    with_import = formfile.ensure_import(form, "ctlA", "ctlA")
    assert with_import.splitlines()[2] == "from ctlA import ctlA"
    assert formfile.ensure_import(with_import, "ctlA", "ctlA") == with_import
    assert formfile.ensure_import("x = 1\n", "m", "c") == "from m import c\nx = 1\n"
    # A control whose class isn't known (e.g. couldn't be imported): its values are kept
    form_def = formfile.FormDef("Form1", controls=[formfile.ControlDef(
        "ctlGone", "ctl1", None, {"Value": 3, "Left": 1})])
    region = formfile.generate_region(form_def)
    assert "self.ctl1 = ctlGone(self, Left=1, Value=3)" in region


# --- the registry ------------------------------------------------------------------------------

def test_registry():
    register_user_control(ctlCounter)
    assert CONTROL_TYPES["ctlCounter"] is ctlCounter and user_control_types() == ["ctlCounter"]
    with pytest.raises(TypeError):
        register_user_control(Label)

    class Label2(UserControl):
        pass

    Label2.TypeName = "Label"
    with pytest.raises(ValueError, match="built-in"):
        register_user_control(Label2)
    unregister_user_controls()
    assert "ctlCounter" not in CONTROL_TYPES and "Label" in CONTROL_TYPES


# --- the project ------------------------------------------------------------------------------

def test_project_file(tmp_path):
    project = Project(name="P", forms=["Form1.py"], modules=["Module1.py"],
                      user_controls=["ctlA.py"], path=str(tmp_path / "P.vp6p"))
    assert project.files() == ["Form1.py", "ctlA.py", "Module1.py"]
    assert project.kind_of("ctlA.py") == "usercontrol"
    assert project.tree()[1] == {"group": "User Controls", "items": ["ctlA.py"]}
    project.save()
    assert '"user_controls": ["ctlA.py"],' in (tmp_path / "P.vp6p").read_text()
    loaded = Project.load(project.path)
    assert loaded == project
    loaded.rename_file("ctlA.py", "ctlB.py")
    assert loaded.user_controls == ["ctlB.py"]
    loaded.remove_file("ctlB.py")
    assert loaded.user_controls == [] and loaded.kind_of("ctlB.py") is None
    assert Project(name="Q", forms=["F.py"]).tree() == [{"group": "Forms", "items": ["F.py"]},
                                                         {"group": "Modules", "items": []}]


# --- the IDE ----------------------------------------------------------------------------------

@pytest.fixture
def window(qapp):
    w = MainWindow()
    w.show()
    yield w
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


def test_designing_and_using_a_user_control(window, tmp_path):
    path = create_project(str(tmp_path), "Demo", "exe")
    window.open_project(path)
    window.add_user_control()  # Project > Add User Control
    project = window.project
    assert project.user_controls == ["UserControl1.py"]
    assert ("User Controls",) in project.group_paths()
    assert project.group_of("UserControl1.py") == ("User Controls",)
    uc_path = project.abspath("UserControl1.py")
    uc_doc = window.documents[uc_path]
    assert uc_doc.kind == "usercontrol" and uc_path in window.designer_windows
    assert "UserControl1" in CONTROL_TYPES and "UserControl1" in window.toolbox.buttons
    # Its designer: its surface, with its own properties only, no window frame
    uc_designer = window._designer_for(uc_path)
    assert set(uc_designer.form._specs) == set(formfile.surface_specs())
    assert uc_designer.frame_info().border_style == 0
    assert uc_designer.all_objects()[0] == ("UserControl1", "UserControl")
    uc_designer.create_control("UserControl1", None, None)  # (not on itself)
    assert uc_designer.form_def.controls == []
    uc_designer.create_control("Label", None, None)
    assert "self.Label1 = Label(self" in uc_doc.text
    # Its code window: "UserControl" with its own events
    code = CodeWindow(uc_doc)
    assert ("UserControl", OWN_EVENTS) in code._objects()
    code.goto_event("UserControl", "PropertyChanged")
    assert "def UserControl_PropertyChanged(self, PropertyName):" in uc_doc.text
    # Edited: loaded again (a moment later), here a property added
    uc_doc.replace_text(uc_doc.text.replace(
        'Property("Caption", "str", "", description="Its text"),',
        'Property("Caption", "str", "", description="Its text"), Property("Size", "int", 7),'))
    QTest.qWait(800)
    assert "Size" in CONTROL_TYPES["UserControl1"]._specs
    # On a form: placed from the Toolbox, its properties in the Properties window
    form_path = project.abspath("Form1.py")
    designer = window.view_object(form_path)
    designer.create_control("UserControl1", None, None)
    form_doc = window.documents[form_path]
    assert "self.UserControl11 = UserControl1(self" in form_doc.text or \
        "UserControl1(self" in form_doc.text
    assert "from UserControl1 import UserControl1" in form_doc.text  # imported for it
    instance = next(c for c in designer.controls.values() if c.TypeName == "UserControl1")
    assert instance.Size == 7 and not instance.UserMode
    assert (instance.Width, instance.Height) == (161, 97)  # its designed size
    designer.select([designer.key_of(instance)])
    window.properties.refresh()
    names = [window.properties.table.item(r, 0).text()
             for r in range(window.properties.table.rowCount())]
    assert "Size" in names and "Caption" in names
    form_code = CodeWindow(form_doc)
    form_code.goto_event(instance.Name, "Click")
    assert f"def {instance.Name}_Click(self):" in form_doc.text
    window.save_all()
    # The project closes: its controls are no longer control types
    window.close_project()
    assert "UserControl1" not in CONTROL_TYPES and "UserControl1" not in window.toolbox.buttons
    # Opened again: loaded before the forms that use them
    assert window.open_project(path)
    assert "UserControl1" in CONTROL_TYPES
    assert any(c.type == "UserControl1" for c in window.documents[form_path].form_def.controls)


def test_a_broken_user_control_keeps_the_project_usable(window, tmp_path, monkeypatch):
    path = create_project(str(tmp_path), "Demo", "exe")
    window.open_project(path)
    window.add_user_control()
    uc_path = window.project.abspath("UserControl1.py")
    window.documents[uc_path].replace_text(
        window.documents[uc_path].text.replace("    Events = (\"Click\",)",
                                               "    Events = (\"Click\",)\n    1 / 0"))
    warnings = []
    monkeypatch.setattr("vp6.ide.mainwindow.QMessageBox.warning",
                        lambda *args: warnings.append(args[2]))
    problems = window._load_user_controls()
    assert problems and "division by zero" in problems[0]
    assert "UserControl1" not in CONTROL_TYPES  # (not a tool now, nothing else broken)


def test_running_a_project_with_a_user_control(tmp_path):
    """A program runs its user controls without the IDE."""
    import subprocess

    (tmp_path / "ctlHello.py").write_text(
        "from vp6 import *\n\n\n"
        "class ctlHello(UserControl):\n"
        '    Properties = (Property("Who", "str", "World"),)\n'
        "    # region VP6 Designer - generated by the form designer, do not edit\n"
        "    def InitializeComponent(self):\n"
        "        self.Surface.Width = 100\n"
        "        self.lbl = Label(self, Caption='', Left=0, Top=0, Width=100, Height=20)\n"
        "    # endregion\n\n"
        "    def UserControl_PropertyChanged(self, PropertyName):\n"
        "        self.lbl.Caption = f'Hello, {self.Who}!'\n")
    (tmp_path / "Module1.py").write_text(
        "from vp6 import *\nfrom ctlHello import ctlHello\n\n\n"
        "def Main():\n"
        "    form = Form()\n"
        "    ctl = ctlHello(form, Name='ctl', Who='VP6')\n"
        "    print(ctl.lbl.Caption, ctl.Width)\n")
    project = Project(name="Hi", type="exe", startup="Sub Main", modules=["Module1.py"],
                      user_controls=["ctlHello.py"], path=str(tmp_path / "Hi.vp6p"))
    project.save()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, str(tmp_path / "Hi.vp6p")], capture_output=True,
                            text=True, timeout=60, env=env)
    assert "Hello, VP6! 100" in result.stdout, result.stderr
