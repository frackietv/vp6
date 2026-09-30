"""The editing API TextBox and RichTextBox share: lines and columns, the caret's
place on screen, scrolling, undo and redo, AcceptsTab and SelChange."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from vp6 import Form, RichTextBox, TextBox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

TEXT = "first line\n\tsecond\n\nfourth line here"
LONG = "\n".join(f"line {n}" for n in range(100))


class Editors(Form):
    def InitializeComponent(self):
        self.txtMulti = TextBox(self, MultiLine=True, Text=TEXT, Width=300, Height=100,
                                ScrollBars=3)
        self.rtb = RichTextBox(self, Text=TEXT, Top=110, Width=300, Height=100, ScrollBars=3)
        self.txtSingle = TextBox(self, Text="one line", Top=220, Width=200)
        self.txtOther = TextBox(self, Text="", Top=250, Width=200)

    def Form_Load(self):
        self.changes = []

    def txtMulti_SelChange(self):
        self.changes.append(("txtMulti", self.txtMulti.SelStart, self.txtMulti.SelLength))

    def rtb_SelChange(self):
        self.changes.append(("rtb", self.rtb.SelStart, self.rtb.SelLength))

    def txtSingle_SelChange(self):
        self.changes.append(("txtSingle", self.txtSingle.SelStart, self.txtSingle.SelLength))


@pytest.fixture
def form(qapp):
    form = Editors()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


@pytest.fixture(params=["txtMulti", "rtb"])
def editor(form, request):
    return getattr(form, request.param)


def test_lines_and_columns(editor):
    assert editor.LineCount == 4
    assert [editor.GetLine(n) for n in range(4)] == ["first line", "\tsecond", "",
                                                    "fourth line here"]
    assert [editor.GetCharFromLine(n) for n in range(4)] == [0, 11, 19, 20]
    assert [editor.GetLineFromChar(p) for p in (0, 10, 11, 19, 20, 999)] == [0, 0, 1, 2, 3, 3]
    assert [editor.GetColumnFromChar(p) for p in (0, 10, 12, 19, 27, 999)] == [0, 10, 1, 0, 7, 16]
    for bad in (-1, 4):
        with pytest.raises(IndexError, match="LineCount is 4"):
            editor.GetLine(bad)
        with pytest.raises(IndexError):
            editor.GetCharFromLine(bad)
    editor.Text = ""
    assert editor.LineCount == 1 and editor.GetLine(0) == ""


def test_the_caret_line_and_column(form, editor):
    editor.SelStart = 25  # "fourth" + 5
    assert (editor.CurrentLine, editor.CurrentColumn) == (3, 5)
    editor.CurrentLine = 0  # the same column on another line
    assert (editor.SelStart, editor.CurrentColumn) == (5, 5)
    editor.CurrentLine = 1  # "\tsecond" is long enough
    assert editor.SelStart == 16
    editor.CurrentLine = 2  # an empty line: its end
    assert (editor.CurrentLine, editor.CurrentColumn) == (2, 0)
    editor.CurrentLine = 3
    editor.CurrentColumn = 99  # no further than the line's end
    assert editor.SelStart == len(TEXT) and editor.CurrentColumn == 16
    editor.CurrentColumn = 6
    assert editor.SelStart == 26
    with pytest.raises(IndexError):
        editor.CurrentLine = 4
    name = "txtMulti" if editor is form.txtMulti else "rtb"
    assert (name, 26, 0) in form.changes  # SelChange for every move
    count = len(form.changes)
    editor.SelLength = 3  # a selection is a change too
    assert form.changes[-1] == (name, 26, 3) and len(form.changes) == count + 1
    editor.SelLength = 3  # (nothing moved: no event)
    assert len(form.changes) == count + 1


def test_caret_on_screen(editor):
    editor.SelStart = 0
    left, top, height = editor.CaretLeft, editor.CaretTop, editor.CaretHeight
    assert 0 <= left < 20 and 0 <= top < 20 and 8 < height < 40
    editor.CurrentLine = 3  # three lines down
    assert editor.CaretTop >= top + 3 * height - 3 and editor.CaretLeft == left
    editor.CurrentColumn = 6  # further right
    assert editor.CaretLeft > left + 20
    # and back: the character at the caret's place
    middle = editor.CaretTop + editor.CaretHeight // 2
    assert editor.GetCharFromPoint(editor.CaretLeft + 1, middle) == editor.SelStart
    assert editor.GetCharFromPoint(0, 0) == 0


def test_scrolling(form, editor):
    editor.Text = LONG
    assert editor.FirstVisibleLine == 0
    editor.FirstVisibleLine = 40
    assert editor.FirstVisibleLine == 40
    editor.FirstVisibleLine = 0
    assert editor.FirstVisibleLine == 0
    editor.FirstVisibleLine = 500  # (as far as it goes)
    assert 90 <= editor.FirstVisibleLine <= 99
    editor.CurrentLine = 10
    editor.FirstVisibleLine = 50
    editor.ScrollToCaret()  # the caret's line comes back into view
    assert editor.FirstVisibleLine <= 10
    editor.Text = "x" * 400  # one long line (no wrapping with both scroll bars)
    assert editor.ScrollLeft == 0
    editor.ScrollLeft = 100
    assert editor.ScrollLeft == 100


def test_undo_and_redo(editor):
    assert not editor.CanUndo and not editor.CanRedo
    editor.SelStart = 0
    editor.SelText = "new "
    assert editor.CanUndo and editor.Text.startswith("new first")
    editor.Undo()
    assert editor.Text == TEXT and editor.CanRedo
    editor.Redo()
    assert editor.Text.startswith("new first")
    editor.ClearUndo()
    assert not editor.CanUndo and not editor.CanRedo
    editor.Undo()  # (nothing to undo)
    assert editor.Text.startswith("new first")


def test_accepts_tab(form, editor):
    editor.SetFocus()
    QTest.keyClick(editor._widget, Qt.Key_Tab)  # by default: the next control
    assert editor.Text == TEXT and not editor._widget.hasFocus()
    editor.AcceptsTab = True
    editor.SetFocus()
    editor.SelStart = 0
    QTest.keyClick(editor._widget, Qt.Key_Tab)
    assert editor.Text == "\t" + TEXT and editor._widget.hasFocus()


def test_accepts_tab_survives_a_rebuild(form):
    box = TextBox(form, Name="txtNew", AcceptsTab=True)
    box.MultiLine = True  # a new widget: still taking Tab
    assert not box._widget.tabChangesFocus()


def test_a_single_line_text_box(form):
    box = form.txtSingle
    assert box.LineCount == 1 and box.GetLine(0) == "one line" and box.GetCharFromLine(0) == 0
    assert box.GetLineFromChar(5) == 0 and box.GetColumnFromChar(5) == 5
    with pytest.raises(IndexError):
        box.GetLine(1)
    box.SelStart = 4
    assert (box.CurrentLine, box.CurrentColumn) == (0, 4) and ("txtSingle", 4, 0) in form.changes
    box.CurrentColumn = 2
    assert box.SelStart == 2
    box.CurrentLine = 0
    assert box.SelStart == 2
    assert box.CaretLeft > 0 and box.CaretHeight > 8
    assert box.GetCharFromPoint(box.CaretLeft, box.CaretTop + 2) == 2
    assert box.FirstVisibleLine == 0 and box.ScrollLeft == 0
    box.FirstVisibleLine = 3  # (nothing to scroll)
    box.ScrollLeft = 10
    box.ScrollToCaret()
    box.SelStart = 0
    box.SelText = "just "
    assert box.CanUndo
    box.Undo()
    assert box.Text == "one line" and box.CanRedo
    box.Redo()
    changes = []
    form.txtSingle_Change = lambda: changes.append(1)
    box.ClearUndo()  # (no Change)
    assert not box.CanUndo and box.Text == "just one line" and not changes
    assert box.SelStart == 5  # the caret stays
