"""The MarkdownBox: its three modes (source with the syntax colored, the visual
editor, the preview), the Markdown the visual editor writes, ApplyFormat and its keys,
lists continued by Enter, links, pictures, files and data binding."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QImage, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtTest import QTest

import vp6.markdown
from vp6 import (Form, MarkdownBox, RGB, vpMarkdownBold, vpMarkdownBulletList, vpMarkdownCode,
                 vpMarkdownHeading1, vpMarkdownHeading2, vpMarkdownItalic,
                 vpMarkdownNumberedList, vpMarkdownParagraph, vpMarkdownPreview, vpMarkdownQuote,
                 vpMarkdownSource, vpMarkdownStrikeThru, vpMarkdownVisual)
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.data import BINDINGS
from vp6.ide.icons import icon
from vp6.markdown import markdown_of

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

SAMPLE = """# Title

Some **bold**, *italic*, ~~gone~~ and `code`, ***both***.

- one
- two
    - nested

1. a
2. b

> quoted
>
> more

[VP6](https://example.org/vp6) ![alt](pic.png)

```python
x = 1

y = 2
```

| a | b |
| --- | --- |
| 1 | **2** |

- [x] done
- [ ] todo

---

A snake_case \\* star
"""


class Notes(Form):
    def InitializeComponent(self):
        self.events = []
        self.mdSource = MarkdownBox(self, Text=SAMPLE, Width=300, Height=300)
        self.mdVisual = MarkdownBox(self, Mode=vpMarkdownVisual, Text=SAMPLE, Left=310,
                                    Width=300, Height=300)
        self.mdPreview = MarkdownBox(self, Mode=vpMarkdownPreview, Text=SAMPLE, Left=620,
                                     Width=300, Height=300)

    def mdSource_Change(self):
        self.events.append(("source", self.mdSource.Text))

    def mdVisual_Change(self):
        self.events.append(("visual", self.mdVisual.Text))

    def mdPreview_LinkClick(self, URL):
        self.events.append(("link", URL))


@pytest.fixture
def form(qapp):
    form = Notes()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def _document(markdown: str) -> QTextDocument:
    document = QTextDocument()
    document.setMarkdown(markdown)
    return document


# --- the Markdown the visual editor writes ------------------------------------------------------

def test_markdown_of_writes_what_it_read():
    assert markdown_of(_document(SAMPLE)) == SAMPLE
    assert markdown_of(QTextDocument()) == ""


def test_markdown_of_cases():
    # Qt's own toMarkdown breaks a table after a code block; this one doesn't
    assert markdown_of(_document("```\ncode\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")) == \
        "```\ncode\n```\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    # a list right after another, numbered from its start
    assert markdown_of(_document("- a\n\n3. b\n4. c\n")) == "- a\n\n3. b\n4. c\n"
    # emphasis around spaces: the spaces go outside the markers
    document = QTextDocument()
    cursor = QTextCursor(document)
    cursor.insertText("plain ")
    bold = cursor.charFormat()
    bold.setFontWeight(QFont.Bold)
    cursor.insertText("bold ", bold)
    bold.setFontItalic(True)
    cursor.insertText("both", bold)
    assert markdown_of(document) == "plain **bold *both***\n"
    # text that would be Markdown is escaped
    document = QTextDocument()
    QTextCursor(document).insertText("# not a heading, 1. [not] a <link> *or* list")
    assert markdown_of(document) == \
        "\\# not a heading, 1. \\[not\\] a \\<link> \\*or\\* list\n"


# --- the modes -------------------------------------------------------------------------------------

def test_registration(qapp):
    assert CONTROL_TYPES["MarkdownBox"] is MarkdownBox
    assert list(CONTROL_TYPES)[-1] == "Menu"  # (the Toolbox: Menu stays last)
    assert MarkdownBox.DefaultEvent == "Change" and EVENT_ARGS["LinkClick"] == "URL"
    assert "CausesValidation" in MarkdownBox._specs and "MousePointer" in MarkdownBox._specs
    assert "DataField" in MarkdownBox._specs and "MarkdownBox" in BINDINGS
    assert not icon("MarkdownBox").isNull()


def test_the_three_modes(form):
    assert (vpMarkdownSource, vpMarkdownVisual, vpMarkdownPreview) == (0, 1, 2)
    source, visual, preview = form.mdSource, form.mdVisual, form.mdPreview
    assert source.Mode == 0 and source._widget.toPlainText() == SAMPLE
    assert visual.Text == SAMPLE and preview.Text == SAMPLE  # (as given, until edited)
    document = visual._widget.document()
    assert document.begin().blockFormat().headingLevel() == 1
    assert document.toPlainText().startswith("Title\nSome bold, italic")
    assert not source._widget.isReadOnly() and not visual._widget.isReadOnly()
    assert preview._widget.isReadOnly()
    visual.Locked = True
    assert visual._widget.isReadOnly()
    visual.Locked = False
    assert not visual._widget.isReadOnly()
    assert "<!DOCTYPE HTML" in source.TextHTML and ">bold<" in source.TextHTML


def test_changing_the_mode_keeps_the_text(form):
    box = form.mdSource
    box.Mode = vpMarkdownVisual
    assert isinstance(box._widget, vp6.markdown._VisualEdit) and box.Text == SAMPLE
    box.Mode = vpMarkdownPreview
    assert box._widget.isReadOnly() and box.Text == SAMPLE
    box.Mode = vpMarkdownSource
    assert isinstance(box._widget, vp6.markdown._SourceEdit)
    assert box._widget.toPlainText() == SAMPLE


def test_editing_visually_writes_markdown(form):
    visual = form.mdVisual
    visual.Text = "Hello"
    form.events.clear()
    visual.SetFocus()
    visual.SelStart = 5
    QTest.keyClicks(visual._widget, " world")
    assert visual.Text == "Hello world\n" and form.events[-1] == ("visual", "Hello world\n")
    visual.SelStart, visual.SelLength = 6, 5
    QTest.keyClick(visual._widget, Qt.Key_B, Qt.ControlModifier)  # Ctrl+B: bold
    assert visual.Text == "Hello **world**\n"
    QTest.keyClick(visual._widget, Qt.Key_I, Qt.ControlModifier)
    assert visual.Text == "Hello ***world***\n"
    visual.SelStart = 99  # (the editor's own length: the Markdown is longer)
    assert visual.SelStart == len("Hello world")


def test_setting_text_fires_change_with_the_new_text(form):
    form.events.clear()
    form.mdVisual.Text = "# New"
    assert ("visual", "# New") in form.events
    form.mdSource.Text = "*new*"
    assert form.events[-1] == ("source", "*new*")


# --- formatting --------------------------------------------------------------------------------------

def test_apply_format_in_the_source(form):
    box = form.mdSource
    box.Text = "hello world\nsecond"
    box.SelStart, box.SelLength = 6, 5
    box.ApplyFormat(vpMarkdownBold)
    assert box.Text == "hello **world**\nsecond" and box.SelText == "world"
    box.ApplyFormat(vpMarkdownBold)  # the same again: undone
    assert box.Text == "hello world\nsecond" and box.SelText == "world"
    box.SelStart, box.SelLength = 6, 5
    box.ApplyFormat(vpMarkdownItalic)
    box.ApplyFormat(vpMarkdownStrikeThru)
    assert box.Text == "hello *~~world~~*\nsecond"
    box.SelStart, box.SelLength = 0, 0
    box.ApplyFormat(vpMarkdownCode)  # nothing selected: the markers, the caret between them
    assert box.Text.startswith("``hello") and box.SelStart == 1
    box.Text = "hello world\nsecond"
    box.SelStart, box.SelLength = 0, 14  # (both lines)
    box.ApplyFormat(vpMarkdownNumberedList)
    assert box.Text == "1. hello world\n2. second"
    box.ApplyFormat(vpMarkdownBulletList)
    assert box.Text == "- hello world\n- second"
    box.ApplyFormat(vpMarkdownBulletList)
    assert box.Text == "hello world\nsecond"
    box.ApplyFormat(vpMarkdownHeading2)
    assert box.Text == "## hello world\n## second"
    box.ApplyFormat(vpMarkdownQuote)
    assert box.Text == "> hello world\n> second"
    box.ApplyFormat(vpMarkdownParagraph)
    assert box.Text == "hello world\nsecond"
    with pytest.raises(ValueError):
        box.ApplyFormat(99)


def test_apply_format_in_the_visual_editor(form):
    box = form.mdVisual
    box.Text = "hello world\n\nsecond\n"
    box.SelStart, box.SelLength = 6, 5
    box.ApplyFormat(vpMarkdownCode)
    assert box.Text == "hello `world`\n\nsecond\n"
    box.ApplyFormat(vpMarkdownCode)
    assert box.Text == "hello world\n\nsecond\n"
    box.SelStart, box.SelLength = 0, 0  # the caret's word
    box.ApplyFormat(vpMarkdownStrikeThru)
    assert box.Text == "~~hello~~ world\n\nsecond\n"
    box.SelStart, box.SelLength = 0, 15  # (both paragraphs)
    box.ApplyFormat(vpMarkdownBulletList)
    assert box.Text == "- ~~hello~~ world\n- second\n"
    box.ApplyFormat(vpMarkdownNumberedList)
    assert box.Text == "1. ~~hello~~ world\n2. second\n"
    box.ApplyFormat(vpMarkdownNumberedList)
    assert box.Text == "~~hello~~ world\n\nsecond\n"
    box.ApplyFormat(vpMarkdownQuote)
    assert box.Text == "> ~~hello~~ world\n>\n> second\n"
    box.ApplyFormat(vpMarkdownHeading1)
    assert box.Text == "# ~~hello~~ world\n\n# second\n"
    letter = QTextCursor(box._widget.document())
    letter.setPosition(1)
    assert letter.charFormat().fontWeight() == QFont.Bold
    assert letter.charFormat().property(QTextFormat.FontSizeAdjustment) == 3  # (as Qt's own)
    box.ApplyFormat(vpMarkdownHeading1)
    assert box.Text == "~~hello~~ world\n\nsecond\n"
    preview = form.mdPreview
    preview.ApplyFormat(vpMarkdownBold)  # nothing in the preview
    assert preview.Text == SAMPLE


def test_enter_continues_a_list_in_the_source(form):
    box = form.mdSource
    box.Text = "- one"
    box.SetFocus()
    box.SelStart = 5
    QTest.keyClick(box._widget, Qt.Key_Return)
    QTest.keyClicks(box._widget, "two")
    assert box.Text == "- one\n- two"
    QTest.keyClick(box._widget, Qt.Key_Return)
    QTest.keyClick(box._widget, Qt.Key_Return)  # an empty item ends the list
    assert box.Text == "- one\n- two\n"
    box.Text = "  9. nine\n- [x] done"
    box.SelStart = len("  9. nine")
    QTest.keyClick(box._widget, Qt.Key_Return)
    assert box.Text == "  9. nine\n  10. \n- [x] done"
    box.SelStart = len(box.Text)
    QTest.keyClick(box._widget, Qt.Key_Return)
    assert box.Text.endswith("- [x] done\n- [ ] ")
    box.Text = "plain"
    box.SelStart = 5
    QTest.keyClick(box._widget, Qt.Key_Return)
    assert box.Text == "plain\n"


def test_enter_in_the_visual_editor(form):
    box = form.mdVisual
    box.Text = "# Heading"
    box.SetFocus()
    box.SelStart = len("Heading")
    QTest.keyClick(box._widget, Qt.Key_Return)  # after a heading: a plain paragraph
    QTest.keyClicks(box._widget, "text")
    assert box.Text == "# Heading\n\ntext\n"
    box.Text = "- one"
    box.SelStart = 3
    QTest.keyClick(box._widget, Qt.Key_Return)
    QTest.keyClicks(box._widget, "two")
    assert box.Text == "- one\n- two\n"
    QTest.keyClick(box._widget, Qt.Key_Return)
    QTest.keyClick(box._widget, Qt.Key_Return)  # an empty item ends the list
    QTest.keyClicks(box._widget, "after")
    assert box.Text == "- one\n- two\n\nafter\n"


# --- the source's colors ------------------------------------------------------------------------

def _color_at(box, line, column) -> QColor:
    block = box._widget.document().findBlockByNumber(line)
    for format_range in block.layout().formats():
        if format_range.start <= column < format_range.start + format_range.length:
            return format_range.format.foreground().color()
    return QColor()


def test_source_colors(form):
    box = form.mdSource
    box.Text = "# Head\n- item **bold**\n```\n# not a heading\n```\n[x](http://a.b)"
    heading = QColor(vp6.markdown._MD_COLORS["heading"][0])
    code = QColor(vp6.markdown._MD_COLORS["code"][0])
    assert _color_at(box, 0, 3) == heading
    assert _color_at(box, 1, 0) == QColor(vp6.markdown._MD_COLORS["list"][0])
    assert _color_at(box, 1, 7) == QColor(vp6.markdown._MD_COLORS["markup"][0])  # **
    assert _color_at(box, 3, 2) == code  # inside the fence: code, not a heading
    assert _color_at(box, 5, 1) == QColor(vp6.markdown._MD_COLORS["link"][0])
    assert _color_at(box, 5, 5) == QColor(vp6.markdown._MD_COLORS["url"][0])
    box.BackColor = RGB(20, 20, 20)  # on a dark background: the dark colors
    assert _color_at(box, 0, 3) == QColor(vp6.markdown._MD_COLORS["heading"][1])


# --- links, pictures, files --------------------------------------------------------------------------

def _click_link(box, modifiers=Qt.NoModifier):
    widget = box._widget
    position = widget.document().toPlainText().index("VP6") + 1
    cursor = QTextCursor(widget.document())
    cursor.setPosition(position)
    widget.setTextCursor(cursor)
    widget.ensureCursorVisible()
    point = widget.cursorRect(cursor).center()
    QTest.mouseClick(widget.viewport(), Qt.LeftButton, modifiers, point)


def test_links(form, monkeypatch):
    opened = []
    monkeypatch.setattr(vp6.markdown.QDesktopServices, "openUrl", opened.append)
    _click_link(form.mdPreview)
    assert ("link", "https://example.org/vp6") in form.events
    _click_link(form.mdVisual)  # editing: a plain click only puts the caret there
    assert not opened
    _click_link(form.mdVisual, Qt.ControlModifier)  # Ctrl+click: no handler, the browser
    assert [url.toString() for url in opened] == ["https://example.org/vp6"]


def test_pictures_fit_the_width(form, tmp_path):
    QImage(800, 100, QImage.Format_RGB32).save(str(tmp_path / "wide.png"))
    box = form.mdPreview
    box._widget.document().setBaseUrl(vp6.markdown.QUrl.fromLocalFile(str(tmp_path) + "/"))
    box.Text = "![wide](wide.png)"
    image = box._widget.document().resource(QTextDocument.ImageResource,
                                             vp6.markdown.QUrl("wide.png"))
    if image is None:  # (the document keeps it under the resolved name)
        image = box._widget.loadResource(QTextDocument.ImageResource,
                                         vp6.markdown.QUrl.fromLocalFile(str(tmp_path / "wide.png")))
    assert 32 <= image.width() < 300


def test_files(form, tmp_path):
    path = tmp_path / "notes.md"
    form.mdVisual.Text = "# Saved\n"
    form.mdVisual.SaveFile(str(path))
    assert path.read_text() == "# Saved\n"
    form.mdSource.LoadFile(str(path))
    assert form.mdSource.Text == "# Saved\n"
