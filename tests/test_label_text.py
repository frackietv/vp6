"""Label TextFormat: plain, rich (HTML) and Markdown captions, and links."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QToolButton

from vp6 import CommandButton, Form, Label, TextBox, formfile, vpMarkdown, vpPlainText, vpRichText
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

MARKDOWN = "# Welcome\n\nSome **bold** text and a [link](demo:first)."


class About(Form):
    def InitializeComponent(self):
        self.lblPlain = Label(self, Caption="&Name && more", Left=8, Top=8, Width=200)
        self.lblRich = Label(self, TextFormat=vpRichText, Left=8, Top=40, Width=300,
                             Caption="<b>Bold</b> &amp; <a href='https://example.com'>a link</a>")
        self.lblMarkdown = Label(self, TextFormat=vpMarkdown, Caption=MARKDOWN, Left=8,
                                 Top=80, Width=300, Height=120, WordWrap=True)

    def Form_Load(self):
        self.links = []

    def lblMarkdown_LinkClick(self, URL):
        self.links.append(URL)


@pytest.fixture
def about(qapp):
    form = About()
    form.Show()
    yield form
    form.Unload()


def test_plain_text_underlines_access_keys(about):
    # (drawn as rich text, the access key letter underlined; still plain text to VB code)
    assert about.lblPlain._widget.text() == \
        '<span style="white-space: pre-wrap"><u>N</u>ame &amp; more</span>'
    assert about.lblPlain.AccessKey == "N"
    assert about.lblPlain.TextFormat == vpPlainText


def test_rich_and_markdown(about):
    rich, markdown = about.lblRich._widget, about.lblMarkdown._widget
    assert rich.textFormat() == Qt.RichText and "&amp;" in rich.text()  # kept as given
    assert markdown.textFormat() == Qt.MarkdownText and markdown.text() == MARKDOWN
    # Markdown is really rendered: a heading is taller than a plain line of text
    about.lblMarkdown.AutoSize = True
    plain_height = about.lblPlain._widget.sizeHint().height()
    assert about.lblMarkdown.Height > 3 * plain_height
    about.lblMarkdown.TextFormat = vpPlainText  # back to plain: shown as it is
    assert markdown.textFormat() == Qt.PlainText


def test_links(about, monkeypatch):
    about.lblMarkdown._widget.linkActivated.emit("demo:first")  # the user clicked the link
    assert about.links == ["demo:first"]
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    about.lblRich._widget.linkActivated.emit("https://example.com")  # no handler: the browser
    assert opened == ["https://example.com"]
    assert about.lblRich._widget.textInteractionFlags() & Qt.LinksAccessibleByMouse
    assert not about.lblPlain._widget.textInteractionFlags() & Qt.LinksAccessibleByMouse


def test_file_and_designer(qapp, tmp_path):
    body = ("def InitializeComponent(self):\n"
            "    self.lblA = Label(self, TextFormat=2, Caption='**hi**\\nthere', Left=8, Top=8, "
            "Width=97, Height=25)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("lblA").props["Caption"] == "**hi**\nthere"
    assert "self.lblA = Label(self, TextFormat=2, Caption='**hi**\\nthere'," in \
        formfile.generate_region(form)
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.show()
    name = d.create_control("Label", None, None, d.form_canvas_rect().topLeft() + QPoint(8, 8))
    d.select([name])
    assert d.set_property("TextFormat", vpMarkdown) is None
    assert d.set_property("Caption", "**bold**\n\nnext") is None
    label = d.controls[name]._widget
    assert label.textFormat() == Qt.MarkdownText
    assert not label.textInteractionFlags() & Qt.LinksAccessibleByMouse  # no links while designing
    window = PropertiesWindow()
    window.set_designer(d)
    row = next(r for r in range(window.table.rowCount())
               if window.table.item(r, 0).text() == "Caption")
    buttons = window.table.cellWidget(row, 1).findChildren(QToolButton)
    assert [b.text() for b in buttons] == ["…"]  # the multi-line editor's button
    d.close()


def test_constants():
    assert (vpPlainText, vpRichText, vpMarkdown) == (0, 1, 2)


# --- access keys (& in a Caption) and UseMnemonic ----------------------------------------------

def test_parse_mnemonic():
    from vp6.controls import parse_mnemonic
    assert parse_mnemonic("&Name:") == ("Name:", 0)
    assert parse_mnemonic("N&otes") == ("Notes", 1)
    assert parse_mnemonic("Save && E&xit") == ("Save & Exit", 8)  # && is a literal &
    assert parse_mnemonic("Tom &&Jerry") == ("Tom &Jerry", -1)
    assert parse_mnemonic("&One &Two") == ("One Two", 0)  # the first & only
    assert parse_mnemonic("end&") == ("end", -1) and parse_mnemonic("") == ("", -1)


def test_access_key_sequence():
    import sys

    from vp6.controls import access_key_sequence
    expected = "Meta+Alt+N" if sys.platform == "darwin" else "Alt+N"  # Control+Option on macOS
    assert access_key_sequence("n").toString() == expected
    assert access_key_sequence("7").toString().endswith("+7")
    assert access_key_sequence("é") is None and access_key_sequence("-") is None


class Keys(Form):
    def InitializeComponent(self):
        self.lblName = Label(self, Caption="&Name:", TabIndex=1)
        self.txtName = TextBox(self, Top=0, Left=100, TabIndex=2)
        self.lblHidden = Label(self, Caption="&Hidden:", Top=40, TabIndex=3)
        self.txtHidden = TextBox(self, Top=40, Left=100, Visible=False, TabIndex=4)
        self.txtOff = TextBox(self, Top=40, Left=200, Enabled=False, TabIndex=5)
        self.lblInfo = Label(self, Caption="no key", Top=80, TabIndex=6)
        self.cmdLast = CommandButton(self, Caption="Last", Top=120, TabIndex=7)
        self.lblLoop = Label(self, Caption="&Loop", Top=160, TabIndex=8)


@pytest.fixture
def keys(qapp):
    form = Keys()
    form.Show()
    yield form
    form.Unload()


def _focused(form):
    return form._widget.window().focusWidget()


def test_access_keys_focus_the_next_control(keys):
    name = keys.lblName
    assert name.AccessKey == "N" and "<u>N</u>ame:" in name._widget.text()
    assert name._widget.textFormat() == Qt.RichText and name._shortcut is not None
    name._shortcut.activated.emit()
    assert _focused(keys) is keys.txtName._widget  # the next control in the tab order
    keys.lblHidden._shortcut.activated.emit()  # skipping a hidden and a disabled box,
    assert _focused(keys) is keys.cmdLast._widget  # and a Label (it takes no focus)
    keys.lblLoop._shortcut.activated.emit()  # the last one: round to the first
    assert _focused(keys) is keys.txtName._widget
    assert keys.lblInfo.AccessKey == "" and keys.lblInfo._shortcut is None
    keys.lblName.Enabled = False  # a disabled label's key does nothing
    keys.cmdLast.SetFocus()
    keys.lblName._shortcut.activated.emit()
    assert _focused(keys) is keys.cmdLast._widget


def test_changing_the_caption_and_use_mnemonic(keys):
    name = keys.lblName
    old = name._shortcut
    name.Caption = "Na&me:"  # a new key replaces the old one
    assert name.AccessKey == "m" and name._shortcut is not old and not old.isEnabled()
    name.UseMnemonic = False  # the & as it is, no key
    assert name._widget.text() == "Na&me:" and name._widget.textFormat() == Qt.PlainText
    assert name.AccessKey == "" and name._shortcut is None
    name.UseMnemonic = True
    name.Caption = "Rock && Roll"  # && is a literal &
    assert name._widget.text() == "Rock & Roll" and name._shortcut is None
    name.TextFormat = vpRichText  # formatted captions have no access keys
    name.Caption = "<b>&amp;Bold</b>"
    assert name.AccessKey == "" and name._shortcut is None


def test_no_access_keys_while_designing(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    from PySide6.QtCore import QRect
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("Label", QRect(origin + QPoint(16, 16), origin + QPoint(120, 40)),
                            None)
    d.select([name])
    assert d.set_property("Caption", "&Name:") is None
    label = d.controls[name]
    assert "<u>N</u>" in label._widget.text() and label._shortcut is None  # shown, not active
    d.close()
