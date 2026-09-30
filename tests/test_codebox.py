"""The CodeBox: Python coloring and the Highlight event, the gutter (line numbers,
LineMarker, GutterClick), the current line, hidden lines, protected lines, indenting
and its editing API."""

import os

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest

from vp6 import CodeBox, Form, RGB, vpRed
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

CODE = '''def area(r):
    """The area,
    of a circle."""
    return 3.14 * r * r  # TODO: math.pi

print(area(2))
'''


class Editor(Form):
    def InitializeComponent(self):
        self.events = []  # (Highlight comes before Form_Load)
        self.code = CodeBox(self, Text=CODE, Language=1, Width=400, Height=220)

    def code_Highlight(self, Line, Text, State):
        self.events.append(("Highlight", Line, State))
        start = Text.find("TODO")
        if start >= 0:
            self.code.HighlightText(start, 4, BackColor=vpRed, Bold=True)
        return Line + 1  # (a state for the next line: the line after this one)

    def code_GutterClick(self, Line):
        self.events.append(("GutterClick", Line))

    def code_ProtectedEdit(self, Line):
        self.events.append(("ProtectedEdit", Line))


@pytest.fixture
def form(qapp):
    form = Editor()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def char_format(box, line, column):
    """The format the highlighter gave a character."""
    block = box._widget.document().findBlockByNumber(line)
    ranges = block.layout().formats()
    for format_range in ranges:
        if format_range.start <= column < format_range.start + format_range.length:
            return QTextCharFormat(format_range.format)  # (a copy: the list goes away)
    return None


def test_python_colors(form):
    code = form.code
    keyword = char_format(code, 0, 0)  # def
    assert keyword is not None and keyword.foreground().color().isValid()
    name = char_format(code, 0, 4)  # area
    string = char_format(code, 2, 6)  # inside the triple-quoted string's second line
    comment = char_format(code, 3, 28)
    colors = {f.foreground().color().name() for f in (keyword, name, string, comment)}
    assert len(colors) == 4 and comment.fontItalic()
    assert char_format(code, 5, 0) is None  # print: not colored
    code.Language = 0  # none: only the Highlight event's
    assert char_format(code, 0, 0) is None and char_format(code, 3, 30).background().color() \
        == QColor(255, 0, 0)


def test_dark_and_light(form):
    code = form.code
    code.BackColor = RGB(255, 255, 255)
    light = char_format(code, 0, 0).foreground().color().name()
    code.BackColor = RGB(30, 30, 30)
    dark = char_format(code, 0, 0).foreground().color().name()
    assert light != dark and QColor(dark).lightness() > QColor(light).lightness()


def test_the_highlight_event(form):
    code = form.code
    # Every line, with the State the line before returned (0 for the first)
    states = {line: state for event, line, state in
              [e for e in form.events if e[0] == "Highlight"]}
    assert states[0] == 0 and states[3] == 3
    todo = char_format(code, 3, 28)  # (TODO: in a comment, red behind, bold)
    assert todo.background().color() == QColor(255, 0, 0) and todo.fontWeight() >= 600
    assert todo.fontItalic()  # (the language's italic stays)
    with pytest.raises(RuntimeError, match="Highlight event"):
        code.HighlightText(0, 1, ForeColor=vpRed)
    form.events.clear()
    code.Rehighlight()
    assert len([e for e in form.events if e[0] == "Highlight"]) >= 6


def test_highlight_is_called_once_the_control_has_its_name(qapp):
    class Late(Form):
        def InitializeComponent(self):
            self.code = CodeBox(self, Text="TODO")  # (no name while it is made)

        def code_Highlight(self, Line, Text, State):
            self.code.HighlightText(0, 4, ForeColor=vpRed)

    form = Late()
    assert char_format(form.code, 0, 0).foreground().color() == QColor(255, 0, 0)
    form.Unload()


