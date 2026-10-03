"""The IDE's Terminal panel: a shell in the project's folder, next to the
Immediate window."""

import os
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.ide.terminalpanel import TerminalPanel
from vp6.ide.theme import DARK, LIGHT, theme_manager

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the shell is /bin/sh")


@pytest.fixture
def window(qapp):
    w = MainWindow()
    w.show()
    yield w
    w.close_project()
    w.close()


def _run(panel, command, expected):
    panel.terminal.Write(command + "\r")
    wait_for(lambda: expected in panel.terminal._screen.text())


def test_hidden_by_default_next_to_the_immediate_window(window):
    assert window.terminal_dock.isHidden() and not window.terminal.running
    assert window.terminal_dock.windowTitle() == "Terminal"
    window.act_view_terminal.trigger()  # View > Terminal Window
    assert not window.terminal_dock.isHidden()
    assert window.terminal_dock in window.tabifiedDockWidgets(window.immediate_dock)
    shown = [d for d in (window.immediate_dock, window.terminal_dock)
             if d.geometry().intersects(window.rect())]  # (Qt parks the other tab outside)
    assert shown == [window.terminal_dock]
    wait_for(lambda: window.terminal.running)
    assert window.terminal.view.hasFocus() or not window.isActiveWindow()
    window.reset_layout()  # back to the default: hidden, the Immediate window shown
    assert window.terminal_dock.isHidden() and not window.immediate_dock.isHidden()


def test_view_menu_and_key(window):
    assert window.act_view_terminal in window.view_menu.actions()
    control = "Meta" if sys.platform == "darwin" else "Ctrl"
    assert window.act_view_terminal.shortcut() == QKeySequence(control + "+`")


def test_the_shell_starts_in_the_project_folder(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = window.project.directory
    window.show_terminal()
    wait_for(lambda: window.terminal.running)
    _run(window.terminal, "pwd; echo done-$((40+2))", "done-42")
    text = window.terminal.terminal._screen.text()  # (macOS: /var is /private/var)
    assert folder.removeprefix("/private") + "\n" in text.replace("/private/", "/")
    assert window.terminal.terminal.TermName == "xterm-256color"


def test_without_a_project_it_starts_at_home(qapp):
    panel = TerminalPanel()
    assert panel.folder() == os.path.expanduser("~")
    panel = TerminalPanel(lambda: "/no/such/folder")
    assert panel.folder() == os.path.expanduser("~")
    panel.deleteLater()


def test_typing_goes_to_the_shell(window):
    window.show_terminal()
    wait_for(lambda: window.terminal.running)
    view = window.terminal.view
    QTest.keyClicks(view, "echo typed-$((6*7))")
    QTest.keyClick(view, Qt.Key_Return)
    wait_for(lambda: "typed-42" in window.terminal.terminal._screen.text())


def test_enter_starts_a_new_shell_once_it_ended(window):
    panel = window.terminal
    window.show_terminal()
    wait_for(lambda: panel.running)
    panel.terminal.Write("exit 3\r")
    wait_for(lambda: not panel.running)
    assert "The shell ended with code 3. Press Enter for a new one." in \
        panel.terminal._screen.text()
    QTest.keyClick(panel.view, Qt.Key_Return)
    assert panel.running
    assert "ended" not in panel.terminal._screen.text()  # (a clear screen)
    _run(panel, "echo again", "again")


def test_new_shell_replaces_the_one_running(window):
    panel = window.terminal
    window.show_terminal()
    wait_for(lambda: panel.running)
    first = panel.terminal.ProcessID
    panel.new_shell()
    assert panel.running and panel.terminal.ProcessID != first
    assert "ended" not in panel.terminal._screen.text()  # (no word of the one before)
    panel.end_shell()
    assert not panel.running  # (at once)


def test_the_menu(window):
    panel = window.terminal
    window.show_terminal()
    wait_for(lambda: panel.running)
    menu = panel._context_menu()
    actions = {a.text(): a for a in menu.actions() if a.text()}
    assert list(actions) == ["Copy", "Paste", "Clear", "New Shell", "End Shell"]
    assert not actions["Copy"].isEnabled()  # (nothing selected)
    assert actions["Paste"].isEnabled() and actions["End Shell"].isEnabled()
    _run(panel, "echo menu-test", "menu-test")
    actions["Clear"].trigger()
    assert "menu-test" not in panel.terminal._screen.text()
    actions["End Shell"].trigger()
    assert not panel.running
    menu.deleteLater()
    menu = panel._context_menu()
    assert not {a.text(): a for a in menu.actions()}["End Shell"].isEnabled()
    menu.deleteLater()


def test_editor_theme_colors_and_font(window):
    panel = window.terminal
    manager = theme_manager()
    for name in (DARK, LIGHT):
        manager.select(name)
        colors = manager.current().colors
        back, fore = panel.terminal._default_colors()
        assert back == QColor(colors["background"]) and fore == QColor(colors["foreground"])
        font = manager.font()
        assert panel.view.font().family() == font.family()
        assert panel.terminal.FontSize == max(font.pointSize() - 1, 6)


def test_closing_the_ide_ends_the_shell(qapp):
    w = MainWindow()
    w.show()
    w.show_terminal()
    wait_for(lambda: w.terminal.running)
    w.close()
    assert not w.terminal.running


def test_screenshot(window, tmp_path):
    window.resize(900, 600)
    window.show_terminal()
    wait_for(lambda: window.terminal.running)
    _run(window.terminal, "printf '\\033[31mred\\033[0m\\n'", "red")
    QTest.qWait(50)
    image = window.terminal.grab().toImage()
    assert image.width() > 100 and image.height() > 50
