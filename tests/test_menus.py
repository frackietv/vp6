"""Menus on forms: the runtime Menu control, the form file, the designer's
menu bar and the Menu Editor."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vp6 import (ControlArray, Form, Label, Load, Menu, PictureBox, Unload, formfile,
                 vpAlignFill, vpNegotiateLeft, vpNegotiateMiddle, vpNegotiateNone,
                 vpNegotiateRight)
from vp6.ide import menueditor
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.ide.menueditor import MenuEditorDialog, MenuEntry
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


# --- runtime ---------------------------------------------------------------------------------

class Editor(Form):
    def InitializeComponent(self):
        self.Height = 300
        self.lblText = Label(self, Caption="text", Left=8, Top=8, Width=100, Height=25)
        self.mnuFile = Menu(self, Caption="&File")
        self.mnuFileOpen = Menu(self.mnuFile, Caption="&Open...", Shortcut="Ctrl+O")
        self.mnuFileSep = Menu(self.mnuFile, Caption="-")
        self.mnuRecent = ControlArray()
        self.mnuRecent[0] = Menu(self.mnuFile, Caption="first.txt")
        self.mnuFileExit = Menu(self.mnuFile, Caption="E&xit")
        self.mnuView = Menu(self, Caption="&View")
        self.mnuViewBold = Menu(self.mnuView, Caption="&Bold", Checked=True)

    def Form_Load(self):
        self.events = []

    def Form_Click(self):
        self.events.append("form click")

    def mnuFile_Click(self):
        self.events.append("file opens")

    def mnuFileOpen_Click(self):
        self.events.append("open")

    def mnuRecent_Click(self, Index):
        self.events.append(("recent", Index))

    def mnuViewBold_Click(self):
        self.mnuViewBold.Checked = not self.mnuViewBold.Checked


@pytest.fixture
def editor(qapp):
    form = Editor()
    form.Show()
    yield form
    form.Unload()


def _texts(menu):
    return [a.text() for a in menu._submenu.actions() if a.isVisible()]


def test_menu_bar_and_items(editor):
    bar = editor._menubar
    assert [a.text() for a in bar.actions()] == ["&File", "&View"]
    assert _texts(editor.mnuFile) == ["&Open...", "-", "first.txt", "E&xit"]
    assert editor.mnuFileSep._action.isSeparator()
    assert editor.mnuFileOpen._action.shortcut().toString() == "Ctrl+O"
    assert editor.mnuFileOpen in editor.Controls and editor.mnuFileOpen.Parent is editor.mnuFile


def test_menu_bar_in_the_window_keeps_the_client_area(editor):
    if editor._menubar.isNativeMenuBar():
        pytest.skip("the menu bar is the system's (macOS)")
    height = editor._menu_height
    assert height > 0 and editor.Height == 300 == editor.ScaleHeight
    assert editor._widget.height() == 300 + height  # the window grew
    label = editor.lblText._widget
    assert label.mapTo(editor._widget, QPoint(0, 0)).y() == 8 + height
    assert editor.lblText.Top == 8  # positions are still relative to the client area
    editor.Height = 200
    assert editor.Height == 200 and editor._widget.height() == 200 + height
    QTest.mouseClick(editor._client, Qt.LeftButton, Qt.NoModifier, QPoint(150, 150))
    assert "form click" in editor.events  # the area below the menu bar is the form


def test_click_events_and_checked(editor):
    editor.mnuFileOpen._action.trigger()
    editor.mnuFile._submenu.aboutToShow.emit()  # opening a menu fires its Click
    assert editor.events == ["open", "file opens"]
    editor.mnuViewBold._action.trigger()  # Checked only changes when code changes it
    assert not editor.mnuViewBold.Checked and not editor.mnuViewBold._action.isChecked()
    editor.mnuViewBold._action.trigger()
    assert editor.mnuViewBold.Checked and editor.mnuViewBold._action.isChecked()
    editor.mnuFileOpen.Enabled = False
    editor.mnuFileExit.Visible = False
    assert not editor.mnuFileOpen._action.isEnabled()
    assert "E&xit" not in _texts(editor.mnuFile)
    editor.mnuFileOpen.Caption = "&Open File..."
    editor.mnuFileOpen.Shortcut = "F3"
    assert editor.mnuFileOpen._action.text() == "&Open File..."
    assert editor.mnuFileOpen._action.shortcut().toString() == "F3"


def test_menu_control_arrays_load_after_the_last_element(editor):
    second = Load(editor.mnuRecent, 1)  # VB's most-recently-used list
    second.Caption, second.Visible = "second.txt", True
    third = editor.mnuRecent.Load(2)
    third.Caption, third.Visible = "third.txt", True
    assert _texts(editor.mnuFile) == ["&Open...", "-", "first.txt", "second.txt", "third.txt",
                                      "E&xit"]
    third._action.trigger()
    assert editor.events == [("recent", 2)]
    Unload(editor.mnuRecent, 1)
    assert _texts(editor.mnuFile) == ["&Open...", "-", "first.txt", "third.txt", "E&xit"]


def test_menus_need_a_menu_or_the_form_as_parent(qapp):
    class Wrong(Form):
        def InitializeComponent(self):
            self.lbl = Label(self)
            self.mnu = Menu(self.lbl, Caption="x")

    with pytest.raises(TypeError, match="parent"):
        Wrong()


# --- the form file ---------------------------------------------------------------------------

def test_form_file_round_trip():
    form = formfile.FormDef("Form1", {"Caption": "Form1", "Width": 480, "Height": 360})
    defs = menueditor.menu_defs([
        MenuEntry(0, "&File", "mnuFile"),
        MenuEntry(1, "&Open", "mnuOpen", shortcut="Ctrl+O"),
        MenuEntry(1, "one", "mnuRecent", 0),
        MenuEntry(1, "two", "mnuRecent", 1, checked=True),
    ])
    form.controls = defs
    source = formfile.new_form_source("Form1").replace(
        formfile.generate_region(formfile.parse(formfile.new_form_source("Form1"))),
        formfile.generate_region(form))
    assert "self.mnuOpen = Menu(self.mnuFile, Caption='&Open', Shortcut='Ctrl+O')" in source
    assert "self.mnuRecent[1] = Menu(self.mnuFile, Caption='two', Checked=True)" in source
    assert formfile.parse(source) == form


# --- the Menu Editor ------------------------------------------------------------------------

ENTRIES = [
    MenuEntry(0, "&File", "mnuFile"),
    MenuEntry(1, "&Open...", "mnuFileOpen", shortcut="Ctrl+O"),
    MenuEntry(1, "-", "mnuFileSep"),
    MenuEntry(1, "E&xit", "mnuFileExit"),
    MenuEntry(0, "&Help", "mnuHelp"),
    MenuEntry(1, "&About", "mnuHelpAbout"),
]


def test_entries_and_defs_round_trip():
    form = formfile.FormDef("Form1", controls=menueditor.menu_defs(ENTRIES))
    assert form.control("mnuFileExit").parent == "mnuFile"
    assert form.control("mnuHelpAbout").parent == "mnuHelp"
    entries = menueditor.entries_from(form)
    assert [(e.level, e.name) for e in entries] == [(e.level, e.name) for e in ENTRIES]
    assert entries[1].shortcut == "Ctrl+O" and entries[1].original == "mnuFileOpen"


@pytest.mark.parametrize("change, message", [
    (lambda e: setattr(e[1], "name", ""), "needs a Name"),
    (lambda e: setattr(e[1], "name", "not valid"), "not a valid name"),
    (lambda e: setattr(e[1], "name", "lblText"), "already used on the form"),
    (lambda e: setattr(e[3], "name", "mnuFileOpen"), "used twice"),
    (lambda e: setattr(e[5], "level", 3), "more than one level"),
    (lambda e: setattr(e[2], "level", 0), "separator can't be on the menu bar"),
    (lambda e: (setattr(e[1], "index", 0), setattr(e[3], "name", "mnuFileOpen")),
     "each needs an Index"),
])
def test_validation(change, message):
    entries = [MenuEntry(**vars(e)) for e in ENTRIES]
    change(entries)
    assert message in menueditor.validate(entries, {"lblText", "Form1"})
    assert menueditor.validate(ENTRIES, {"lblText"}) is None


def test_dialog_editing(qapp):
    dialog = MenuEditorDialog([], {"Form1"})
    dialog.caption.setText("&File")
    dialog.caption.textEdited.emit("&File")
    dialog.name.setText("mnuFile")
    dialog.name.textEdited.emit("mnuFile")
    dialog.next()  # a new item at the end
    dialog.indent()  # an item of the File menu
    dialog.caption.setText("&Quit")
    dialog.caption.textEdited.emit("&Quit")
    dialog.name.setText("mnuQuit")
    dialog.name.textEdited.emit("mnuQuit")
    dialog.shortcut.setCurrentIndex(dialog.shortcut.findData("Ctrl+Q"))
    dialog.shortcut.activated.emit(dialog.shortcut.currentIndex())
    dialog.checked.setChecked(True)
    assert [dialog.list.item(i).text() for i in range(dialog.list.count())] == \
        ["&File", "····&Quit"]
    assert not dialog.buttons["right"].isEnabled()  # at most one level below the item above
    dialog.next()  # an empty item: dropped on OK
    assert dialog.error() is None
    entries = dialog.result_entries()
    assert [(e.level, e.name, e.shortcut, e.checked) for e in entries] == \
        [(0, "mnuFile", "", False), (1, "mnuQuit", "Ctrl+Q", True)]
    dialog.list.setCurrentRow(1)
    dialog.insert()  # above Quit, same level
    assert dialog.row == 1 and dialog.current.level == 1 and dialog.current.is_blank()
    dialog.delete()
    dialog.move_up()  # Quit above File
    assert [e.name for e in dialog.entries[:2]] == ["mnuQuit", "mnuFile"]
    dialog.outdent()
    assert dialog.current.level == 0


# --- the designer ------------------------------------------------------------------------------

@pytest.fixture
def designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    yield d
    d.close()


def test_designer_draws_the_menu_bar_and_opens_code(designer):
    d = designer
    top_before = d.form_widget().y()
    assert d.set_menus(ENTRIES) is None
    assert d.form_widget().y() == top_before + 22  # the menu bar is above the form
    assert d.menu_bar_keys() == ["mnuFile", "mnuHelp"]
    assert d.frame_info().menus == ("&File", "&Help")
    assert "self.mnuFileOpen = Menu(self.mnuFile, Caption='&Open...'" in d.document.text
    rect = d.menu_rect("mnuHelp")
    assert d.menu_at(rect.center()) == "mnuHelp" and d.menu_at(QPoint(0, 0)) is None
    popup = d.menu_popup("mnuFile")
    texts = [a.text() for a in popup.actions()]
    assert texts == ["&Open...\tCtrl+O", "", "E&xit"]
    requests = []
    d.viewCodeRequested.connect(lambda obj, event: requests.append((obj, event)))
    popup.actions()[2].trigger()  # choosing an item opens its Click code
    assert requests == [("mnuFileExit", "Click")]
    popup.deleteLater()


def test_designer_canvas_ignores_menus(designer):
    d = designer
    d.set_menus(ENTRIES)
    origin = d.form_canvas_rect().topLeft()
    d.create_control("Label", None, None, origin + QPoint(16, 16))
    d.select_all()
    assert d.selection == ["Label1"]  # menus aren't on the canvas
    d.select(["Label1", "mnuFile"])
    assert d.selection == ["Label1"]
    d.select(["mnuFileOpen"])  # e.g. from the Properties window: alone
    d.nudge(8, 8)
    d.copy_selection()
    d.align("left")
    assert d.selection == ["mnuFileOpen"]
    window = PropertiesWindow()
    window.set_designer(d)
    rows = [window.table.item(r, 0).text() for r in range(window.table.rowCount())]
    assert rows == ["(Name)", "Index", "Caption", "Checked", "Enabled", "NegotiatePosition",
                    "Shortcut", "Tag", "Visible", "WindowList"]
    assert d.set_property("Caption", "&Open File...") is None
    assert "Caption='&Open File...'" in d.document.text
    d.select(["mnuFile"])
    d.delete_selection()  # a menu and its items
    assert d.menu_bar_keys() == ["mnuHelp"]
    assert d.form_def.control("mnuFileOpen") is None


def test_menu_editor_renames_and_arrays_update_handlers(designer):
    d = designer
    d.set_menus(ENTRIES)
    d.document.replace_text(d.document.text.replace(
        "    def Form_Load(self):", "    def mnuFileExit_Click(self):\n        pass\n\n"
                                    "    def mnuHelpAbout_Click(self):\n        pass\n\n"
                                    "    def Form_Load(self):"))
    entries = d.menu_entries()
    entries[3].name = "mnuQuit"  # renamed in the Menu Editor
    entries[5].index = 0  # About becomes a control array
    assert d.set_menus(entries) is None
    text = d.document.text
    assert "def mnuQuit_Click(self):" in text and "mnuFileExit" not in text
    assert "def mnuHelpAbout_Click(self, Index):" in text
    assert "self.mnuHelpAbout[0] = Menu(self.mnuHelp, Caption='&About')" in text
    d.undo()
    assert d.form_def.control("mnuFileExit") is not None


def test_ide_menu_editor_command(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    window.show()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    opened = []
    monkeypatch.setattr(MenuEditorDialog, "exec", lambda self: opened.append(self) or 0)
    window.act_menu_editor.trigger()  # Ctrl+E with Form1's designer active
    assert opened and opened[0].windowTitle() == "Menu Editor"
    assert window.act_menu_editor.shortcut().toString() == "Ctrl+E"
    tools = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Tools")
    assert window.act_menu_editor in tools.actions()
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
    window.close()


# --- menu negotiation: forms shown in other forms ---------------------------------------------

class Page(Form):
    def InitializeComponent(self):
        self.mnuLeft = Menu(self, Caption="&Left", NegotiatePosition=vpNegotiateLeft)
        self.mnuPage = Menu(self, Caption="&Page", NegotiatePosition=vpNegotiateRight)
        self.mnuPageHello = Menu(self.mnuPage, Caption="&Hello", Shortcut="Ctrl+H")
        self.mnuMiddle = Menu(self, Caption="&Middle", NegotiatePosition=vpNegotiateMiddle)
        self.mnuPrivate = Menu(self, Caption="&Private")  # None (the default): not shown

    def Form_Load(self):
        self.said = []

    def mnuPageHello_Click(self):
        self.said.append("hello")


class Window(Form):
    def InitializeComponent(self):
        self.mnuFile = Menu(self, Caption="&File")
        self.mnuView = Menu(self, Caption="&View")
        self.mnuHelp = Menu(self, Caption="&Help", NegotiatePosition=vpNegotiateRight)
        self.picPane = PictureBox(self, Align=vpAlignFill, BorderStyle=0)


def _bar(form):
    return [action.text() for action in form._menubar.actions()]


@pytest.fixture
def window(qapp):
    form = Window()
    form.Show()
    yield form
    form.Unload()


def test_menus_of_a_form_inside_join_the_window(window):
    page = Page()
    page.ShowIn(window.picPane)
    # Left before the window's menus, Middle after its first, Right before its Right ones
    assert _bar(window) == ["&Left", "&File", "&Middle", "&View", "&Page", "&Help"]
    assert not page._menubar.isVisible()  # no second menu bar inside the pane
    assert page.ScaleHeight == window.picPane.Height  # and no room kept for one
    page.mnuPageHello._action.trigger()  # the page's own handler
    assert page.said == ["hello"]
    assert vpNegotiateNone == 0


def test_they_leave_with_the_form(window):
    page, other = Page(), Page()
    page.ShowIn(window.picPane)
    page.Hide()
    assert _bar(window) == ["&File", "&View", "&Help"]
    page.Show()
    other.ShowIn(window.picPane)  # replaces the page: only the new one's menus
    assert _bar(window).count("&Page") == 1
    other.Unload()
    assert _bar(window) == ["&File", "&View", "&Help"]


def test_popped_out_it_has_its_own_menu_bar(window):
    page = Page()
    page.ShowIn(window.picPane)
    page.ShowIn(None)
    assert _bar(window) == ["&File", "&View", "&Help"]
    assert _bar(page) == ["&Left", "&Page", "&Middle", "&Private"]
    if not page._menubar.isNativeMenuBar():
        assert page._menubar.isVisible() and page._menu_height > 0
    page.ShowIn(window.picPane)  # and back
    assert "&Page" in _bar(window)
    page.Unload()


def test_negotiate_menus_and_positions_change(window):
    page = Page()
    page.ShowIn(window.picPane)
    window.NegotiateMenus = False  # the window doesn't take them
    assert _bar(window) == ["&File", "&View", "&Help"]
    window.NegotiateMenus = True
    page.mnuPage.NegotiatePosition = vpNegotiateLeft  # moves at once
    assert _bar(window)[:2] == ["&Left", "&Page"]
    page.mnuAdded = Menu(page, Caption="&Added", NegotiatePosition=vpNegotiateRight)
    assert _bar(window)[-2:] == ["&Added", "&Help"]  # a menu added while merged


def test_a_window_without_menus_gets_a_bar(qapp):
    class Plain(Form):
        def InitializeComponent(self):
            self.picPane = PictureBox(self, Align=vpAlignFill)

    plain, page = Plain(), Page()
    plain.Show()
    page.ShowIn(plain.picPane)
    assert _bar(plain) == ["&Left", "&Middle", "&Page"]
    plain.Unload()


def test_menu_editor_negotiate_position(qapp):
    entries = [MenuEntry(0, "&Page", "mnuPage", props={"NegotiatePosition": 3})]
    dialog = MenuEditorDialog(entries, set())
    assert dialog.negotiate.currentData() == 3
    dialog.negotiate.setCurrentIndex(1)
    dialog.negotiate.activated.emit(1)
    assert dialog.result_entries()[0].props["NegotiatePosition"] == 1
    defs = menueditor.menu_defs(dialog.result_entries())
    assert defs[0].props["NegotiatePosition"] == 1
