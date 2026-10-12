"""WizardForm, the splash screen (App.ShowSplash and the Splash Screen form), ProgressBox
and ShowError."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QCheckBox, QWizard

import vp6
from vp6 import App, Form, Label, ProgressBox, ShowError, TextBox, WizardForm, formfile


class Setup(WizardForm):
    def InitializeComponent(self):
        self.Pages = ["Welcome|Hello", "Name|Type it", "Color|", "Done|"]
        self.lblHi = Label(self, Page=0, Caption="Hi")
        self.txtName = TextBox(self, Page=1, Text="")
        self.lblColor = Label(self, Page=2, Caption="Red")
        self.lblDone = Label(self, Page=3, Caption="")

    def Form_Load(self):
        self.events = []
        self.keep_open = False

    def Form_ValidatePage(self, Page):
        self.events.append(("Validate", Page))
        return Page == 1 and not self.txtName.Text

    def Form_NextPage(self, Page):
        if Page == 1 and self.txtName.Text == "Zed":
            return 3

    def Form_PageChange(self):
        self.events.append(("Page", self.CurrentPage))

    def Form_Finish(self):
        self.events.append("Finish")

    def Form_Cancel(self):
        self.events.append("Cancel")
        return self.keep_open


@pytest.fixture
def wizard(qapp):
    w = Setup()
    w.Show()
    yield w
    if w._loaded:
        w.Unload()


def test_wizard_pages(wizard):
    w = wizard
    assert w.PageCount == 4 and w.CurrentPage == 0 and w.PageTitle(1) == "Name"
    assert w.txtName.Page == 1 and w.txtName._widget.parentWidget() is w._page_widget(1)
    assert w._wizard.page(1).subTitle() == "Type it"
    assert not w._wizard.isWindow()  # (a part of the form's window)
    w.Next()
    assert w.CurrentPage == 1 and w.events == [("Validate", 0), ("Page", 1)]
    w.Next()  # no name: stays
    assert w.CurrentPage == 1
    w.txtName.Text = "Zed"
    w.Next()  # NextPage skips the Color page
    assert w.CurrentPage == 3 and w.VisitedPages == [0, 1, 3]
    w.Back()
    assert w.CurrentPage == 1
    w.Next()
    w._wizard.button(QWizard.FinishButton).click()
    assert w.events[-1] == "Finish" and w.Accepted and not w._loaded


def test_wizard_cancel(wizard):
    wizard.keep_open = True
    wizard._wizard.button(QWizard.CancelButton).click()
    assert wizard._loaded and wizard.events == ["Cancel"]
    wizard.keep_open = False
    wizard._wizard.button(QWizard.CancelButton).click()
    assert not wizard._loaded and not wizard.Accepted


def test_wizard_style_and_current_page(wizard):
    wizard.WizardStyle = vp6.vpWizardClassic
    assert wizard._wizard.wizardStyle() == QWizard.ClassicStyle
    wizard.CurrentPage = 2
    assert wizard.CurrentPage == 2 and wizard.lblColor._widget.isVisible()
    wizard.Pages = ["Only|"]  # (fewer pages)
    assert wizard.PageCount == 1


def test_wizard_form_file_and_designer(qapp, tmp_path):
    from vp6.ide.codeeditor import CodeWindow
    from vp6.ide.designer import DesignWizardForm, FormDesigner
    from vp6.ide.documents import FormDocument

    source = formfile.new_form_source("Wizard1", base="WizardForm")
    assert "class Wizard1(WizardForm):" in source and "def Form_ValidatePage(self, Page)" in source
    assert formfile.find_form_base(source) == "WizardForm"
    assert formfile.replace_region(source, formfile.parse(source)) == source
    path = tmp_path / "Wizard1.py"
    path.write_text(source)
    document = FormDocument(str(path))
    designer = FormDesigner(document, str(tmp_path))
    designer.resize(700, 600)
    designer.show()
    assert isinstance(designer.form, DesignWizardForm)
    first = designer.create_control("TextBox", None, None, QPoint(80, 160))
    designer.step_page(1)
    second = designer.create_control("Label", None, None, QPoint(80, 160))
    text = document.text
    assert f"self.{first} = TextBox(self, Page=0," in text
    assert f"self.{second} = Label(self, Page=1," in text
    assert text.index("self.Pages = ") < text.index("self.CurrentPage = 1")
    assert designer.paged_object() is designer.form
    events = dict(CodeWindow(document)._objects())["Form"]
    assert "ValidatePage" in events and "Finish" in events
    designer.close()


def test_splash_screen_form(qapp, tmp_path):
    source = formfile.new_splash_source("frmSplash1")
    assert formfile.replace_region(source, formfile.parse(source)) == source
    namespace = {}
    exec(compile(source, "frmSplash1.py", "exec"), namespace)
    splash = namespace["frmSplash1"]()
    splash.Show()
    try:
        assert splash.lblTitle.Caption == App.Title and splash.BorderStyle == 0
        assert splash.tmrClose.Interval == 3000
    finally:
        splash.Unload()


def test_show_splash(qapp, tmp_path):
    picture = vp6.Picture(80, 40, BackColor=vp6.vpBlue)
    App.ShowSplash(picture, "Loading...", vp6.vpLeftJustify, vp6.vpWhite)
    assert App.SplashVisible
    App.SplashMessage("Almost there")
    assert App._splash.message() == "Almost there"
    App.HideSplash()
    assert not App.SplashVisible
    App.ShowSplash(picture)
    form = Form()
    form.Show()  # the first form shown: the splash screen goes
    try:
        assert not App.SplashVisible
    finally:
        form.Unload()
    with pytest.raises(ValueError):
        App.ShowSplash(str(tmp_path / "missing.png"))


def test_progress_box(qapp):
    progress = ProgressBox("Working", 10, Delay=0)
    for number in range(1, 4):
        progress.Value = number
    progress.Text = "Step 3"
    assert progress.Value == 3 and progress.Text == "Step 3" and progress.Visible
    assert not progress.Cancelled
    progress._dialog.cancel()
    assert progress.Cancelled
    progress.Close()
    with ProgressBox("Again", 2, Modal=False, CancelText="") as again:
        again.Value = 2  # (reaching Max closes it)
        assert not again.Visible


def test_show_error(qapp):
    from vp6.dialogs import _error_box

    ShowError("The disk is full", "disk")
    box = _error_box[0]
    assert box.isVisible()
    box.findChild(QCheckBox).setChecked(False)  # "Show this message again": no
    box.done(0)
    ShowError("Still full", "disk")
    assert not box.isVisible()
    ShowError("Something else")
    assert box.isVisible()
    box.done(0)


def test_project_menu_adds_them(qapp, tmp_path):
    import os

    from vp6.ide.designer import DesignWizardForm
    from vp6.ide.mainwindow import MainWindow, create_project

    window = MainWindow()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    project = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Project")
    assert window.act_add_wizard in project.actions() and window.act_add_splash in \
        project.actions()
    window.act_add_wizard.trigger()
    wizard = os.path.join(tmp_path, "Demo", "WizardForm1.py")
    assert "WizardForm1.py" in window.project.forms
    assert isinstance(window._designers[wizard].form, DesignWizardForm)
    window.act_add_splash.trigger()
    splash = os.path.join(tmp_path, "Demo", "frmSplash1.py")
    assert "frmSplash1.py" in window.project.forms and "tmrClose_Timer" in open(splash).read()
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
