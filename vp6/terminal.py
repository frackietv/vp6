"""The ``Terminal`` control: a shell (or another program) in a terminal on the
form, speaking ANSI (``TERM=ansi``).

``AnsiScreen`` is the terminal itself, in plain Python: ``feed(text)`` applies
what the program writes (printable characters, CR, LF, BS, TAB, BEL and the
ANSI escape sequences: cursor movement and positioning, erasing in the
display and the line, inserting and deleting lines and characters, a scroll
region, saving the cursor, colors and attributes with SGR, the cursor shown or
hidden, the alternate screen, the window title by OSC) to a grid of
``rows`` x ``cols`` cells, with ``history``: the lines scrolled off the top,
up to ``scrollback``. ``text()`` is the screen as text.

``Terminal`` runs its program in a pseudo-terminal on macOS and Linux (the
program sees a terminal: a shell is interactive, Ctrl+C interrupts, the size
follows the control's), with pipes on Windows (no pseudo-terminal there).
Keys go to the program as a terminal sends them (arrows, Home, End, Delete,
Ctrl+letter...); copy and paste are the system's (Cmd+C / Cmd+V on macOS,
Ctrl+Shift+C / Ctrl+Shift+V elsewhere); the mouse selects; the scroll bar
and the wheel go through the history.
"""

from __future__ import annotations

import codecs
import os
import re
import sys
from dataclasses import dataclass, replace

from PySide6.QtCore import QEvent, QPoint, QRect, QSocketNotifier, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication,
                           QPainter, QPalette)
from PySide6.QtWidgets import QLabel, QScrollBar, QWidget

from . import colors
from ._props import P
from .controls import _COMMON, CONTROL_TYPES, EVENT_ARGS, Control, _geometry, resolve_path

EVENT_ARGS.update({"Exited": "ExitCode", "TitleChange": "Title"})

TERM = "ansi"  # what the Terminal tells the programs it runs it is

# The 16 ANSI colors (normal, then bright), as most terminals show them
ANSI_COLORS = ("#000000", "#cd3131", "#0dbc79", "#e5e510", "#2472c8", "#bc3fbc", "#11a8cd",
               "#e5e5e5", "#666666", "#f14c4c", "#23d18b", "#f5f543", "#3b8eea", "#d670d6",
               "#29b8db", "#ffffff")


@dataclass(frozen=True)
class Attr:
    """How a cell's character looks: colors (None: the default; 0..255 an
    index; an (r, g, b) tuple), bold, underline, inverse."""
    fg: object = None
    bg: object = None
    bold: bool = False
    underline: bool = False
    inverse: bool = False


PLAIN = Attr()


