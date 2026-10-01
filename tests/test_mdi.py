"""Form kinds: MDI forms (MDIForm and MDIChild forms: the workspace, showing
and loading children, ActiveForm, Activate, Arrange, menus, WindowList,
unloading) and popup forms (ShowPopup); MDI forms in the form file, the
designer, the Menu Editor and the IDE (Project > Add MDI Form)."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMdiArea

import vp6
from vp6 import (Form, MDIForm, Menu, PictureBox, TextBox, formfile, vpAlignTop, vpCascade,
                 vpFormMDIForm, vpTileHorizontal, vpTileVertical)
from vp6.form import _loaded_forms


class frmShell(MDIForm):
    def InitializeComponent(self):
        self.Caption = "Shell"
        self.Width, self.Height = 600, 400
        self.picTools = PictureBox(self, Align=vpAlignTop, Height=30)
        self.mnuFile = Menu(self, Caption="&File")
        self.mnuFileNew = Menu(self.mnuFile, Caption="&New")
        self.mnuWindow = Menu(self, Caption="&Window", WindowList=True)
        self.mnuWindowCascade = Menu(self.mnuWindow, Caption="&Cascade")
        self.log = []

    def MDIForm_QueryUnload(self, UnloadMode):
        self.log.append(("shell QueryUnload", UnloadMode))


class frmChild(Form):
    def InitializeComponent(self):
        self.MDIChild = True
        self.Width, self.Height = 200, 120
        self.txt = TextBox(self, Left=4, Top=4)
        self.log = []
        self.keep = False

    def Form_Activate(self):
        self.log.append("Activate")

    def Form_Deactivate(self):
        self.log.append("Deactivate")

    def Form_QueryUnload(self, UnloadMode):
        self.log.append(("QueryUnload", UnloadMode))
        return self.keep


class frmMenus(Form):
    def InitializeComponent(self):
        self.MDIChild = True
        self.Caption = "With menus"
        self.mnuEdit = Menu(self, Caption="&Edit")
        self.mnuEditCopy = Menu(self.mnuEdit, Caption="&Copy")


@pytest.fixture
def shell(qapp, monkeypatch):
    from vp6 import mdi

    # (the project's MDI form: other tests' MDIForm classes are still about)
    monkeypatch.setattr(mdi, "_subclasses", lambda cls: [frmShell])
    yield
    for form in list(_loaded_forms):  # (the default instances: unloaded, made again next time)
        form._query_unload(force=True)
        form._widget.hide()
    for cls in (frmShell, frmChild, frmMenus):
        type.__setattr__(cls, "_vp_default", None)


def child(caption):
    form = frmChild()
    form.Caption = caption
    form.Show()
    return form


def test_children_in_the_workspace(shell):
    one = child("One")  # the MDI form is loaded and shown first
    main = frmShell._vp_default_instance()
    assert main.Visible and main._loaded
    area = main._area
    assert isinstance(area, QMdiArea) and one._widget.parent() is one._mdi_sub
    # The workspace: the client area but the docked pane
    assert area.geometry().top() == 30 and area.width() == main.ScaleWidth
    assert (one.Width, one.Height) == (200, 120) and one.Visible
    two = child("Two")
    assert main.ActiveForm is two and one.log == ["Activate", "Deactivate"]
    assert two.log == ["Activate"] and vp6.Screen.ActiveForm in (None, two, main)
    main._activate_child(one)
    assert main.ActiveForm is one and one.log[-1] == "Activate"
    one.Left, one.Top = 30, 20  # in the workspace
    assert (one._mdi_sub.x(), one._mdi_sub.y()) == (30, 20) == (one.Left, one.Top)
    one.Width = 260  # its inside; the subwindow fits
    assert one._widget.width() == 260
    one.WindowState = 2
    assert one._mdi_sub.isMaximized()
    one.WindowState = 0
    assert one._mdi_sub.isVisible() and not one._mdi_sub.isMaximized()
    with pytest.raises(RuntimeError, match="modally"):
        frmChild().Show(1)


def test_a_child_shown_while_the_mdi_form_loads(shell, monkeypatch):
    # Regression: children shown in MDIForm_Load (the window not laid out yet) were
    # sized to nothing: just their title bar
    monkeypatch.setattr(frmShell, "MDIForm_Load",
                        lambda self: self.__dict__.update(first=child("First")),
                        raising=False)
    main = frmShell._vp_default_instance()
    main.Show()
    QTest.qWait(10)
    first = main.first
    assert first._widget.size().width() == 200 and first._widget.size().height() == 120
    margins = first._mdi_sub.contentsMargins()
    assert first._mdi_sub.height() == 120 + margins.top() + margins.bottom()


def test_load_shows_a_child_while_auto_show_children(shell):
    form = frmChild()
    vp6.Load(form)  # (AutoShowChildren: shown too)
    main = frmShell._vp_default_instance()
    assert form._mdi_sub.isVisible() and main.AutoShowChildren
    main.AutoShowChildren = False
    other = frmChild()
    vp6.Load(other)
    assert other._loaded and other.__dict__.get("_mdi_sub") is None


def test_arrange(shell):
    one, two = child("One"), child("Two")
    main = frmShell._vp_default_instance()
    main.Arrange(vpTileVertical)  # side by side
    a, b = one._mdi_sub.geometry(), two._mdi_sub.geometry()
    assert a.top() == b.top() and a.right() < b.left()
    main.Arrange(vpTileHorizontal)  # one above the other
    a, b = one._mdi_sub.geometry(), two._mdi_sub.geometry()
    assert a.left() == b.left() and a.bottom() < b.top()
    main.Arrange(vpCascade)
    assert one._mdi_sub.pos() != two._mdi_sub.pos()


def test_menus_and_the_window_list(shell):
    one = child("One")
    main = frmShell._vp_default_instance()
    assert [a.text() for a in main._menubar.actions()] == ["&File", "&Window"]
    menus = frmMenus()
    menus.Show()  # its menus replace the MDI form's while it is active
    assert [a.text() for a in main._menubar.actions()] == ["&Edit"]
    assert not menus._menubar.isVisible() and not menus._menubar.isNativeMenuBar()
    main._activate_child(one)
    assert [a.text() for a in main._menubar.actions()] == ["&File", "&Window"]
    main.mnuWindow._on_about_to_show()  # WindowList: the children, the active one checked
    items = main.mnuWindow._submenu.actions()
    listed = [(a.text(), a.isChecked()) for a in items if not a.isSeparator()]
    assert listed == [("&Cascade", False), ("&1 One", True), ("&2 With menus", False)]
    items[-1].trigger()  # activates that child
    assert main.ActiveForm is menus
    main.mnuWindow._on_about_to_show()  # (filled again, not twice)
    assert len(main.mnuWindow._submenu.actions()) == len(items)


def test_unloading(shell):
    one, two = child("One"), child("Two")
    main = frmShell._vp_default_instance()
    assert one.Unload()  # its subwindow closes; out of the workspace
    QTest.qWait(10)
    assert one not in main._mdi_children and not one._loaded
    assert one.log[-1] == ("QueryUnload", vp6.vpFormCode)
    one.Show()  # shown again: a new subwindow
    assert one._mdi_sub is not None and one in main._mdi_children
    two.keep = True  # a child that won't go stops the MDI form too
    assert not main.Unload() and main._loaded
    assert two.log[-1] == ("QueryUnload", vpFormMDIForm)
    two.keep = False
    assert main.Unload()
    assert not main._loaded and not two._loaded and not one._loaded and not main._mdi_children
    assert ("shell QueryUnload", vp6.vpFormCode) in main.log


def test_no_mdi_form(qapp, monkeypatch):
    from vp6 import mdi

    monkeypatch.setattr(mdi, "_subclasses", lambda cls: [])
    with pytest.raises(RuntimeError, match="needs an MDIForm"):
        frmChild().Show()


def test_mdi_form_properties():
    specs = MDIForm._specs
    assert "AutoShowChildren" in specs and "ScrollBars" in specs and "MDIChild" not in specs
    assert "BorderStyle" not in specs and "MDIChild" in Form._specs
    assert MDIForm.BorderStyle == 2 and "WindowList" in Menu._specs


# --- popup forms ---------------------------------------------------------------------------

def test_show_popup(qapp):
    class Owner(Form):
        def InitializeComponent(self):
            self.txt = TextBox(self, Left=10, Top=10)

    class Popup(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 120, 80

    owner, popup = Owner(), Popup()
    owner.Show()
    popup.ShowPopup(10, 40, owner)  # under the TextBox, in the owner's client area
    widget = popup._widget
    assert popup.Visible and widget.windowFlags() & Qt.FramelessWindowHint
    assert widget.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert widget.testAttribute(Qt.WA_ShowWithoutActivating)
    assert widget.pos() == owner._container_widget().mapToGlobal(QPoint(10, 40))
    widget._on_application_state(Qt.ApplicationInactive)  # the program in the background
    assert not popup.Visible
    popup.Show()  # a window again
    assert not widget.testAttribute(Qt.WA_ShowWithoutActivating)
    assert not widget.windowFlags() & Qt.FramelessWindowHint
    popup.Unload()
    owner.Unload()
    assert QApplication.instance() is not None


# --- in the IDE ----------------------------------------------------------------------------

def test_the_form_file():
    source = formfile.new_form_source("MDIForm1", base="MDIForm")
    assert "class MDIForm1(MDIForm):" in source and "def MDIForm_Load(self):" in source
    assert formfile.find_form_base(source) == "MDIForm" and formfile.find_form_kind(source) == \
        "form"
    assert formfile.parse(source).class_name == "MDIForm1"
    assert formfile.find_form_base(formfile.new_form_source("Form1")) == "Form"


def test_in_the_designer_and_the_ide(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vp6.ide.designer import DesignMDIForm
    from vp6.ide.mainwindow import MainWindow, create_project
    from vp6.ide.properties import PropertiesWindow

    window = MainWindow()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    project = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Project")
    assert window.act_add_mdi_form in project.actions()
    window.act_add_mdi_form.trigger()
    path = os.path.join(tmp_path, "Demo", "MDIForm1.py")
    assert os.path.isfile(path) and "MDIForm1.py" in window.project.forms
    designer = window._designers[path]
    assert isinstance(designer.form, DesignMDIForm)
    assert isinstance(designer.form._area, QMdiArea)  # (its workspace, shown)
    properties = PropertiesWindow()
    properties.set_designer(designer)
    rows = [properties.table.item(r, 0).text() for r in range(properties.table.rowCount())]
    assert "AutoShowChildren" in rows and "BorderStyle" not in rows and "MDIChild" not in rows
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: told.append(args[2]))
    window.act_add_mdi_form.trigger()  # (one a project)
    assert "has an MDI form already" in told[0]
    assert not os.path.exists(os.path.join(tmp_path, "Demo", "MDIForm2.py"))
    form1 = window._designer_for(os.path.join(tmp_path, "Demo", "Form1.py"))
    assert "MDIChild" in form1.form._specs
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
    window.close()


def test_window_list_in_the_menu_editor(qapp):
    from vp6.ide.menueditor import MenuEditorDialog, MenuEntry

    editor = MenuEditorDialog([MenuEntry(0, "&Window", "mnuWindow")], set())
    assert not editor.window_list.isChecked()
    editor.window_list.setChecked(True)
    assert editor.entries[0].props.get("WindowList") is True
    editor.window_list.setChecked(False)
    assert "WindowList" not in editor.entries[0].props
