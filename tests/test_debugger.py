"""The debugger: breakpoints in the code windows, real programs run by the IDE
paused at them, stepping, Break (in a loop and between events), errors,
watches and the Immediate window while paused."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6 import debugagent
from vp6.ide.codeeditor import MARKERS, CodeWindow
from vp6.ide.debugger import DebugSession, WatchWindow, describe
from vp6.ide.debugpanel import BreakpointList, CallStackView, DebugPanel
from vp6.ide.documents import Document
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.ide.theme import theme_manager


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setenv("VP6_NO_ERROR_DIALOG", "1")
    w = MainWindow()
    w.show()
    yield w
    w.stop_project()
    wait_for(lambda: not w.running)
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


CONSOLE = '''from vp6 import *


def add(a, b):
    result = a + b
    return result


def Main():
    total = 0
    for i in range(3):
        total = add(total, i)
    print("total", total)
'''


def _project(window, tmp_path, kind="console", text=CONSOLE, name="Module1.py"):
    window.open_project(create_project(str(tmp_path), "Demo", kind))
    doc = next(d for d in window.documents.values() if d.filename == name)
    doc.replace_text(text)
    return doc


class _Stops:
    """The pauses of a run, as they come."""

    def __init__(self, window):
        self.window = window
        self.seen = []

    def attach(self):
        self.window.debug.paused.connect(self.seen.append)

    def next(self, count: int) -> dict:
        wait_for(lambda: len(self.seen) >= count and self.window.paused, 10000)
        return self.seen[count - 1]


def _run(window, step=False) -> _Stops:
    stops = _Stops(window)
    window.run_project(step=step)
    stops.attach()
    return stops


def _evaluate(window, expression: str) -> dict:
    results = []
    window.debug.evaluate(expression, results.append, statements=True)
    wait_for(lambda: results)
    return results[0]


# --- breakpoints in the documents and the code windows ----------------------------------------

def test_disabled_breakpoints(qapp, tmp_path):
    path = tmp_path / "Module1.py"
    path.write_text("a = 1\nb = 2\nc = 3\n")
    doc = Document(str(path))
    doc.set_breakpoint(1, True)
    doc.set_breakpoint(3, True, enabled=False)
    assert doc.breakpoints() == [(1, True), (3, False)]
    assert doc.breakpoint_lines() == [1, 3] and doc.breakpoint_lines(enabled_only=True) == [1]
    changes = []
    doc.breakpointsChanged.connect(lambda: changes.append(1))
    doc.enable_breakpoint(3, True)
    doc.enable_breakpoint(3, True)  # (no change: no signal)
    assert doc.breakpoint_enabled(3) and len(changes) == 1
    doc.enable_breakpoint(1, False)
    doc.replace_text("first = 0\n" + doc.text)  # (a whole new text keeps them, as they were)
    assert doc.breakpoints() == [(1, False), (3, True)]
    assert doc.toggle_breakpoint(1) is False and doc.breakpoints() == [(3, True)]


def test_breakpoints_follow_the_edits(qapp, tmp_path):
    path = tmp_path / "Module1.py"
    path.write_text("a = 1\n\nb = 2\n# note\nc = 3\n")
    doc = Document(str(path))
    changes = []
    doc.breakpointsChanged.connect(lambda: changes.append(1))
    assert doc.toggle_breakpoint(3) and doc.breakpoint_lines() == [3] and changes
    assert doc.can_break_at(1) and not doc.can_break_at(2) and not doc.can_break_at(4)
    cursor = doc.text_document.find("a = 1")
    cursor.movePosition(cursor.MoveOperation.StartOfBlock)
    cursor.insertText("first = 0\n")  # a line above: it moves down
    assert doc.breakpoint_lines() == [4]
    cursor = doc.text_document.find("b = 2")
    cursor.movePosition(cursor.MoveOperation.StartOfBlock)
    cursor.insertText("\n")  # Enter at its start: it goes with its line
    assert doc.breakpoint_lines() == [5]
    doc.set_breakpoint(1, True)
    doc.replace_text(doc.text.replace("first", "zeroth"))  # (a rename keeps them)
    assert doc.breakpoint_lines() == [1, 5]
    assert not doc.toggle_breakpoint(5) and doc.breakpoint_lines() == [1]
    doc.clear_breakpoints()
    assert doc.breakpoint_lines() == []


def test_f9_and_the_gutter(window, tmp_path):
    doc = _project(window, tmp_path)
    code = window.view_code(doc.path)
    assert isinstance(code, CodeWindow)
    code.editor.goto_line(10)
    window.act_toggle_breakpoint.trigger()  # F9
    assert doc.breakpoint_lines() == [10]
    assert window.act_toggle_breakpoint.shortcut().toString() == "F9"
    editor = code.editor
    editor.show_line(1)
    QTest.qWait(20)
    top = editor.blockBoundingGeometry(editor.document().findBlockByNumber(11)) \
        .translated(editor.contentOffset()).top()
    QTest.mouseClick(editor.gutter, Qt.LeftButton, Qt.NoModifier,
                     QPoint(MARKERS // 2, int(top) + 3))  # line 12
    assert doc.breakpoint_lines() == [10, 12]
    editor.goto_line(2)  # a blank line: refused
    window.act_toggle_breakpoint.trigger()
    assert doc.breakpoint_lines() == [10, 12]
    assert "line of code" in window.statusBar().currentMessage()
    window.act_clear_breakpoints.trigger()
    assert doc.breakpoint_lines() == []


def test_the_editor_marks_breakpoints_and_the_execution_point(window, tmp_path):
    doc = _project(window, tmp_path)
    editor = window.view_code(doc.path).editor
    doc.toggle_breakpoint(5)
    doc.set_execution_line(10)
    colors = theme_manager().current().colors
    backgrounds = {s.cursor.blockNumber() + 1: s.format.background().color()
                   for s in editor.extraSelections()[1:]}
    assert backgrounds == {5: QColor(colors["breakpoint"]), 10: QColor(colors["execution_point"])}
    editor.show_line(1)
    QTest.qWait(20)
    image = editor.gutter.grab().toImage()
    row = editor.blockBoundingGeometry(editor.document().findBlockByNumber(4)) \
        .translated(editor.contentOffset())
    dot = image.pixelColor(int(MARKERS / 2) - 1, int(row.center().y()))
    assert dot.red() > 180 and dot.green() < 80  # the red dot
    doc.set_execution_line(None)
    assert len(editor.extraSelections()) == 2


# --- the Watches window -------------------------------------------------------------------------

def test_watch_window(qapp):
    watches = WatchWindow()
    changed = []
    watches.changed.connect(lambda: changed.append(1))
    watches.add("total")
    watches.add("  ")  # (nothing)
    watches.add("len(items)")
    assert watches.expressions() == ["total", "len(items)"] and len(changed) == 2
    first, second = watches.items()
    watches.show_result(first, "total", {"value": "42", "type": "int"})
    watches.show_result(second, "len(items)", {"error": "NameError: name 'items' is not defined"})
    assert (first.text(1), first.text(2)) == ("42", "int")
    assert second.text(1).startswith("<NameError")
    watches.show_result(first, "something else", {"value": "1", "type": "int"})  # (stale)
    assert first.text(1) == "42"
    first.setText(0, "total * 2")  # edited: asked again
    assert len(changed) == 3 and first.text(1) == ""
    watches.out_of_context()
    assert first.text(1) == "<not running>"
    watches.tree.setCurrentItem(second)
    second.setSelected(True)
    QTest.keyClick(watches.tree, Qt.Key_Delete)
    assert watches.expressions() == ["total * 2"]
    menu = watches._context_menu()
    assert [a.text() for a in menu.actions() if a.text()] == ["Edit Watch", "Delete Watch",
                                                               "Clear All"]
    menu.deleteLater()
    watches.clear()
    assert watches.expressions() == []
    watches.deleteLater()


def test_describe():
    assert describe({"file": None}) == "Paused between events"
    assert describe({"file": "/x/Form1.py", "line": 3, "reason": "breakpoint"}) == \
        "Breakpoint at Form1.py, line 3"
    assert describe({"file": "/x/Form1.py", "line": 3, "reason": "error"}) == \
        "Error at Form1.py, line 3"
    assert describe({"file": "/x/Form1.py", "line": 3, "reason": "step"}) == \
        "Paused at Form1.py, line 3"


def test_the_agent_knows_the_programs_own_code(tmp_path):
    import socket

    a, b = socket.socketpair()
    agent = debugagent.Agent(a, str(tmp_path))
    (tmp_path / "sub").mkdir()
    for name in ("Form1.py", "sub/Module2.py", "relative.py"):
        (tmp_path / name).write_text("")
    assert agent.is_user_file(str(tmp_path / "Form1.py"))
    assert agent.is_user_file(str(tmp_path / "sub" / "Module2.py"))
    assert not agent.is_user_file(str(tmp_path / "Missing.py"))
    assert not agent.is_user_file("relative.py")  # (embedded code: not a file of its own)
    assert not agent.is_user_file(debugagent.__file__)  # (VP6's own)
    assert not agent.is_user_file(os.__file__)
    assert not agent.is_user_file(str(tmp_path / ".venv" / "lib" / "site-packages" / "x.py"))
    assert not agent.is_user_file("<string>")
    a.close()
    b.close()


def test_no_ide_no_agent(monkeypatch):
    monkeypatch.delenv(debugagent.PORT_ENV, raising=False)
    assert debugagent.start_from_environment() is None and debugagent.active() is None


# --- real programs ---------------------------------------------------------------------------------

def test_a_breakpoint_watches_and_the_immediate_window(window, tmp_path):
    doc = _project(window, tmp_path)
    doc.toggle_breakpoint(12)  # total = add(total, i)
    stops = _run(window)
    stop = stops.next(1)
    assert stop["reason"] == "breakpoint" and stop["line"] == 12 and stop["function"] == "Main"
    assert doc.execution_line == 12 and window.windowTitle() == "Demo - VP6 [break]"
    assert window.act_run.text() == "&Continue" and not window.act_break.isEnabled()
    assert window.immediate.paused and window.immediate.input.isEnabled()
    assert window.statusBar().currentMessage() == "Breakpoint at Module1.py, line 12"
    window.add_watch("total")
    window.add_watch("i * 10")
    window.add_watch("missing")
    assert not window.debug_dock.isHidden()
    wait_for(lambda: all(item.text(1) for item in window.watches.items()))
    assert [(item.text(1), item.text(2)) for item in window.watches.items()][:2] == \
        [("0", "int"), ("0", "int")]
    assert "NameError" in window.watches.items()[2].text(1)
    # The Immediate window: expressions (? too) and statements, in the paused frame
    window.immediate.input.setText("? total + 100")
    window.immediate._submit()
    wait_for(lambda: "100\n" in window.immediate.output.toPlainText())
    window.immediate.input.setText("total = 5")  # a statement: it changes the program's
    window.immediate._submit()
    wait_for(lambda: window.watches.items()[0].text(1) == "5")
    window.immediate.input.setText("1 / 0")
    window.immediate._submit()
    wait_for(lambda: "ZeroDivisionError" in window.immediate.output.toPlainText())
    window.act_run.trigger()  # Continue: the breakpoint again, the next time round
    stop = stops.next(2)
    assert stop["line"] == 12 and _evaluate(window, "i")["value"] == "1"
    assert window.watches.items()[0].text(1) == "5"  # (5 + 0)
    window.act_clear_breakpoints.trigger()  # (the program is told)
    window.act_run.trigger()
    wait_for(lambda: not window.running, 10000)
    assert "total 8" in window.immediate.output.toPlainText()  # (5 + 1 + 2)
    assert doc.execution_line is None and window.watches.items()[0].text(1) == "<not running>"
    assert window.windowTitle() == "Demo - VP6 [design]"


def test_stepping(window, tmp_path):
    doc = _project(window, tmp_path)
    stops = _run(window, step=True)  # Step Into before it runs: the first line of Main
    stop = stops.next(1)
    assert (stop["function"], stop["line"]) == ("Main", 10)
    window.act_step_over.trigger()
    assert stops.next(2)["line"] == 11
    window.act_step_over.trigger()
    assert stops.next(3)["line"] == 12
    window.act_step_into.trigger()  # into add
    stop = stops.next(4)
    assert (stop["function"], stop["line"]) == ("add", 5)
    assert [f["function"] for f in stop["stack"]][:2] == ["add", "Main"]  # (then the launcher)
    assert doc.execution_line == 5
    window.act_step_out.trigger()  # back in Main, after the call
    stop = stops.next(5)
    assert stop["function"] == "Main" and _evaluate(window, "total")["value"] == "0"
    window.act_step_over.trigger()  # over add this time
    while stops.next(len(stops.seen) + 1)["line"] != 12:
        window.act_step_over.trigger()
    assert stops.seen[-1]["function"] == "Main"
    window.act_end.trigger()
    wait_for(lambda: not window.running)
    assert doc.execution_line is None and not window.immediate.paused


def test_break_in_a_loop_and_breakpoints_set_while_running(window, tmp_path):
    doc = _project(window, tmp_path, text='''from vp6 import *


def Main():
    count = 0
    while True:
        count += 1
''')
    stops = _run(window)
    wait_for(lambda: window.debug.is_connected)
    assert window.act_break.isEnabled()
    QTest.qWait(200)
    window.act_break.trigger()  # Run > Break
    stop = stops.next(1)
    assert stop["reason"] == "pause" and stop["line"] in (6, 7)
    count = int(_evaluate(window, "count")["value"])
    assert count > 0
    window.act_run.trigger()
    wait_for(lambda: not window.paused)
    doc.toggle_breakpoint(7)  # while it runs: it stops there
    stop = stops.next(2)
    assert stop["reason"] == "breakpoint" and stop["line"] == 7
    assert int(_evaluate(window, "count")["value"]) > count


def test_a_gui_program_errors_and_break_between_events(window, tmp_path):
    doc = _project(window, tmp_path, kind="exe", name="Form1.py", text='''from vp6 import *


class Form1(Form):
    # region VP6 Designer - generated by the form designer, do not edit
    def InitializeComponent(self):
        self.Caption = 'Form1'
        self.Width = 480
        self.Height = 360
    # endregion

    def Form_Load(self):
        self.count = 41
        self.count += 1
        ratio = self.count / 0
        self.Caption = "never"
''')
    stops = _run(window)
    stop = stops.next(1)  # an unhandled error: it stops at its line
    assert stop["reason"] == "error" and stop["line"] == 15
    assert stop["error"] == "ZeroDivisionError: division by zero"
    assert doc.execution_line == 15 and doc.execution_error
    assert "Error at Form1.py, line 15: ZeroDivisionError" in \
        window.immediate.output.toPlainText()
    assert _evaluate(window, "self.count")["value"] == "42"  # (its frame as it was)
    window.act_run.trigger()
    wait_for(lambda: not window.paused)
    QTest.qWait(200)
    window.act_break.trigger()  # waiting for events: paused between them
    stop = stops.next(2)
    assert stop["file"] is None and stop["reason"] == "pause" and doc.execution_line is None
    assert window.statusBar().currentMessage() == "Paused between events"
    assert _evaluate(window, "Form1.Caption")["value"] == "'Form1'"  # (the forms by name)
    _evaluate(window, "Form1.Caption = 'Changed'")
    assert _evaluate(window, "Form1.Caption")["value"] == "'Changed'"
    assert _evaluate(window, "vpYes")["value"] == "6"  # (and VP6's names)
    window.act_step_into.trigger()  # (the next line of its own code: none comes)
    wait_for(lambda: not window.paused)
    window.act_end.trigger()
    wait_for(lambda: not window.running)


def test_the_debugger_session_alone(qapp):
    session = DebugSession({}, parent=None)
    assert session.port > 0 and not session.is_paused and not session.is_connected
    results = []
    session.evaluate("1", results.append)  # (not paused)
    assert results == [{"error": "The program isn't paused"}]
    session.close()
    session.deleteLater()


def test_the_debug_menu(window):
    menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Debug")
    assert [a.text() for a in menu.actions() if a.text()] == [
        "Step &Into", "Step &Over", "Step Ou&t", "Apply Code C&hanges", "&Add Watch…",
        "Toggle &Breakpoint",
        "&Clear All Breakpoints", "&Debug Window"]
    run = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Run")
    assert window.act_break in run.actions()
    names = [a.text() for a in window.menuBar().actions()]
    assert names.index("&Debug") == names.index("&Run") - 1  # (VB6's order)
    assert window.act_step_into.shortcut().toString() == "F8"
    assert window.act_step_over.shortcut().toString() == "Shift+F8"
    assert window.debug_dock.isHidden()  # until there is a watch


# --- the Debug panel ----------------------------------------------------------------------------

def test_the_debug_panel(qapp):
    panel = DebugPanel()
    assert [section.title.text() for section in panel.sections] == [
        "Watches", "Call Stack", "Breakpoints"]
    assert panel.splitter.orientation() == Qt.Horizontal
    stack = panel.call_stack
    chosen = []
    stack.frameChosen.connect(lambda *args: chosen.append(args))
    stack.show_stack([{"file": "/p/Module1.py", "line": 5, "function": "add"},
                      {"file": "/p/Module1.py", "line": 12, "function": "Main"},
                      {"file": "/p/Demo.vp6p", "line": 50, "function": "<module>"}])
    assert [stack.topLevelItem(i).text(0) for i in range(stack.topLevelItemCount())] == [
        "Module1.add", "Module1.Main"]  # (not the project file that started it)
    assert stack.topLevelItem(0).font(0).bold() and not stack.topLevelItem(1).font(0).bold()
    stack.choose(1)
    assert chosen == [(1, "/p/Module1.py", 12)] and stack.topLevelItem(1).font(0).bold()
    panel.not_paused()
    assert stack.topLevelItemCount() == 0
    panel.deleteLater()


def test_the_breakpoint_list(qapp):
    listing = BreakpointList()
    events = []
    for name in ("goTo", "enableRequested", "removeRequested", "removeAllRequested",
                 "enableAllRequested"):
        getattr(listing, name).connect(lambda *args, n=name: events.append((n, *args)))
    listing.show_breakpoints([("/p/Form1.py", 12, True, "        x = 1"),
                              ("/p/Module1.py", 3, False, "y = 2")])
    assert [listing.topLevelItem(i).text(0) for i in range(2)] == ["Form1.py:12", "Module1.py:3"]
    assert listing.topLevelItem(0).text(1) == "x = 1"
    assert listing.entries() == [("/p/Form1.py", 12, True), ("/p/Module1.py", 3, False)]
    assert events == []  # (showing them asks for nothing)
    listing.topLevelItem(1).setCheckState(0, Qt.Checked)
    assert events[-1] == ("enableRequested", "/p/Module1.py", 3, True)
    listing.itemActivated.emit(listing.topLevelItem(0), 0)
    assert events[-1] == ("goTo", "/p/Form1.py", 12)
    listing.setCurrentItem(listing.topLevelItem(0))
    listing.topLevelItem(0).setSelected(True)
    QTest.keyClick(listing, Qt.Key_Delete)
    assert events[-1] == ("removeRequested", "/p/Form1.py", 12)
    menu = listing._context_menu()
    actions = {a.text(): a for a in menu.actions() if a.text()}
    assert list(actions) == ["Go to Breakpoint", "Delete Breakpoint", "Enable All",
                             "Disable All", "Delete All"]
    actions["Disable All"].trigger()
    actions["Delete All"].trigger()
    assert events[-2:] == [("enableAllRequested", False), ("removeAllRequested",)]
    menu.deleteLater()
    listing.deleteLater()


def test_the_debug_window_in_the_ide(window, tmp_path):
    doc = _project(window, tmp_path)
    window.act_view_debug.trigger()  # View > Debug Window
    assert not window.debug_dock.isHidden()
    assert window.debug_dock in window.tabifiedDockWidgets(window.immediate_dock)
    listing = window.debug_panel.breakpoints
    doc.toggle_breakpoint(12)
    doc.toggle_breakpoint(5)
    wait_for(lambda: listing.topLevelItemCount() == 2)
    assert [e[1:] for e in listing.entries()] == [(5, True), (12, True)]
    # The list follows the edits
    cursor = doc.text_document.find("from vp6")
    cursor.movePosition(cursor.MoveOperation.StartOfBlock)
    cursor.insertText("# top\n")
    wait_for(lambda: [e[1] for e in listing.entries()] == [6, 13])
    listing.topLevelItem(0).setCheckState(0, Qt.Unchecked)  # disabled from the list
    assert doc.breakpoints() == [(6, False), (13, True)]
    assert window._all_breakpoints() == {doc.path: [13]}  # (the program: enabled ones only)
    listing.itemActivated.emit(listing.topLevelItem(1), 0)  # go to it
    assert window.view_code(doc.path).editor.current_line() == 13
    window.enable_all_breakpoints(True)
    assert window._all_breakpoints() == {doc.path: [6, 13]}
    listing.removeRequested.emit(doc.path, 6)
    assert doc.breakpoint_lines() == [13]
    # Paused: the call stack, and a frame chosen to evaluate in
    stops = _run(window)
    stops.next(1)
    window.act_step_into.trigger()  # into add
    stop = stops.next(2)
    stack = window.debug_panel.call_stack
    assert [stack.topLevelItem(i).text(0) for i in range(stack.topLevelItemCount())] == [
        "Module1.add", "Module1.Main"]
    window.add_watch("total")
    wait_for(lambda: window.watches.items()[0].text(1))
    assert "NameError" in window.watches.items()[0].text(1)  # (in add: no total)
    stack.choose(1)  # Main's frame
    assert window.debug.frame == 1
    wait_for(lambda: window.watches.items()[0].text(1) == "0")
    assert _evaluate(window, "i")["value"] == "0"
    assert window.view_code(doc.path).editor.current_line() == 13  # (its line shown)
    assert doc.execution_line == stop["line"]  # (the execution point stays)
    window.act_end.trigger()
    wait_for(lambda: not window.running)
    assert stack.topLevelItemCount() == 0
    window.close_project()
    assert listing.topLevelItemCount() == 0


# --- Edit and Continue --------------------------------------------------------------------------

def _replace(doc, old: str, new: str) -> None:
    cursor = doc.text_document.find(old)
    assert not cursor.isNull()
    cursor.insertText(new)


def test_edit_and_continue(window, tmp_path):
    doc = _project(window, tmp_path)
    doc.toggle_breakpoint(12)
    stops = _run(window)
    stops.next(1)
    assert window.pending_changes() == {} and window.act_apply_changes.isEnabled()
    _replace(doc, "a + b", "a + b * 10")  # add, not running: from its next call
    assert list(window.pending_changes()) == [doc.path]
    window.act_clear_breakpoints.trigger()
    window.act_run.trigger()  # Continue: applied first
    wait_for(lambda: not window.running, 10000)
    output = window.immediate.output.toPlainText()
    assert "✎ Code changes applied: add" in output
    assert "total 30" in output  # (0 + 10 + 20: the new code)


def test_a_running_procedure_and_apply_without_going_on(window, tmp_path):
    doc = _project(window, tmp_path)
    doc.toggle_breakpoint(12)
    stops = _run(window)
    stops.next(1)
    _replace(doc, 'print("total", total)', 'print("sum", total)')  # Main runs: old code
    _replace(doc, "from vp6 import *", "from vp6 import *\n# a new line")
    assert doc.execution_line == 13 and doc.breakpoint_lines() == [13]  # (they follow)
    window.act_apply_changes.trigger()  # Debug > Apply Code Changes: still paused
    wait_for(lambda: "is running" in window.immediate.output.toPlainText())
    assert window.paused and window.pending_changes() == {}
    assert "✎ Main is running: it goes on with its old code" in \
        window.immediate.output.toPlainText()
    assert window.act_apply_changes.shortcut().toString() == "Alt+F10"
    window.act_clear_breakpoints.trigger()
    window.act_run.trigger()
    wait_for(lambda: not window.running, 10000)
    assert "total 3" in window.immediate.output.toPlainText()  # (Main's old code)


def test_an_error_in_the_changes_keeps_it_paused(window, tmp_path):
    doc = _project(window, tmp_path)
    doc.toggle_breakpoint(12)
    stops = _run(window)
    stops.next(1)
    _replace(doc, "result = a + b", "result = (a + b")
    window.act_run.trigger()  # Continue: refused
    wait_for(lambda: "Not applied" in window.immediate.output.toPlainText())
    assert window.paused and "SyntaxError" in window.immediate.output.toPlainText()
    assert "fix it" in window.statusBar().currentMessage()
    assert list(window.pending_changes()) == [doc.path]
    _replace(doc, "result = (a + b", "result = a - b")  # fixed
    window.act_clear_breakpoints.trigger()
    window.act_step_over.trigger()  # a step goes on too, once applied
    wait_for(lambda: len(stops.seen) == 2)
    window.act_run.trigger()
    wait_for(lambda: not window.running, 10000)
    assert "total -3" in window.immediate.output.toPlainText()


def test_edit_a_form_while_it_runs(window, tmp_path):
    doc = _project(window, tmp_path, kind="exe", name="Form1.py", text='''from vp6 import *


class Form1(Form):
    # region VP6 Designer - generated by the form designer, do not edit
    def InitializeComponent(self):
        self.Caption = 'Form1'
        self.Width = 480
        self.Height = 360
    # endregion

    def Form_Load(self):
        self.clicks = 1

    def describe(self):
        return "old"
''')
    doc.toggle_breakpoint(13)
    stops = _run(window)
    stops.next(1)
    assert _evaluate(window, "self.describe()")["value"] == "'old'"
    _replace(doc, 'return "old"', 'return f"new {self.Caption}"')
    window.act_apply_changes.trigger()
    wait_for(lambda: not window.pending_changes())
    assert window.paused  # (applied, not gone on)
    assert _evaluate(window, "self.describe()")["value"] == "'new Form1'"  # (the form it has)