class AnsiScreen:
    """A terminal's screen: the module's documentation."""

    def __init__(self, rows: int = 24, cols: int = 80, scrollback: int = 1000):
        self.rows, self.cols = max(1, rows), max(1, cols)
        self.scrollback = max(0, scrollback)
        self.history: list[list] = []
        self.lines = [self._blank() for _ in range(self.rows)]
        self.row = self.col = 0
        self.attr = PLAIN
        self.saved = (0, 0, PLAIN)
        self.top, self.bottom = 0, self.rows - 1  # the scroll region
        self.wrap_pending = False
        self.cursor_visible = True
        self.title = ""
        self._alternate = None  # the main screen while the alternate one shows
        self._state = "text"
        self._sequence = ""
        self.changed = True

    def _blank(self) -> list:
        return [(" ", PLAIN)] * self.cols

    # -- what the program writes -----------------------------------------------------------
    def feed(self, text: str) -> None:
        self.changed = True
        for char in text:
            state = self._state
            if state == "text":
                self._text_char(char)
            elif state == "esc":
                self._escape(char)
            elif state == "csi":
                if "\x40" <= char <= "\x7e":
                    self._state = "text"
                    self._csi(self._sequence, char)
                else:
                    self._sequence += char
            elif state == "osc":
                if char == "\x07" or (char == "\\" and self._sequence.endswith("\x1b")):
                    self._state = "text"
                    self._osc(self._sequence.rstrip("\x1b"))
                else:
                    self._sequence += char
            elif state == "charset":  # ESC ( B and the like: a character set (ignored)
                self._state = "text"

    def _text_char(self, char: str) -> None:
        if char == "\x1b":
            self._state = "esc"
        elif char == "\r":
            self.col = 0
            self.wrap_pending = False
        elif char in "\n\x0b\x0c":
            self._line_feed()
        elif char == "\b":
            self.col = max(0, self.col - 1)
            self.wrap_pending = False
        elif char == "\t":
            self.col = min(self.cols - 1, (self.col // 8 + 1) * 8)
        elif char == "\x07" or ord(char) < 32 or char == "\x7f":
            pass  # (BEL and other controls: nothing to show)
        else:
            self._put(char)

    def _put(self, char: str) -> None:
        if self.wrap_pending:
            self.col = 0
            self._line_feed()
        self.lines[self.row][self.col] = (char, self.attr)
        if self.col == self.cols - 1:
            self.wrap_pending = True  # (the next character goes on the next line)
        else:
            self.col += 1

    def _line_feed(self) -> None:
        self.wrap_pending = False
        if self.row == self.bottom:
            self._scroll_up(1)
        elif self.row < self.rows - 1:
            self.row += 1

    def _scroll_up(self, count: int) -> None:
        for _ in range(count):
            gone = self.lines.pop(self.top)
            if self.top == 0 and self._alternate is None:  # (into the history)
                self.history.append(gone)
                if len(self.history) > self.scrollback:
                    del self.history[:len(self.history) - self.scrollback]
            self.lines.insert(self.bottom, self._blank())

    def _scroll_down(self, count: int) -> None:
        for _ in range(count):
            del self.lines[self.bottom]
            self.lines.insert(self.top, self._blank())

    def _escape(self, char: str) -> None:
        self._state = "text"
        if char == "[":
            self._state, self._sequence = "csi", ""
        elif char == "]":
            self._state, self._sequence = "osc", ""
        elif char in "()":
            self._state = "charset"
        elif char == "7":
            self.saved = (self.row, self.col, self.attr)
        elif char == "8":
            self.row, self.col, self.attr = self.saved
        elif char == "D":  # index
            self._line_feed()
        elif char == "E":  # next line
            self.col = 0
            self._line_feed()
        elif char == "M":  # reverse index
            if self.row == self.top:
                self._scroll_down(1)
            else:
                self.row = max(0, self.row - 1)
        elif char == "c":  # reset
            self.__init__(self.rows, self.cols, self.scrollback)

    def _osc(self, text: str) -> None:
        number, _, value = text.partition(";")
        if number in ("0", "2"):
            self.title = value

    def _csi(self, params: str, final: str) -> None:
        private = params.startswith("?")
        numbers = [int(p) if p.isdigit() else 0
                   for p in params.lstrip("?>=").split(";")] if params.lstrip("?>=") else []

        def arg(index=0, default=1):
            value = numbers[index] if index < len(numbers) else 0
            return value or default

        self.wrap_pending = False
        if private:
            if final in "hl":
                on = final == "h"
                for number in numbers:
                    if number == 25:
                        self.cursor_visible = on
                    elif number in (47, 1047, 1049):
                        self._alternate_screen(on)
            return
        if final == "A":
            self.row = max(self.top if self.row >= self.top else 0, self.row - arg())
        elif final == "B":
            self.row = min(self.bottom if self.row <= self.bottom else self.rows - 1,
                           self.row + arg())
        elif final == "C":
            self.col = min(self.cols - 1, self.col + arg())
        elif final == "D":
            self.col = max(0, self.col - arg())
        elif final == "E":
            self.row, self.col = min(self.rows - 1, self.row + arg()), 0
        elif final == "F":
            self.row, self.col = max(0, self.row - arg()), 0
        elif final == "G":
            self.col = min(self.cols - 1, arg() - 1)
        elif final == "d":
            self.row = min(self.rows - 1, arg() - 1)
        elif final in "Hf":
            self.row = min(self.rows - 1, arg(0) - 1)
            self.col = min(self.cols - 1, arg(1) - 1)
        elif final == "J":
            self._erase_display(arg(0, 0))
        elif final == "K":
            self._erase_line(arg(0, 0))
        elif final == "L":
            if self.top <= self.row <= self.bottom:
                for _ in range(min(arg(), self.bottom - self.row + 1)):
                    del self.lines[self.bottom]
                    self.lines.insert(self.row, self._blank())
        elif final == "M":
            if self.top <= self.row <= self.bottom:
                for _ in range(min(arg(), self.bottom - self.row + 1)):
                    del self.lines[self.row]
                    self.lines.insert(self.bottom, self._blank())
        elif final == "P":
            line = self.lines[self.row]
            count = min(arg(), self.cols - self.col)
            self.lines[self.row] = line[:self.col] + line[self.col + count:] + \
                [(" ", self.attr)] * count
        elif final == "@":
            line = self.lines[self.row]
            count = min(arg(), self.cols - self.col)
            self.lines[self.row] = (line[:self.col] + [(" ", self.attr)] * count +
                                    line[self.col:])[:self.cols]
        elif final == "X":
            count = min(arg(), self.cols - self.col)
            self.lines[self.row][self.col:self.col + count] = [(" ", self.attr)] * count
        elif final == "S":
            self._scroll_up(arg())
        elif final == "T":
            self._scroll_down(arg())
        elif final == "r":
            top, bottom = arg(0, 1) - 1, arg(1, self.rows) - 1
            if 0 <= top < bottom < self.rows:
                self.top, self.bottom = top, bottom
                self.row, self.col = 0, 0
        elif final == "s":
            self.saved = (self.row, self.col, self.attr)
        elif final == "u":
            self.row, self.col, self.attr = self.saved
        elif final == "m":
            self._sgr(numbers or [0])

    def _erase_display(self, how: int) -> None:
        blank = (" ", replace(PLAIN, bg=self.attr.bg))
        if how == 0:
            self._erase_line(0)
            for row in range(self.row + 1, self.rows):
                self.lines[row] = [blank] * self.cols
        elif how == 1:
            self._erase_line(1)
            for row in range(self.row):
                self.lines[row] = [blank] * self.cols
        elif how in (2, 3):
            self.lines = [[blank] * self.cols for _ in range(self.rows)]
            if how == 3:
                self.history = []

    def _erase_line(self, how: int) -> None:
        blank = (" ", replace(PLAIN, bg=self.attr.bg))
        line = self.lines[self.row]
        if how == 0:
            line[self.col:] = [blank] * (self.cols - self.col)
        elif how == 1:
            line[:self.col + 1] = [blank] * (self.col + 1)
        else:
            self.lines[self.row] = [blank] * self.cols

    def _sgr(self, numbers: list[int]) -> None:
        attr = self.attr
        index = 0
        while index < len(numbers):
            n = numbers[index]
            if n == 0:
                attr = PLAIN
            elif n == 1:
                attr = replace(attr, bold=True)
            elif n == 4:
                attr = replace(attr, underline=True)
            elif n == 7:
                attr = replace(attr, inverse=True)
            elif n == 22:
                attr = replace(attr, bold=False)
            elif n == 24:
                attr = replace(attr, underline=False)
            elif n == 27:
                attr = replace(attr, inverse=False)
            elif 30 <= n <= 37:
                attr = replace(attr, fg=n - 30)
            elif n == 39:
                attr = replace(attr, fg=None)
            elif 40 <= n <= 47:
                attr = replace(attr, bg=n - 40)
            elif n == 49:
                attr = replace(attr, bg=None)
            elif 90 <= n <= 97:
                attr = replace(attr, fg=n - 90 + 8)
            elif 100 <= n <= 107:
                attr = replace(attr, bg=n - 100 + 8)
            elif n in (38, 48) and index + 1 < len(numbers):  # (256 colors, RGB)
                color = None
                if numbers[index + 1] == 5 and index + 2 < len(numbers):
                    color, index = numbers[index + 2], index + 2
                elif numbers[index + 1] == 2 and index + 4 < len(numbers):
                    color, index = tuple(numbers[index + 2:index + 5]), index + 4
                attr = replace(attr, **{"fg" if n == 38 else "bg": color})
            index += 1
        self.attr = attr

    def _alternate_screen(self, on: bool) -> None:
        if on and self._alternate is None:
            self._alternate = (self.lines, self.row, self.col)
            self.lines = [self._blank() for _ in range(self.rows)]
            self.row = self.col = 0
        elif not on and self._alternate is not None:
            self.lines, self.row, self.col = self._alternate
            self._alternate = None

    # -- size and text ---------------------------------------------------------------------
    def resize(self, rows: int, cols: int) -> None:
        rows, cols = max(1, rows), max(1, cols)
        if (rows, cols) == (self.rows, self.cols):
            return
        lines = [(line + [(" ", PLAIN)] * cols)[:cols] for line in self.lines]
        self.history = [(line + [(" ", PLAIN)] * cols)[:cols] for line in self.history]
        while len(lines) > rows:  # (the cursor stays on screen: lines above go first)
            if self.row > 0:
                self.history.append(lines.pop(0))
                self.row -= 1
            else:
                lines.pop()
        while len(lines) < rows:
            if self.history and self._alternate is None:
                lines.insert(0, self.history.pop())
                self.row += 1
            else:
                lines.append([(" ", PLAIN)] * cols)
        self.lines, self.rows, self.cols = lines, rows, cols
        self.top, self.bottom = 0, rows - 1
        self.row, self.col = min(self.row, rows - 1), min(self.col, cols - 1)
        self.wrap_pending = False
        self.changed = True

    def all_lines(self) -> list[list]:
        """The history, then the screen."""
        return self.history + self.lines

    @staticmethod
    def line_text(line) -> str:
        return "".join(char for char, _attr in line).rstrip()

    def text(self) -> str:
        """The screen as text (trailing spaces and empty lines at the end left out)."""
        return "\n".join(self.line_text(line) for line in self.lines).rstrip("\n")


# --- the program: in a pseudo-terminal (or pipes) -------------------------------------------

def default_shell() -> list[str]:
    """The user's shell: $SHELL (macOS, Linux), %COMSPEC% (Windows)."""
    if sys.platform == "win32":
        return [os.environ.get("COMSPEC", "cmd.exe")]
    return [os.environ.get("SHELL") or "/bin/sh"]


class _PtyProgram:
    """A program in a pseudo-terminal (macOS, Linux)."""

    def __init__(self, argv, cwd, rows, cols, on_data, on_exit):
        import fcntl
        import pty
        import subprocess
        import termios

        master, slave = pty.openpty()
        self._set_size(master, rows, cols)
        env = dict(os.environ, TERM=TERM, COLUMNS=str(cols), LINES=str(rows))

        def take_the_terminal():  # (in the child: the terminal is its controlling one)
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        try:
            self.process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                                            cwd=cwd or None, env=env, start_new_session=True,
                                            preexec_fn=take_the_terminal, close_fds=True)
        finally:
            os.close(slave)
        self.master = master
        self._on_data, self._on_exit = on_data, on_exit
        self._notifier = QSocketNotifier(master, QSocketNotifier.Read)
        self._notifier.activated.connect(self._read)
        self._done = False

    @staticmethod
    def _set_size(fd, rows, cols):
        import fcntl
        import struct
        import termios

        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def _read(self, *_):
        try:
            data = os.read(self.master, 65536)
        except OSError:
            data = b""
        if data:
            self._on_data(data)
            return
        self._finish()

    def _finish(self):
        if self._done:
            return
        self._done = True
        self._notifier.setEnabled(False)
        try:
            code = self.process.wait(timeout=5)
        except Exception:  # noqa: BLE001 - (it won't end: killed)
            self.process.kill()
            code = self.process.wait()
        os.close(self.master)
        self._on_exit(code if code >= 0 else -1)

    @property
    def pid(self) -> int:
        return self.process.pid

    def running(self) -> bool:
        return not self._done

    def write(self, data: bytes) -> None:
        if not self._done:
            os.write(self.master, data)

    def resize(self, rows, cols) -> None:
        if not self._done:
            self._set_size(self.master, rows, cols)

    def kill(self) -> None:
        if not self._done:
            import signal

            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                self.process.kill()


class _PipeProgram:
    """A program with pipes (Windows: no pseudo-terminal)."""

    def __init__(self, argv, cwd, rows, cols, on_data, on_exit):
        from PySide6.QtCore import QProcess, QProcessEnvironment

        process = QProcess()
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", TERM)
        process.setProcessEnvironment(env)
        if cwd:
            process.setWorkingDirectory(cwd)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda: on_data(bytes(process.readAllStandardOutput())))
        process.finished.connect(lambda code, status: on_exit(
            code if status == QProcess.NormalExit else -1))
        process.start(argv[0], argv[1:])
        if not process.waitForStarted(5000):
            raise OSError(process.errorString())
        self.process = process

    @property
    def pid(self) -> int:
        return int(self.process.processId())

    def running(self) -> bool:
        from PySide6.QtCore import QProcess

        return self.process.state() != QProcess.NotRunning

    def write(self, data: bytes) -> None:
        self.process.write(data)

    def resize(self, rows, cols) -> None:
        pass

    def kill(self) -> None:
        self.process.kill()


