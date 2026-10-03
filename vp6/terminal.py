"""The ``Terminal`` control: a shell (or another program) in a terminal on the
form, as an xterm (``TERM=xterm-256color``, the default), xterm, vt100, vt102,
vt220 or ansi terminal (``TerminalType``).

``AnsiScreen`` is the terminal itself, in plain Python: ``feed(text)`` applies
what the program writes (printable characters, CR, LF, BS, TAB, BEL, SO and
SI, 8-bit C1 controls for the vt220 and xterms, and the escape sequences:
cursor movement and positioning, erasing in the display and the line,
inserting and deleting lines and characters, repeating one, a scroll region,
origin mode, autowrap, insert mode, new line mode, tab stops, saving the
cursor, colors and attributes with SGR (true color too: the xterm types
announce it in COLORTERM and terminfo answers), the cursor shown, hidden or shaped,
reverse video, the alternate screen, character sets (the DEC line drawing
set), the window title by OSC, keypad and cursor key modes, mouse reporting,
focus reporting, bracketed paste, a soft and a full reset) to a grid of
``rows`` x ``cols`` cells, with ``history``: the lines scrolled off the top,
up to ``scrollback``. ``text()`` is the screen as text. What the terminal
answers the program (Device Attributes as its ``term``, the cursor's
position, its size, modes, settings, colors) collects in ``replies``.

``Terminal`` runs its program in a pseudo-terminal on macOS and Linux (the
program sees a terminal: a shell is interactive, Ctrl+C interrupts, the size
follows the control's), with pipes on Windows (no pseudo-terminal there).
Keys go to the program as its terminal type sends them (arrows, Home, End,
Delete, function keys, the keypad, Ctrl+letter, xterm's Shift/Alt/Ctrl
modifiers...); copy and paste are the system's (Cmd+C / Cmd+V on macOS,
Ctrl+Shift+C / Ctrl+Shift+V elsewhere); the mouse selects (or goes to the
program when it asked for it: Shift+mouse still selects); the scroll bar and
the wheel go through the history. With ``Ligatures``, text is drawn a run at
a time where the font keeps it in its cells, so a font's ligatures show.
"""

from __future__ import annotations

import codecs
import os
import re
import sys
from dataclasses import dataclass, replace

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSocketNotifier, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication,
                           QPainter, QPalette)
from PySide6.QtWidgets import QLabel, QScrollBar, QWidget

from . import colors
from ._props import P, enum_choices
from .controls import _COMMON, CONTROL_TYPES, EVENT_ARGS, Control, _geometry, resolve_path
from .termgraphics import MAX_SIDE, SIXEL_REGISTERS, UNDER_BACKGROUNDS, TerminalGraphics

EVENT_ARGS.update({"Exited": "ExitCode", "TitleChange": "Title"})

# The terminal types (TerminalType: vpTermXterm256Color...), as TERM names them
TERMINAL_TYPES = ("xterm-256color", "xterm", "vt100", "vt102", "vt220", "ansi")
TERM = TERMINAL_TYPES[0]  # what the Terminal tells the programs it runs it is, by default
_XTERMS = ("xterm-256color", "xterm")
_EIGHT_BIT = ("xterm-256color", "xterm", "vt220")  # (8-bit C1 controls: CSI as one character)

# Device Attributes: what each terminal says it is (CSI c)
_DEVICE_ATTRIBUTES = {"xterm-256color": "\x1b[?62;1;2;4;6;7;8;9;22c",  # (4: sixel)
                      "xterm": "\x1b[?62;1;2;4;6;7;8;9;22c", "vt100": "\x1b[?1;2c",
                      "vt102": "\x1b[?6c", "vt220": "\x1b[?62;1;2;6;7;8;9c",
                      "ansi": "\x1b[?1;2c"}

# The 16 ANSI colors (normal, then bright), as most terminals show them
ANSI_COLORS = ("#000000", "#cd3131", "#0dbc79", "#e5e510", "#2472c8", "#bc3fbc", "#11a8cd",
               "#e5e5e5", "#666666", "#f14c4c", "#23d18b", "#f5f543", "#3b8eea", "#d670d6",
               "#29b8db", "#ffffff")

# The DEC Special Graphics character set (ESC ( 0): lines and boxes
DEC_GRAPHICS = dict(zip("`abcdefghijklmnopqrstuvwxyz{|}~_",
                        "◆▒␉␌␍␊°±␤␋┘┐┌└┼⎺⎻─⎼⎽├┤┴┬│≤≥π≠£· ", strict=True))
_CHARSETS = {"0": DEC_GRAPHICS, "A": {"#": "£"}}  # (the others: ASCII)

# The private modes it knows (DECRQM answers for these): cursor keys, 132 columns,
# reverse video, origin, autowrap, blinking, the cursor shown, sixel display mode, the
# alternate screen, the keypad, the mouse, focus, SGR mouse coordinates, private sixel
# color registers, bracketed paste, the cursor to the right of a sixel picture
_KNOWN_MODES = {1, 3, 5, 6, 7, 9, 12, 25, 47, 66, 80, 1000, 1002, 1003, 1004, 1006, 1047,
                1048, 1049, 1070, 2004, 8452}
_MOUSE_MODES = (9, 1000, 1002, 1003)  # (X10: presses; presses and releases; with a
                                      # button held, moves too; all moves)
_CURSOR_SHAPES = {0: "block", 1: "block", 2: "block", 3: "underline", 4: "underline",
                  5: "bar", 6: "bar"}
# What ends a string (OSC, DCS, APC...): ST (ESC \\, or C1's), BEL; CAN and SUB cancel it
_STRING_STOP = re.compile("[\x07\x18\x1a\x1b\x9c]")
_STRINGS = {"]": "osc", "P": "dcs", "_": "apc"}  # (and "string": SOS, PM)
_STRING_STATES = ("osc", "dcs", "apc", "string")
_SIXEL_START = re.compile(r"([0-9;]*)q")  # (a DCS string's parameters, then q: sixel data)
# True color (24-bit RGB, SGR 38;2;r;g;b and 48;2;r;g;b): the xterm types say they have it,
# in COLORTERM and in the terminfo capabilities they answer (XTGETTCAP): RGB (ncurses'),
# Tc (tmux's), setrgbf and setrgbb (how to set them)
COLORTERM = "truecolor"
_TRUE_COLOR_CAPABILITIES = {"RGB": "8/8/8", "Tc": None,
                            "setrgbf": "\x1b[38;2;%p1%d;%p2%d;%p3%dm",
                            "setrgbb": "\x1b[48;2;%p1%d;%p2%d;%p3%dm"}


