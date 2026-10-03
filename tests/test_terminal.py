"""The Terminal control: the ANSI screen (text, controls, escape sequences,
colors, scrolling, history, the alternate screen, resizing), the terminal
types (xterm-256color, xterm, vt100, vt102, vt220, ansi: their character sets,
modes, answers and keys), keys as a terminal sends them, the mouse, focus and
pastes reported to the program, a real shell in a pseudo-terminal (macOS,
Linux: its output, Ctrl+C, its size, its exit, its TERM, a program asking the
terminal), copy and paste, and the IDE."""

import codecs
import os
import sys

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFocusEvent, QGuiApplication
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6 import (Form, Terminal, formfile, vpTermAnsi, vpTermVT100, vpTermVT102, vpTermVT220,
                 vpTermXterm, vpTermXterm256Color)
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.terminal import PLAIN, TERM, TERMINAL_TYPES, AnsiScreen, Attr, key_text

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


def test_terminal_types_answer_as_themselves():
    assert TERM == "xterm-256color" and TERMINAL_TYPES == (
        "xterm-256color", "xterm", "vt100", "vt102", "vt220", "ansi")
    assert (vpTermXterm256Color, vpTermXterm, vpTermVT100, vpTermVT102, vpTermVT220,
            vpTermAnsi) == (0, 1, 2, 3, 4, 5)
    attributes = {}
    for term in TERMINAL_TYPES:
        screen = AnsiScreen(3, 10, term=term)
        screen.feed("\x1b[c\x1b[>c")  # Device Attributes: primary and secondary
        attributes[term] = screen.replies
    assert attributes["vt100"] == ["\x1b[?1;2c"] and attributes["vt102"] == ["\x1b[?6c"]
    assert attributes["vt220"] == ["\x1b[?62;1;2;6;7;8;9c", "\x1b[>1;10;0c"]
    assert attributes["xterm-256color"][0] == "\x1b[?62;1;2;6;7;8;9;22c"
    assert attributes["xterm"] == attributes["xterm-256color"]
    screen = AnsiScreen(5, 20)
    screen.feed("ab\x1b[5n\x1b[6n\x1b[18t\x1b[0x")  # status, the cursor, the size, vt100's
    assert screen.replies == ["\x1b[0n", "\x1b[1;3R", "\x1b[8;5;20t",
                              "\x1b[2;1;1;112;112;1;0x"]
    screen.replies.clear()
    screen.colors = lambda: ((255, 255, 255), (0, 0, 16))
    screen.feed("\x1b]11;?\x07\x1b]4;1;?\x1b\\")  # colors: the background, a palette's
    assert screen.replies == ["\x1b]11;rgb:0000/0000/1010\x1b\\",
                              "\x1b]4;1;rgb:cdcd/3131/3131\x1b\\"]
    screen.replies.clear()
    screen.feed("\x1b[?2004h\x1b[?2004$p\x1b[4$p\x1b[?77$p")  # modes: set, reset, unknown
    assert screen.replies == ["\x1b[?2004;1$y", "\x1b[4;2$y", "\x1b[?77;0$y"]
    screen.replies.clear()
    screen.feed("\x1b[1;31m\x1bP$qm\x1b\\\x1bP+q544e;436f;7878\x1b\\")  # settings, terminfo
    assert screen.replies == ["\x1bP1$r0;1;31m\x1b\\",
                              "\x1bP1+r544e=787465726d2d323536636f6c6f72\x1b\\",
                              "\x1bP1+r436f=323536\x1b\\", "\x1bP0+r7878\x1b\\"]
    screen.replies.clear()
    screen.feed("\x1b[>q")
    assert screen.replies[0].startswith("\x1bP>|VP6 ")
    vt100 = AnsiScreen(3, 10, term="vt100")
    vt100.feed("\x1b[18t\x1bP$qm\x1b\\\x1b[?1$p")  # (xterm's questions: not a vt100's)
    assert vt100.replies == [] and vt100.text() == ""