# --- the view -----------------------------------------------------------------------------

_KEYS = {Qt.Key_Return: "\r", Qt.Key_Enter: "\r", Qt.Key_Backspace: "\x7f", Qt.Key_Tab: "\t",
         Qt.Key_Escape: "\x1b", Qt.Key_Up: "\x1b[A", Qt.Key_Down: "\x1b[B",
         Qt.Key_Right: "\x1b[C", Qt.Key_Left: "\x1b[D", Qt.Key_Home: "\x1b[H",
         Qt.Key_End: "\x1b[F", Qt.Key_Delete: "\x1b[3~", Qt.Key_Insert: "\x1b[2~",
         Qt.Key_PageUp: "\x1b[5~", Qt.Key_PageDown: "\x1b[6~", Qt.Key_Backtab: "\x1b[Z"}
_FUNCTION_KEYS = {Qt.Key_F1: "\x1bOP", Qt.Key_F2: "\x1bOQ", Qt.Key_F3: "\x1bOR",
                  Qt.Key_F4: "\x1bOS", Qt.Key_F5: "\x1b[15~", Qt.Key_F6: "\x1b[17~",
                  Qt.Key_F7: "\x1b[18~", Qt.Key_F8: "\x1b[19~", Qt.Key_F9: "\x1b[20~",
                  Qt.Key_F10: "\x1b[21~", Qt.Key_F11: "\x1b[23~", Qt.Key_F12: "\x1b[24~"}
