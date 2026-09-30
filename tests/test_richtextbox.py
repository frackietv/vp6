"""The RichTextBox: the selection's format (Sel... properties, None when mixed),
SelChange, AppendText, Find, GetLineFromChar, HTML, files, MaxLength and Locked."""

import os

import pytest
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtTest import QTest

from vp6 import (Form, RichTextBox, RGB, vpBlue, vpCenter, vpLeftJustify, vpRed,
                 vpRightJustify, vpRtfHTML, vpRtfMatchCase, vpRtfNoHighlight, vpRtfText,
                 vpRtfWholeWord)
from vp6.controls import CONTROL_TYPES
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Editor(Form):
    def InitializeComponent(self):
        self.rtb = RichTextBox(self, Text="Hello world\nSecond line", Width=300, Height=120)

    def Form_Load(self):
        self.events = []

    def rtb_Change(self):
        self.events.append("Change")

    def rtb_SelChange(self):
        self.events.append(("SelChange", self.rtb.SelStart, self.rtb.SelLength))


@pytest.fixture
def form(qapp):
    form = Editor()
    form.Load()
    return form


def select(rtb, start, length):
    rtb.SelStart = start
    rtb.SelLength = length


def test_text_and_selection(form):
    rtb = form.rtb
    assert rtb.Text == "Hello world\nSecond line" and rtb.SelStart == 0 and rtb.SelLength == 0
    select(rtb, 6, 5)
    assert rtb.SelText == "world" and ("SelChange", 6, 5) in form.events
    select(rtb, 6, 10)  # across lines: a real "\n"
    assert rtb.SelText == "world\nSeco"
    select(rtb, 0, 5)
    form.events.clear()
    rtb.SelText = "Howdy"  # replaces the selection; the cursor after it
    assert rtb.Text.startswith("Howdy world") and (rtb.SelStart, rtb.SelLength) == (5, 0)
    assert "Change" in form.events
    rtb.SelStart = 999  # (kept inside the text)
    assert rtb.SelStart == len(rtb.Text)
    rtb.Text = "plain"
    assert rtb.Text == "plain" and rtb.SelBold is False


def test_formatting_the_selection(form):
    rtb = form.rtb
    select(rtb, 6, 5)
    assert rtb.SelBold is False and rtb.SelItalic is False and rtb.SelUnderline is False
    assert rtb.SelAlignment == vpLeftJustify
    rtb.SelBold = rtb.SelItalic = rtb.SelUnderline = rtb.SelStrikeThru = True
    rtb.SelColor = vpRed
    rtb.SelFontSize = 20
    rtb.SelFontName = "Courier New"
    assert (rtb.SelBold, rtb.SelItalic, rtb.SelUnderline, rtb.SelStrikeThru) == (True,) * 4
    assert rtb.SelColor == vpRed and rtb.SelFontSize == 20
    assert rtb.SelFontName == "Courier New"
    select(rtb, 0, 11)  # "Hello world": partly formatted, so None (VB's Null)
    assert rtb.SelBold is None and rtb.SelColor is None and rtb.SelFontSize is None
    select(rtb, 0, 5)
    assert rtb.SelBold is False and rtb.SelColor not in (None, vpRed)  # the default
    form.rtb.ForeColor = vpBlue
    assert rtb.SelColor == vpBlue  # the control's ForeColor where none was given
    select(rtb, 6, 5)
    rtb.SelColor = None
    assert rtb.SelColor == vpBlue
    rtb.SelBold = False
    assert rtb.SelBold is False and rtb.SelItalic is True


def test_typing_in_a_format(form):
    rtb = form.rtb
    rtb.SelStart = len(rtb.Text)  # nothing selected: the format of what comes next
    rtb.SelBold = True
    rtb.SelColor = RGB(0, 128, 0)
    assert rtb.SelBold is True
    rtb.SelText = " bold green"
    select(rtb, len(rtb.Text) - 10, 10)
    assert rtb.SelText == "bold green" and rtb.SelBold and rtb.SelColor == RGB(0, 128, 0)
    select(rtb, 0, 5)
    assert rtb.SelBold is False  # (the rest unchanged)


def test_alignment(form):
    rtb = form.rtb
    rtb.SelStart = 14  # in the second paragraph
    rtb.SelAlignment = vpCenter
    assert rtb.SelAlignment == vpCenter
    rtb.SelStart = 0
    assert rtb.SelAlignment == vpLeftJustify
    rtb.SelAlignment = vpRightJustify
    select(rtb, 0, len(rtb.Text))  # both paragraphs: mixed
    assert rtb.SelAlignment is None
    rtb.SelAlignment = vpLeftJustify
    assert rtb.SelAlignment == vpLeftJustify


def test_append_text(form):
    rtb = form.rtb
    select(rtb, 0, 5)
    rtb.AppendText("\nERROR", Color=vpRed, Bold=True)
    rtb.AppendText(" disk full", Italic=True, Underline=True)
    assert rtb.Text.endswith("line\nERROR disk full")
    assert (rtb.SelStart, rtb.SelLength) == (0, 5)  # the selection stays
    end = len(rtb.Text)
    select(rtb, end - 15, 5)
    assert rtb.SelText == "ERROR" and rtb.SelBold and rtb.SelColor == vpRed
    assert not rtb.SelItalic
    select(rtb, end - 9, 9)
    assert rtb.SelItalic and rtb.SelUnderline and not rtb.SelBold
    assert rtb.SelColor != vpRed


