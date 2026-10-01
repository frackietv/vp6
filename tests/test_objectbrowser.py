"""The Object Browser: VP6's classes, members, events and constants, the
project's forms, user controls and modules, search, the window, and going to
a project member from it (View > Object Browser, F2)."""

import os

import pytest

from vp6.ide.mainwindow import MainWindow, create_project
from vp6.ide.objectbrowser import (ALL_LIBRARIES, VP6_LIBRARY, ObjectBrowser, project_library,
                                   search, vp6_library)

MODULE = '''"""Helpers for the demo."""

LIMIT = 10
count = 0


def Main():
    """Starts the program."""
    pass


def add(a, b):
    return a + b


class Totals:
    """A running total."""


def broken(:
'''


def by_name(classes, name):
    return next(c for c in classes if c.name == name)


def member(info, name):
    return next(m for m in info.members() if m.name == name)


# --- VP6 --------------------------------------------------------------------------------------

def test_vp6_classes_and_members(qapp):
    library = vp6_library()
    names = [c.name for c in library]
    assert names == sorted(names, key=str.lower)
    button = by_name(library, "CommandButton")
    assert button.kind == "Class" and button.library == VP6_LIBRARY
    caption = member(button, "Caption")
    assert (caption.kind, caption.declaration) == ("Property", "Property Caption As String")
    assert "access key" in caption.description
    click = member(button, "MouseDown")
    assert click.kind == "Event" and click.declaration == "Event MouseDown(Button, Shift, X, Y)"
    move = member(button, "Move")
    assert move.kind == "Method" and move.declaration.startswith("Move(Left")
    style = member(button, "Style")  # an enum: its choices
    assert "0 - Standard" in style.description
    assert member(by_name(library, "ListBox"), "ListIndex").kind == "Property"  # (run time)
    assert member(by_name(library, "Form"), "Paint").kind == "Event"
    # Objects, functions and constants
    assert {"Major", "Title", "PrevInstance"} <= {m.name for m in by_name(library, "App")
                                                  .members()}
    assert by_name(library, "Printer").kind == "Object"
    msgbox = member(by_name(library, "Globals"), "MsgBox")
    assert msgbox.kind == "Method" and msgbox.declaration.startswith("MsgBox(prompt")
    results = by_name(library, "MsgBox results")
    assert results.kind == "Constants"
    assert member(results, "vpYes").declaration == "Const vpYes = 6"
    assert member(by_name(library, "Colors"), "vpRed").declaration == "Const vpRed = 255"
    assert "vpSchemeDark" in [m.name for m in by_name(library, "Color schemes").members()]


# --- the project -------------------------------------------------------------------------------

@pytest.fixture
def ide(qapp, tmp_path):
    window = MainWindow()
    window.show()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = os.path.join(tmp_path, "Demo")
    module1, form1 = os.path.join(folder, "Module1.py"), os.path.join(folder, "Form1.py")
    window.documents[module1].replace_text(MODULE)
    designer = window._designer_for(form1)
    designer.create_control("CommandButton", None, None)
    form = window.documents[form1]
    form.replace_text(form.text.replace("    # endregion\n", "    # endregion\n\n"
                                        "    def helper(self, value):\n"
                                        '        """Does something."""\n', 1))
    yield window, form1, module1
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
    window.close()


def test_project_classes(ide):
    window, form1, module1 = ide
    name, documents = window._browser_project()
    library = project_library(name, documents)
    assert [c.name for c in library] == ["Form1", "Module1"]
    form = by_name(library, "Form1")
    assert form.kind == "Form" and form.library == "Demo" and form.path == form1
    button = member(form, "Command1")
    assert (button.kind, button.declaration, button.type_name) == \
        ("Control", "Command1 As CommandButton", "CommandButton")
    helper = member(form, "helper")
    assert helper.declaration == "helper(value)" and helper.description == "Does something."
    assert "InitializeComponent" not in [m.name for m in form.members()]
    module = by_name(library, "Module1")
    assert module.kind == "Module" and module.description == "Helpers for the demo."
    kinds = {m.name: (m.kind, m.declaration) for m in module.members()}
    assert kinds["LIMIT"] == ("Constant", "Const LIMIT = 10")
    assert kinds["count"] == ("Variable", "Dim count = 0")
    assert kinds["add"] == ("Method", "add(a, b)") and kinds["Totals"][0] == "Class"
    assert "broken" not in kinds  # (its syntax error: what came before is there)
    assert member(module, "add").line == MODULE.splitlines().index("def add(a, b):") + 1


