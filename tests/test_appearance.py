import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QMessageBox

from vp6 import *  # noqa: F403
from vp6 import appearance, formfile
from vp6.ide.designer import FormDesigner, ide_is_dark
from vp6.ide.dialogs import ProjectPropertiesDialog
from vp6.ide.documents import FormDocument
from vp6.ide.theme import DARK, LIGHT, theme_manager
from vp6.project import Project


@pytest.fixture(autouse=True)
def _reset_project_scheme():
    appearance.project_scheme = None
    appearance._found_schemes.clear()
    yield
    appearance.project_scheme = None
    appearance._found_schemes.clear()


def window_color(widget) -> str:
    return widget.palette().color(QPalette.Window).name()


def is_fusion(widget) -> bool:
    return widget.testAttribute(Qt.WA_SetStyle) and widget.style().name().lower() == "fusion"


class SchemeForm(Form):
    def InitializeComponent(self):
        self.ColorScheme = vpSchemeDark
        self.Frame1 = Frame(self, Caption="Group")
        self.Command1 = CommandButton(self.Frame1, Caption="OK")


def test_forced_dark_scheme_styles_form_and_controls(qapp):
    form = SchemeForm()
    assert form._is_dark()
    assert window_color(form._widget) == "#353535"
    button = form.Command1._widget
    assert is_fusion(button) and is_fusion(form.Frame1._widget)
    # The frame follows the form's palette instead of freezing a copy of it
    assert window_color(form.Frame1._widget) == "#353535"
    form.List1 = ListBox(form)  # controls added later get the scheme too
    assert is_fusion(form.List1._widget)
    assert form.List1._widget.palette().color(QPalette.Base).name() == "#252525"


def test_switching_to_light_and_system(qapp):
    form = SchemeForm()
    form.ColorScheme = vpSchemeLight
    assert window_color(form.Frame1._widget) == "#efefef"
    form.ColorScheme = vpSchemeSystem
    button = form.Command1._widget
    assert not button.testAttribute(Qt.WA_SetStyle)  # back to the native style
    assert form._effective_scheme() == vpSchemeSystem


def test_back_color_overrides_scheme(qapp):
    form = SchemeForm()
    form.BackColor = vpRed
    assert window_color(form._widget) == "#ff0000"
    assert form._widget.palette().color(QPalette.Base).name() == "#252525"


def test_project_default_from_runner_or_vp6p(qapp, tmp_path):
    class Plain(Form):
        pass

    form = Plain()
    assert form._effective_scheme() == vpSchemeSystem
    appearance.project_scheme = vpSchemeDark  # what the runner does
    form.ColorScheme = vpSchemeProjectDefault
    assert form._is_dark()

    appearance.project_scheme = None
    Project(name="App", color_scheme="light").save(str(tmp_path / "App.vp6p"))
    assert appearance.project_scheme_for(str(tmp_path)) == vpSchemeLight
    assert appearance.project_scheme_for(str(tmp_path / "nowhere")) == vpSchemeSystem


def test_dialogs_match_the_form(qapp):
    form = SchemeForm()
    box = QMessageBox()
    appearance.match_dialog(box, form.Command1._widget)
    assert is_fusion(box) and window_color(box) == "#353535"


def test_project_scheme_round_trip(tmp_path):
    project = Project(name="P", forms=["Form1.py"], color_scheme="dark")
    project.save(str(tmp_path / "P.vp6p"))
    assert Project.load(str(tmp_path / "P.vp6p")).color_scheme == "dark"
    assert Project.load(str(tmp_path / "P.vp6p")) == project
    (tmp_path / "Old.vp6p").write_text('PROJECT = {"name": "Old"}\n')  # no color_scheme
    assert Project.load(str(tmp_path / "Old.vp6p")).color_scheme == "system"


def test_color_scheme_in_designer_region():
    form = formfile.parse(formfile.new_form_source("Form1"))
    assert "ColorScheme" not in formfile.generate_region(form)  # default is omitted
    form.props["ColorScheme"] = vpSchemeDark
    region = formfile.generate_region(form)
    assert "self.ColorScheme = 3" in region


@pytest.fixture
def designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.create_control("CommandButton", None, None, None)
    return d


def test_designer_form_uses_project_then_own_scheme(designer):
    d = designer
    assert not d.form._is_dark() or appearance.system_is_dark()
    d.set_project_scheme(vpSchemeDark)
    assert d.form._is_dark()
    assert is_fusion(d.controls["Command1"]._widget)
    assert "ColorScheme" not in d.document.text  # inherited, not written
    d.select([])
    d.set_property("ColorScheme", vpSchemeLight)  # the form overrides the project
    assert not d.form._is_dark()
    assert "self.ColorScheme = 2" in d.document.text
    # The designer's grid background keeps the form's scheme color
    assert d.form._widget.palette().window().texture().toImage().pixelColor(4, 4).name() \
        == "#efefef"


def test_workspace_follows_ide_theme(designer):
    theme_manager().select(DARK)
    assert ide_is_dark()
    theme_manager().select(LIGHT)
    assert not ide_is_dark()


def test_project_properties_dialog_sets_scheme(qapp):
    project = Project(name="P", forms=["Form1.py"])
    dialog = ProjectPropertiesDialog(project, ["Form1"])
    dialog.color_scheme.setCurrentIndex(dialog.color_scheme.findData("dark"))
    dialog.apply(project)
    assert project.color_scheme == "dark"


# --- "IDE" color scheme --------------------------------------------------------------------

def test_ide_scheme_at_runtime_uses_launch_environment(qapp, monkeypatch):
    appearance.ide_scheme_provider = None  # not inside the IDE
    form = SchemeForm()
    form.ColorScheme = vpSchemeIDE
    monkeypatch.setenv(appearance.IDE_SCHEME_ENV, "dark")
    form.ColorScheme = vpSchemeIDE
    assert form._effective_scheme() == vpSchemeDark and is_fusion(form.Command1._widget)
    monkeypatch.setenv(appearance.IDE_SCHEME_ENV, "light")
    form._apply_ColorScheme()
    assert form._effective_scheme() == vpSchemeLight
    monkeypatch.delenv(appearance.IDE_SCHEME_ENV)  # run on its own: System
    form._apply_ColorScheme()
    assert form._effective_scheme() == vpSchemeSystem
    appearance.project_scheme = appearance.scheme_from_name("ide")  # project-level too
    monkeypatch.setenv(appearance.IDE_SCHEME_ENV, "dark")
    form.ColorScheme = vpSchemeProjectDefault
    assert form._is_dark()


def test_ide_scheme_follows_the_ide_live_in_the_designer(designer):
    d = designer
    d.select([])
    d.set_property("ColorScheme", vpSchemeIDE)
    assert "self.ColorScheme = 4" in d.document.text
    theme_manager().select(DARK)
    assert d.form._effective_scheme() == vpSchemeDark
    assert is_fusion(d.controls["Command1"]._widget)
    theme_manager().select(LIGHT)
    assert d.form._effective_scheme() == vpSchemeLight
    theme_manager().select("System")  # IDE follows the OS, so does the form
    assert d.form._effective_scheme() == vpSchemeSystem


def test_project_properties_offers_follow_ide(qapp):
    project = Project(name="P", forms=["Form1.py"])
    dialog = ProjectPropertiesDialog(project, ["Form1"])
    dialog.color_scheme.setCurrentIndex(dialog.color_scheme.findData("ide"))
    dialog.apply(project)
    assert project.color_scheme == "ide"
    assert appearance.scheme_from_name(project.color_scheme) == vpSchemeIDE