def test_gutter_and_markers(form):
    code = form.code
    gutter = code._widget.gutter
    assert gutter.width() > 20  # line numbers
    code.LineNumbers = False
    assert gutter.width() == 0
    code.LineMarker[3] = "\u25cf"
    assert gutter.width() > 0 and code.LineMarker(3) == "\u25cf" and code.LineMarker[0] == ""
    code.SelStart = 0
    code.SelText = "import math\n"  # a line above: the marker moves with its line
    assert code.LineMarker(4) == "\u25cf" and code.LineMarker(3) == ""
    code.LineMarker[4] = ""
    assert code.LineMarker(4) == ""
    with pytest.raises(IndexError):
        code.LineMarker[99] = "x"
    code.LineNumbers = True
    block = code._widget.document().findBlockByNumber(2)
    y = code._widget.cursorRect(QTextCursor(block)).center().y()
    QTest.mouseClick(gutter, Qt.LeftButton, Qt.NoModifier, QPoint(5, y))
    assert form.events[-1] == ("GutterClick", 2)
    code.Text = "new"  # a new text: no markers
    assert code.LineMarker(0) == "" and not code._markers


def test_hidden_lines(form):
    code = form.code
    code.CurrentLine = 2
    code.HideLines(1, 2)  # (the caret leaves them)
    assert code.IsLineHidden(1) and code.IsLineHidden(2) and not code.IsLineHidden(3)
    assert code.CurrentLine == 0
    assert code.LineCount == 7  # (still there)
    code.ShowLines(2, 2)
    assert code.IsLineHidden(1) and not code.IsLineHidden(2)
    code.ShowLines()
    assert not code.IsLineHidden(1)
    with pytest.raises(ValueError):
        code.HideLines(3, 1)
    with pytest.raises(IndexError):
        code.HideLines(0, 99)


def test_protected_lines(form):
    code = form.code
    widget = code._widget
    code.ProtectLines(1, 2)
    assert [code.IsLineProtected(n) for n in range(4)] == [False, True, True, False]
    code.SetFocus()
    code.CurrentLine, code.CurrentColumn = 1, 6
    QTest.keyClicks(widget, "x")  # typing in them: refused (ProtectedEdit)
    assert code.GetLine(1) == '    """The area,' and form.events[-1] == ("ProtectedEdit", 1)
    for key in (Qt.Key_Backspace, Qt.Key_Delete):
        QTest.keyClick(widget, key)
    assert code.Text == CODE
    code.CurrentLine, code.CurrentColumn = 3, 0  # Backspace at the next line's start
    QTest.keyClick(widget, Qt.Key_Backspace)
    assert code.Text == CODE
    code.CurrentLine, code.CurrentColumn = 0, 0  # Delete at the end of the line before
    code.CurrentColumn = 99
    QTest.keyClick(widget, Qt.Key_Delete)
    assert code.Text == CODE
    QTest.keyClick(widget, Qt.Key_Return)  # Enter at the end of the line before: allowed
    assert code.LineCount == 8 and code.IsLineProtected(2) and not code.IsLineProtected(1)
    widget.undo()
    code.CurrentLine, code.CurrentColumn = 1, 0  # pasting, a selection reaching into them
    data = QMimeData()
    data.setText("pasted")
    widget.insertFromMimeData(data)
    assert code.Text == CODE
    code.SelStart, code.SelLength = 0, 20
    QTest.keyClick(widget, Qt.Key_X, Qt.ControlModifier)  # cut
    assert code.Text == CODE
    code.SelStart, code.SelLength = 0, 3  # outside them: fine
    QTest.keyClicks(widget, "DEF")
    assert code.Text.startswith("DEF area")
    code.SelStart = code.GetCharFromLine(1)  # code may change them
    code.SelText = "#"
    assert code.GetLine(1).startswith("#    ")
    code.UnprotectLines()
    assert not code.IsLineProtected(1)
    code.CurrentLine, code.CurrentColumn = 1, 1
    QTest.keyClicks(widget, "y")
    assert code.GetLine(1).startswith("#y")


