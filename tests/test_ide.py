import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

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
    assert list(rows) == ["(Name)", "ColorScheme", "StartupObject", "Type"]
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
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    iterator = QTreeWidgetItemIterator(window.explorer.tree)
    while iterator.value() is not None:
        if iterator.value().text(0).startswith(text):
            window.explorer.tree.setCurrentItem(iterator.value())
            return
        iterator += 1
    raise AssertionError(f"no explorer item {text!r}")


def test_properties_follow_project_panel_selection(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Sink", "kitchensink"))
    _select_item(window, "Module1")
    assert _props(window) == ("Module1  Module", ["(Name)"])  # modules have a Name
    _select_item(window, "frmDialog")  # a form whose designer isn't open
    assert _props(window) == ("frmDialog  Form", ["(Name)"])
    _select_item(window, "Form1")  # designer open: all its properties
    assert _props(window)[0] == "Form1  Form" and "Caption" in _props(window)[1]
    _select_item(window, "Forms")  # a folder has no properties
    assert _props(window) == ("", [])
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
    assert _props(window) == ("frmDialog  Form", ["(Name)"])
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
    form1 = next(d for d in window.documents.values() if d.name == "Form1")
    assert "from frmDialog import dlgAdd" in form1.text and "dialog = dlgAdd()" in form1.text
    assert _props(window) == ("dlgAdd  Form", ["(Name)"])


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
    window.reset_layout()  # back to the default: hidden again
    assert window.output_dock.isHidden() and not window.immediate_dock.isHidden()