def test_character_sets_and_controls():
    screen = AnsiScreen(4, 20)
    screen.feed("\x1b(0lqqk\x1b(B x")  # the DEC line drawing set, then ASCII again
    assert AnsiScreen.line_text(screen.lines[0]) == "┌──┐ x"
    screen.feed("\r\n\x1b)0\x0ex\x0fx\x1b*0\x1bNjj")  # G1 by SO, G2 for one character
    assert AnsiScreen.line_text(screen.lines[1]) == "│x┘j"
    screen.feed("\r\n\x9b1m8\x9b0m\x9d2;C1\x9c")  # 8-bit controls: CSI, OSC, ST
    assert screen.lines[2][0] == ("8", Attr(bold=True)) and screen.title == "C1"
    vt100 = AnsiScreen(2, 10, term="vt100")
    vt100.feed("\x9b1mA")  # (a vt100 has no 8-bit controls)
    assert vt100.lines[0][0] == ("1", PLAIN)
    screen = AnsiScreen(2, 20)
    screen.feed("a\x1bP+q544e\x1b\\b\x1b_Gq=1;AAAA\x1b\\c\x1b^pm\x1b\\d\x1bXsos\x9ce")
    assert screen.text() == "abcde"  # (DCS, APC, PM, SOS: none of them shown)
    screen.feed("\x1b[3b\x1b#8")  # REP: the last character again; then all E's
    assert screen.text() == "E" * 20 + "\n" + "E" * 20


def test_modes():
    screen = AnsiScreen(4, 6)
    screen.feed("\x1b[?7labcdefgh")  # autowrap off: the last column is overwritten
    assert screen.text() == "abcdeh"
    screen.feed("\x1b[?7h\x1b[2;1Habcdef\x1b[0mg")  # (an SGR keeps the pending wrap)
    assert AnsiScreen.line_text(screen.lines[2]) == "g"
    screen = AnsiScreen(4, 10)
    screen.feed("abc\x1b[1;2H\x1b[4hX\x1b[4lY")  # insert mode, then replacing again
    assert screen.text() == "aXYc"
    screen.feed("\x1b[20h\n!")  # new line mode: LF goes back to the start too
    assert AnsiScreen.line_text(screen.lines[1]) == "!"
    screen = AnsiScreen(5, 10)
    screen.feed("\x1b[2;4r\x1b[?6h\x1b[1;1HO\x1b[9;1HB\x1b[6n")  # origin: in the region
    assert screen.lines[1][0][0] == "O" and screen.lines[3][0][0] == "B"
    assert screen.replies == ["\x1b[3;2R"]  # (the position from the region's top)
    screen.feed("\x1b[!p")  # soft reset: origin mode and the region gone
    assert 6 not in screen.modes and (screen.top, screen.bottom) == (0, 4)
    screen = AnsiScreen(2, 30)
    screen.feed("\x1b[3g\x1b[1;5H\x1bH\x1b[1;15H\x1bH\r\ta\tb\x1b[2Zc")  # tab stops
    assert AnsiScreen.line_text(screen.lines[0]) == "    c         b"
    screen.feed("\x1b[?25l\x1b[5 q\x1b[?5h\x1b[?1000h\x1b[?1006h\x1b[?1h\x1b=")
    assert not screen.cursor_visible and screen.cursor_shape == "bar"
    assert screen.mouse_mode == 1000 and {1, 5, 1006} <= screen.modes and screen.keypad_app
    screen.feed("\x1b[?1003h")  # (one mouse mode at a time)
    assert screen.mouse_mode == 1003 and 1000 not in screen.modes
    screen.feed("\x1bc")
    assert screen.cursor_visible and screen.mouse_mode == 0 and not screen.keypad_app