def test_protected_edit_beeps_without_a_handler(qapp, monkeypatch):
    beeps = []
    monkeypatch.setattr("vp6.controls.QApplication.beep", lambda: beeps.append(1))
    form = Form()
    code = CodeBox(form, Name="code", Text="a\nb")
    code.ProtectLines(0, 0)
    form.Show()
    code.SetFocus()
    QTest.keyClicks(code._widget, "x")
    assert beeps and code.Text == "a\nb"
    form.Unload()


def test_indenting(form):
    code = form.code
    widget = code._widget
    code.Text = "if x:\nreturn"
    code.SetFocus()
    code.CurrentLine, code.CurrentColumn = 0, 5
    QTest.keyClick(widget, Qt.Key_Return)  # Python: one level more after a colon
    assert code.GetLine(1) == "    "
    QTest.keyClicks(widget, "pass")
    QTest.keyClick(widget, Qt.Key_Return)  # and one less after pass
    assert code.GetLine(2) == ""
    code.Text = "a\n  b"
    code.CurrentLine, code.CurrentColumn = 1, 3
    QTest.keyClick(widget, Qt.Key_Return)  # keeps the indentation
    assert code.GetLine(2) == "  "
    code.Text = "ab"
    code.CurrentColumn = 1
    QTest.keyClick(widget, Qt.Key_Tab)  # to the next tab stop
    assert code.Text == "a   b"
    code.Text = "one\ntwo\nthree"
    code.SelStart, code.SelLength = 0, code.GetCharFromLine(2)  # lines 0-1 (not 2)
    QTest.keyClick(widget, Qt.Key_Tab)
    assert code.Text == "    one\n    two\nthree"
    QTest.keyClick(widget, Qt.Key_Backtab)
    assert code.Text == "one\ntwo\nthree"
    code.UseTabs = True
    code.TabWidth = 2
    code.SelStart = 0
    QTest.keyClick(widget, Qt.Key_Tab)
    assert code.Text.startswith("\tone")
    QTest.keyClick(widget, Qt.Key_Backtab)
    assert code.Text.startswith("one")
    code.AutoIndent = False
    code.UseTabs = False
    code.Text = "    x"
    code.CurrentColumn = 5
    QTest.keyClick(widget, Qt.Key_Return)
    assert code.GetLine(1) == ""


def test_options(form):
    code = form.code
    widget = code._widget
    fixed = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()
    assert widget.font().family() == fixed  # code: a fixed-width font by default
    code.FontName = "Arial"
    assert widget.font().family() == "Arial"
    assert widget.lineWrapMode() == widget.LineWrapMode.NoWrap
    code.WordWrap = True
    assert widget.lineWrapMode() == widget.LineWrapMode.WidgetWidth
    space = widget.fontMetrics().horizontalAdvance(" ")
    assert widget.tabStopDistance() == pytest.approx(space * 4, abs=1)
    code.TabWidth = 8
    assert widget.tabStopDistance() == pytest.approx(space * 8, abs=1)
    code.Locked = True
    code.SetFocus()
    QTest.keyClicks(widget, "zz")
    assert code.Text == CODE
    assert not widget.tabChangesFocus()  # AcceptsTab is on by default
    code.HighlightCurrentLine = False
    code.CurrentLineColor = RGB(1, 2, 3)
    code.ProtectedColor = RGB(4, 5, 6)
    widget.grab()  # (paints)


def test_editing_api(form):
    code = form.code
    assert code.LineCount == 7 and code.GetLine(5) == "print(area(2))"
    code.CurrentLine = 5
    assert code.SelStart == code.GetCharFromLine(5) and code.SelText == ""
    code.SelLength = 5
    assert code.SelText == "print"
    code.SelText = "show"
    assert code.GetLine(5) == "show(area(2))" and code.CanUndo
    code.Undo()
    assert code.GetLine(5) == "print(area(2))"
    assert code.CaretHeight > 0


def test_toolbox_icon_and_events(qapp):
    assert "CodeBox" in Toolbox().buttons and "CodeBox" in CONTROL_TYPES
    assert not icon("CodeBox").isNull()
    assert EVENT_ARGS["Highlight"] == "Line, Text, State"
    assert EVENT_ARGS["GutterClick"] == EVENT_ARGS["ProtectedEdit"] == "Line"
