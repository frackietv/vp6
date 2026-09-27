"""The Outline window: structure of the current file, icons, sorting,
placement and navigation."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from conftest import wait_for

from vp6.ide import kitchensink
from vp6.ide.documents import Document, FormDocument
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.ide.outline import GLOBAL_CODE, OutlineWindow, outline, sorted_outline


def flatten(items, prefix=""):
    """['HELP', 'Form1', 'Form1::Form_Load', ...] like the backlog example."""
    names = []
    for item in items:
        names.append(prefix + item.name)
        names += flatten(item.children, f"{prefix}{item.name}::")
    return names


# --- the outline itself ---------------------------------------------------------------------

def test_kitchen_sink_form1():
    source = (kitchensink.TEMPLATE_DIR / "Form1.py").read_text()
    expected = [
        "PAGES", "HELP", "Form1", "Form1::InitializeComponent", "Form1::Form_Load",
        "Form1::Form_Unload", "Form1::status", "Form1::show_page", "Form1::page_titles",
        "Form1::tvwIndex_NodeClick", "Form1::picNav_Resize", "Form1::picHeader_Resize",
        "Form1::picStatus_Resize", "Form1::splNav_Moved", "Form1::picContent_Scroll",
        "Form1::show_navigation", "Form1::set_scheme", "Form1::mnuFileEnd_Click",
        "Form1::mnuFileClose_Click", "Form1::mnuView_Click", "Form1::mnuViewNav_Click",
        "Form1::mnuScheme_Click", "Form1::add_bookmark", "Form1::mnuBookmark_Click",
        "Form1::mnuHelpKeys_Click", "Form1::mnuHelpAbout_Click", GLOBAL_CODE,
    ]
    assert flatten(outline(source)) == expected


SAMPLE = '''"""Module docstring (not listed)."""
import os
from vp6 import *

LIMIT = 10
counter, _MAX = 0, 5
counter += 1


class Shape:
    """Class docstring (not listed)."""
    sides = 0

    def area(self):
        pass

    class Unit:
        name = "px"


def helper():
    pass


print("top-level code")
Main = helper
'''


def test_kinds_lines_and_skipped_statements():
    items = outline(SAMPLE)
    kinds = [(item.name, item.kind, item.line) for item in items]
    assert kinds == [
        ("LIMIT", "constant", 5), ("counter", "variable", 6), ("_MAX", "constant", 6),
        ("counter", "variable", 7), ("Shape", "class", 10), ("helper", "function", 21),
        ("Main", "variable", 26), (GLOBAL_CODE, "code", 25),
    ]
    shape = items[4]
    assert [(m.name, m.kind) for m in shape.children] == [
        ("sides", "attribute"), ("area", "method"), ("Unit", "class")]
    assert [(m.name, m.kind) for m in shape.children[2].children] == [("name", "attribute")]
    assert items[-1].detail == 'print("top-level code")'  # the first line of top-level code


def test_syntax_error_is_reported():
    with pytest.raises(SyntaxError):
        outline("def broken(:\n")


def test_sorting():
    items = outline(SAMPLE)
    assert [i.name for i in sorted_outline(items, "order")][:3] == ["LIMIT", "counter", "_MAX"]
    assert [i.name for i in sorted_outline(items, "order", descending=True)][0] == "Main"
    by_name = [i.name for i in sorted_outline(items, "name")]
    assert by_name == sorted(by_name, key=str.lower)
    by_type = [i.kind for i in sorted_outline(items, "type")]
    assert by_type == ["constant", "constant", "variable", "variable", "variable", "class",
                       "function", "code"]
    assert [i.kind for i in sorted_outline(items, "type", descending=True)][0] == "code"
    shape = next(i for i in sorted_outline(items, "name") if i.name == "Shape")
    assert [m.name for m in shape.children] == ["area", "sides", "Unit"]  # members too


# --- the panel ------------------------------------------------------------------------------

def _tree_names(window):
    names = []

    def walk(node, prefix):
        for i in range(node.childCount()):
            child = node.child(i)
            names.append(prefix + child.text(0))
            walk(child, prefix + child.text(0) + "::")

    walk(window.tree.invisibleRootItem(), "")
    return names


def test_outline_window_shows_sorts_and_follows_edits(qapp, tmp_path):
    path = tmp_path / "Module1.py"
    path.write_text(SAMPLE)
    document = Document(str(path))
    window = OutlineWindow()
    window.set_document(document)
    assert _tree_names(window)[:3] == ["LIMIT", "counter", "_MAX"]
    top = window.tree.topLevelItem(0)
    assert not top.icon(0).isNull() and "Constant, line 5" in top.toolTip(0)

    window.buttons["name"].click()  # sort by name
    assert window.buttons["name"].text() == "Name ▲"
    window.buttons["name"].click()  # again: reversed
    assert window.buttons["name"].text() == "Name ▼"
    names = [window.tree.topLevelItem(i).text(0) for i in range(window.tree.topLevelItemCount())]
    assert names == sorted(names, key=str.lower, reverse=True)

    lines = []
    window.lineChosen.connect(lines.append)
    helper = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())
                  if window.tree.topLevelItem(i).text(0) == "helper")
    window.tree.itemClicked.emit(helper, 0)
    assert lines == [21]

    document.replace_text(SAMPLE + "\n\ndef added():\n    pass\n")  # edits update the outline
    wait_for(lambda: "added" in _tree_names(window), 2000)
    document.replace_text(SAMPLE + "\n\ndef broken(:\n")  # a syntax error keeps the last one
    wait_for(lambda: not window.problem.isHidden(), 2000)
    assert "added" in _tree_names(window) and "line" in window.problem.text()


# --- in the IDE -------------------------------------------------------------------------------

@pytest.fixture
def ide(qapp, tmp_path):
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    w.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    yield w
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


def _select(ide, text):
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    iterator = QTreeWidgetItemIterator(ide.explorer.tree)
    while iterator.value() is not None:
        if iterator.value().text(0).startswith(text):
            ide.explorer.tree.setCurrentItem(iterator.value())
            return
        iterator += 1
    raise AssertionError(text)


def _showing(ide):
    """Which of the two panels sharing a place shows: 'properties', 'outline'
    or both/neither."""
    shown = {name for name, dock in (("properties", ide.properties_dock),
                                     ("outline", ide.outline_dock)) if not dock.isHidden()}
    return shown.pop() if len(shown) == 1 else shown


def test_outline_replaces_properties_for_code_windows(ide, tmp_path):
    assert QTest.qWaitForWindowExposed(ide)
    folder = os.path.join(tmp_path, "Sink")
    assert _showing(ide) == "properties"  # a designer is active
    properties_place = ide.properties_dock.geometry()
    ide.view_code(os.path.join(folder, "Module1.py"))
    QTest.qWait(20)
    assert _showing(ide) == "outline"  # a code window: the Outline instead
    assert ide.dockWidgetArea(ide.outline_dock) == Qt.RightDockWidgetArea
    assert ide.outline_dock.geometry() == properties_place  # in the same place
    ide.view_object(os.path.join(folder, "Form1.py"))
    QTest.qWait(20)
    assert _showing(ide) == "properties"  # a designer again
    ide.act_view_outline.trigger()  # View > Outline Window: in its place anyway
    assert _showing(ide) == "outline"
    ide.act_view_props.trigger()  # F4: the Properties panel back
    assert _showing(ide) == "properties"


def test_a_closed_panel_stays_closed(ide, tmp_path):
    folder = os.path.join(tmp_path, "Sink")
    ide.properties_dock.close()  # the user closes the Properties panel
    ide.view_code(os.path.join(folder, "Module1.py"))
    ide.view_object(os.path.join(folder, "Form1.py"))
    QTest.qWait(20)
    assert _showing(ide) == set()  # neither comes back by itself
    ide.act_view_props.trigger()  # until asked for
    assert _showing(ide) == "properties"


def test_closing_the_last_window_shows_properties(ide, tmp_path):
    folder = os.path.join(tmp_path, "Sink")
    ide.view_code(os.path.join(folder, "Module1.py"))
    QTest.qWait(20)
    assert _showing(ide) == "outline"
    for sub in ide.mdi.subWindowList():
        sub.close()
    QTest.qWait(20)
    assert _showing(ide) == "properties"


def test_default_layout(ide):
    ide.act_view_outline.trigger()
    ide.reset_layout()
    assert _showing(ide) == "properties" and ide.outline_dock.isHidden()


def test_outline_follows_the_context_and_navigates(ide, tmp_path):
    folder = os.path.join(tmp_path, "Sink")
    ide.act_view_outline.trigger()
    _select(ide, "Module1")
    assert _tree_names(ide.outline) == ["Main", GLOBAL_CODE]
    _select(ide, "Form1")
    assert "Form1::tvwIndex_NodeClick" in _tree_names(ide.outline)
    ide.explorer.select_project()  # the project isn't code
    assert _tree_names(ide.outline) == []
    ide.explorer_dock.hide()  # Project panel closed: follows the active window
    ide.view_code(os.path.join(folder, "frmDialog.py"))
    assert "frmDialog::cmdOK_Click" in _tree_names(ide.outline)

    # Clicking an item opens the code window at that line
    node = ide.outline.tree.topLevelItem(0).child(1)  # frmDialog::Form_Load
    ide.outline.tree.itemClicked.emit(node, 0)
    editor = ide.code_windows[os.path.join(folder, "frmDialog.py")].widget().editor
    line = editor.textCursor().block().text()
    assert line.strip().startswith("def Form_Load")
    # Items inside the folded designer region unfold it
    region_item = ide.outline.tree.topLevelItem(0).child(0)  # InitializeComponent
    assert region_item.text(0) == "InitializeComponent"
    ide.outline.tree.itemClicked.emit(region_item, 0)
    assert editor.textCursor().block().isVisible()
    assert "def InitializeComponent" in editor.textCursor().block().text()


def test_outline_of_a_form_document(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text((kitchensink.TEMPLATE_DIR / "frmDialog.py").read_text())
    window = OutlineWindow()
    window.set_document(FormDocument(str(path)))
    assert _tree_names(window)[:3] == ["frmDialog", "frmDialog::InitializeComponent",
                                       "frmDialog::Form_Load"]