def test_title_stack_and_the_alternate_screen_keeping_the_cursor():
    screen = AnsiScreen(3, 10)
    screen.feed("\x1b]2;shell\x07\x1b[22t\x1b]2;vim\x07")
    assert screen.title == "vim"
    screen.feed("\x1b[23t")  # (the title kept before)
    assert screen.title == "shell"
    screen.feed("ab\x1b[1;31m\x1b[?1049h\x1b[0mXYZ\x1b[?1049lc")
    assert screen.text() == "abc" and screen.lines[0][2][1].fg == 1
    screen.feed("\x1b[?1049h")
    screen.resize(4, 12)  # (the main screen behind it: the new size too)
    screen.feed("\x1b[?1049l")
    assert len(screen.lines) == 4 and len(screen.lines[0]) == 12


def test_more_attributes():
    screen = AnsiScreen(2, 20)
    screen.feed("\x1b[2;3;5;8;9mA\x1b[22;23;25;28;29mB\x1b[4:3mC\x1b[4:0mD"
                "\x1b[38:2::10:20:30;48:5:17mE\x1b[>4;1mF")
    cells = [attr for _, attr in screen.lines[0][:6]]
    assert cells[0] == Attr(dim=True, italic=True, blink=True, invisible=True, strike=True)
    assert cells[1] == PLAIN and cells[2] == Attr(underline=True) and cells[3] == PLAIN
    assert cells[4] == Attr(fg=(10, 20, 30), bg=17)
    assert cells[5] == cells[4]  # (xterm's key options, not an underline)


def test_keys_by_terminal_type_and_mode():
    screen = AnsiScreen()
    assert key_text(Qt.Key_Up, Qt.NoModifier, "", screen) == "\x1b[A"
    assert key_text(Qt.Key_Up, Qt.ShiftModifier, "", screen) == "\x1b[1;2A"  # (xterm's)
    assert key_text(Qt.Key_Home, Qt.NoModifier, "", screen) == "\x1b[H"
    assert key_text(Qt.Key_Delete, Qt.AltModifier, "", screen) == "\x1b[3;3~"
    assert key_text(Qt.Key_F1, Qt.ShiftModifier, "", screen) == "\x1b[1;2P"
    assert key_text(Qt.Key_F5, Qt.NoModifier, "", screen) == "\x1b[15~"
    assert key_text(Qt.Key_F13, Qt.NoModifier, "", screen) == "\x1b[1;2P"
    screen.feed("\x1b[?1h\x1b=\x1b[20h")  # cursor and keypad keys: application; new line
    assert key_text(Qt.Key_Up, Qt.NoModifier, "", screen) == "\x1bOA"
    assert key_text(Qt.Key_End, Qt.NoModifier, "", screen) == "\x1bOF"
    assert key_text(Qt.Key_5, Qt.KeypadModifier, "5", screen) == "\x1bOu"
    assert key_text(Qt.Key_Enter, Qt.KeypadModifier, "\r", screen) == "\x1bOM"
    assert key_text(Qt.Key_5, Qt.NoModifier, "5", screen) == "5"
    assert key_text(Qt.Key_Return, Qt.NoModifier, "\r", screen) == "\r\n"
    vt220 = AnsiScreen(term="vt220")
    assert key_text(Qt.Key_Home, Qt.NoModifier, "", vt220) == "\x1b[1~"  # Find, Select
    assert key_text(Qt.Key_End, Qt.NoModifier, "", vt220) == "\x1b[4~"
    assert key_text(Qt.Key_Up, Qt.ShiftModifier, "", vt220) == "\x1b[A"  # (no modifiers)
    assert key_text(Qt.Key_F13, Qt.NoModifier, "", vt220) == "\x1b[25~"
    vt100 = AnsiScreen(term="vt100")
    assert key_text(Qt.Key_F1, Qt.NoModifier, "", vt100) == "\x1bOP"  # PF1
    assert key_text(Qt.Key_F5, Qt.NoModifier, "", vt100) == "\x1bOt"  # (its keypad's)
    assert key_text(Qt.Key_F11, Qt.NoModifier, "", vt100) == "\x1b[23~"


class _Program:
    """A stand-in for the program: what the Terminal sends it."""

    def __init__(self):
        self.sent = b""

    def running(self):
        return True

    def write(self, data):
        self.sent += data

    def kill(self):
        pass


