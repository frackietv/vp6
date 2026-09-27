"""Label TextFormat: plain, rich (HTML) and Markdown captions, and links."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QToolButton

from vp6 import Form, Label, formfile, vpMarkdown, vpPlainText, vpRichText
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


def test_plain_text_hides_access_keys(about):
    assert about.lblPlain._widget.text() == "Name & more"
    assert about.lblPlain._widget.textFormat() == Qt.PlainText
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
