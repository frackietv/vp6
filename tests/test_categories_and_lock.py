"""The Properties window's Categorized view (VB's Alphabetic / Categorized
tabs) and Format > Lock Controls in the designer."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vp6 import formfile
from vp6._props import P, category_of
from vp6.controls import CONTROL_TYPES
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.ide.properties import PropertiesWindow
from vp6.ide.theme import ide_settings
from vp6.usercontrol import Property


@pytest.fixture
def designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    QTest.qWait(10)
    yield d
    d.close()


def rows(window):
    table = window.table
    return [table.item(r, 0).text() if table.item(r, 0) else "" for r in range(table.rowCount())]


# --- categories ------------------------------------------------------------------------------

def test_categories():
    specs = {name: spec for cls in CONTROL_TYPES.values() for name, spec in cls._specs.items()}
    assert category_of(specs["BackColor"]) == "Appearance"
    assert category_of(specs["Enabled"]) == "Behavior"
    assert category_of(specs["FontName"]) == "Font"
    assert category_of(specs["Left"]) == "Position"
    assert category_of(specs["Text"]) == "Text"
    assert category_of(specs["List"]) == "List"
    assert category_of(specs["Tag"]) == category_of(P("Unknown")) == "Misc"
    assert category_of(P("Stars", category="Appearance")) == "Appearance"  # its own
    assert category_of(Property("Rating", "int", category="Behavior")) == "Behavior"
    known = {"Appearance", "Behavior", "Data", "Font", "List", "Misc", "Position", "Text"}
    assert {category_of(spec) for spec in specs.values()} <= known


def test_the_categorized_view(designer):
    name = designer.create_control("CommandButton", None, None)
    designer.select([name])
    window = PropertiesWindow()
    window.set_designer(designer)
    assert [window.view_tabs.tabText(i) for i in range(2)] == ["Alphabetic", "Categorized"]
    alphabetic = rows(window)
    assert alphabetic[:2] == ["(Name)", "Index"] and alphabetic[2:] == sorted(alphabetic[2:])
    window.view_tabs.setCurrentIndex(1)
    categorized = rows(window)
    headings = [r for r in categorized if r.startswith("▾")]
    assert [h.split()[-1] for h in headings] == ["Appearance", "Behavior", "Font", "Misc",
                                                 "Position"]
    misc = categorized.index("▾  Misc")
    assert categorized[misc + 1] == "(Name)"  # (Name) first in Misc, like VB
    position = categorized.index("▾  Position")
    assert categorized[position + 1:] == ["Height", "Left", "Top", "Width", "ZIndex"]
    assert set(categorized) - set(headings) == set(alphabetic)  # the same properties
    # Editing still works there: the row's editor sets the property
    caption = categorized.index("Caption")
    window.table.cellWidget(caption, 1).setText("OK")
    window.table.cellWidget(caption, 1).editingFinished.emit()
    assert designer.form_def.control(name).props["Caption"] == "OK"
    # A heading collapses and expands its category (kept while showing others)
    behavior = rows(window).index("▾  Behavior")
    window.table.cellClicked.emit(behavior, 0)
    assert rows(window)[behavior] == "▸  Behavior"
    enabled = rows(window).index("Enabled")
    assert window.table.isRowHidden(enabled) and "Behavior" in window.collapsed
    designer.select([])  # the form: Behavior still collapsed
    assert window.table.isRowHidden(rows(window).index("Enabled"))
    window.select_property("Enabled")  # (shown: its category opens)
    assert not window.table.isRowHidden(rows(window).index("Enabled"))
    window.table.setCurrentCell(rows(window).index("▾  Font"), 0)
    assert window.description.text() == "<b>Font</b>"
    # The view is remembered (the IDE's settings)
    assert ide_settings().value("properties/view") == "categorized"
    assert PropertiesWindow().categorized()
    window.view_tabs.setCurrentIndex(0)
    assert rows(window) == [r for r in rows(window) if not r.startswith(("▾", "▸"))]
    assert not PropertiesWindow().categorized()


# --- Lock Controls ---------------------------------------------------------------------------

def test_locked_controls_stay_put(designer):
    name = designer.create_control("CommandButton", None, None)
    designer.select([name])
    props = designer.form_def.control(name).props
    before = (props["Left"], props["Top"], props["Width"], props["Height"])
    overlay = designer.overlay
    designer.set_locked(True)
    rect = designer.canvas_rect(name)
    # Not dragged...
    QTest.mousePress(overlay, Qt.LeftButton, Qt.NoModifier, rect.center())
    QTest.mouseMove(overlay, rect.center() + QPoint(40, 30))
    QTest.mouseRelease(overlay, Qt.LeftButton, Qt.NoModifier, rect.center() + QPoint(40, 30))
    assert designer.selection == [name]  # (still selected)
    # ...nor resized by a handle...
    corner = rect.bottomRight() + QPoint(1, 1)
    assert overlay._handle_at(corner) is None
    QTest.mousePress(overlay, Qt.LeftButton, Qt.NoModifier, corner)
    QTest.mouseMove(overlay, corner + QPoint(30, 30))
    QTest.mouseRelease(overlay, Qt.LeftButton, Qt.NoModifier, corner + QPoint(30, 30))
    # ...nor nudged with the arrow keys
    messages = []
    designer.statusMessage.connect(messages.append)
    designer.select([name])  # (the click beside it chose the form)
    QTest.keyClick(overlay, Qt.Key_Right)
    assert (props["Left"], props["Top"], props["Width"], props["Height"]) == before
    assert "locked" in messages[-1]
    # The Properties window still moves it; the form itself still resizes
    assert designer.set_property("Left", before[0] + 8) is None
    assert designer.form_def.control(name).props["Left"] == before[0] + 8
    designer.select([])
    assert overlay._handle_at(overlay._form_handles()["br"].center()) is not None
    # Unlocked: dragged again
    designer.set_locked(False)
    designer.select([name])
    rect = designer.canvas_rect(name)
    QTest.mousePress(overlay, Qt.LeftButton, Qt.NoModifier, rect.center())
    QTest.mouseMove(overlay, rect.center() + QPoint(40, 30))
    QTest.mouseRelease(overlay, Qt.LeftButton, Qt.NoModifier, rect.center() + QPoint(40, 30))
    assert designer.form_def.control(name).props["Left"] != before[0] + 8


def test_lock_controls_in_the_ide(qapp, tmp_path):
    window = MainWindow()
    window.show()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    form1 = os.path.join(tmp_path, "Demo", "Form1.py")
    fmt = next(a.menu() for a in window.menuBar().actions() if a.text() == "F&ormat")
    assert window.act_lock in fmt.actions() and window.act_lock.isCheckable()
    assert window.act_lock.isEnabled() and not window.act_lock.isChecked()
    window.act_lock.trigger()  # lock
    designer = window._designers[form1]
    assert designer.locked and window.act_lock.isChecked()
    window.view_code(os.path.join(tmp_path, "Demo", "Module1.py"))  # a module: nothing to lock
    assert not window.act_lock.isEnabled()
    window.view_object(form1)
    assert window.act_lock.isEnabled() and window.act_lock.isChecked()
    window.close_project()
    # Remembered for the form (the IDE's settings): locked again when reopened
    window.open_project(os.path.join(tmp_path, "Demo", "Demo.vp6p"))
    assert window._designers[form1].locked and window.act_lock.isChecked()
    window.act_lock.trigger()  # unlock
    assert not window._designers[form1].locked
    window.close_project()
    window.close()