# The Control key: Qt calls it Meta on macOS (Ctrl there is Command)
_CONTROL = Qt.MetaModifier if sys.platform == "darwin" else Qt.ControlModifier


def key_text(key: int, modifiers, text: str) -> str:
    """What a terminal sends for a key ("" for none: e.g. a modifier alone)."""
    if modifiers & _CONTROL:
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key - Qt.Key_A + 1)
        special = {Qt.Key_BracketLeft: "\x1b", Qt.Key_Backslash: "\x1c",
                   Qt.Key_BracketRight: "\x1d", Qt.Key_Space: "\x00",
                   Qt.Key_At: "\x00"}.get(key)
        if special is not None:
            return special
    if key in _KEYS:
        return _KEYS[key]
    if key in _FUNCTION_KEYS:
        return _FUNCTION_KEYS[key]
    if modifiers & Qt.AltModifier and text and sys.platform != "darwin":
        return "\x1b" + text  # (Alt+key: ESC then the key, as terminals do)
    return text


def _copy_or_paste(event) -> str | None:
    """"copy", "paste" or None: the system's keys for them in a terminal."""
    modifiers = event.modifiers()
    if sys.platform == "darwin":
        if modifiers & Qt.ControlModifier and not modifiers & Qt.MetaModifier:  # Command
            return {Qt.Key_C: "copy", Qt.Key_V: "paste"}.get(event.key())
        return None
    if modifiers & Qt.ControlModifier and modifiers & Qt.ShiftModifier:
        return {Qt.Key_C: "copy", Qt.Key_V: "paste"}.get(event.key())
    if modifiers & Qt.ShiftModifier and event.key() == Qt.Key_Insert:
        return "paste"
    return None