def color_rgb(index: int) -> tuple[int, int, int]:
    """A color of the 256 (16 ANSI ones, a 6 x 6 x 6 cube, 24 grays) as (r, g, b)."""
    if index < 16:
        color = QColor(ANSI_COLORS[index])
        return color.red(), color.green(), color.blue()
    if index < 232:  # the 6 x 6 x 6 cube
        index -= 16
        steps = (0, 95, 135, 175, 215, 255)
        return steps[index // 36], steps[index // 6 % 6], steps[index % 6]
    gray = 8 + (index - 232) * 10
    return gray, gray, gray


def _xcolor(rgb) -> str:
    """An X color specification (OSC answers): rgb:rrrr/gggg/bbbb."""
    return "rgb:" + "/".join(f"{value:02x}{value:02x}" for value in rgb)


@dataclass(frozen=True)
class Attr:
    """How a cell's character looks: colors (None: the default; 0..255 an
    index; an (r, g, b) tuple), bold, dim, italic, underline, blink (shown
    steady), inverse, invisible, strikethrough."""
    fg: object = None
    bg: object = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    blink: bool = False
    inverse: bool = False
    invisible: bool = False
    strike: bool = False


PLAIN = Attr()

# SGR numbers that turn an attribute on or off
_SGR_FLAGS = {1: {"bold": True}, 2: {"dim": True}, 3: {"italic": True}, 4: {"underline": True},
              5: {"blink": True}, 6: {"blink": True}, 7: {"inverse": True},
              8: {"invisible": True}, 9: {"strike": True}, 21: {"underline": True},
              22: {"bold": False, "dim": False}, 23: {"italic": False},
              24: {"underline": False}, 25: {"blink": False}, 27: {"inverse": False},
              28: {"invisible": False}, 29: {"strike": False}}


class AnsiScreen:
    """A terminal's screen: the module's documentation."""

    def __init__(self, rows: int = 24, cols: int = 80, scrollback: int = 1000,
                 term: str = TERM):
        self.rows, self.cols = max(1, rows), max(1, cols)
        self.scrollback = max(0, scrollback)
        self.term = term
        self.history: list[list] = []
        self.replies: list[str] = []  # (what it answers the program: the Terminal sends them)
        self.colors = None  # () -> ((r, g, b), (r, g, b)): the default fore and back colors
        self.scrolled = 0  # (lines gone into the history, ever: pictures are placed on lines
        self.cell_pixels = (10, 20)  # counted from the first) a cell's size in device pixels
        self.pixel_ratio = 1.0  # (device pixels to points: iTerm2's ReportCellSize)
        self.graphics = TerminalGraphics(self)  # (pictures: Kitty's, iTerm2's, sixel)
        self._reset()

    def _reset(self) -> None:
        """The power-on state (but the history and the replies stay)."""
        self.lines = [self._blank() for _ in range(self.rows)]
        self.row = self.col = 0
        self.attr = PLAIN
        self.top, self.bottom = 0, self.rows - 1  # the scroll region
        self.wrap_pending = False
        self.modes = {7, 25, 1070}  # the private modes on (CSI ? n h): autowrap, the
                                    # cursor shown, private sixel color registers
        self.ansi_modes: set[int] = set()  # 4: insert, 20: new line (CSI n h)
        self.keypad_app = False  # (ESC =: the keypad sends its own keys)
        self.charsets = ["B"] * 4  # G0..G3 ("B": ASCII, "0": DEC line drawing)
        self.gl = 0  # the one in use (SO: G1, SI: G0)
        self._single_shift = None
        self.tabs = set(range(8, self.cols, 8))
        self.cursor_style = 1  # (DECSCUSR: 1, 2 block, 3, 4 underline, 5, 6 bar)
        self.title = ""
        self._titles: list[str] = []
        self._alternate = None  # the main screen while the alternate one shows
        self._main_graphics = None  # (and its pictures)
        self.sixel_colors = None  # (sixel color registers shared while mode 1070 is reset)
        self.graphics.reset()
        self._saved_modes: dict[int, bool] = {}
        self.saved = self._cursor_state()
        self._last = None  # the last character written (REP repeats it)
        self._state = "text"
        self._sequence = ""
        self._parts: list[str] = []  # (a string's text so far)
        self.changed = True

    def _blank(self) -> list:
        return [(" ", PLAIN)] * self.cols

    @property
    def cursor_visible(self) -> bool:
        return 25 in self.modes

    @property
    def cursor_shape(self) -> str:
        """"block", "underline" or "bar"."""
        return _CURSOR_SHAPES.get(self.cursor_style, "block")

    @property
    def mouse_mode(self) -> int:
        """The mouse events the program asked for: 0 (none), 9, 1000, 1002 or 1003."""
        return next((mode for mode in _MOUSE_MODES if mode in self.modes), 0)

    def _reply(self, text: str) -> None:
        self.replies.append(text)

    # -- what the program writes -----------------------------------------------------------
    def feed(self, text: str) -> None:
        self.changed = True
        index, length = 0, len(text)
        while index < length:
            state = self._state
            if state in _STRING_STATES and not self._sequence.endswith("\x1b"):
                stop = _STRING_STOP.search(text, index)  # (pictures: long strings, in bulk)
                end = stop.start() if stop else length
                if end > index:
                    self._parts.append(text[index:end])
                    index = end
                    continue
            char = text[index]
            index += 1
            if state == "text":
                self._text_char(char)
            elif state == "esc":
                self._escape(char)
            elif state == "esc+":  # ESC, an intermediate character, then the final one
                self._state = "text"
                self._escape_final(self._sequence, char)
            elif state == "csi":
                if "\x40" <= char <= "\x7e":
                    self._state = "text"
                    self._csi(self._sequence, char)
                elif char == "\x1b":
                    self._state = "esc"  # (a new sequence cancels it)
                elif char in "\x18\x1a":
                    self._state = "text"
                elif char < " ":
                    self._text_char(char)  # (controls act in the middle of one)
                else:
                    self._sequence += char
            else:  # "osc", "dcs", "apc", "string" (SOS, PM: ignored): up to ST (OSC: or BEL)
                if self._sequence.endswith("\x1b"):
                    self._sequence = ""
                    if char == "\\":
                        self._string_end(state)
                    else:  # (ESC and something else: a new sequence instead)
                        self._state = "esc"
                        self._escape(char)
                elif (char == "\x07" and state == "osc") or char == "\x9c":
                    self._string_end(state)
                elif char in "\x18\x1a":
                    self._state = "text"
                elif char == "\x1b":
                    self._sequence = char  # (ESC: the end, or a new sequence)
                else:
                    self._parts.append(char)

    def _string_end(self, state: str) -> None:
        self._state = "text"
        text, self._parts = "".join(self._parts), []
        if state == "osc":
            self._osc(text)
        elif state == "dcs":
            self._dcs(text)
        elif state == "apc" and self.term in _XTERMS:
            self.graphics.kitty(text)

    def _text_char(self, char: str) -> None:
        if char == "\x1b":
            self._state = "esc"
        elif "\x80" <= char <= "\x9f":  # a C1 control: ESC and a character
            if self.term in _EIGHT_BIT:
                self._escape(chr(ord(char) - 0x40))
        elif char == "\r":
            self.col = 0
            self.wrap_pending = False
        elif char in "\n\x0b\x0c":
            self._line_feed()
            if 20 in self.ansi_modes:  # (new line mode: and back to the start)
                self.col = 0
        elif char == "\b":
            self.col = max(0, self.col - 1)
            self.wrap_pending = False
        elif char == "\t":
            self._tab(1)
        elif char == "\x0e":  # SO: the G1 character set
            self.gl = 1
        elif char == "\x0f":  # SI: G0 again
            self.gl = 0
        elif char < " " or char == "\x7f":
            pass  # (BEL and other controls: nothing to show)
        else:
            self._put(char)

    def _put(self, char: str) -> None:
        shift = self._single_shift
        self._single_shift = None
        table = _CHARSETS.get(self.charsets[self.gl if shift is None else shift])
        if table:
            char = table.get(char, char)
        if self.wrap_pending:
            self.col = 0
            self._line_feed()
        line = self.lines[self.row]
        if 4 in self.ansi_modes:  # insert mode: the rest of the line moves right
            line.insert(self.col, (char, self.attr))
            line.pop()
        else:
            line[self.col] = (char, self.attr)
        self._last = char
        if self.col == self.cols - 1:
            self.wrap_pending = 7 in self.modes  # (the next character goes on the next line)
        else:
            self.col += 1

    def _line_feed(self) -> None:
        self.wrap_pending = False
        if self.row == self.bottom:
            self._scroll_up(1)
        elif self.row < self.rows - 1:
            self.row += 1

    def _tab(self, count: int) -> None:
        for _ in range(count):
            self.col = min((stop for stop in self.tabs if stop > self.col),
                           default=self.cols - 1)

    def _back_tab(self, count: int) -> None:
        for _ in range(count):
            self.col = max((stop for stop in self.tabs if stop < self.col), default=0)

    def _scroll_up(self, count: int) -> None:
        for _ in range(count):
            gone = self.lines.pop(self.top)
            into_history = self.top == 0 and self._alternate is None
            self.graphics.scrolled(self.top, self.bottom, -1, into_history)
            if into_history:
                self.history.append(gone)
                self.scrolled += 1
                if len(self.history) > self.scrollback:
                    del self.history[:len(self.history) - self.scrollback]
                    self.graphics.prune()
            self.lines.insert(self.bottom, self._blank())

    def _scroll_down(self, count: int) -> None:
        for _ in range(count):
            del self.lines[self.bottom]
            self.lines.insert(self.top, self._blank())
            self.graphics.scrolled(self.top, self.bottom, 1, False)

    def _goto(self, row: int, col: int) -> None:
        """To a row (from the scroll region's top in origin mode) and column."""
        if 6 in self.modes:
            self.row = max(self.top, min(self.bottom, self.top + row))
        else:
            self.row = max(0, min(self.rows - 1, row))
        self.col = max(0, min(self.cols - 1, col))
        self.wrap_pending = False

    def _cursor_state(self) -> tuple:
        """What DECSC saves: the position, attributes, character sets, origin mode."""
        return (self.row, self.col, self.attr, tuple(self.charsets), self.gl,
                6 in self.modes, self.wrap_pending)

    def _restore_cursor(self, state: tuple) -> None:
        row, col, self.attr, charsets, self.gl, origin, self.wrap_pending = state
        self.row, self.col = min(row, self.rows - 1), min(col, self.cols - 1)
        self.charsets = list(charsets)
        (self.modes.add if origin else self.modes.discard)(6)

    def _escape(self, char: str) -> None:
        self._state = "text"
        if char == "[":
            self._state, self._sequence = "csi", ""
        elif char in "]P_":  # OSC, DCS, APC (the Kitty graphics protocol)
            self._state, self._sequence, self._parts = _STRINGS[char], "", []
        elif char in "X^":  # SOS, PM: strings it ignores
            self._state, self._sequence, self._parts = "string", "", []
        elif char in " #%()*+-./":
            self._state, self._sequence = "esc+", char
        elif char == "7":
            self.saved = self._cursor_state()
        elif char == "8":
            self._restore_cursor(self.saved)
        elif char == "D":  # index
            self._line_feed()
        elif char == "E":  # next line
            self.col = 0
            self._line_feed()
        elif char == "M":  # reverse index
            self.wrap_pending = False
            if self.row == self.top:
                self._scroll_down(1)
            else:
                self.row = max(0, self.row - 1)
        elif char == "H":  # a tab stop here
            self.tabs.add(self.col)
        elif char in "=>":  # the keypad: application keys, or numbers
            self.keypad_app = char == "="
        elif char in "NO":  # the next character from G2 or G3
            self._single_shift = 2 if char == "N" else 3
        elif char in "no":  # G2 or G3 from now on
            self.gl = 2 if char == "n" else 3
        elif char == "c":  # reset
            self._reset()

    def _escape_final(self, intermediate: str, char: str) -> None:
        if intermediate in "()*+-./":  # a character set for G0..G3
            self.charsets[{"(": 0, ")": 1, "*": 2, "+": 3, "-": 1, ".": 2,
                           "/": 3}[intermediate]] = char
        elif intermediate == "#" and char == "8":  # the screen alignment test: all E's
            self.lines = [[("E", PLAIN)] * self.cols for _ in range(self.rows)]
            self.top, self.bottom = 0, self.rows - 1
            self._goto(0, 0)

    def _osc(self, text: str) -> None:
        number, _, value = text.partition(";")
        if number in ("0", "2"):
            self.title = value
        elif number == "1337" and self.term in _XTERMS:  # iTerm2's: inline images
            self.graphics.iterm2(value)
        elif number in ("10", "11") and value == "?" and self.colors is not None:
            rgb = self.colors()[int(number) - 10]
            self._reply(f"\x1b]{number};{_xcolor(rgb)}\x1b\\")
        elif number == "4":  # (questions about the palette: 4;index;?)
            fields = value.split(";")
            for index, spec in zip(fields[::2], fields[1::2]):
                if spec == "?" and index.isdigit() and int(index) < 256:
                    self._reply(f"\x1b]4;{index};{_xcolor(color_rgb(int(index)))}\x1b\\")

    def _dcs(self, text: str) -> None:
        if self.term not in _XTERMS:
            return
        sixel = _SIXEL_START.match(text)
        if sixel:  # a sixel picture
            self.graphics.sixel(sixel.group(1), text[sixel.end():])
        elif text.startswith("$q"):  # DECRQSS: a setting
            setting = {"m": lambda: self._sgr_text() + "m",
                       "r": lambda: f"{self.top + 1};{self.bottom + 1}r",
                       " q": lambda: f"{self.cursor_style} q"}.get(text[2:])
            self._reply(f"\x1bP1$r{setting()}\x1b\\" if setting else "\x1bP0$r\x1b\\")
        elif text.startswith("+q"):  # XTGETTCAP: terminfo capabilities
            for name in text[2:].split(";"):
                try:
                    capability = bytes.fromhex(name).decode("ascii")
                except ValueError:
                    capability = ""
                known = {"TN": self.term, "name": self.term,
                         "Co": str(self._color_count()),
                         "colors": str(self._color_count()), **_TRUE_COLOR_CAPABILITIES}
                if capability not in known:
                    self._reply(f"\x1bP0+r{name}\x1b\\")
                elif known[capability] is None:  # (a flag: no value)
                    self._reply(f"\x1bP1+r{name}\x1b\\")
                else:
                    self._reply(f"\x1bP1+r{name}={known[capability].encode().hex()}\x1b\\")

    def _color_count(self) -> int:
        return 256 if self.term == "xterm-256color" else 8

    def _sgr_text(self) -> str:
        """The current attributes as SGR numbers (DECRQSS)."""
        attr = self.attr
        parts = ["0"] + [str(number) for number, flag in
                         ((1, attr.bold), (2, attr.dim), (3, attr.italic), (4, attr.underline),
                          (5, attr.blink), (7, attr.inverse), (8, attr.invisible),
                          (9, attr.strike)) if flag]
        for color, base, bright in ((attr.fg, 30, 90), (attr.bg, 40, 100)):
            if isinstance(color, tuple):
                parts.append(f"{base + 8};2;{color[0]};{color[1]};{color[2]}")
            elif color is not None:
                parts.append(str(base + color) if color < 8 else
                             str(bright + color - 8) if color < 16 else
                             f"{base + 8};5;{color}")
        return ";".join(parts)

    def _csi(self, params: str, final: str) -> None:
        prefix = params[:1] if params[:1] in ("<", "=", ">", "?") else ""
        body = params[len(prefix):]
        intermediate = ""
        while body and " " <= body[-1] <= "/":
            body, intermediate = body[:-1], body[-1] + intermediate
        fields = body.split(";") if body else []
        numbers = [int(field) if field.isdigit() else 0 for field in fields]

        def arg(index=0, default=1):
            value = numbers[index] if index < len(numbers) else 0
            return value or default

        if final not in "mnchlqtpxsu":  # (moving the cursor: no wrap to the next line)
            self.wrap_pending = False
        if intermediate:
            if intermediate == "!" and final == "p":
                self._soft_reset()
            elif intermediate == " " and final == "q":  # the cursor's shape
                self.cursor_style = arg(0, 1) if arg(0, 1) in _CURSOR_SHAPES else 1
            elif intermediate == "$" and final == "p" and self.term in _XTERMS:
                self._report_mode(arg(0, 0), prefix == "?")
            return
        if prefix == ">":
            if final == "c" and self.term in _EIGHT_BIT:  # Secondary Device Attributes
                self._reply("\x1b[>1;10;0c")
            elif final == "q" and self.term in _XTERMS:  # its name and version
                from . import __version__

                self._reply(f"\x1bP>|VP6 {__version__}\x1b\\")
            return
        if prefix in ("<", "="):
            return
        if prefix == "?":
            if final in "hl":
                self._set_modes(numbers, final == "h")
            elif final == "s":
                self._saved_modes.update({number: number in self.modes for number in numbers})
            elif final == "r":
                for number in numbers:
                    if number in self._saved_modes:
                        self._set_modes([number], self._saved_modes[number])
            elif final == "n" and arg(0, 0) == 6 and self.term != "ansi":
                self._reply(f"\x1b[?{self._report_row()};{self.col + 1}R")
            elif final == "S" and self.term in _XTERMS:  # XTSMGRAPHICS
                self._graphics_attribute(arg(0, 0), arg(1, 0))
            if final not in "JK":  # (selective erasing: as erasing)
                return
        if final == "A":
            self.row = max(self.top if self.row >= self.top else 0, self.row - arg())
        elif final in "Be":
            self.row = min(self.bottom if self.row <= self.bottom else self.rows - 1,
                           self.row + arg())
        elif final in "Ca":
            self.col = min(self.cols - 1, self.col + arg())
        elif final == "D":
            self.col = max(0, self.col - arg())
        elif final == "E":
            self.row, self.col = min(self.rows - 1, self.row + arg()), 0
        elif final == "F":
            self.row, self.col = max(0, self.row - arg()), 0
        elif final in "G`":
            self.col = min(self.cols - 1, arg() - 1)
        elif final == "d":
            self._goto(arg() - 1, self.col)
        elif final in "Hf":
            self._goto(arg(0) - 1, arg(1) - 1)
        elif final == "J":
            self._erase_display(arg(0, 0))
        elif final == "K":
            self._erase_line(arg(0, 0))
        elif final == "L":
            if self.top <= self.row <= self.bottom:
                for _ in range(min(arg(), self.bottom - self.row + 1)):
                    del self.lines[self.bottom]
                    self.lines.insert(self.row, self._blank())
                    self.graphics.scrolled(self.row, self.bottom, 1, False)
        elif final == "M":
            if self.top <= self.row <= self.bottom:
                for _ in range(min(arg(), self.bottom - self.row + 1)):
                    del self.lines[self.row]
                    self.lines.insert(self.bottom, self._blank())
                    self.graphics.scrolled(self.row, self.bottom, -1, False)
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
        elif final == "b":  # repeat the last character
            if self._last is not None:
                for _ in range(min(arg(), self.rows * self.cols)):
                    self._put(self._last)
        elif final == "S":
            self._scroll_up(arg())
        elif final == "T":
            self._scroll_down(arg())
        elif final == "I":
            self._tab(arg())
        elif final == "Z":
            self._back_tab(arg())
        elif final == "g":  # clear a tab stop: here (0), or all of them (3)
            if arg(0, 0) == 0:
                self.tabs.discard(self.col)
            elif arg(0, 0) == 3:
                self.tabs.clear()
        elif final == "r":
            top, bottom = arg(0, 1) - 1, arg(1, self.rows) - 1
            if 0 <= top < bottom < self.rows:
                self.top, self.bottom = top, bottom
                self._goto(0, 0)
        elif final == "s":
            self.saved = self._cursor_state()
        elif final == "u":
            self._restore_cursor(self.saved)
        elif final == "m":
            self._sgr(fields or ["0"])
        elif final in "hl":  # ANSI modes: 4 insert, 20 new line
            for number in numbers:
                (self.ansi_modes.add if final == "h" else self.ansi_modes.discard)(number)
        elif final == "c" and arg(0, 0) == 0:  # Device Attributes: what it is
            self._reply(_DEVICE_ATTRIBUTES.get(self.term, _DEVICE_ATTRIBUTES[TERM]))
        elif final == "n":  # Device Status Report: fine (5), where the cursor is (6)
            if arg(0, 0) == 5:
                self._reply("\x1b[0n")
            elif arg(0, 0) == 6:
                self._reply(f"\x1b[{self._report_row()};{self.col + 1}R")
        elif final == "x" and arg(0, 0) in (0, 1):  # the vt100's terminal parameters
            self._reply(f"\x1b[{arg(0, 0) + 2};1;1;112;112;1;0x")
        elif final == "t" and self.term in _XTERMS:  # xterm's window operations
            operation = arg(0, 0)
            if operation == 18:  # its size in characters
                self._reply(f"\x1b[8;{self.rows};{self.cols}t")
            elif operation in (14, 16):  # in pixels: the text area's, a cell's
                width, height = self.cell_pixels
                if operation == 14:
                    width, height = width * self.cols, height * self.rows
                self._reply(f"\x1b[{operation - 10};{height};{width}t")
            elif operation == 22:  # keep the title
                self._titles = (self._titles + [self.title])[-10:]
            elif operation == 23 and self._titles:  # the title kept
                self.title = self._titles.pop()

    def _graphics_attribute(self, item: int, action: int) -> None:
        """XTSMGRAPHICS: the sixel color registers (1) and the largest sixel
        picture (2), read (1), reset (2), set (3: they stay) or their most (4);
        ReGIS (3) isn't there."""
        if item == 1 and action in (1, 2, 3, 4):
            self._reply(f"\x1b[?1;0;{SIXEL_REGISTERS}S")
        elif item == 2 and action in (1, 2, 3, 4):
            width, height = (self.cell_pixels[0] * self.cols, self.cell_pixels[1] * self.rows) \
                if action != 4 else (MAX_SIDE, MAX_SIDE)  # (the screen's size, or the most)
            self._reply(f"\x1b[?2;0;{min(MAX_SIDE, width)};{min(MAX_SIDE, height)}S")
        else:
            self._reply(f"\x1b[?{item};{1 if item not in (1, 2) else 2};0S")

    def _report_row(self) -> int:
        return self.row - (self.top if 6 in self.modes else 0) + 1

    def _set_modes(self, numbers: list[int], on: bool) -> None:
        for number in numbers:
            if number in (47, 1047, 1049):
                if number == 1049 and on:
                    self.saved = self._cursor_state()
                self._alternate_screen(on)
                if number == 1049 and not on:
                    self._restore_cursor(self.saved)
                continue
            if number == 1048:  # save or restore the cursor
                if on:
                    self.saved = self._cursor_state()
                else:
                    self._restore_cursor(self.saved)
                continue
            if on and number in _MOUSE_MODES:  # (one way of reporting the mouse at a time)
                self.modes.difference_update(_MOUSE_MODES)
            (self.modes.add if on else self.modes.discard)(number)
            if number == 6:  # origin mode: the cursor home
                self._goto(0, 0)
            elif number == 3:  # 132 or 80 columns: the screen cleared (the size stays)
                self.lines = [self._blank() for _ in range(self.rows)]
                self.top, self.bottom = 0, self.rows - 1
                self._goto(0, 0)

    def _report_mode(self, number: int, private: bool) -> None:
        """DECRQM: 1 set, 2 reset, 0 a mode it doesn't know."""
        if private:
            if number in (47, 1047, 1049):
                state = 1 if self._alternate is not None else 2
            else:
                state = (1 if number in self.modes else 2) if number in _KNOWN_MODES else 0
            self._reply(f"\x1b[?{number};{state}$y")
        else:
            state = (1 if number in self.ansi_modes else 2) if number in (4, 20) else 0
            self._reply(f"\x1b[{number};{state}$y")

    def _soft_reset(self) -> None:
        """DECSTR: modes, margins, attributes and character sets as they start."""
        self.modes.difference_update({1, 6})
        self.modes.update({7, 25})
        self.ansi_modes.discard(4)
        self.keypad_app = False
        self.top, self.bottom = 0, self.rows - 1
        self.attr = PLAIN
        self.charsets, self.gl = ["B"] * 4, 0
        self.saved = (0, 0, PLAIN, ("B",) * 4, 0, False, False)

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
            self.graphics.clear(history=how == 3)
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

    @staticmethod
    def _extended_color(numbers: list[int]):
        """38;5;n (one of 256) or 38;2;r;g;b (RGB), from the numbers after 38 or 48."""
        if numbers[:1] == [5] and len(numbers) >= 2:
            return min(255, numbers[1])
        if numbers[:1] == [2] and len(numbers) >= 4:
            return tuple(min(255, value) for value in numbers[-3:])
        return None

    def _sgr(self, fields: list[str]) -> None:
        attr = self.attr
        index = 0
        while index < len(fields):
            parts = [int(part) if part.isdigit() else 0 for part in fields[index].split(":")]
            n = parts[0]
            if n in (38, 48, 58):  # (256 colors, RGB; 58: the underline's, not shown)
                if len(parts) > 1:  # (with colons: 38:2::r:g:b)
                    color = self._extended_color(parts[1:])
                else:
                    rest = [int(field) if field.isdigit() else 0
                            for field in fields[index + 1:index + 5]]
                    color = self._extended_color(rest[:2] if rest[:1] == [5] else rest)
                    index += 2 if rest[:1] == [5] else 4 if rest[:1] == [2] else 0
                if n != 58:
                    attr = replace(attr, **{"fg" if n == 38 else "bg": color})
            elif n == 0:
                attr = PLAIN
            elif n == 4 and len(parts) > 1:  # (4:0 none, 4:1.. a kind of underline)
                attr = replace(attr, underline=parts[1] != 0)
            elif n in _SGR_FLAGS:
                attr = replace(attr, **_SGR_FLAGS[n])
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
            index += 1
        self.attr = attr

    def _alternate_screen(self, on: bool) -> None:
        if on and self._alternate is None:
            self._alternate = (self.lines, self.row, self.col)
            self.lines = [self._blank() for _ in range(self.rows)]
            self.row = self.col = 0
            self._main_graphics, self.graphics = self.graphics, TerminalGraphics(self)
        elif not on and self._alternate is not None:
            self.lines, self.row, self.col = self._alternate
            self._alternate = None
            self.graphics, self._main_graphics = self._main_graphics, None

    # -- size and text ---------------------------------------------------------------------
    def resize(self, rows: int, cols: int) -> None:
        rows, cols = max(1, rows), max(1, cols)
        if (rows, cols) == (self.rows, self.cols):
            return

        def fit(lines):
            return [(line + [(" ", PLAIN)] * cols)[:cols] for line in lines]

        lines = fit(self.lines)
        self.history = fit(self.history)
        while len(lines) > rows:  # (the cursor stays on screen: lines above go first)
            if self.row > 0:
                self.history.append(lines.pop(0))
                self.scrolled += 1
                self.row -= 1
            else:
                lines.pop()
        while len(lines) < rows:
            if self.history and self._alternate is None:
                lines.insert(0, self.history.pop())
                self.scrolled -= 1
                self.row += 1
            else:
                lines.append([(" ", PLAIN)] * cols)
        if self._alternate is not None:  # (the main screen, behind: the new size too)
            main, row, col = self._alternate
            main = (fit(main) + [[(" ", PLAIN)] * cols for _ in range(rows)])[:rows]
            self._alternate = (main, min(row, rows - 1), min(col, cols - 1))
        old_cols = self.cols
        self.tabs = {stop for stop in self.tabs if stop < cols} | \
            set(range((old_cols + 7) // 8 * 8, cols, 8))
        self.lines, self.rows, self.cols = lines, rows, cols
        self.top, self.bottom = 0, rows - 1
        self.row, self.col = min(self.row, rows - 1), min(self.col, cols - 1)
        self.wrap_pending = False
        for graphics in (self.graphics, self._main_graphics):
            if graphics is not None:
                graphics.prune()
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

    def __init__(self, argv, cwd, rows, cols, term, on_data, on_exit, pixels=(0, 0)):
        import fcntl
        import pty
        import subprocess
        import termios

        master, slave = pty.openpty()
        self._set_size(master, rows, cols, *pixels)
        env = dict(os.environ, TERM=term, COLUMNS=str(cols), LINES=str(rows))
        env.pop("COLORTERM", None)  # (the outer terminal's, if any: not this one's)
        if term in _XTERMS:
            env["COLORTERM"] = COLORTERM

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
    def _set_size(fd, rows, cols, width=0, height=0):
        """Its size in characters, and in pixels (pictures: programs size them)."""
        import fcntl
        import struct
        import termios

        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, width, height))

    def _read(self, *_):
        try:
            data = os.read(self.master, 65536)
        except OSError:
            data = b""
        if data:
            self._on_data(data)
            return
        self._finish()

    def _finish(self, killed=False):
        if self._done:
            return
        self._done = True
        self._notifier.setEnabled(False)
        if killed:  # (closed first: on macOS a program ends only once its output is read)
            os.close(self.master)
        try:
            code = self.process.wait(timeout=5)
        except Exception:  # noqa: BLE001 - (it won't end: killed)
            self.process.kill()
            code = self.process.wait()
        if not killed:
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

    def resize(self, rows, cols, width=0, height=0) -> None:
        if not self._done:
            self._set_size(self.master, rows, cols, width, height)

    def kill(self) -> None:
        if not self._done:
            import signal

            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                self.process.kill()

    def end(self) -> None:
        """Kill it and wait for it: its exit is reported before this returns."""
        self.kill()
        self._finish(killed=True)


class _PipeProgram:
    """A program with pipes (Windows: no pseudo-terminal)."""

    def __init__(self, argv, cwd, rows, cols, term, on_data, on_exit, pixels=(0, 0)):
        from PySide6.QtCore import QProcess, QProcessEnvironment

        process = QProcess()
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", term)
        env.remove("COLORTERM")
        if term in _XTERMS:
            env.insert("COLORTERM", COLORTERM)
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

    def resize(self, rows, cols, width=0, height=0) -> None:
        pass

    def kill(self) -> None:
        self.process.kill()

    def end(self) -> None:
        """Kill it and wait for it: its exit is reported before this returns."""
        self.kill()
        self.process.waitForFinished(5000)


# --- the view -----------------------------------------------------------------------------

_KEYS = {Qt.Key_Backspace: "\x7f", Qt.Key_Tab: "\t", Qt.Key_Escape: "\x1b",
         Qt.Key_Backtab: "\x1b[Z"}
_CURSOR_KEYS = {Qt.Key_Up: "A", Qt.Key_Down: "B", Qt.Key_Right: "C", Qt.Key_Left: "D",
                Qt.Key_Home: "H", Qt.Key_End: "F"}
_EDITING_KEYS = {Qt.Key_Insert: 2, Qt.Key_Delete: 3, Qt.Key_PageUp: 5, Qt.Key_PageDown: 6}
_PF_KEYS = {Qt.Key_F1: "P", Qt.Key_F2: "Q", Qt.Key_F3: "R", Qt.Key_F4: "S"}
_FUNCTION_KEYS = {Qt.Key_F5: 15, Qt.Key_F6: 17, Qt.Key_F7: 18, Qt.Key_F8: 19, Qt.Key_F9: 20,
                  Qt.Key_F10: 21, Qt.Key_F11: 23, Qt.Key_F12: 24, Qt.Key_F13: 25,
                  Qt.Key_F14: 26, Qt.Key_F15: 28, Qt.Key_F16: 29, Qt.Key_F17: 31,
                  Qt.Key_F18: 32, Qt.Key_F19: 33, Qt.Key_F20: 34}
# The vt100 and vt102: F5..F10 are keys of their keypad (as their terminfo has them)
_VT100_KEYS = {Qt.Key_F5: "t", Qt.Key_F6: "u", Qt.Key_F7: "v", Qt.Key_F8: "l",
               Qt.Key_F9: "w", Qt.Key_F10: "x"}
# The keypad's keys in application mode (ESC =)
_KEYPAD_KEYS = dict(zip("0123456789.-+*/,=", "pqrstuvwxynmkjolX"))
# The light box drawing characters (the DEC line drawing set's): up, down, left, right
_BOX_LINES = {"─": (0, 0, 1, 1), "│": (1, 1, 0, 0), "┌": (0, 1, 0, 1), "┐": (0, 1, 1, 0),
              "└": (1, 0, 0, 1), "┘": (1, 0, 1, 0), "├": (1, 1, 0, 1), "┤": (1, 1, 1, 0),
              "┬": (0, 1, 1, 1), "┴": (1, 0, 1, 1), "┼": (1, 1, 1, 1)}
# A part of a run drawn at once: a line drawing character, or text without them (from
# its first character that isn't a space to its last)
_BOX_PART = "[{0}]|[^{0}\\s]+(?:\\s+[^{0}\\s]+)*".format("".join(_BOX_LINES))
# The Control key: Qt calls it Meta on macOS (Ctrl there is Command)
_CONTROL = Qt.MetaModifier if sys.platform == "darwin" else Qt.ControlModifier


def key_text(key: int, modifiers, text: str, screen: AnsiScreen | None = None) -> str:
    """What a terminal sends for a key ("" for none: e.g. a modifier alone): as
    the screen's terminal type in its modes (cursor keys, keypad, new line)."""
    term = screen.term if screen is not None else TERM
    xterm = term in _XTERMS
    cursor_app = screen is not None and 1 in screen.modes
    keypad = screen is not None and screen.keypad_app and modifiers & Qt.KeypadModifier
    # xterm's modifier number: 1 + Shift 1 + Alt 2 + Ctrl 4 (Shift+Up: ESC [ 1 ; 2 A)
    modifier = 1 + (1 if modifiers & Qt.ShiftModifier else 0) + \
        (2 if modifiers & Qt.AltModifier else 0) + (4 if modifiers & _CONTROL else 0)
    modified = xterm and modifier > 1
    if modifiers & _CONTROL:
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key - Qt.Key_A + 1)
        special = {Qt.Key_BracketLeft: "\x1b", Qt.Key_Backslash: "\x1c",
                   Qt.Key_BracketRight: "\x1d", Qt.Key_Space: "\x00",
                   Qt.Key_At: "\x00"}.get(key)
        if special is not None:
            return special
    if key in (Qt.Key_Return, Qt.Key_Enter):
        if keypad and key == Qt.Key_Enter:
            return "\x1bOM"
        return "\r\n" if screen is not None and 20 in screen.ansi_modes else "\r"
    if keypad and text in _KEYPAD_KEYS:
        return "\x1bO" + _KEYPAD_KEYS[text]
    if term == "vt220" and key in (Qt.Key_Home, Qt.Key_End):  # (its Find and Select keys)
        return "\x1b[1~" if key == Qt.Key_Home else "\x1b[4~"
    if key in _CURSOR_KEYS:
        if modified:
            return f"\x1b[1;{modifier}{_CURSOR_KEYS[key]}"
        return ("\x1bO" if cursor_app else "\x1b[") + _CURSOR_KEYS[key]
    if key in _EDITING_KEYS:
        return f"\x1b[{_EDITING_KEYS[key]};{modifier}~" if modified else \
            f"\x1b[{_EDITING_KEYS[key]}~"
    if key in _PF_KEYS:
        return f"\x1b[1;{modifier}{_PF_KEYS[key]}" if modified else "\x1bO" + _PF_KEYS[key]
    if term in ("vt100", "vt102") and key in _VT100_KEYS:
        return "\x1bO" + _VT100_KEYS[key]
    if xterm and Qt.Key_F13 <= key <= Qt.Key_F20:  # (an xterm's F13..: Shift+F1..)
        return key_text(key - Qt.Key_F13 + Qt.Key_F1, modifiers | Qt.ShiftModifier, "",
                        screen)
    if key in _FUNCTION_KEYS:
        return f"\x1b[{_FUNCTION_KEYS[key]};{modifier}~" if modified else \
            f"\x1b[{_FUNCTION_KEYS[key]}~"
    if key in _KEYS:
        return _KEYS[key]
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
        self._mouse_cell = None  # (where the mouse was last reported: moves within a cell
        self.setMouseTracking(True)  # aren't)

    # (the Terminal's own keys: Tab doesn't move the focus)
    def focusNextPrevChild(self, forward):
        return False

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride:  # the program's, not the menus'
            if _copy_or_paste(event) is None and key_text(
                    event.key(), event.modifiers(), event.text(), self._terminal._screen):
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
        text = key_text(event.key(), event.modifiers(), event.text(), self._terminal._screen)
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
        steps = event.angleDelta().y() // 120
        if steps and self._report_mouse(event, 64 if steps > 0 else 65, "press"):
            for _ in range(abs(steps) - 1):
                self._report_mouse(event, 64 if steps > 0 else 65, "press")
            return
        lines = -event.angleDelta().y() // 40
        self.scroll.setValue(self.scroll.value() + lines)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if 1004 in self._terminal._screen.modes:  # (the program asked to know)
            self._terminal._send("\x1b[I")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if 1004 in self._terminal._screen.modes:
            self._terminal._send("\x1b[O")

    # -- the mouse: the program's when it asks for it (Shift+mouse still selects) ----------------
    def _report_mouse(self, event, button: int, kind: str) -> bool:
        """Send a mouse event (button: 0 left, 1 middle, 2 right, 3 none, 64 and 65
        the wheel; kind: "press", "release" or "move") to the program, when its
        mode asks for it: True if it went to the program."""
        terminal = self._terminal
        screen = terminal._screen
        mode = screen.mouse_mode
        modifiers = event.modifiers()
        if not mode or modifiers & Qt.ShiftModifier or not terminal.Running:
            return False
        if mode == 9 and (kind != "press" or button > 2):
            return True  # (X10: presses only)
        if kind == "move" and (mode in (9, 1000) or (mode == 1002 and button == 3)):
            return True
        width, height = self.cell_size()
        pos = event.position()
        row = max(0, min(screen.rows - 1, int((pos.y() - 2) // height)))
        col = max(0, min(screen.cols - 1, int((pos.x() - 2) // width)))
        if kind == "move":
            if (row, col) == self._mouse_cell:
                return True
            button += 32
        self._mouse_cell = (row, col)
        if mode != 9:
            button += (8 if modifiers & Qt.AltModifier else 0) + \
                (16 if modifiers & _CONTROL else 0)
        if 1006 in screen.modes:  # SGR: numbers, and the button released too
            terminal._send(f"\x1b[<{button};{col + 1};{row + 1}"
                           f"{'m' if kind == 'release' else 'M'}")
        elif col < 223 and row < 223:  # (X10's coordinates: a byte each)
            code = (button & ~3) | 3 if kind == "release" else button
            terminal._send_bytes(b"\x1b[M" + bytes((32 + code, 33 + col, 33 + row)))
        return True

    @staticmethod
    def _button(button) -> int:
        return {Qt.LeftButton: 0, Qt.MiddleButton: 1, Qt.RightButton: 2}.get(button, 3)

    def _held_button(self, event) -> int:
        buttons = event.buttons()
        return next((self._button(b) for b in (Qt.LeftButton, Qt.MiddleButton,
                                               Qt.RightButton) if buttons & b), 3)

    def _first_line(self) -> int:
        """The index (in all_lines) of the top line shown."""
        return self.scroll.value()

    def _cell_at(self, pos: QPoint) -> tuple[int, int]:
        width, height = self.cell_size()
        line = self._first_line() + int((pos.y() - 2) // height)
        return line, max(0, int((pos.x() - 2) // width))

    def mousePressEvent(self, event):
        self.setFocus()
        if self._report_mouse(event, self._button(event.button()), "press"):
            return
        if event.button() == Qt.LeftButton:
            self._anchor = self._cell_at(event.position().toPoint())
            self.selection = None
            self.update()
        elif event.button() == Qt.MiddleButton:
            self._terminal.Paste()

    def mouseMoveEvent(self, event):
        if self._anchor is None and self._report_mouse(event, self._held_button(event), "move"):
            return
        if self._anchor is not None and event.buttons() & Qt.LeftButton:
            here = self._cell_at(event.position().toPoint())
            self.selection = tuple(sorted((self._anchor, here)))
            self.update()

    def mouseReleaseEvent(self, event):
        if self._anchor is None:
            self._report_mouse(event, self._button(event.button()), "release")
        self._anchor = None

    def mouseDoubleClickEvent(self, event):  # a word
        if self._report_mouse(event, self._button(event.button()), "press"):
            return
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
        return QColor(*(value if isinstance(value, tuple) else color_rgb(value)))

    def paintEvent(self, event):
        terminal = self._terminal
        screen = terminal._screen
        painter = QPainter(self)
        back, fore = terminal._default_colors()
        if 5 in screen.modes:  # (reverse video: the whole screen)
            back, fore = fore, back
        painter.fillRect(self.rect(), back)
        width, height = self.cell_size()
        metrics = QFontMetricsF(self.font())
        lines = screen.all_lines()
        first = self._first_line()
        rows = int(self.height() // height) + 1
        selection = self.selection
        ligatures = terminal._values.get("Ligatures", True)
        cursor = (len(screen.history) + screen.row, screen.col) \
            if ligatures and screen.cursor_visible else None  # (a run stops at it)
        fonts = {}

        def font_for(attr):
            key = (attr.bold, attr.italic)
            if key not in fonts:
                fonts[key] = font = QFont(self.font())
                font.setBold(attr.bold)
                font.setItalic(attr.italic)
            return fonts[key]
        runs = []  # (y, the cells' rect, attr, text, fg, the first column, bg or None)
        for index in range(first, min(len(lines), first + rows)):
            y = 2 + (index - first) * height
            line = lines[index]
            col = 0
            while col < len(line):  # runs of one look
                attr = line[col][1]
                end = col + 1
                while end < len(line) and line[end][1] == attr and \
                        self._selected(selection, index, end) == \
                        self._selected(selection, index, col) and \
                        (index, end) != cursor and (index, end - 1) != cursor:
                    end += 1
                text = "".join(char for char, _ in line[col:end])
                fg = self._color(attr.fg, fore)
                if attr.bold and isinstance(attr.fg, int) and attr.fg < 8:
                    fg = self._color(attr.fg + 8, fore)  # (bold: the bright color, as in VB's day)
                bg = self._color(attr.bg, back)
                if attr.inverse:
                    fg, bg = bg, fg
                if attr.dim:  # (halfway to the background)
                    fg = QColor((fg.red() + bg.red()) // 2, (fg.green() + bg.green()) // 2,
                                (fg.blue() + bg.blue()) // 2)
                if self._selected(selection, index, col):
                    bg = self.palette().color(QPalette.Highlight)
                    fg = self.palette().color(QPalette.HighlightedText)
                rect = QRect(round(2 + col * width), round(y), round((end - col) * width) + 1,
                             round(height) + 1)
                runs.append((y, rect, attr, text, fg, col, bg if bg != back else None))
                col = end
        # Pictures (Kitty's, iTerm2's, sixel) in three layers: under the cells'
        # backgrounds, under the text, over it
        pictures = self._pictures(first, rows)
        self._draw_pictures(painter, pictures, None, UNDER_BACKGROUNDS)
        for _y, rect, *_rest, bg in runs:
            if bg is not None:
                painter.fillRect(rect, bg)
        self._draw_pictures(painter, pictures, UNDER_BACKGROUNDS, 0)
        for y, rect, attr, text, fg, col, _bg in runs:
            if text.strip() and not attr.invisible:
                font = font_for(attr)
                painter.setFont(font)
                painter.setPen(fg)
                baseline = round(y + metrics.ascent())
                for offset, part in _text_parts(text, ligatures):
                    x = 2 + (col + offset) * width
                    if part in _BOX_LINES:  # (drawn: lines that meet across cells)
                        self._draw_box(painter, part, x, y, width, height)
                    elif len(part) > 1 and _fits_cells(font, part, width):  # (whole: the
                        painter.drawText(QPoint(round(x), baseline), part)  # ligatures)
                    else:  # (cell by cell: a fixed grid)
                        for index_in, char in enumerate(part):
                            if char != " ":
                                painter.drawText(
                                    QPoint(round(x + index_in * width), baseline), char)
            if attr.underline and not attr.invisible:
                painter.setPen(fg)
                painter.drawLine(rect.left(), round(y + metrics.ascent() + 2),
                                 rect.right(), round(y + metrics.ascent() + 2))
            if attr.strike and not attr.invisible:
                painter.setPen(fg)
                middle = round(y + metrics.ascent() - metrics.strikeOutPos())
                painter.drawLine(rect.left(), middle, rect.right(), middle)
        self._draw_pictures(painter, pictures, 0, None)
        # The cursor: a block, an underline or a bar (a block's outline when the terminal
        # doesn't have the focus)
        cursor_line = len(screen.history) + screen.row
        if screen.cursor_visible and first <= cursor_line < first + rows:
            rect = QRect(round(2 + screen.col * width), round(2 + (cursor_line - first) * height),
                         round(width), round(height))
            shape = screen.cursor_shape
            if shape == "underline":
                rect.setTop(rect.bottom() - 1)
            elif shape == "bar":
                rect.setWidth(2)
            if shape != "block":
                painter.fillRect(rect, fore)
            elif self.hasFocus():
                painter.fillRect(rect, QColor(fore.red(), fore.green(), fore.blue(), 160))
            else:
                painter.setPen(fore)
                painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def _pictures(self, first: int, rows: int) -> list:
        """The placements showing in lines first..first + rows (of all_lines), with
        where they go: [(placement, image, QRectF)], lowest z first."""
        screen = self._terminal._screen
        graphics = screen.graphics
        width, height = self.cell_size()
        scale_x = width / screen.cell_pixels[0]  # (device pixels to the view's, in the
        scale_y = height / screen.cell_pixels[1]  # cells' size: the font's)
        shown = []
        for placement in graphics.placements:
            line = len(screen.history) + graphics.screen_row(placement)
            stored = graphics.images.get(placement.image)
            if stored is None or line + placement.rows <= first or line >= first + rows:
                continue
            x_offset, y_offset = placement.offset
            target = QRectF(2 + placement.col * width + x_offset * scale_x,
                            2 + (line - first) * height + y_offset * scale_y,
                            placement.width * scale_x, placement.height * scale_y)
            shown.append((placement, stored.image, target))
        return sorted(shown, key=lambda item: item[0].z)

    @staticmethod
    def _draw_pictures(painter, pictures, low, high) -> None:
        """The pictures with a z-index from low (None: all) up to high (not included)."""
        for placement, image, target in pictures:
            if (low is None or placement.z >= low) and (high is None or placement.z < high):
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                painter.drawImage(target, image, QRectF(placement.source))

    @staticmethod
    def _draw_box(painter, char: str, x: float, y: float, width: float, height: float):
        """A box drawing character: lines from the cell's middle to its edges."""
        up, down, left, right = _BOX_LINES[char]
        middle_x, middle_y = round(x + width / 2), round(y + height / 2)
        if up or down:
            painter.drawLine(middle_x, round(y) if up else middle_y, middle_x,
                             round(y + height) if down else middle_y)
        if left or right:
            painter.drawLine(round(x) if left else middle_x, middle_y,
                             round(x + width) if right else middle_x, middle_y)

    @staticmethod
    def _selected(selection, line: int, col: int) -> bool:
        if selection is None:
            return False
        (l1, c1), (l2, c2) = selection
        return (line, col) >= (l1, c1) and (line, col) <= (l2, c2)


def _text_parts(text: str, ligatures: bool) -> list[tuple[int, str]]:
    """A run's text in the parts it's drawn in, with each one's column in it:
    each line drawing character on its own, and the text between them (with
    ligatures: as one part, words and spaces; without: a character a part)."""
    parts = []
    for match in re.finditer(_BOX_PART if ligatures else ".", text, re.DOTALL):
        if match.group().strip():  # (spaces alone: nothing to draw)
            parts.append((match.start(), match.group()))
    return parts


def _fits_cells(font: QFont, text: str, width: float) -> bool:
    """Whether the font draws the text exactly in its cells (ligatures and all):
    a monospaced font's own characters; not wider ones from another font."""
    return abs(QFontMetricsF(font).horizontalAdvance(text) - len(text) * width) < 0.5


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
        P("TerminalType", "enum", 0, enum_choices(*TERMINAL_TYPES),
          description="The terminal it is (its TERM, keys and answers); a program started "
                      "before keeps the TERM it had", category="Behavior"),
        P("ScrollbackLines", "int", 1000, description="How many lines scrolled off it keeps"),
        P("BackColor", "color", None, description="Background color; unset: the scheme's"),
        P("ForeColor", "color", None, description="Text color; unset: the scheme's"),
        P("FontName", "font", None, description="Its font; unset: the system's fixed one"),
        P("FontSize", "int", None, description="Font size in points; unset: the system's"),
        P("Ligatures", "bool", True,
          description="Show the font's ligatures (->, !=, >=... in Fira Code, JetBrains "
                      "Mono...); the cursor's cell shows its own character",
          category="Font"),
        *_COMMON,
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.update(_program=None, _screen=AnsiScreen(), _decoder=None,
                             _started=False, _exit_code=-1)
        self._screen.colors = self._default_rgb
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

    _apply_BackColor = _apply_ForeColor = _apply_Ligatures = _apply_colors

    def _default_rgb(self):
        """The default fore and back colors as (r, g, b) (the program may ask)."""
        if self._widget is None:
            return (229, 229, 229), (0, 0, 0)
        back, fore = self._default_colors()
        return (fore.red(), fore.green(), fore.blue()), (back.red(), back.green(), back.blue())

    def _apply_ScrollbackLines(self, v):
        self._screen.scrollback = max(0, int(v))

    def _apply_TerminalType(self, v):
        if not 0 <= v < len(TERMINAL_TYPES):
            raise ValueError(f"TerminalType must be 0 to {len(TERMINAL_TYPES) - 1}, not {v}")
        self._screen.term = TERMINAL_TYPES[v]

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
    def TermName(self) -> str:
        """The TerminalType's name, as TERM has it: "xterm-256color", "vt100"..."""
        return self._screen.term

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
        self.__dict__["_program"] = backend(argv, cwd, rows, cols, self._screen.term,
                                            self._on_data, self._on_exit, self._pixels())

    def _on_data(self, data: bytes) -> None:
        title = self._screen.title
        screen = self._screen
        screen.feed(self._decoder.decode(data))
        replies, screen.replies = screen.replies, []
        for reply in replies:  # (its answers: Device Attributes, the cursor's position...)
            self._send(reply)
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
        width, height = view.cell_size()
        ratio = view.devicePixelRatioF()
        cell_pixels = (max(1, round(width * ratio)), max(1, round(height * ratio)))
        if (rows, cols, cell_pixels) != (self._screen.rows, self._screen.cols,
                                         self._screen.cell_pixels):
            self._screen.resize(rows, cols)
            self._screen.cell_pixels = cell_pixels
            self._screen.pixel_ratio = ratio
            if self.Running:
                self._program.resize(rows, cols, *self._pixels())
        self._redraw()

    def _pixels(self) -> tuple[int, int]:
        """The text area's size in device pixels (the program sees it with its size)."""
        screen = self._screen
        return screen.cols * screen.cell_pixels[0], screen.rows * screen.cell_pixels[1]

    def _send(self, text: str) -> None:
        self._send_bytes(text.encode("utf-8"))

    def _send_bytes(self, data: bytes) -> None:
        if self.Running:
            self._program.write(data)

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
        """Clear the screen, its history and its pictures (the program may draw
        again)."""
        screen = self._screen
        screen.history = []
        screen.lines = [screen._blank() for _ in range(screen.rows)]
        screen.row = screen.col = 0
        screen.graphics.reset()  # (its pictures too)
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
            text = text.replace("\r\n", "\r").replace("\n", "\r")
            if 2004 in self._screen.modes:  # bracketed paste: the program knows it's pasted
                text = "\x1b[200~" + text.replace("\x1b[201~", "") + "\x1b[201~"
            self._send(text)

    def SetFocus(self) -> None:
        if self._widget is not None:
            self._widget.setFocus()

    def _form_unloaded(self) -> None:
        if self.Running:
            self.Kill()


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["Terminal"] = Terminal
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
