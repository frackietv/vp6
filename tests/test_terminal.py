"""The Terminal control: the ANSI screen (text, controls, escape sequences,
colors, scrolling, history, the alternate screen, resizing), keys as a
terminal sends them, a real shell in a pseudo-terminal (macOS, Linux: its
output, Ctrl+C, its size, its exit), copy and paste, and the IDE."""

import os
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6 import Form, Terminal, formfile
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.terminal import PLAIN, TERM, AnsiScreen, Attr, key_text

posix = pytest.mark.skipif(sys.platform == "win32", reason="a pseudo-terminal")


# --- the screen ------------------------------------------------------------------------------

def test_text_and_controls():
    screen = AnsiScreen(4, 10)
    screen.feed("ab\rX\nc\td\b\bE")
    assert screen.text() == "Xb\n c     Ed"  # (LF: down only; CR: back to the start)
    screen.feed("\r\n0123456789wrap")  # wraps at the last column
    assert screen.lines[2] == list(zip("0123456789", [PLAIN] * 10))
    assert AnsiScreen.line_text(screen.lines[3]) == "wrap"


def test_cursor_and_erasing():
    screen = AnsiScreen(5, 10)
    screen.feed("\x1b[3;4HX\x1b[1;1HY\x1b[2B\x1b[3CZ")  # positions, down, forward
    assert screen.text() == "Y\n\n   XZ"
    screen.feed("\x1b[1;1Habcdef\x1b[1;3H\x1b[K")  # erase to the end of the line
    assert AnsiScreen.line_text(screen.lines[0]) == "ab"
    screen.feed("\x1b[1;1H\x1b[2J")  # erase the display
    assert screen.text() == ""
    screen.feed("one\r\ntwo\r\nthree\x1b[2;1H\x1b[L")  # insert a line
    assert screen.text() == "one\n\ntwo\nthree"
    screen.feed("\x1b[1M")  # delete it again
    assert screen.text() == "one\ntwo\nthree"
    screen.feed("\x1b[1;1H\x1b[P")  # delete a character
    assert AnsiScreen.line_text(screen.lines[0]) == "ne"
    screen.feed("\x1b[2@")  # insert two
    assert AnsiScreen.line_text(screen.lines[0]) == "  ne"
    screen.feed("\x1b7\x1b[5;5H\x1b8!")  # save and restore the cursor
    assert AnsiScreen.line_text(screen.lines[0]) == "! ne"


def test_colors_and_attributes():
    screen = AnsiScreen(2, 20)
    screen.feed("\x1b[1;4;31mA\x1b[0;7;44mB\x1b[0;92mC\x1b[38;5;200mD\x1b[48;2;1;2;3mE"
                "\x1b[0mF")
    cells = [attr for _, attr in screen.lines[0][:6]]
    assert cells[0] == Attr(fg=1, bold=True, underline=True)
    assert cells[1] == Attr(bg=4, inverse=True)
    assert cells[2] == Attr(fg=10)
    assert cells[3].fg == 200 and cells[4].bg == (1, 2, 3) and cells[5] == PLAIN


def test_scrolling_history_and_regions():
    screen = AnsiScreen(3, 10, scrollback=5)
    for number in range(10):
        screen.feed(f"line {number}\r\n")
    assert screen.text() == "line 8\nline 9" and len(screen.history) == 5  # (at most 5 kept)
    assert AnsiScreen.line_text(screen.history[-1]) == "line 7"
    screen = AnsiScreen(4, 10)
    screen.feed("top\x1b[2;3r")  # a scroll region: rows 2 and 3
    screen.feed("\x1b[2;1Ha\r\nb\r\nc")
    assert screen.text() == "top\nb\nc" and not screen.history  # (top stays put)


def test_title_alternate_screen_and_reset():
    screen = AnsiScreen(3, 10)
    screen.feed("\x1b]0;Hello\x07main")
    assert screen.title == "Hello"
    screen.feed("\x1b]2;Again\x1b\\")
    assert screen.title == "Again"
    screen.feed("\x1b[?1049h")  # e.g. an editor
    assert screen.text() == ""
    screen.feed("editor\x1b[?1049l")  # back: the main screen as it was
    assert screen.text() == "main"
    screen.feed("\x1b[?25l")
    assert not screen.cursor_visible
    screen.feed("\x1bc")
    assert screen.text() == "" and screen.cursor_visible


def test_resize():
    screen = AnsiScreen(4, 10)
    screen.feed("1\r\n2\r\n3\r\n4")
    screen.resize(2, 5)  # the cursor's line stays on the screen
    assert screen.text() == "3\n4" and (screen.rows, screen.cols) == (2, 5)
    assert [AnsiScreen.line_text(line) for line in screen.history] == ["1", "2"]
    screen.resize(4, 5)  # the history comes back
    assert screen.text() == "1\n2\n3\n4"


