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
    assert project.modules == ["Module1.py"]
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
    doc = next(iter(window.documents.values()))
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
    doc = next(iter(window.documents.values()))
    doc.text_document.setPlainText(
        "import os\n\ndef Main():\n    print('scheme=' + os.environ['VP6_IDE_SCHEME'])\n")
    window.run_project()
    wait_for(lambda: window.process is None, 15000)
    assert "scheme=dark" in window.immediate.output.toPlainText()


def test_project_explorer_follows_active_window(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    form_path = os.path.join(tmp_path, "Demo", "Form1.py")
    assert window.explorer._current() == (form_path, "form")  # startup form selected
    window.add_module()  # opens Module1's code window
    module_path = os.path.join(tmp_path, "Demo", "Module1.py")
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