def test_user_controls_in_the_project(qapp, tmp_path):
    window = MainWindow()
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    library = project_library(*window._browser_project())
    rating = by_name(library, "ctlRating")
    assert rating.kind == "UserControl"
    kinds = {m.name: m.kind for m in rating.members()}
    assert kinds["Value"] == "Property" and kinds["Change"] == "Event"
    assert kinds["UserControl_PropertyChanged"] == "Method"
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
    window.close()


def test_search(qapp):
    found = search(vp6_library(), "listindex")
    assert ("ListBox", "ListIndex") in [(c.name, m.name if m else None) for c, m in found]
    assert ("Picture", None) in [(c.name, m and m.name) for c, m in search(vp6_library(),
                                                                           "Picture")]
    assert search(vp6_library(), "  ") == []


# --- the window and the IDE ---------------------------------------------------------------------

def test_the_window(qapp):
    browser = ObjectBrowser()  # (no project)
    assert [browser.library.itemText(i) for i in range(browser.library.count())] == \
        [ALL_LIBRARIES, VP6_LIBRARY]
    browser.library.setCurrentIndex(1)
    assert browser.show_class("TextBox", "SelStart")
    assert "SelStart" in browser.details.text() and "VP6.TextBox" in browser.details.text()
    browser.show_class("MsgBox results")
    assert "Constants MsgBox results" in browser.details.text()
    browser.search_edit.setText("nowhere at all")
    browser.run_search()
    assert not browser.results.isHidden()
    assert browser.results.item(0).text() == "(nothing found)"
    browser.search_edit.setText("PrevInstance")
    browser.run_search()
    assert browser.results.count() == 1
    browser.results.setCurrentRow(0)  # chosen: its class and member
    assert browser.classes[browser.class_list.currentRow()].name == "App"
    assert browser.shown_members[browser.member_list.currentRow()].name == "PrevInstance"
    browser.close()


def test_in_the_ide(ide):
    window, form1, module1 = ide
    view = next(a.menu() for a in window.menuBar().actions() if a.text() == "&View")
    assert window.act_view_browser in view.actions()
    assert window.act_view_browser.shortcut().toString() == "F2"
    browser = window.show_object_browser()
    libraries = [browser.library.itemText(i) for i in range(browser.library.count())]
    assert libraries == [ALL_LIBRARIES, VP6_LIBRARY, "Demo"]
    browser.library.setCurrentIndex(0)  # all: VP6's and the project's
    assert {"Form1", "CommandButton"} <= {c.name for c in browser.classes}
    browser.library.setCurrentIndex(2)
    assert [c.name for c in browser.classes] == ["Form1", "Module1"]
    # Double-click a member: its code...
    browser.show_class("Module1", "add")
    browser.member_list.itemActivated.emit(browser.member_list.currentItem())
    editor = window.mdi.currentSubWindow().widget().editor
    assert editor.current_line() == MODULE.splitlines().index("def add(a, b):") + 1
    # ...or, a control: the form's designer with it selected
    browser.show_class("Form1", "Command1")
    browser.member_list.itemActivated.emit(browser.member_list.currentItem())
    assert window._designers[form1].selection == ["Command1"]
    # The project as it is now: shown again, new code is there
    window.documents[module1].replace_text(MODULE.replace("def broken(:\n", "") +
                                           "\ndef later():\n    pass\n")
    window.show_object_browser()
    assert browser.library.currentText() == "Demo"
    browser.show_class("Module1")
    assert browser.show_class("Module1", "later")
    browser.close()
