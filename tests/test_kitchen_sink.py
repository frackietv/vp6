"""The Kitchen Sink template must keep demonstrating everything VP6 offers.

If a test here fails after you added a control, event or API function to
VP6: demonstrate it in vp6/ide/templates/kitchensink/ (see the development
guide, "Keep the Kitchen Sink up to date").
"""

import importlib
import re
import sys

import pytest
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest

import vp6
from vp6 import formfile
from vp6.controls import CONTROL_TYPES
from vp6.ide import kitchensink
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.mainwindow import create_project
from vp6.project import SUB_MAIN, Project

UPDATE_HINT = "update the Kitchen Sink (vp6/ide/templates/kitchensink/)"


def template_sources() -> dict[str, str]:
    return {name: (kitchensink.TEMPLATE_DIR / name).read_text()
            for name in kitchensink.FORMS + kitchensink.MODULES}


def form_defs() -> dict[str, formfile.FormDef]:
    return {name: formfile.parse(source) for name, source in template_sources().items()
            if name in kitchensink.FORMS}


# --- coverage: fails when VP6 grows and the Kitchen Sink doesn't ----------------------------

def test_every_control_type_is_used():
    used = {c.type for form in form_defs().values() for c in form.controls}
    missing = sorted(set(CONTROL_TYPES) - used)
    assert not missing, f"Controls not in the Kitchen Sink: {missing} - {UPDATE_HINT}"


def test_every_public_api_name_is_used():
    code = "\n".join(template_sources().values())
    names = [n for n in vp6.__all__ if not n.startswith("vp")]  # constants are too many
    missing = [n for n in names if not re.search(rf"\b{re.escape(n)}\b", code)]
    assert not missing, f"API names not used in the Kitchen Sink: {missing} - {UPDATE_HINT}"


def test_every_control_type_handles_its_default_event():
    handled = set()
    for filename, form in form_defs().items():
        methods = set(formfile.defined_methods(template_sources()[filename]))
        for control in form.controls:
            event = CONTROL_TYPES[control.type].DefaultEvent
            if f"{control.name}_{event}" in methods:
                handled.add(control.type)
    missing = sorted(set(CONTROL_TYPES) - handled)
    assert not missing, f"No default-event handler for: {missing} - {UPDATE_HINT}"


def test_every_color_scheme_is_demonstrated():
    code = "\n".join(template_sources().values())
    for name in ("vpSchemeSystem", "vpSchemeLight", "vpSchemeDark", "vpSchemeIDE"):
        assert name in code, f"{name} not demonstrated - {UPDATE_HINT}"


def test_designer_regions_are_canonical():
    # Regenerating a region must not change it, so the IDE opens the forms cleanly
    for filename, source in template_sources().items():
        if filename in kitchensink.FORMS:
            assert formfile.replace_region(source, formfile.parse(source)) == source, filename


# --- creating and using the project -----------------------------------------------------------

def test_create_kitchen_sink_project(qapp, tmp_path):
    path = create_project(str(tmp_path), "Sink", "kitchensink")
    project = Project.load(path)
    assert project.forms == ["Form1.py", "frmDialog.py"]
    assert project.modules == ["Module1.py"]  # like every new project: Form1 and Module1
    assert project.startup == SUB_MAIN and project.type == "exe"
    folder = tmp_path / "Sink"
    for name in kitchensink.FORMS + kitchensink.MODULES:
        assert (folder / name).read_text() == (kitchensink.TEMPLATE_DIR / name).read_text()
    assert not QPixmap(str(folder / kitchensink.PICTURE)).isNull()


def test_designer_opens_every_form(qapp, tmp_path):
    create_project(str(tmp_path), "Sink", "kitchensink")
    for name in kitchensink.FORMS:
        designer = FormDesigner(FormDocument(str(tmp_path / "Sink" / name)),
                                str(tmp_path / "Sink"))
        problems = []
        designer.statusMessage.connect(problems.append)
        designer.load_def(designer.document.form_def)
        assert not problems, problems
        assert set(designer.controls) == {c.name for c in designer.form_def.controls}


@pytest.fixture
def sink_forms(qapp, tmp_path, monkeypatch):
    """Import the created project's forms in this process."""
    create_project(str(tmp_path), "Sink", "kitchensink")
    folder = str(tmp_path / "Sink")
    sys.path.insert(0, folder)
    modules = {name: importlib.import_module(name) for name in ("frmDialog", "Form1")}
    # Answer the Form_Unload confirmation and silence message boxes
    monkeypatch.setattr(modules["Form1"], "MsgBox", lambda *args, **kwargs: vp6.vpYes)
    monkeypatch.setattr(modules["Form1"].time, "sleep", lambda seconds: None)
    yield modules
    sys.path.remove(folder)
    for name in ("Form1", "frmDialog", "Module1"):
        sys.modules.pop(name, None)


def test_kitchen_sink_runs(sink_forms, capsys):
    form = sink_forms["Form1"].Form1()
    form.Show()
    assert form.lblOnPicture.Parent is form.picLogo  # a Label inside the PictureBox
    assert "controls loaded" in form.lblStatus.Caption

    QTest.keyClicks(form.txtUpper._widget, "abc")
    assert form.txtUpper.Text == "ABC"  # KeyPress transformation

    form.txtName.Text = "Delta"
    assert form.cmdAdd.Enabled  # Change event
    form.cmdAdd._widget.click()
    assert "Delta" in form.lstItems.List and form.txtName.Text == ""

    form.lstItems.ListIndex = 0
    form.cmdRemove._widget.click()
    assert form.lstItems.ListCount == 3

    form.hsbSize.Value = 16
    assert form.lblSizeValue.Caption == "16" and form.lblSwatch.FontSize == 16

    form.cboColors.ListIndex = form.cboColors.List.index("Red")
    assert form.lblSwatch.BackColor == vp6.vpRed

    form.optDark.Value = True
    assert form._effective_scheme() == vp6.vpSchemeDark

    form.chkPicture.Value = vp6.vpUnchecked
    assert not form.picLogo.Visible

    form.cmdCount._widget.click()  # DoEvents loop
    assert form.cmdCount.Caption == "Count to &100"

    def answer_dialog():
        dialog = next(f for f in vp6.Forms if type(f).__name__ == "frmDialog")
        assert dialog._is_dark()  # the dialog's own ColorScheme = 3 - Dark
        dialog.txtItem.Text = "Zulu"
        dialog.cmdOK._widget.click()

    QTimer.singleShot(50, answer_dialog)
    form.cmdDialog._widget.click()  # modal: returns after OK
    assert "Zulu" in form.lstItems.List

    form.tmrClock_Timer()
    assert re.fullmatch(r"\d\d:\d\d:\d\d", form.lblClock.Caption)

    assert form.Unload() is True
    assert "Traceback" not in capsys.readouterr().err


def test_kitchen_sink_z_order_demo(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    widget = form._widget
    overlap = QPoint(100, 460)  # inside both lblZRed (16,440 132x40) and lblZBlue (80,452)

    def on_top():
        return widget.childAt(overlap)._vp_control.Name

    assert on_top() == "lblZRed"  # ZIndex 2 beats 1, although created first
    form.cmdSwapZ._widget.click()
    assert on_top() == "lblZBlue" and form.lblZBlue.Caption == "Blue: ZIndex 2"
    form.lblZRed_Click()  # ZOrder(0)
    assert on_top() == "lblZRed" and form.lblZRed.ZIndex == 3
    form.Unload()
