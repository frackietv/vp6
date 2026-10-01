import os

import pytest
from PySide6.QtCore import QItemSelectionModel, QSize, Qt
from PySide6.QtTest import QTest

import vp6
from conftest import wait_for

from vp6.ide.codeeditor import CodeWindow, complete
from vp6.ide.designer import FormDesigner
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.project import Project


@pytest.fixture
def window(qapp):
    w = MainWindow()
    w.show()
    yield w
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


def test_new_exe_project_opens_designer(window, tmp_path):
    path = create_project(str(tmp_path), "Demo", "exe")
    assert window.open_project(path)
    assert isinstance(window._active_widget(), FormDesigner)
    assert window.windowTitle() == "Demo - VP6 [design]"


def test_add_form_and_module(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    window.add_form()
    window.add_module()
    project = Project.load(os.path.join(tmp_path, "Demo", "Demo.vp6p"))
    assert project.forms == ["Form1.py", "Form2.py"]
    assert project.modules == ["Module1.py", "Module2.py"]
    assert isinstance(window._active_widget(), CodeWindow)


def test_double_click_creates_handler(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    designer = window._active_widget()
    designer.create_control("CommandButton", None, None, None)
    designer.viewCodeRequested.emit("Command1", "Click")
    code = window._active_widget()
    assert isinstance(code, CodeWindow)
    assert "    def Command1_Click(self):\n        pass" in code.doc.text
    assert code.object_combo.currentText() == "Command1"
    assert code.proc_combo.currentText() == "Click"
    # Choosing MouseDown creates a stub with VB's parameters
    code.goto_event("Command1", "MouseDown")
    assert "def Command1_MouseDown(self, Button, Shift, X, Y):" in code.doc.text


def test_completion(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    designer = window._active_widget()
    designer.create_control("TextBox", None, None, None)
    doc = designer.document
    assert "Text1" in complete("self.", doc)
    members = complete("self.Text1.", doc)
    assert {"Text", "SelStart", "SetFocus", "Locked"} <= set(members)
    assert "MsgBox" in complete("", doc)


def test_run_console_project_with_input(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Hello", "console"))
    window.run_project()
    assert window.windowTitle() == "Hello - VP6 [run]"
    wait_for(lambda: "What is your name?" in window.immediate.output.toPlainText(), 15000)
    window.immediate.input.setText("Ada")
    window.immediate.input.returnPressed.emit()
    wait_for(lambda: window.process is None, 15000)
    output = window.immediate.output.toPlainText()
    assert "Hello, Ada!" in output
    assert "exited with code 0" in output
    assert window.windowTitle() == "Hello - VP6 [design]"


def test_runtime_error_is_reported_with_location(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Crash", "console"))
    doc = next(d for d in window.documents.values() if d.name == "Module1")
    doc.text_document.setPlainText("def Main():\n    1 / 0\n")
    window.run_project()
    wait_for(lambda: window.process is None, 15000)
    output = window.immediate.output.toPlainText()
    assert "ZeroDivisionError" in output
    assert f'File "{doc.path}", line 2' in output


def test_hidden_toolbar_can_be_shown_from_view_menu(window):
    toolbar = window.toolbar
    toggle = toolbar.toggleViewAction()
    texts = [a.text() for a in window.view_menu.actions()]
    assert "Tool&bars" in texts and "&Reset Window Layout" in texts
    toolbar.hide()
    assert not toggle.isChecked()
    toggle.trigger()  # View > Toolbars > Standard
    assert toolbar.isVisible()


def test_reset_window_layout(window):
    window.settings.setValue("state", window.saveState())
    window.toolbar.hide()
    window.properties_dock.hide()
    window.immediate_dock.setFloating(True)
    window.reset_layout()
    assert window.toolbar.isVisible() and window.properties_dock.isVisible()
    assert not window.immediate_dock.isFloating()
    assert window.dockWidgetArea(window.properties_dock) == Qt.RightDockWidgetArea
    assert window.settings.value("state") is None


def test_toolbar_theme_toggle(window):
    from vp6.ide.theme import DARK, LIGHT, theme_manager

    manager = theme_manager()
    toolbar = window.toolbar
    assert toolbar.actions()[-1] is window.act_theme_toggle  # right end of the toolbar
    manager.select(LIGHT)
    assert "dark" in window.act_theme_toggle.toolTip()
    window.act_theme_toggle.trigger()
    assert manager.state.selection == DARK and manager.app_is_dark()
    assert "light" in window.act_theme_toggle.toolTip()
    window.act_theme_toggle.trigger()
    assert manager.state.selection == LIGHT and not manager.app_is_dark()


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter])
def test_ctrl_enter_runs_from_the_code_editor(window, tmp_path, key):
    window.open_project(create_project(str(tmp_path), "Hello", "console"))
    code = window._active_widget()
    assert isinstance(code, CodeWindow)
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)  # shortcuts only fire in the active window
    code.editor.setFocus()
    before = code.doc.text
    # Qt maps ControlModifier to the Command key on macOS
    QTest.keyClick(code.editor, key, Qt.ControlModifier)
    assert window.running
    assert code.doc.text == before  # the editor didn't take it as a new line
    window.stop_project()
    wait_for(lambda: window.process is None, 15000)


def test_immediate_context_menu_clear(qapp):
    from vp6.ide.panels import ImmediateWindow

    immediate = ImmediateWindow()

    def clear_action():
        menu = immediate._context_menu()
        return next(a for a in menu.actions() if a.text() == "Clear"), menu

    action, _menu = clear_action()
    assert not action.isEnabled()  # nothing to clear yet
    immediate.append("hello\n")
    immediate.append("boom\n", "err")
    action, _menu = clear_action()
    assert action.isEnabled()
    assert any("Copy" in a.text() for a in _menu.actions())  # standard items kept
    action.trigger()
    assert immediate.output.toPlainText() == ""


def test_run_passes_ide_scheme_to_program(window, tmp_path):
    from vp6.ide.theme import DARK, theme_manager

    theme_manager().select(DARK)
    window.open_project(create_project(str(tmp_path), "Env", "console"))
    doc = next(d for d in window.documents.values() if d.name == "Module1")
    doc.text_document.setPlainText(
        "import os\n\ndef Main():\n    print('scheme=' + os.environ['VP6_IDE_SCHEME'])\n")
    window.run_project()
    wait_for(lambda: window.process is None, 15000)
    assert "scheme=dark" in window.immediate.output.toPlainText()


def test_project_explorer_follows_active_window(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    form_path = os.path.join(tmp_path, "Demo", "Form1.py")
    assert window.explorer._current() == (form_path, "form")  # startup form selected
    window.add_module()  # opens Module2's code window (Module1 comes with the project)
    module_path = os.path.join(tmp_path, "Demo", "Module2.py")
    assert window.explorer._current() == (module_path, "module")
    window.view_object(form_path)
    assert window.explorer._current() == (form_path, "form")
    window._refresh_explorer()  # rebuilt tree (e.g. theme change) keeps the selection
    assert window.explorer._current() == (form_path, "form")


def _property_rows(window):
    table = window.properties.table
    return {table.item(r, 0).text(): table.cellWidget(r, 1) for r in range(table.rowCount())}


def test_project_properties_in_properties_window(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    designer = window._last_designer
    window.explorer.select_project()
    assert window.properties.designer is window.project_target
    assert window.properties.object_combo.currentText() == "Demo  Project"
    rows = _property_rows(window)
    assert list(rows) == ["(Name)", "Arguments", "ArgumentsHelp", "ColorScheme", "CompanyName",
                          "Description", "Icon", "ProductName", "StartupObject", "Type", "Version"]
    assert rows["Type"].currentData() == "exe"
    assert [rows["StartupObject"].itemText(i) for i in range(rows["StartupObject"].count())] \
        == ["Form1", "Sub Main"]

    # Editing through the grid's editors saves the project and updates the IDE
    scheme = rows["ColorScheme"]
    scheme.activated.emit(scheme.findData("dark"))
    assert Project.load(window.project.path).color_scheme == "dark"
    assert designer.project_scheme == 3  # vpSchemeDark reaches open designers
    assert window.explorer.project_selected()  # still showing the project
    assert _property_rows(window)["ColorScheme"].currentData() == "dark"

    target = window.project_target
    assert target.set_property("Name", "not valid") is not None
    assert target.set_property("Name", "Renamed") is None
    assert window.windowTitle().startswith("Renamed - VP6")
    assert Project.load(window.project.path).name == "Renamed"

    # App's version and descriptions, and the command line F5 runs it with
    assert target.set_property("Version", "2.x") is not None
    assert target.set_property("Version", "2.5") is None
    assert target.set_property("ProductName", " Demo Pro ") is None
    assert target.set_property("Arguments", '--open "a file.txt"') is None
    saved = Project.load(window.project.path)
    assert (saved.version, saved.product_name, saved.arguments) == \
        ("2.5.0", "Demo Pro", '--open "a file.txt"')
    assert saved.version_numbers() == (2, 5, 0)
    assert window.run_arguments() == ["--open", "a file.txt"]


def test_selecting_a_form_or_designer_shows_its_properties_again(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    designer = window._last_designer
    window.explorer.select_project()
    assert window.properties.designer is window.project_target
    window.explorer.select_path(designer.document.path)  # form item in the explorer
    assert window.properties.designer is designer
    window.explorer.select_project()
    designer.create_control("CommandButton", None, None, None)  # working in the designer
    assert window.properties.designer is designer
    assert not window.explorer.project_selected()


@pytest.mark.parametrize("template", ["exe", "console"])
def test_new_projects_have_form1_and_module1_with_main(tmp_path, template):
    path = create_project(str(tmp_path), "Demo", template)
    project = Project.load(path)
    assert project.forms == ["Form1.py"] and project.modules == ["Module1.py"]
    assert project.startup == "Sub Main"
    assert project.type == template
    module = (tmp_path / "Demo" / "Module1.py").read_text()
    assert "def Main():" in module and 'if __name__ == "__main__":\n    Main()' in module
    if template == "exe":
        assert "from Form1 import Form1" in module and "run(Form1)" in module
    else:
        assert "input(" in module and "Form1" not in module  # console Main unchanged
    compile(module, "Module1.py", "exec")


def test_exe_project_main_shows_form1(tmp_path):
    """Run the new windowed project for real: Main() must show Form1."""
    import subprocess
    import sys

    path = create_project(str(tmp_path), "Demo", "exe")
    form1 = tmp_path / "Demo" / "Form1.py"
    form1.write_text(form1.read_text().replace(
        "    def Form_Load(self):\n        pass",
        "    def Form_Load(self):\n        print('Form1 loaded', flush=True)\n        End()"))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = subprocess.run([sys.executable, path], capture_output=True, text=True,
                            timeout=60, env=env)
    assert "Form1 loaded" in result.stdout


def test_new_exe_project_opens_form_designer_even_with_sub_main(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    designer = window._active_widget()
    assert isinstance(designer, FormDesigner) and designer.document.name == "Form1"


@pytest.mark.parametrize("tabbed", [False, True])
def test_closed_windows_reopen_with_their_contents(window, tmp_path, tabbed):
    """Regression: closing a code window or designer and opening it again showed
    an empty frame (Qt hides the widget inside a closed subwindow)."""
    window.act_tabbed.setChecked(tabbed)
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    form1 = os.path.join(tmp_path, "Sink", "Form1.py")
    for open_window, windows in ((window.view_code, window.code_windows),
                                 (window.view_object, window.designer_windows)):
        open_window(form1)
        for _ in range(2):  # close and reopen twice
            windows[form1].close()
            QTest.qWait(10)
            content = open_window(form1)
            QTest.qWait(10)
            assert windows[form1].isVisible() and content.isVisible()
    code = window.code_windows[form1].widget()
    assert code.editor.isVisible() and "class Form1(Form):" in code.editor.toPlainText()
    window.act_tabbed.setChecked(False)


# --- Properties panel follows the Project panel / active window --------------------------------

def _props(window):
    """(object combo text, property row labels) of the Properties panel."""
    table = window.properties.table
    rows = [table.item(r, 0).text() for r in range(table.rowCount())]
    return window.properties.object_combo.currentText(), rows


def _select_item(window, text):
    for item in window.explorer.items():
        if item.text(0).startswith(text):
            window.explorer.tree.setCurrentItem(item)
            return
    raise AssertionError(f"no explorer item {text!r}")


def test_properties_follow_project_panel_selection(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    _select_item(window, "Module1")
    assert _props(window) == ("Module1  Module", ["(Name)"])  # modules have a Name
    _select_item(window, "frmDialog")  # a form whose designer isn't open: all its properties
    assert _props(window)[0] == "frmDialog  Form" and "Caption" in _props(window)[1]
    assert "frmDialog.py" not in " ".join(window.designer_windows)  # still not open
    _select_item(window, "Form1")  # designer open: all its properties
    assert _props(window)[0] == "Form1  Form" and "Caption" in _props(window)[1]
    _select_item(window, "Forms")  # a group: its (Name)
    assert _props(window) == ("Forms  Group", ["(Name)"])
    window.explorer.tree.setCurrentItem(None)  # nothing selected
    assert _props(window) == ("", [])
    window.explorer.select_project()
    assert _props(window)[0] == "Sink  Project"


def test_properties_follow_active_window_when_project_panel_closed(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    folder = os.path.join(tmp_path, "Sink")
    window.explorer_dock.hide()
    window.view_code(os.path.join(folder, "Module1.py"))
    assert _props(window) == ("Module1  Module", ["(Name)"])
    window.view_code(os.path.join(folder, "frmDialog.py"))  # form code, no designer
    assert _props(window)[0] == "frmDialog  Form" and "Caption" in _props(window)[1]
    window.view_code(os.path.join(folder, "Form1.py"))  # form code, designer open
    assert _props(window)[0] == "Form1  Form" and "Caption" in _props(window)[1]
    window.explorer_dock.show()  # back to following the Project panel
    _select_item(window, "Module1")
    assert _props(window) == ("Module1  Module", ["(Name)"])


def test_rename_module_from_properties(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = tmp_path / "Demo"
    form1 = window.documents[str(folder / "Form1.py")]
    form1.replace_text(form1.text.replace("from vp6 import *\n",
                                          "from vp6 import *\nimport Module1\n", 1))
    _select_item(window, "Module1")
    target = window.properties.designer
    assert target.set_property("Name", "not valid") is not None
    assert target.set_property("Name", "Form1") is not None  # already used
    assert target.set_property("Name", "Startup") is None
    assert (folder / "Startup.py").exists() and not (folder / "Module1.py").exists()
    assert Project.load(str(folder / "Demo.vp6p")).modules == ["Startup.py"]
    assert "import Startup\n" in form1.text  # references in other files follow
    assert _props(window) == ("Startup  Module", ["(Name)"])
    window.view_code(str(folder / "Startup.py"))
    assert "Startup" in window.code_windows[str(folder / "Startup.py")].windowTitle()


def test_renaming_a_form_updates_references_and_still_runs(window, tmp_path):
    """Regression: renaming Form1 left Module1's `from Form1 import Form1` /
    `run(Form1)` behind, so a new Standard EXE failed on the next run."""
    import subprocess
    import sys

    path = create_project(str(tmp_path), "Demo", "exe")
    window.open_project(path)
    designer = window._last_designer
    designer.select([])
    assert designer.set_property("Name", "frmMain") is None
    module = next(d for d in window.documents.values() if d.name == "Module1")
    assert "from Form1 import frmMain" in module.text and "run(frmMain)" in module.text
    assert window.project.startup == "Sub Main"
    form = designer.document
    form.replace_text(form.text.replace(
        "    def Form_Load(self):\n        pass",
        "    def Form_Load(self):\n        print('frmMain loaded', flush=True)\n        End()"))
    assert window.save_all()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = subprocess.run([sys.executable, path], capture_output=True, text=True,
                            timeout=60, env=env)
    assert "frmMain loaded" in result.stdout, result.stderr


def test_rename_unopened_form_from_properties(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    _select_item(window, "frmDialog")
    assert window.properties.designer.set_property("Name", "Form1") is not None  # taken
    assert window.properties.designer.set_property("Name", "dlgAdd") is None
    page = next(d for d in window.documents.values() if d.name == "pgDialogs")  # its user
    assert "from frmDialog import dlgAdd" in page.text and "dlgAdd.Show(vpModal" in page.text
    assert _props(window)[0] == "dlgAdd  Form"


def test_ide_exits_without_errors(tmp_path):
    """Regression: signals fired while the IDE shut down reached an already
    destroyed MainWindow and printed a traceback on exit."""
    import subprocess
    import sys

    script = f"""
import sys
from PySide6.QtCore import QSettings
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, {str(tmp_path / 'settings')!r})
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from vp6.ide.mainwindow import MainWindow, create_project
w = MainWindow()
w.show()
w.open_project(create_project({str(tmp_path)!r}, "Sink", "kitchensink"))
w.explorer.select_project()
app.processEvents()
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            timeout=60, env=env)
    assert result.returncode == 0 and "Traceback" not in result.stderr, result.stderr


def _start_ide(tmp_path, *args):
    """Start the IDE in its own process, with its settings in tmp_path."""
    import subprocess
    import sys

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", VP6_SETTINGS_DIR=str(tmp_path),
               PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return subprocess.Popen([sys.executable, "-m", "vp6.ide", *args], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _interrupt_after_startup(process, seconds=4.0):
    import signal
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert process.poll() is None, process.communicate()[1]  # still starting / running
        time.sleep(0.1)
    process.send_signal(signal.SIGINT)  # what Ctrl+C in the terminal sends
    return process.communicate(timeout=30)


@pytest.mark.skipif(os.name == "nt", reason="SIGINT from another process is POSIX")
def test_ctrl_c_quits_like_file_exit(tmp_path):
    project = create_project(str(tmp_path), "Demo", "exe")
    process = _start_ide(tmp_path, project)
    _out, err = _interrupt_after_startup(process)
    assert process.returncode == 0, err
    assert "Traceback" not in err and "KeyboardInterrupt" not in err
    # File > Exit saves the window layout on the way out
    assert "geometry" in (tmp_path / "VP6 IDE.ini").read_text()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT from another process is POSIX")
def test_ctrl_c_closes_the_start_dialog_and_quits(tmp_path):
    process = _start_ide(tmp_path)  # no project: the New Project dialog is open
    _out, err = _interrupt_after_startup(process)
    assert process.returncode == 0, err
    assert "Traceback" not in err


def test_settings_dir_override(tmp_path, monkeypatch):
    from vp6.ide.theme import ide_settings

    monkeypatch.setenv("VP6_SETTINGS_DIR", str(tmp_path / "alt"))
    assert ide_settings().fileName() == str(tmp_path / "alt" / "VP6 IDE.ini")


def test_output_window_hidden_by_default(window):
    assert window.output_dock.isHidden()
    window.act_view_output.trigger()  # View > Output Window
    assert not window.output_dock.isHidden()
    # it opens as a tab next to the Immediate window (Qt lists shown tabs only)
    assert window.output_dock in window.tabifiedDockWidgets(window.immediate_dock)
    from PySide6.QtWidgets import QTabWidget
    for area in (Qt.BottomDockWidgetArea, Qt.RightDockWidgetArea):  # their tabs above them
        assert window.tabPosition(area) == QTabWidget.North
    window.reset_layout()  # back to the default: hidden again
    assert window.output_dock.isHidden() and not window.immediate_dock.isHidden()


def _bottom_group(window):
    first = window.immediate_dock
    return {first, *window.tabifiedDockWidgets(first)}


def _shown_bodies(window, docks):
    """Docks whose body is on screen. Qt keeps non-current tabs "visible" but
    parks them outside the window, so check the geometry."""
    return [d for d in docks if d.isVisible() and d.geometry().intersects(window.rect())]


def _bottom_tab_titles(window):
    from PySide6.QtWidgets import QTabBar

    return [[bar.tabText(i) for i in range(bar.count())]
            for bar in window.findChildren(QTabBar) if bar.isVisible()]


def test_bottom_edge_panels_are_tabs(window):
    from PySide6.QtCore import Qt

    assert QTest.qWaitForWindowExposed(window)
    window.act_view_output.trigger()
    QTest.qWait(20)
    assert _bottom_group(window) == {window.immediate_dock, window.output_dock}
    # Put Output beside Immediate (like dragging it next to it): it becomes a tab again
    window.splitDockWidget(window.immediate_dock, window.output_dock, Qt.Horizontal)
    QTest.qWait(20)
    assert window.output_dock in _bottom_group(window)
    # Move another panel to the bottom edge: it joins the tabs too
    window.addDockWidget(Qt.BottomDockWidgetArea, window.properties_dock)
    QTest.qWait(20)
    group = _bottom_group(window)
    assert group == {window.immediate_dock, window.output_dock, window.properties_dock}
    assert len(_shown_bodies(window, group)) == 1  # one body shown...
    assert ["Immediate", "Output", "Properties"] in _bottom_tab_titles(window)  # ...all titles
    # The right edge keeps its panels stacked, not tabbed
    assert window.tabifiedDockWidgets(window.explorer_dock) == []


def test_bottom_tabs_after_restoring_a_side_by_side_layout(qapp, tmp_path):
    from PySide6.QtCore import Qt

    first = MainWindow()
    first.show()
    first.output_dock.show()
    first.splitDockWidget(first.immediate_dock, first.output_dock, Qt.Horizontal)
    first.settings.setValue("state", first.saveState())  # as a previous session left it
    first.close()
    second = MainWindow()
    second.show()
    QTest.qWait(20)
    assert second.output_dock in second.tabifiedDockWidgets(second.immediate_dock)
    second.close()


# --- sizing and placing windows in the MDI area --------------------------------------------------

def _inside(window, sub) -> bool:
    return window.mdi.viewport().rect().contains(sub.geometry())


def test_a_form_window_is_just_large_enough_for_the_form(window, tmp_path):
    window.resize(1600, 1000)
    QTest.qWait(20)
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))  # Form1: 480 x 360
    sub = window.mdi.currentSubWindow()
    designer = sub.widget()
    frame = sub.contentsMargins()
    wanted = designer.preferred_size()
    assert sub.size() == QSize(wanted.width() + frame.left() + frame.right(),
                               wanted.height() + frame.top() + frame.bottom())
    assert sub.size().width() < window.mdi.viewport().width()  # not maximized
    assert designer.form_canvas_rect().width() == 480  # the whole form shows
    assert _inside(window, sub) and not sub.isMaximized()


def test_a_form_too_big_for_the_area_fills_it(window, tmp_path):
    window.resize(900, 600)  # the Kitchen Sink's Form1 (920 wide) can't fit
    QTest.qWait(20)
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    sub = window.mdi.currentSubWindow()
    assert sub.geometry() == window.mdi.viewport().rect()  # as large as maximized
    assert not sub.isMaximized()  # so the next windows aren't maximized too


def test_other_windows_open_inside_the_area(window, tmp_path):
    window.resize(1000, 700)
    QTest.qWait(20)
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    folder = tmp_path / "Sink"
    for path in ("Module1.py", "Form1.py", "frmDialog.py"):
        window.view_code(str(folder / path))
        sub = window.code_windows[str(folder / path)]
        assert _inside(window, sub), path
    dialog = window.view_object(str(folder / "frmDialog.py"))
    assert _inside(window, window.designer_windows[str(folder / "frmDialog.py")])
    assert dialog.form_canvas_rect().width() == dialog.form.Width
    # A window moved partly out and closed comes back inside
    sub = window.code_windows[str(folder / "Module1.py")]
    sub.move(900, 600)
    sub.close()
    window.view_code(str(folder / "Module1.py"))
    assert _inside(window, sub)


def test_windows_opened_before_the_ide_shows_are_fitted_when_it_does(qapp, tmp_path):
    w = MainWindow()
    w.resize(1600, 1000)
    w.open_project(create_project(str(tmp_path), "Demo", "exe"))
    sub = w.mdi.subWindowList()[0]
    w.show()
    QTest.qWait(50)
    wanted = sub.widget().preferred_size()
    frame = sub.contentsMargins()
    assert sub.width() == wanted.width() + frame.left() + frame.right()
    assert _inside(w, sub)
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


# --- the Project panel's order --------------------------------------------------------------------

def _listed(window, *group):
    """The names of what is in a group of the Project panel, e.g. ("Forms",)."""
    item = window.explorer.tree.topLevelItem(0)
    for name in group:
        item = next(item.child(i) for i in range(item.childCount())
                    if item.child(i).data(0, Qt.UserRole + 2) == name)
    return [item.child(i).data(0, Qt.UserRole + 2) for i in range(item.childCount())]


def test_project_panel_sorts_by_name(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    window.add_module()  # Module2: with a form selected, into the modules' group
    explorer = window.explorer
    forms = ["Form1", "frmDialog", "frmMDI", "frmNote", "frmSuggest"]
    assert _listed(window, "Forms") == ["Pages"] + forms  # groups first
    pages = _listed(window, "Forms", "Pages")
    assert pages == sorted(pages, key=str.lower)  # A to Z by default, not the project's order
    assert pages[0] == "pgArrays" and pages[-1] == "pgZOrder"
    assert explorer.sort_button.text() == "Groups, Name ▲"
    explorer.select_path(os.path.join(tmp_path, "Sink", "pgLists.py"))
    # The Name button cycles: A to Z with the groups among the files...
    explorer.sort_button.click()
    assert explorer.sort_button.text() == "Name ▲"
    assert _listed(window, "Forms") == forms + ["Pages"]
    assert _listed(window, "Forms", "Pages") == pages
    # ...Z to A, groups first...
    explorer.sort_button.click()
    assert explorer.sort_button.text() == "Groups, Name ▼"
    assert _listed(window, "Forms", "Pages") == pages[::-1]
    assert _listed(window, "Forms") == ["Pages"] + forms[::-1]
    assert _listed(window, "Modules") == ["Module2", "Module1"]
    assert explorer._current()[0].endswith("pgLists.py")  # still selected
    window.add_form()  # with a page selected: into the Pages group, in its place
    assert _listed(window, "Forms", "Pages")[0] == "pgZOrder"
    assert "Form2" in _listed(window, "Forms", "Pages")
    # ...Z to A among the files (a group named after them: in its place)
    explorer.sort_button.click()
    assert explorer.sort_button.text() == "Name ▼"
    window.project.add_group(("Forms",), "Gadgets")
    window._refresh_explorer()
    assert _listed(window, "Forms") == ["Pages", "Gadgets"] + forms[::-1]
    assert explorer._current()[0].endswith("Form2.py")
    # The IDE remembers the order
    other = MainWindow()
    assert (other.explorer.sort_descending, other.explorer.groups_first) == (True, False)
    other.close()
    explorer.sort_button.click()  # and back to the start
    assert explorer.sort_button.text() == "Groups, Name ▲"
    assert _listed(window, "Forms") == ["Gadgets", "Pages"] + forms
    other = MainWindow()
    assert (other.explorer.sort_descending, other.explorer.groups_first) == (False, True)
    other.close()


def test_group_properties(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    window.explorer.select_group(("Forms",))
    assert window.properties.designer is window.group_target
    assert _props(window) == ("Forms  Group", ["(Name)"])
    window.properties._on_row_changed(0)
    assert "changes no file" in window.properties.description.text()
    window.properties._commit("Name", "Modules")  # a sibling's name: refused
    assert warnings and "already" in warnings[0]
    assert _listed(window) == ["Forms", "Modules"]
    window.properties._commit("Name", "Windows and dialogs")  # any name, not an identifier
    assert _listed(window) == ["Modules", "Windows and dialogs"]
    assert window.explorer.selected_group() == ("Windows and dialogs",)  # still selected
    assert _props(window) == ("Windows and dialogs  Group", ["(Name)"])
    assert Project.load(window.project.path).group_paths() == [("Windows and dialogs",),
                                                               ("Modules",)]
    # A subgroup; a file's selection shows the file again
    window.project.add_group(("Modules",), "Helpers")
    window._refresh_explorer()
    window.explorer.select_group(("Modules", "Helpers"))
    assert _props(window)[0] == "Helpers  Group"
    _select_item(window, "Module1")
    assert window.properties.designer is not window.group_target


def _item(window, *path):
    """The Project panel's item for a group or file, by names from the project."""
    item = window.explorer.tree.topLevelItem(0)
    for name in path:
        item = next(item.child(i) for i in range(item.childCount())
                    if item.child(i).data(0, Qt.UserRole + 2) == name)
    return item


def _menu(window, item):
    """The context menu's actions by text (the Move to submenu's under "Move to/...")."""
    actions = {}
    for action in window.explorer.context_menu(item).actions():
        actions[action.text()] = action
        if action.menu() is not None:
            for sub in action.menu().actions():
                actions["Move to/" + sub.text()] = sub
    return actions


def test_project_panel_groups(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    answers = []
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *args, **kw: (answers.pop(0), True))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    assert _listed(window) == ["Forms", "Modules"]  # the default groups
    # New Group from a group's menu: inside it, selected
    answers.append("Dialogs")
    _menu(window, _item(window, "Forms"))["New Group…"].trigger()
    assert _listed(window, "Forms") == ["Dialogs", "Form1"]
    assert window.explorer.selected_group() == ("Forms", "Dialogs")
    window.add_form()  # into the selected group
    assert _listed(window, "Forms", "Dialogs") == ["Form2"]
    # Move to: a module into a group of forms (no group is special)
    menu = _menu(window, _item(window, "Modules", "Module1"))
    assert "Move to/Modules" not in menu  # where it is already
    menu["Move to/Forms / Dialogs"].trigger()
    assert _listed(window, "Forms", "Dialogs") == ["Form2", "Module1"]
    # A group can't go into itself; dragging it onto the project: the top level
    menu = _menu(window, _item(window, "Forms"))
    assert "Move to/Forms / Dialogs" not in menu and "Move to/Modules" in menu
    window.explorer._request_move(_item(window, "Forms", "Dialogs"), _item(window))
    assert _listed(window) == ["Dialogs", "Forms", "Modules"]
    assert _listed(window, "Dialogs") == ["Form2", "Module1"]
    # Dropping on a file: into that file's group
    window.explorer._request_move(_item(window, "Dialogs", "Module1"),
                                  _item(window, "Forms", "Form1"))
    assert _listed(window, "Forms") == ["Form1", "Module1"]
    # Rename: a name already there is refused (and said)
    answers.append("Forms")
    _menu(window, _item(window, "Dialogs"))["Rename Group…"].trigger()
    assert warnings and "already" in warnings[0]
    answers.append("Windows")
    _menu(window, _item(window, "Dialogs"))["Rename Group…"].trigger()
    assert _listed(window) == ["Forms", "Modules", "Windows"]
    # Delete: what it held moves up; nothing leaves the project
    _menu(window, _item(window, "Windows"))["Delete Group (keeps what is in it)"].trigger()
    assert _listed(window) == ["Forms", "Modules", "Form2"]
    # Saved in the project file, not as folders on disk
    loaded = Project.load(window.project.path)
    assert loaded.group_of("Module1.py") == ("Forms",) and loaded.group_of("Form2.py") == ()
    assert os.path.isfile(os.path.join(os.path.dirname(window.project.path), "Form2.py"))


def test_about_vp6(window, monkeypatch):
    import sys

    from PySide6.QtGui import QAction

    from vp6.ide.dialogs import LOGO_WIDTH, AboutDialog
    shown = []
    monkeypatch.setattr(AboutDialog, "exec", lambda self: shown.append(self) or 0)
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Help")
    # Help > About VP6 stays in the Help menu (not moved to the macOS application menu)
    assert window.act_about in help_menu.actions()
    assert window.act_about.menuRole() == QAction.NoRole
    window.act_about.trigger()
    if sys.platform == "darwin":  # and VP6 > About VP6: the same dialog
        assert window.act_about_app.menuRole() == QAction.AboutRole
        window.act_about_app.trigger()
        assert len(shown) == 2
    dialog = shown[0]
    logo = dialog.logo.pixmap()
    assert not logo.isNull()  # the logo, packaged with the IDE
    assert round(logo.width() / logo.devicePixelRatio()) == LOGO_WIDTH
    assert vp6.__version__ in dialog.text.text()


def test_project_item_is_not_collapsible(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    tree = window.explorer.tree
    root = tree.topLevelItem(0)
    assert root.isExpanded() and not tree.rootIsDecorated()  # no arrow
    assert tree.visualItemRect(root.child(0)).isValid()  # its contents are shown
    root.setExpanded(False)
    assert root.isExpanded()
    tree.setCurrentItem(root)
    tree.setFocus()
    for key in (Qt.Key_Left, Qt.Key_Minus):  # the keys that collapse an item
        QTest.keyClick(tree, key)
        assert root.isExpanded()
    rect = tree.visualItemRect(root)
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, pos=rect.center())
    assert root.isExpanded()
    groups = root.child(0)  # the groups still collapse
    groups.setExpanded(False)
    assert not groups.isExpanded()


def test_project_panel_expand_collapse_all(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    explorer = window.explorer
    button = explorer.expand_button
    root = explorer.tree.topLevelItem(0)
    pages = _item(window, "Forms", "Pages")
    assert button.text() == "-" and explorer.all_expanded()  # everything open at first
    button.click()  # collapse every group; the project stays open
    assert button.text() == "+"
    assert root.isExpanded() and not _item(window, "Forms").isExpanded()
    assert not pages.isExpanded() and not _item(window, "Modules").isExpanded()
    button.click()  # and expand everything again
    assert button.text() == "-" and pages.isExpanded() and _item(window, "Forms").isExpanded()
    pages.setExpanded(False)  # one group collapsed by hand: + expands all
    assert button.text() == "+"
    # Collapsed groups stay collapsed when the panel is refilled (e.g. a new form)
    window.explorer.select_group(("Modules",))
    window.add_module()
    assert not _item(window, "Forms", "Pages").isExpanded()
    assert _item(window, "Modules").isExpanded()
    button.click()
    assert button.text() == "-" and _item(window, "Forms", "Pages").isExpanded()
    # Another project starts with everything open
    button.click()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    assert window.explorer.all_expanded() and button.text() == "-"


def _names(item):
    return [item.child(i).text(0) for i in range(item.childCount())]


def test_project_panel_files_view(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = os.path.dirname(window.project.path)
    os.makedirs(os.path.join(folder, "assets", "icons"))
    open(os.path.join(folder, "assets", "logo.png"), "wb").close()
    open(os.path.join(folder, "notes.txt"), "w").close()
    open(os.path.join(folder, ".env"), "w").close()
    os.makedirs(os.path.join(folder, ".git", "objects"))
    os.makedirs(os.path.join(folder, ".venv"))
    os.makedirs(os.path.join(folder, "__pycache__"))
    os.makedirs(os.path.join(folder, "assets", "__pycache__"))
    os.makedirs(os.path.join(folder, "assets", "vendored", ".git"))
    explorer = window.explorer
    assert explorer.project_button.isChecked() and not explorer.hidden_button.isVisible()
    _select_item(window, "Form1")
    explorer.files_button.click()  # the folder as it is on disk
    assert explorer.files_mode and explorer.hidden_button.isVisibleTo(explorer)
    root = explorer.tree.topLevelItem(0)
    assert root.text(0) == "Demo" and root.toolTip(0) == folder
    # Folders first, then the files, by name; hidden ones left out, and never
    # the project file, __pycache__ or .git
    assert _names(root) == ["assets", "Form1.py", "Module1.py", "notes.txt"]
    assert _names(root.child(0)) == ["icons", "vendored", "logo.png"]
    assert explorer.sort_button.text() == "Folders, Name ▲"
    # The form stays selected, and works as in the Project view
    assert explorer._current() == (os.path.join(folder, "Form1.py"), "form")
    assert explorer.view_object.isEnabled()
    menu = [a.text() for a in explorer.context_menu(explorer.tree.currentItem()).actions()]
    assert "View Object" in menu and "Set as Start Up" in menu
    assert "New Group…" not in menu  # groups are the Project view's
    assert "Rename…" in menu and "Move to" in menu  # files and folders on disk
    notes = root.child(3)
    explorer.tree.setCurrentItem(notes)  # any other file: listed, nothing to open
    assert explorer._current() == (None, None) and not explorer.view_code.isEnabled()
    assert explorer.selected_group("form") is None  # new files: where the project puts them
    # Hidden files and folders on request
    explorer.hidden_button.click()
    assert _names(root := explorer.tree.topLevelItem(0)) == [
        ".venv", "assets", ".env", "Form1.py", "Module1.py", "notes.txt"]  # no .git
    assert _names(root.child(1)) == ["icons", "vendored", "logo.png"]  # nor __pycache__
    assert _names(root.child(1).child(1)) == []
    assert explorer.tree.currentItem().text(0) == "notes.txt"  # still selected
    explorer.hidden_button.click()
    root = explorer.tree.topLevelItem(0)
    # +/- works on folders; they stay collapsed when the view is refilled
    explorer.expand_button.click()
    assert not explorer.tree.topLevelItem(0).child(0).isExpanded()
    # The view follows the disk
    open(os.path.join(folder, "readme.md"), "w").close()
    wait_for(lambda: "readme.md" in _names(explorer.tree.topLevelItem(0)))
    assert not explorer.tree.topLevelItem(0).child(0).isExpanded()
    # The IDE remembers the view
    other = MainWindow()
    assert other.explorer.files_mode and not other.explorer.show_hidden
    other.close()
    # Back to the Project view: the groups again, the form still selected
    _select_item(window, "Form1.py")
    explorer.project_button.click()
    assert not explorer.files_mode and not explorer.hidden_button.isVisibleTo(explorer)
    assert _listed(window) == ["Forms", "Modules"]
    assert explorer._current()[0] == os.path.join(folder, "Form1.py")
    assert explorer.sort_button.text() == "Groups, Name ▲"
    other = MainWindow()
    assert not other.explorer.files_mode
    other.close()


def test_files_view_changes_on_disk(window, tmp_path, monkeypatch):
    import shutil

    from PySide6.QtWidgets import QInputDialog, QMessageBox
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = os.path.dirname(window.project.path)
    here = lambda *parts: os.path.join(folder, *parts)  # noqa: E731
    open(here("notes.txt"), "w").close()
    answers, warnings = [], []
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kw: (answers.pop(0), True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(MainWindow, "_move_to_trash", staticmethod(
        lambda path: (shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)) or True))
    explorer = window.explorer
    explorer.files_button.click()

    def item(*parts):
        return explorer._find(lambda i: explorer._item_path(i) == here(*parts))

    def menu(it):
        actions = {}
        for action in explorer.context_menu(it).actions():
            actions[action.text()] = action
            if action.menu() is not None:
                for sub in action.menu().actions():
                    actions["Move to/" + sub.text()] = sub
        return actions

    # New folders: in the project's folder, and in a folder
    answers.append("lib")
    menu(explorer.tree.topLevelItem(0))["New Folder…"].trigger()
    assert os.path.isdir(here("lib")) and explorer._item_path(explorer.tree.currentItem()) == \
        here("lib")
    answers.append("deep")
    menu(item("lib"))["New Folder…"].trigger()
    assert os.path.isdir(here("lib", "deep"))
    answers.append("lib")  # already there
    menu(explorer.tree.topLevelItem(0))["New Folder…"].trigger()
    assert "already exists" in warnings.pop()
    # A new module in the selected folder (and in the Modules group)
    explorer.select_path(here("lib", "deep"))
    window.add_module()
    assert "lib/deep/Module2.py" in window.project.modules
    assert window.project.group_of("lib/deep/Module2.py") == ("Modules",)
    # Moving: with Move to, and by drag and drop; open windows follow
    window.view_code(here("Module1.py"))
    menu(item("Module1.py"))["Move to/lib"].trigger()
    assert os.path.isfile(here("lib", "Module1.py")) and not os.path.exists(here("Module1.py"))
    assert "lib/Module1.py" in window.project.modules
    assert window.project.group_of("lib/Module1.py") == ("Modules",)  # its place kept
    assert here("lib", "Module1.py") in window.code_windows
    explorer._request_move(item("Form1.py"), item("lib", "Module1.py"))  # onto a file: its folder
    assert window.project.forms == ["lib/Form1.py"]
    assert "Move to/lib" not in menu(item("lib", "Form1.py"))  # where it is already
    assert "Move to/lib/deep" not in menu(item("lib"))  # not into itself
    assert "into itself" in window.relocate(here("lib"), here("lib", "deep", "lib"))
    # Renaming a form's file: the imports of it follow; its class doesn't change
    answers.append("frmMain.py")
    menu(item("lib", "Form1.py"))["Rename…"].trigger()
    assert window.project.forms == ["lib/frmMain.py"]
    module1 = window.documents[here("lib", "Module1.py")]
    assert "from frmMain import Form1" in module1.text
    # A form's or module's file keeps a Python name, unique in the project
    for name, error in (("bad name.py", "identifier"), ("Module1.txt", ".py file"),
                        ("FRMMAIN.py", "already in the project"), ("a/b.py", "not a valid")):
        answers.append(name)
        menu(item("lib", "deep", "Module2.py"))["Rename…"].trigger()
        assert error in warnings.pop(), name
    # Any other file: any name
    answers.append("readme.txt")
    menu(item("notes.txt"))["Rename…"].trigger()
    assert os.path.isfile(here("readme.txt"))
    # Renaming a folder: what is in it follows
    answers.append("code")
    menu(item("lib"))["Rename…"].trigger()
    assert sorted(window.project.modules) == ["code/Module1.py", "code/deep/Module2.py"]
    assert window.project.forms == ["code/frmMain.py"]
    assert here("code", "Module1.py") in window.code_windows
    assert os.path.isfile(here("code", "deep", "Module2.py"))
    loaded = Project.load(window.project.path)  # saved
    assert loaded.forms == ["code/frmMain.py"] and "code/deep/Module2.py" in loaded.modules
    # Deleting a folder: to the Trash, and its modules leave the project
    menu(item("code", "deep"))["Delete"].trigger()
    assert not os.path.exists(here("code", "deep"))
    assert window.project.modules == ["code/Module1.py"]
    assert not any("Module2" in path for path in window.documents)
    # The project file stays put (and isn't in the Files view)
    assert item("Demo.vp6p") is None
    assert "stay where they are" in window.relocate(window.project.path, here("code", "x.vp6p"))


def test_new_folders_and_subfolders(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = os.path.dirname(window.project.path)
    answers = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kw: (answers.pop(0), True))
    explorer = window.explorer
    assert not explorer.new_folder_button.isVisibleTo(explorer)  # the Files view's
    assert window.act_add_folder.isEnabled()
    # Project > Add Folder…: from the Project view too (it switches to the Files view)
    answers.append("assets")
    window.act_add_folder.trigger()
    assert explorer.files_mode and os.path.isdir(os.path.join(folder, "assets"))
    assert explorer.new_folder_button.isVisibleTo(explorer)
    # The New Folder button: in the selected folder (a subfolder)...
    assert explorer._item_path(explorer.tree.currentItem()) == os.path.join(folder, "assets")
    answers.append("icons")
    explorer.new_folder_button.click()
    assert os.path.isdir(os.path.join(folder, "assets", "icons"))
    answers.append("large")
    explorer.new_folder_button.click()  # (the new one is selected: a sub-subfolder)
    assert os.path.isdir(os.path.join(folder, "assets", "icons", "large"))
    # ...or the selected file's folder
    explorer.select_path(os.path.join(folder, "Form1.py"))
    answers.append("docs")
    explorer.new_folder_button.click()
    assert os.path.isdir(os.path.join(folder, "docs"))
    # The context menu of a file: New Folder… next to it
    explorer.select_path(os.path.join(folder, "Form1.py"))
    actions = {a.text(): a for a in explorer.context_menu(explorer.tree.currentItem()).actions()}
    answers.append("more")
    actions["New Folder…"].trigger()
    assert os.path.isdir(os.path.join(folder, "more"))


def _drop(explorer, target):
    """Drop the selected items on ``target``, as a drag and drop does."""
    from PySide6.QtCore import QMimeData, QPointF
    from PySide6.QtGui import QDropEvent
    pos = QPointF(explorer.tree.visualItemRect(target).center())
    event = QDropEvent(pos, Qt.MoveAction, QMimeData(), Qt.LeftButton, Qt.NoModifier)
    explorer.tree.dropEvent(event)


def _selected_names(explorer):
    return sorted(i.data(0, Qt.UserRole + 2) for i in explorer.tree.selectedItems())


def test_moving_several_items(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QAbstractItemView, QMessageBox
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    explorer = window.explorer
    assert explorer.tree.selectionMode() == QAbstractItemView.ExtendedSelection

    def select(*items):
        explorer.tree.clearSelection()
        for it in items:
            it.setSelected(True)
        explorer.tree.setCurrentItem(items[0], 0, QItemSelectionModel.NoUpdate)

    def moves(it):
        move = next(a for a in explorer.context_menu(it).actions() if a.menu() is not None
                    and a.text().startswith("Move"))
        return move.text(), {a.text(): a for a in move.menu().actions()}

    # Project view: three pages from the context menu of one of them
    pages = [_item(window, "Forms", "Pages", name) for name in ("pgLists", "pgMenus", "pgTree")]
    select(*pages)
    text, targets = moves(pages[1])
    assert text == "Move 3 Items to" and "Forms" in targets
    targets["Forms"].trigger()
    assert {"pgLists", "pgMenus", "pgTree"} <= set(_listed(window, "Forms"))
    assert _selected_names(explorer) == ["pgLists", "pgMenus", "pgTree"]  # still selected
    # The context menu of an item outside the selection: that item alone
    select(_item(window, "Forms", "pgLists"), _item(window, "Forms", "pgMenus"))
    assert moves(_item(window, "Forms", "Form1"))[0] == "Move to"
    # Dragging several onto a group; a group and something in it: the group moves
    select(_item(window, "Forms", "pgLists"), _item(window, "Forms", "pgMenus"))
    _drop(explorer, _item(window, "Modules"))
    assert {"pgLists", "pgMenus"} <= set(_listed(window, "Modules"))
    select(_item(window, "Forms", "Pages"), _item(window, "Forms", "Pages", "pgArrays"))
    assert moves(_item(window, "Forms", "Pages"))[0] == "Move to"
    _drop(explorer, _item(window, "Modules", "pgLists"))  # onto a file: into its group
    assert "Pages" in _listed(window, "Modules") and "pgArrays" in _listed(
        window, "Modules", "Pages")
    # Those that can't move are said in one message; the others move
    window.project.add_group((), "Pages")
    window._refresh_explorer()
    select(_item(window, "Modules", "Pages"), _item(window, "Modules", "pgMenus"))
    _drop(explorer, _item(window))
    assert "pgMenus" in _listed(window) and "Pages" in _listed(window, "Modules")
    assert len(warnings) == 1 and "already" in warnings.pop()

    # Files view: several files, then a folder with a file of it
    folder = os.path.dirname(window.project.path)
    for name in ("a", "b"):
        os.mkdir(os.path.join(folder, name))
    open(os.path.join(folder, "notes.txt"), "w").close()
    explorer.files_button.click()

    def item(*parts):
        return explorer._find(lambda i: explorer._item_path(i) == os.path.join(folder, *parts))

    select(item("Form1.py"), item("Module1.py"), item("notes.txt"))
    text, targets = moves(item("notes.txt"))
    assert text == "Move 3 Items to"
    targets["a"].trigger()
    assert sorted(os.listdir(os.path.join(folder, "a"))) == ["Form1.py", "Module1.py",
                                                             "notes.txt"]
    assert "a/Form1.py" in window.project.forms and "a/Module1.py" in window.project.modules
    assert _selected_names(explorer) == ["Form1", "Module1", "notes.txt"]
    select(item("a"), item("a", "Form1.py"))
    _drop(explorer, item("b"))  # the folder moves, and the file with it
    assert os.listdir(os.path.join(folder, "b")) == ["a"]
    assert "b/a/Form1.py" in window.project.forms
    assert "b/a/Form1.py" in Project.load(window.project.path).forms  # saved
    assert not warnings


def test_icons_of_vp6_and_new_projects(window, tmp_path):
    assert sorted(s.width() for s in window.windowIcon().availableSizes()) == [32, 64, 128, 256]
    # New projects have no icon of their own (the installed VP6 icon), and no copy of it
    for template in ("exe", "console", "kitchensink"):
        project = Project.load(create_project(str(tmp_path), template.title(), template))
        assert project.icon == []
        assert not os.path.exists(os.path.join(project.directory, "icons"))
    # The Properties panel: the project's Icon (its largest size); choosing one file
    window.open_project(os.path.join(tmp_path, "Exe", "Exe.vp6p"))
    window.explorer.select_project()
    target = window.properties.designer
    assert target is window.project_target
    assert target.selected_objects()[0].Icon == ""  # (none: the VP6 icon)
    assert target.set_property("Icon", "art/logo.png") is None
    assert window.project.icon == ["art/logo.png"]
    assert Project.load(window.project.path).icon == ["art/logo.png"]  # saved
    assert target.set_property("Icon", "") is None  # none: the VP6 icon
    assert window.project.icon == []