def test_mouse_focus_and_pastes_reported(qapp):
    class Quiet(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 400, 200
            self.term = Terminal(self, Left=0, Top=0, Width=400, Height=200, AutoStart=False)

    form = Quiet()
    form.Show()
    term = form.term
    program = term.__dict__["_program"] = _Program()
    term.__dict__["_decoder"] = codecs.getincrementaldecoder("utf-8")()
    view = term._widget
    width, height = view.cell_size()
    cell = QPoint(round(2 + 3.5 * width), round(2 + 1.5 * height))  # column 4, row 2
    term._screen.feed("\x1b[?1000h\x1b[?1006h")
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, cell)
    assert program.sent == b"\x1b[<0;4;2M\x1b[<0;4;2m"  # SGR: pressed, released
    program.sent = b""
    QTest.mouseClick(view, Qt.LeftButton, Qt.ShiftModifier, cell)  # (Shift: selecting)
    assert program.sent == b""
    term._screen.feed("\x1b[?1006l")
    QTest.mouseClick(view, Qt.RightButton, Qt.NoModifier, cell)  # X10's bytes
    assert program.sent == b"\x1b[M" + bytes((34, 36, 34)) + b"\x1b[M" + bytes((35, 36, 34))
    program.sent = b""
    term._screen.feed("\x1b[?1000l\x1b[?1004h\x1b[?2004h")
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, cell)  # (not asked for: selecting)
    assert program.sent == b""
    QApplication.sendEvent(view, QFocusEvent(QEvent.FocusIn))
    QApplication.sendEvent(view, QFocusEvent(QEvent.FocusOut))
    assert program.sent == b"\x1b[I\x1b[O"
    program.sent = b""
    QGuiApplication.clipboard().setText("ls\nrm -rf /\x1b[201~")
    term.Paste()  # bracketed: the program knows it was pasted (and the end can't be faked)
    assert program.sent == b"\x1b[200~ls\rrm -rf /\x1b[201~"
    program.sent = b""
    term._on_data(b"\x1b[6n")  # its answers go to the program
    assert program.sent == b"\x1b[1;1R"
    term.__dict__["_program"] = None
    form.Unload()


def test_terminal_type_property(qapp):
    class Typed(Form):
        def InitializeComponent(self):
            self.term = Terminal(self, AutoStart=False, TerminalType=vpTermVT220)

    form = Typed()
    assert form.term.TerminalType == vpTermVT220 and form.term.TermName == "vt220"
    form.term.TerminalType = vpTermXterm
    assert form.term.TermName == "xterm" and form.term._screen.term == "xterm"
    with pytest.raises(ValueError, match="TerminalType"):
        form.term.TerminalType = 9
    assert Terminal._specs["TerminalType"].default == vpTermXterm256Color
    form.Unload()


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
@pytest.mark.parametrize("kind, name", [(vpTermVT100, "vt100"), (vpTermXterm, "xterm")])
def test_the_program_sees_its_terminal_type(qapp, kind, name):
    """Its TERM, and its question (Device Attributes) answered as that terminal."""
    script = ("import os, sys, termios, tty\n"
              "mode = termios.tcgetattr(0)\n"
              "tty.setraw(0)\n"
              "os.write(1, b'\\x1b[c')\n"
              "reply = b''\n"
              "while not reply.endswith(b'c'): reply += os.read(0, 1)\n"
              "termios.tcsetattr(0, termios.TCSANOW, mode)\n"
              "print(os.environ['TERM'], reply[1:].decode())\n")

    class Asking(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 640, 200
            self.term = Terminal(self, Left=0, Top=0, Width=640, Height=200, AutoStart=False,
                                 TerminalType=kind)

    form = Asking()
    form.Show()
    form.term.Start([sys.executable, "-c", script])
    wait_for(lambda: not form.term.Running)
    answer = AnsiScreen(term=name)
    answer.feed("\x1b[c")
    assert form.term.Text.strip() == f"{name} {answer.replies[0][1:]}"
    form.Unload()


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