def test_keys():
    control = Qt.MetaModifier if sys.platform == "darwin" else Qt.ControlModifier
    assert key_text(Qt.Key_C, control, "") == "\x03"  # Ctrl+C
    assert key_text(Qt.Key_Return, Qt.NoModifier, "\r") == "\r"
    assert key_text(Qt.Key_Up, Qt.NoModifier, "") == "\x1b[A"
    assert key_text(Qt.Key_Backspace, Qt.NoModifier, "\b") == "\x7f"
    assert key_text(Qt.Key_F1, Qt.NoModifier, "") == "\x1bOP"
    assert key_text(Qt.Key_A, Qt.NoModifier, "a") == "a"
    assert key_text(Qt.Key_Shift, Qt.ShiftModifier, "") == ""


# --- a real terminal --------------------------------------------------------------------------

class Shell(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 640, 320
        self.term = Terminal(self, Left=0, Top=0, Width=640, Height=320,
                             CommandLine="/bin/sh")
        self.log = []

    def term_Exited(self, ExitCode):
        self.log.append(("exit", ExitCode))

    def term_TitleChange(self, Title):
        self.log.append(("title", Title))


@pytest.fixture
def shell(qapp):
    form = Shell()
    form.Show()  # (AutoStart: the shell starts)
    yield form
    form.Unload()


@posix
def test_a_shell_in_a_terminal(shell):
    term = shell.term
    wait_for(lambda: term.Running and "$" in term.Text)
    assert term.ProcessID > 0 and term.Rows > 5 and term.Columns > 40
    term.Write("echo $TERM; tty; stty size\r")
    # (its size: the program knows it)
    wait_for(lambda: f"\n{term.Rows} {term.Columns}" in term.Text)
    assert f"\n{TERM}\n" in term.Text and "/dev/" in term.Text
    term.Write("printf '\\033]0;From the shell\\007'\r")
    wait_for(lambda: ("title", "From the shell") in shell.log)
    assert term.Title == "From the shell"
    term.Write("sleep 30\r")
    QTest.qWait(200)
    term.Write("\x03")  # Ctrl+C interrupts it
    term.Write("echo after\r")
    wait_for(lambda: "\nafter" in term.Text, timeout_ms=10000)
    term.Write("exit 4\r")
    wait_for(lambda: ("exit", 4) in shell.log)
    assert not term.Running and term.ExitCode == 4
    with pytest.raises(RuntimeError, match="isn't running"):
        term.Write("x")
    term.Start('/bin/sh -c "echo again"')  # another program (double quotes group words)
    wait_for(lambda: ("exit", 0) in shell.log)
    assert "again" in term.Text


@posix
def test_resizing_tells_the_program(shell):
    term = shell.term
    wait_for(lambda: "$" in term.Text)
    shell.term.Width, shell.term.Height = 400, 200
    QTest.qWait(50)
    term.Write("stty size\r")
    wait_for(lambda: f"{term.Rows} {term.Columns}" in term.Text)


@posix
def test_typing_copy_and_paste(shell):
    term = shell.term
    wait_for(lambda: "$" in term.Text)
    view = term._widget
    QTest.keyClicks(view, "echo typed")
    QTest.keyClick(view, Qt.Key_Return)
    wait_for(lambda: "\ntyped" in term.Text)
    lines = term._screen.all_lines()
    row = next(i for i, line in enumerate(lines) if AnsiScreen.line_text(line) == "typed")
    view.selection = ((row, 0), (row, 4))
    term.Copy()
    assert QGuiApplication.clipboard().text() == "typed"
    QGuiApplication.clipboard().setText("echo pasted\n")
    term.Paste()
    wait_for(lambda: "\npasted" in term.Text)
    term.Clear()
    assert term.Text == "" and term._screen.history == []


@posix
def test_ended_with_its_form(qapp):
    form = Shell()
    form.Show()
    wait_for(lambda: form.term.Running)
    form.Unload()
    wait_for(lambda: not form.term.Running)


def test_not_started_and_in_the_ide(qapp, tmp_path):
    from vp6.ide import icons
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument
    from vp6.ide.panels import Toolbox

    class Quiet(Form):
        def InitializeComponent(self):
            self.term = Terminal(self, AutoStart=False)

    form = Quiet()
    form.Show()
    assert not form.term.Running and form.term.ProcessID == 0 and form.term.ExitCode == -1
    form.Unload()
    assert "Terminal" in Toolbox().buttons and CONTROL_TYPES["Terminal"] is Terminal
    assert list(CONTROL_TYPES)[-1] == "Menu" and not icons.icon("Terminal").isNull()
    assert Terminal.DefaultEvent == "Exited" and EVENT_ARGS["TitleChange"] == "Title"
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    name = designer.create_control("Terminal", None, None)
    assert name == "Terminal1" and designer.controls[name]._widget.text() == "$ _"
    assert "self.Terminal1 = Terminal(self," in designer.document.text
    designer.close()
    assert os.path.exists(str(path))