class _TerminalView(QWidget):
    """The terminal's screen on the form: the cells, the cursor, a scroll bar."""

    def __init__(self, terminal: "Terminal", parent):
        super().__init__(parent)
        self._terminal = terminal
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setCursor(Qt.IBeamCursor)
        self.scroll = QScrollBar(Qt.Vertical, self)
        self.scroll.valueChanged.connect(lambda *_: self.update())
        self.selection = None  # ((line, col), (line, col)) in all_lines, or None
        self._anchor = None

    # (the Terminal's own keys: Tab doesn't move the focus)
    def focusNextPrevChild(self, forward):
        return False

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride:  # the program's, not the menus'
            if _copy_or_paste(event) is None and key_text(event.key(), event.modifiers(),
                                                          event.text()):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        action = _copy_or_paste(event)
        if action == "copy":
            self._terminal.Copy()
            return
        if action == "paste":
            self._terminal.Paste()
            return
        text = key_text(event.key(), event.modifiers(), event.text())
        if text:
            self.scroll.setValue(self.scroll.maximum())  # (typing: back to the bottom)
            self._terminal._send(text)

    def inputMethodEvent(self, event):
        if event.commitString():
            self._terminal._send(event.commitString())

    # -- the geometry of cells ---------------------------------------------------------------
    def cell_size(self) -> tuple[float, float]:
        metrics = QFontMetricsF(self.font())
        return metrics.horizontalAdvance("M"), metrics.lineSpacing()

    def grid_size(self) -> tuple[int, int]:
        width, height = self.cell_size()
        usable = self.width() - self.scroll.sizeHint().width() - 4
        return max(1, int((self.height() - 4) // height)), max(1, int(usable // width))

    def resizeEvent(self, event):
        bar = self.scroll.sizeHint().width()
        self.scroll.setGeometry(self.width() - bar, 0, bar, self.height())
        self._terminal._resize_screen()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._terminal._shown()

    def wheelEvent(self, event):
        lines = -event.angleDelta().y() // 40
        self.scroll.setValue(self.scroll.value() + lines)

    def _first_line(self) -> int:
        """The index (in all_lines) of the top line shown."""
        return self.scroll.value()

    def _cell_at(self, pos: QPoint) -> tuple[int, int]:
        width, height = self.cell_size()
        line = self._first_line() + int((pos.y() - 2) // height)
        return line, max(0, int((pos.x() - 2) // width))

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.LeftButton:
            self._anchor = self._cell_at(event.position().toPoint())
            self.selection = None
            self.update()
        elif event.button() == Qt.MiddleButton:
            self._terminal.Paste()

    def mouseMoveEvent(self, event):
        if self._anchor is not None and event.buttons() & Qt.LeftButton:
            here = self._cell_at(event.position().toPoint())
            self.selection = tuple(sorted((self._anchor, here)))
            self.update()

    def mouseReleaseEvent(self, event):
        self._anchor = None

    def mouseDoubleClickEvent(self, event):  # a word
        line, col = self._cell_at(event.position().toPoint())
        lines = self._terminal._screen.all_lines()
        if 0 <= line < len(lines):
            text = AnsiScreen.line_text(lines[line])
            for match in re.finditer(r"\S+", text):
                if match.start() <= col < match.end():
                    self.selection = ((line, match.start()), (line, match.end() - 1))
                    self.update()

    # -- painting ----------------------------------------------------------------------------
    def _color(self, value, default: QColor) -> QColor:
        if value is None:
            return default
        if isinstance(value, tuple):
            return QColor(*value)
        if value < 16:
            return QColor(ANSI_COLORS[value])
        if value < 232:  # the 6 x 6 x 6 cube
            value -= 16
            steps = (0, 95, 135, 175, 215, 255)
            return QColor(steps[value // 36], steps[value // 6 % 6], steps[value % 6])
        gray = 8 + (value - 232) * 10
        return QColor(gray, gray, gray)

    def paintEvent(self, event):
        terminal = self._terminal
        screen = terminal._screen
        painter = QPainter(self)
        back, fore = terminal._default_colors()
        painter.fillRect(self.rect(), back)
        width, height = self.cell_size()
        metrics = QFontMetricsF(self.font())
        lines = screen.all_lines()
        first = self._first_line()
        rows = int(self.height() // height) + 1
        selection = self.selection
        font = self.font()
        bold = QFont(font)
        bold.setBold(True)
        for index in range(first, min(len(lines), first + rows)):
            y = 2 + (index - first) * height
            line = lines[index]
            col = 0
            while col < len(line):  # runs of one look
                attr = line[col][1]
                end = col + 1
                while end < len(line) and line[end][1] == attr and \
                        self._selected(selection, index, end) == \
                        self._selected(selection, index, col):
                    end += 1
                text = "".join(char for char, _ in line[col:end])
                fg = self._color(attr.fg, fore)
                if attr.bold and isinstance(attr.fg, int) and attr.fg < 8:
                    fg = self._color(attr.fg + 8, fore)  # (bold: the bright color, as in VB's day)
                bg = self._color(attr.bg, back)
                if attr.inverse:
                    fg, bg = bg, fg
                if self._selected(selection, index, col):
                    bg = self.palette().color(QPalette.Highlight)
                    fg = self.palette().color(QPalette.HighlightedText)
                rect = QRect(round(2 + col * width), round(y), round((end - col) * width) + 1,
                             round(height) + 1)
                if bg != back:
                    painter.fillRect(rect, bg)
                if text.strip():
                    painter.setFont(bold if attr.bold else font)
                    painter.setPen(fg)
                    for offset, char in enumerate(text):  # (cell by cell: a fixed grid)
                        if char != " ":
                            painter.drawText(
                                QPoint(round(2 + (col + offset) * width),
                                       round(y + metrics.ascent())), char)
                    if attr.underline:
                        painter.drawLine(rect.left(), round(y + metrics.ascent() + 2),
                                         rect.right(), round(y + metrics.ascent() + 2))
                col = end
        # The cursor: a block (an outline when the terminal doesn't have the focus)
        cursor_line = len(screen.history) + screen.row
        if screen.cursor_visible and first <= cursor_line < first + rows:
            rect = QRect(round(2 + screen.col * width), round(2 + (cursor_line - first) * height),
                         round(width), round(height))
            if self.hasFocus():
                painter.fillRect(rect, QColor(fore.red(), fore.green(), fore.blue(), 160))
            else:
                painter.setPen(fore)
                painter.drawRect(rect.adjusted(0, 0, -1, -1))

    @staticmethod
    def _selected(selection, line: int, col: int) -> bool:
        if selection is None:
            return False
        (l1, c1), (l2, c2) = selection
        return (line, col) >= (l1, c1) and (line, col) <= (l2, c2)


def _terminal_design_widget(parent: QWidget) -> QLabel:
    """In the designer: a dark box with a prompt (it runs nothing there)."""
    label = QLabel("$ _", parent)
    label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    label.setMargin(6)
    label.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    label.setAutoFillBackground(True)
    palette = label.palette()
    palette.setColor(QPalette.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.WindowText, QColor("#cccccc"))
    label.setPalette(palette)
    return label


class Terminal(Control):
    """A terminal running a shell or another program (the module's
    documentation)."""

    TypeName = "Terminal"
    DefaultEvent = "Exited"
    DefaultSize = (480, 300)
    Events = ("Exited", "TitleChange", "GotFocus", "LostFocus")
    Properties = (
        *_geometry(*DefaultSize),
        P("CommandLine", "str", "",
          description="The program it runs: a command line (double quotes group words); "
                      "empty: your shell"),
        P("WorkingDirectory", "str", "",
          description="Where the program runs (relative to the form's folder); empty: here"),
        P("AutoStart", "bool", True,
          description="Start the program when the Terminal is first shown (else: Start)"),
        P("ScrollbackLines", "int", 1000, description="How many lines scrolled off it keeps"),
        P("BackColor", "color", None, description="Background color; unset: the scheme's"),
        P("ForeColor", "color", None, description="Text color; unset: the scheme's"),
        P("FontName", "font", None, description="Its font; unset: the system's fixed one"),
        P("FontSize", "int", None, description="Font size in points; unset: the system's"),
        *_COMMON,
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.update(_program=None, _screen=AnsiScreen(), _decoder=None,
                             _started=False, _exit_code=-1)
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        if self._design_mode:
            return _terminal_design_widget(parent)
        view = _TerminalView(self, parent)
        self.__dict__["_refresh"] = QTimer(view)  # (output arrives in pieces: drawn at most
        self._refresh.setSingleShot(True)         # every 15 ms)
        self._refresh.setInterval(15)
        self._refresh.timeout.connect(self._redraw)
        return view

    def _on_key_press(self, watched, event) -> bool:
        return False  # (its keys are the program's, Enter and Esc too: not the form's)

    def _event_targets(self):
        return [self._widget]

    # -- look --------------------------------------------------------------------------------
    def _default_colors(self) -> tuple[QColor, QColor]:
        view = self._widget
        back, fore = self._values.get("BackColor"), self._values.get("ForeColor")
        return (colors.to_qcolor(back) if back is not None else
                view.palette().color(QPalette.Base),
                colors.to_qcolor(fore) if fore is not None else
                view.palette().color(QPalette.Text))

    def _apply_font(self, _=None):
        if self._widget is None:
            return
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if self._values.get("FontName"):
            font.setFamily(self._values["FontName"])
        if self._values.get("FontSize"):
            font.setPointSize(int(self._values["FontSize"]))
        self._widget.setFont(font)
        if not self._design_mode:
            self._resize_screen()

    _apply_FontName = _apply_FontSize = _apply_font

    def _apply_colors(self, _=None):
        if self._widget is not None:
            self._widget.update()

    _apply_BackColor = _apply_ForeColor = _apply_colors

    def _apply_ScrollbackLines(self, v):
        self._screen.scrollback = max(0, int(v))

    # -- what it shows -------------------------------------------------------------------------
    @property
    def Text(self) -> str:
        """The screen's text (not the history)."""
        return self._screen.text()

    @property
    def Title(self) -> str:
        """The title the program gave the terminal (an OSC sequence)."""
        return self._screen.title

    @property
    def Rows(self) -> int:
        return self._screen.rows

    @property
    def Columns(self) -> int:
        return self._screen.cols

    @property
    def Running(self) -> bool:
        return self._program is not None and self._program.running()

    @property
    def ProcessID(self) -> int:
        return self._program.pid if self.Running else 0

    @property
    def ExitCode(self) -> int:
        """The program's exit code once it has ended (-1 before, or killed)."""
        return self._exit_code

    # -- running the program -------------------------------------------------------------------
    def _shown(self) -> None:
        if not self._started and self._values.get("AutoStart", True):
            self.Start()

    def Start(self, CommandLine=None) -> None:
        """Start the program: CommandLine (which it keeps), else the CommandLine
        property, else your shell. Raises RuntimeError while one runs, OSError
        when it can't be started."""
        if self.Running:
            raise RuntimeError(f"Terminal '{self.Name}' is already running a program")
        from .process import split_command

        if CommandLine is not None:
            self._values["CommandLine"] = str(CommandLine) if isinstance(CommandLine, str) \
                else " ".join(split_command(CommandLine))
        argv = split_command(CommandLine if CommandLine is not None else
                             self._values.get("CommandLine", "")) or default_shell()
        folder = self._values.get("WorkingDirectory", "")
        cwd = resolve_path(self._form, folder) if folder else None
        self._resize_screen()
        rows, cols = self._screen.rows, self._screen.cols
        backend = _PipeProgram if sys.platform == "win32" else _PtyProgram
        self.__dict__.update(_decoder=codecs.getincrementaldecoder("utf-8")(errors="replace"),
                             _started=True, _exit_code=-1)
        self.__dict__["_program"] = backend(argv, cwd, rows, cols, self._on_data,
                                            self._on_exit)

    def _on_data(self, data: bytes) -> None:
        title = self._screen.title
        self._screen.feed(self._decoder.decode(data))
        if not self._refresh.isActive():
            self._refresh.start()
        if self._screen.title != title:
            self._fire("TitleChange", self._screen.title)

    def _on_exit(self, code: int) -> None:
        rest = self._decoder.decode(b"", final=True) if self._decoder else ""
        if rest:
            self._screen.feed(rest)
        self.__dict__["_exit_code"] = code
        self._redraw()
        self._fire("Exited", code)

    def _redraw(self) -> None:
        view = self._widget
        if view is None:
            return
        bar = view.scroll
        at_bottom = bar.value() >= bar.maximum()
        bar.setRange(0, len(self._screen.history))
        bar.setPageStep(self._screen.rows)
        if at_bottom:
            bar.setValue(bar.maximum())
        view.update()

    def _resize_screen(self) -> None:
        view = self._widget
        if view is None or self._design_mode:
            return
        rows, cols = view.grid_size()
        if (rows, cols) != (self._screen.rows, self._screen.cols):
            self._screen.resize(rows, cols)
            if self.Running:
                self._program.resize(rows, cols)
        self._redraw()

    def _send(self, text: str) -> None:
        if self.Running:
            self._program.write(text.encode("utf-8"))

    def Write(self, Text) -> None:
        """Send text to the program, as if typed ("\\r" for Enter)."""
        if not self.Running:
            raise RuntimeError(f"Terminal '{self.Name}' isn't running a program")
        self._send(str(Text))

    def Kill(self) -> None:
        """End the program at once."""
        if self.Running:
            self._program.kill()

    def Clear(self) -> None:
        """Clear the screen and its history (the program may draw again)."""
        screen = self._screen
        screen.history = []
        screen.lines = [screen._blank() for _ in range(screen.rows)]
        screen.row = screen.col = 0
        self._redraw()

    def Copy(self) -> None:
        """Copy the selected text to the clipboard."""
        view = self._widget
        if view is None or view.selection is None:
            return
        (l1, c1), (l2, c2) = view.selection
        lines = self._screen.all_lines()
        parts = []
        for index in range(l1, min(l2, len(lines) - 1) + 1):
            text = "".join(char for char, _ in lines[index])
            start = c1 if index == l1 else 0
            end = c2 + 1 if index == l2 else len(text)
            parts.append(text[start:end].rstrip())
        QGuiApplication.clipboard().setText("\n".join(parts))

    def Paste(self) -> None:
        """Send the clipboard's text to the program."""
        text = QGuiApplication.clipboard().text()
        if text:
            self._send(text.replace("\r\n", "\r").replace("\n", "\r"))

    def SetFocus(self) -> None:
        if self._widget is not None:
            self._widget.setFocus()

    def _form_unloaded(self) -> None:
        if self.Running:
            self.Kill()


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["Terminal"] = Terminal
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