def test_append_text_follows_the_end(form):
    form.Show()
    rtb = form.rtb
    for line in range(40):
        rtb.AppendText(f"line {line}\n")
    bar = rtb._widget.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()  # (it was at the end)
    bar.setValue(0)  # scrolled up to read: it stays there
    rtb.AppendText("one more\n")
    assert bar.value() == 0
    form.Unload()


def test_find(form):
    rtb = form.rtb
    rtb.Text = "One line, two Lines, a lineup"
    assert rtb.Find("line") == 4 and (rtb.SelStart, rtb.SelLength) == (4, 4)
    assert rtb.Find("line") == 14  # after the selection (not case-sensitive)
    assert rtb.Find("line") == 23
    assert rtb.Find("line") == -1 and rtb.SelStart == 23  # (not found: unchanged)
    assert rtb.Find("line", 0, None, vpRtfMatchCase) == 4
    assert rtb.Find("Line", 0, None, vpRtfMatchCase) == 14
    assert rtb.Find("line", 5, None, vpRtfWholeWord) == -1  # (Lines, lineup)
    assert rtb.Find("line", 0, 10) == 4 and rtb.Find("line", 5, 10) == -1  # up to End
    rtb.SelStart = 0
    assert rtb.Find("two", 0, None, vpRtfNoHighlight) == 10 and rtb.SelLength == 0


def test_lines(form):
    rtb = form.rtb
    assert [rtb.GetLineFromChar(p) for p in (0, 11, 12, 22)] == [0, 0, 1, 1]
    assert rtb.GetLineFromChar(999) == 1


def test_html_and_files(form, tmp_path):
    rtb = form.rtb
    select(rtb, 6, 5)
    rtb.SelBold = True
    rtb.SelColor = vpRed
    assert "world" in rtb.TextHTML and "font-weight" in rtb.TextHTML
    assert "world" in rtb.SelHTML and "Hello" not in rtb.SelHTML
    html, text = tmp_path / "doc.html", tmp_path / "doc.txt"
    rtb.SaveFile(str(html))  # by the extension: HTML
    rtb.SaveFile(str(text))  # and text
    assert text.read_text() == "Hello world\nSecond line" and "<html" in html.read_text()
    rtb.SaveFile(str(tmp_path / "doc.dat"), vpRtfHTML)
    assert "<html" in (tmp_path / "doc.dat").read_text()
    rtb.Text = ""
    rtb.LoadFile(str(html))
    select(rtb, 6, 5)
    assert rtb.Text == "Hello world\nSecond line" and rtb.SelBold and rtb.SelColor == vpRed
    rtb.LoadFile(str(html), vpRtfText)  # the HTML as text
    assert rtb.Text.startswith("<!DOCTYPE")
    rtb.SelStart = 0
    rtb.SelHTML = "<i>new</i> "
    select(rtb, 0, 3)
    assert rtb.SelText == "new" and rtb.SelItalic
    rtb.TextHTML = "<p>a <b>b</b></p>"
    assert rtb.Text == "a b"


def test_max_length_and_locked(form):
    rtb = form.rtb
    rtb.MaxLength = 8
    assert rtb.Text == "Hello wo"
    rtb.SelStart = 5
    rtb.SelText = "XYZ"  # what doesn't fit is dropped
    assert rtb.Text == "Hello wo"
    select(rtb, 0, 5)
    rtb.SelText = "Hi"
    rtb.SelText = "!!!!"
    assert rtb.Text == "Hi!!! wo"  # (only three fitted)
    rtb.MaxLength = 0
    rtb.Locked = True
    form.Show()
    rtb.SetFocus()
    QTest.keyClicks(rtb._widget, "typed")
    assert "typed" not in rtb.Text
    rtb.Locked = False
    rtb.SelStart = 0
    QTest.keyClicks(rtb._widget, "typed")
    assert rtb.Text.startswith("typed")
    form.Unload()


def test_paste_keeps_formatting_not_pictures(form):
    rtb = form.rtb
    rtb.Text = ""
    data = QMimeData()
    data.setHtml('<b>bold</b> <img src="x.png"><table><tr><td>cell</td></tr></table>')
    rtb._widget.insertFromMimeData(data)
    assert rtb.Text == "bold \ncell" and "<img" not in rtb.TextHTML
    assert "<table" not in rtb.TextHTML
    select(rtb, 0, 4)
    assert rtb.SelBold


def test_scroll_bars_and_border(form):
    widget = form.rtb._widget
    assert widget.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded  # Vertical by default
    assert widget.lineWrapMode() == widget.LineWrapMode.WidgetWidth
    form.rtb.ScrollBars = 3
    assert widget.lineWrapMode() == widget.LineWrapMode.NoWrap
    form.rtb.BorderStyle = 0
    assert widget.frameShape() == widget.Shape.NoFrame


def test_toolbox_icon_and_constants(qapp):
    assert "RichTextBox" in Toolbox().buttons and "RichTextBox" in CONTROL_TYPES
    assert not icon("RichTextBox").isNull()
    assert (vpRtfHTML, vpRtfText, vpRtfWholeWord, vpRtfMatchCase, vpRtfNoHighlight) == \
        (0, 1, 2, 4, 8)
