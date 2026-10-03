"""The ``MarkdownBox`` control: Markdown text, written as source with its
syntax colored, edited visually, or shown rendered (``Mode``).

* ``vpMarkdownSource``: the Markdown itself in a plain text editor, colored
  (headings, emphasis, code, links, lists, quotes, rules, fenced code). Enter
  continues a list (an empty item ends it).
* ``vpMarkdownVisual``: a word-processor view of the same text: what is
  typed and formatted there is written back as Markdown (``Text``). Enter
  after a heading starts a plain paragraph; Enter on an empty list item ends
  the list. Ctrl+click opens a link.
* ``vpMarkdownPreview``: the rendered text, read-only; clicking a link fires
  ``LinkClick`` (without a handler, the browser opens it).

``Text`` is always the Markdown (GitHub's dialect: tables, task lists,
strikethrough). The visual editor keeps the Markdown it was given until it
is edited; then ``Text`` is what ``markdown_of`` writes for its document.
``ApplyFormat`` (Ctrl+B and Ctrl+I too) formats the selection in either
editor: bold, italic, strikethrough, code, headings, a paragraph, lists, a
quote. Pictures with relative paths are found in the form's folder.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QByteArray, QEvent, QUrl, Qt
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QImage, QPalette,
                           QSyntaxHighlighter, QTextBlock, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextListFormat)
from PySide6.QtWidgets import QFrame, QPlainTextEdit, QTextEdit

from . import colors
from ._props import P, enum_choices
from .controls import (_COLORS, _COMMON, _FONT, CONTROL_TYPES, Control, _add_mouse_members,
                       _add_validation, _EditorSelection, _geometry, _TextEditing)

MODE_SOURCE, MODE_VISUAL, MODE_PREVIEW = 0, 1, 2

# ApplyFormat's formats (vpMarkdownBold...)
BOLD, ITALIC, STRIKE, CODE = 1, 2, 3, 4
PARAGRAPH, HEADING1, HEADING2, HEADING3 = 10, 11, 12, 13
BULLETS, NUMBERS, QUOTE = 20, 21, 22
_MARKERS = {BOLD: "**", ITALIC: "*", STRIKE: "~~", CODE: "`"}

_HEADING_SIZE = 4  # (a heading's FontSizeAdjustment is this minus its level, as Qt's own)
_QUOTE_MARGIN = 40


# --- the Markdown of a document (the visual editor's) -------------------------------------------

def _escape(text: str) -> str:
    """Plain text in Markdown: the characters that would format it escaped."""
    text = re.sub(r"([\\`*\[\]<|])", r"\\\1", text)
    text = re.sub(r"(?<!\w)_|_(?!\w)", r"\\_", text)  # (snake_case stays as it is)
    return text.replace("~~", "\\~\\~")


def _escape_line_start(line: str) -> str:
    """A paragraph's text mustn't start a heading, a list or a quote."""
    match = re.match(r"(\d+)([.)])(\s|$)", line)
    if match:
        return match.group(1) + "\\" + line[len(match.group(1)):]
    if re.match(r"(#{1,6}|[-+*]|=+)(\s|$)|>", line):
        return "\\" + line
    return line


def _inline(block: QTextBlock, heading: bool = False) -> str:
    """A paragraph's text with its emphasis, code, links and pictures, as
    Markdown (a heading's own boldness and size aren't emphasis)."""
    out: list[str] = []
    open_: list[tuple] = []  # the markers open now, outermost first
    pending = ""  # spaces held back: they go after markers that close

    def close(count: int) -> None:
        while len(open_) > count:
            kind, value = open_.pop()
            out.append(f"]({value})" if kind == "link" else value)

    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        it += 1
        fmt = fragment.charFormat()
        text = fragment.text()
        if fmt.isImageFormat():
            image = fmt.toImageFormat()
            alt = image.property(QTextFormat.ImageAltText) or ""
            close(0)
            out.append(pending + f"![{_escape(str(alt))}]({image.name()})")
            pending = ""
            continue
        wanted = []
        if fmt.isAnchor() and fmt.anchorHref():
            wanted.append(("link", fmt.anchorHref()))
        if not heading and fmt.fontWeight() > QFont.Normal:
            wanted.append(("mark", "**"))
        if fmt.fontItalic():
            wanted.append(("mark", "*"))
        if fmt.fontStrikeOut():
            wanted.append(("mark", "~~"))
        if fmt.fontFixedPitch():
            wanted.append(("mark", "``" if "`" in text else "`"))
        core = text.strip()
        if not core:  # (only spaces: no markers of their own)
            pending += text
            continue
        lead, trail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
        same = 0
        while same < min(len(open_), len(wanted)) and open_[same] == wanted[same]:
            same += 1
        if same == len(open_) == len(wanted):
            out.append(pending + lead)
        else:
            close(same)
            out.append(pending + lead)
            for kind, value in wanted[same:]:
                out.append("[" if kind == "link" else value)
                open_.append((kind, value))
        code = any(value.startswith("`") for _kind, value in open_)
        out.append(core.replace(" ", "\\\n") if code else
                   _escape(core).replace(" ", "\\\n"))
        pending = trail
    close(0)
    return "".join(out)


def _table_markdown(table) -> str:
    rows = []
    for row in range(table.rows()):
        cells = []
        for column in range(table.columns()):
            cell = table.cellAt(row, column)
            parts, block = [], cell.firstCursorPosition().block()
            last = cell.lastCursorPosition().block()
            while block.isValid():
                parts.append(_inline(block, heading=row == 0))  # (a header row is bold)
                if block == last:
                    break
                block = block.next()
            cells.append(" ".join(p for p in parts if p))
        rows.append("| " + " | ".join(cells) + " |")
        if row == 0:
            rows.append("|" + "|".join(" --- " for _ in range(table.columns())) + "|")
    return "\n".join(rows)


def markdown_of(document: QTextDocument) -> str:
    """A document's Markdown, written as people write it: headings, paragraphs,
    lists (nested, numbered, tasks), quotes, fenced code, tables, rules.
    Qt's own ``toMarkdown`` loses tables after code blocks and runs lists
    together, so the visual editor writes its own."""
    groups: list[list] = []  # [kind, key, [lines or items]]

    def add(kind, key, item):
        if groups and groups[-1][0] == kind and groups[-1][1] == key and key is not None:
            groups[-1][2].append(item)
        else:
            groups.append([kind, key, [item]])

    block = document.begin()
    list_key = None
    while block.isValid():
        table = QTextCursor(block).currentTable()
        if table is not None:
            add("table", None, _table_markdown(table))
            end = table.lastPosition()
            while block.isValid() and block.position() <= end:
                block = block.next()
            list_key = None
            continue
        fmt = block.blockFormat()
        text_list = block.textList()
        quote = fmt.intProperty(QTextFormat.BlockQuoteLevel)
        if fmt.hasProperty(QTextFormat.BlockCodeFence) or \
                fmt.hasProperty(QTextFormat.BlockCodeLanguage):
            language = fmt.stringProperty(QTextFormat.BlockCodeLanguage)
            add("code", language, block.text().replace(" ", "\n"))
            list_key = None
        elif text_list is not None:
            list_format = text_list.format()
            indent = max(1, list_format.indent())
            if indent == 1 and (list_key is None or list_key[0] != id(text_list)):
                list_key = (id(text_list), block.position())
            if list_format.style() in (QTextListFormat.ListDecimal,
                                       QTextListFormat.ListLowerAlpha,
                                       QTextListFormat.ListUpperAlpha,
                                       QTextListFormat.ListLowerRoman,
                                       QTextListFormat.ListUpperRoman):
                marker = f"{text_list.itemNumber(block) + max(1, list_format.start())}."
            else:
                marker = "-"
            task = {QTextBlockFormat.MarkerType.Checked: "[x] ",
                    QTextBlockFormat.MarkerType.Unchecked: "[ ] "}.get(fmt.marker(), "")
            add("list", list_key, "    " * (indent - 1) + f"{marker} {task}" + _inline(block))
        elif fmt.headingLevel():
            add("heading", None, "#" * fmt.headingLevel() + " " + _inline(block, heading=True))
            list_key = None
        elif fmt.hasProperty(QTextFormat.BlockTrailingHorizontalRulerWidth):
            add("rule", None, "---")
            list_key = None
        else:
            line = _escape_line_start(_inline(block))
            if line.strip():
                add("quote" if quote else "paragraph", quote or None, line)
                list_key = None
        block = block.next()
    out = []
    for kind, key, items in groups:
        if kind == "code":
            out.append(f"```{key}\n" + "\n".join(items) + "\n```")
        elif kind == "list":
            out.append("\n".join(items))
        elif kind == "quote":
            prefix = "> " * key
            out.append(f"\n{prefix.rstrip()}\n".join(
                "\n".join(prefix + line for line in item.split("\n")) for item in items))
        else:
            out.extend(items)
    return "\n\n".join(out) + "\n" if out else ""


# --- the source editor's colors --------------------------------------------------------------

_MD_COLORS = {  # (on a light background, on a dark one)
    "heading": ("#0b5cad", "#6cb6ff"), "markup": ("#8c8c8c", "#7f8790"),
    "code": ("#a31515", "#ce9178"), "link": ("#0b5cad", "#6cb6ff"),
    "url": ("#7a7a7a", "#8b949e"), "list": ("#af00db", "#c586c0"),
    "quote": ("#4f7a4f", "#8fbf8f"),
}
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})(\s|$)")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_QUOTE = re.compile(r"^\s{0,3}(>\s?)+")
_LIST = re.compile(r"^\s*([-*+]|\d+[.)])\s+(\[[ xX]\]\s)?")
_LIST_CONTINUE = re.compile(r"^(\s*)([-*+]|(\d+)([.)]))(\s+)(\[[ xX]\]\s+)?")
_INLINE = (  # (pattern, the format of its text, of its markers)
    (re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1"), "bold"),
    (re.compile(r"(?<![*\w])(\*)(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])"), "italic"),
    (re.compile(r"(?<![_\w])(_)(?=[^\s_])(.+?)(?<=[^\s_])_(?![_\w])"), "italic"),
    (re.compile(r"(~~)(?=\S)(.+?)(?<=\S)~~"), "strike"),
)
_LINK = re.compile(r"(!?\[)([^\]]*)(\]\()([^)]*)(\))|<(https?://[^>\s]+)>")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")


class _MarkdownHighlighter(QSyntaxHighlighter):
    """Colors the Markdown source line by line; a block's state is 1 inside
    a fenced code block (``` or ~~~: the fence in ``fences``)."""

    def __init__(self, document):
        super().__init__(document)
        self.formats: dict[str, QTextCharFormat] = {}
        self.dark = None

    def set_dark(self, dark: bool) -> None:
        self.dark = dark
        self.formats = {}
        for name, pair in _MD_COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(pair[dark]))
            if name == "heading":
                fmt.setFontWeight(QFont.Bold)
            elif name == "code":
                fmt.setFontFamilies([QFontDatabase.systemFont(QFontDatabase.FixedFont).family()])
            elif name == "quote":
                fmt.setFontItalic(True)
            elif name == "link":
                fmt.setFontUnderline(True)
            self.formats[name] = fmt
        for name, setup in (("bold", lambda f: f.setFontWeight(QFont.Bold)),
                            ("italic", lambda f: f.setFontItalic(True)),
                            ("strike", lambda f: f.setFontStrikeOut(True))):
            fmt = QTextCharFormat()
            setup(fmt)
            self.formats[name] = fmt

    def _merge(self, start: int, length: int, fmt: QTextCharFormat) -> None:
        """Add a format to what the characters have (bold and italic both)."""
        for position in range(start, start + length):
            merged = QTextCharFormat(self.format(position))
            merged.merge(fmt)
            self.setFormat(position, 1, merged)

    def highlightBlock(self, text: str) -> None:
        formats = self.formats
        fence = _FENCE.match(text)
        if self.previousBlockState() == 1:  # inside fenced code
            self.setFormat(0, len(text), formats["code"])
            if fence and fence.group(1)[0] == self._fence_char():
                self.setFormat(0, len(text), formats["markup"])
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            return
        self.setCurrentBlockState(0)
        if fence:
            self.setFormat(0, len(text), formats["markup"])
            self.setCurrentBlockState(1)
            return
        start = 0
        heading = _HEADING.match(text)
        if heading:
            self.setFormat(0, len(text), formats["heading"])
            self._merge(0, heading.end(1), formats["markup"])
            start = heading.end()
        elif _RULE.match(text):
            self.setFormat(0, len(text), formats["markup"])
            return
        else:
            quote = _QUOTE.match(text)
            if quote:
                self.setFormat(quote.end(), len(text) - quote.end(), formats["quote"])
                self.setFormat(0, quote.end(), formats["markup"])
                start = quote.end()
            item = _LIST.match(text[start:])
            if item:
                self.setFormat(start + item.start(1), item.end() - item.start(1),
                               formats["list"])
                start += item.end()
            if text.lstrip().startswith("|"):
                for match in re.finditer(r"(?<!\\)\|", text):
                    self.setFormat(match.start(), 1, formats["markup"])
        for pattern, name in _INLINE:
            for match in pattern.finditer(text, start):
                marker = len(match.group(1))
                self._merge(match.start(), match.end() - match.start(), formats[name])
                self._merge(match.start(), marker, formats["markup"])
                self._merge(match.end() - marker, marker, formats["markup"])
        for match in _LINK.finditer(text, start):
            if match.group(6):  # <https://...>
                self.setFormat(match.start(), match.end() - match.start(), formats["link"])
                continue
            self.setFormat(match.start(1), len(match.group(1)), formats["markup"])
            self._merge(match.start(2), len(match.group(2)), formats["link"])
            self.setFormat(match.start(3), len(match.group(3)), formats["markup"])
            self.setFormat(match.start(4), len(match.group(4)), formats["url"])
            self.setFormat(match.start(5), 1, formats["markup"])
        for match in _CODE_SPAN.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), formats["code"])

    def _fence_char(self) -> str:
        """The character of the fence that opened the code block this line is in."""
        block = self.currentBlock().previous()
        while block.isValid():
            match = _FENCE.match(block.text())
            if match and block.userState() == 1 and (
                    not block.previous().isValid() or block.previous().userState() != 1):
                return match.group(1)[0]
            block = block.previous()
        return "`"


# --- the editors ---------------------------------------------------------------------------------

class _SourceEdit(QPlainTextEdit):
    """The Markdown source: Enter continues a list, Ctrl+B and Ctrl+I format."""

    def __init__(self, box: "MarkdownBox", parent):
        super().__init__(parent)
        self.box = box

    def keyPressEvent(self, event):
        if not self.box._format_key(event) and not self._continue_list(event):
            super().keyPressEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self.box._restyle()

    def _continue_list(self, event) -> bool:
        if event.key() not in (Qt.Key_Return, Qt.Key_Enter) or event.modifiers() & (
                Qt.ShiftModifier | Qt.ControlModifier) or self.isReadOnly():
            return False
        cursor = self.textCursor()
        line = cursor.block().text()
        match = _LIST_CONTINUE.match(line)
        if not match or cursor.hasSelection() or cursor.positionInBlock() < match.end():
            return False
        cursor.beginEditBlock()
        if not line[match.end():].strip():  # an empty item ends the list
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        else:
            indent, number = match.group(1), match.group(3)
            marker = f"{int(number) + 1}{match.group(4)}" if number else match.group(2)
            task = "[ ] " if match.group(6) else ""
            cursor.insertText(f"\n{indent}{marker} {task}")
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True


class _VisualEdit(QTextEdit):
    """The visual editor and the preview: Markdown shown as it reads. Links:
    a click in the preview, Ctrl+click while editing."""

    def __init__(self, box: "MarkdownBox", parent):
        super().__init__(parent)
        self.box = box

    def keyPressEvent(self, event):
        if not self.box._format_key(event) and not self._paragraph_key(event):
            super().keyPressEvent(event)

    def loadResource(self, kind, url):
        """A picture wider than the control is shown smaller, to fit."""
        resource = super().loadResource(kind, url)
        if kind != QTextDocument.ImageResource:
            return resource
        if isinstance(resource, QImage):
            image = resource
        elif isinstance(resource, (QByteArray, bytes)):
            image = QImage.fromData(resource)
        elif resource is None and url.isLocalFile():  # (else the document reads the file)
            image = QImage(url.toLocalFile())
        else:
            return resource
        if image.isNull():
            return resource
        width = max(32, self.box._values.get("Width", 0) - 2 * int(
            self.document().documentMargin()) - self.verticalScrollBar().sizeHint().width() - 4)
        return image.scaledToWidth(width, Qt.SmoothTransformation) if image.width() > width \
            else image

    def mousePressEvent(self, event):
        self._pressed = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        point = event.position().toPoint()
        anchor = self.anchorAt(point)
        editing = self.box._mode() == MODE_VISUAL and not self.box._values.get("Locked")
        pressed = getattr(self, "_pressed", None)
        if anchor and event.button() == Qt.LeftButton and (
                not editing or event.modifiers() & Qt.ControlModifier) and \
                pressed is not None and (point - pressed).manhattanLength() < 4:  # (not a drag)
            self.box._on_link(anchor)

    def _paragraph_key(self, event) -> bool:
        """Enter after a heading or a rule starts a plain paragraph; on an empty
        list item, it ends the list."""
        if event.key() not in (Qt.Key_Return, Qt.Key_Enter) or \
                event.modifiers() & Qt.ShiftModifier or self.isReadOnly():
            return False
        cursor = self.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        if block.textList() is not None and not block.text() and not cursor.hasSelection():
            block.textList().remove(block)
            plain = block.blockFormat()  # (fmt still names the list)
            plain.setIndent(0)
            cursor.setBlockFormat(plain)
            return True
        if (fmt.headingLevel() or fmt.hasProperty(
                QTextFormat.BlockTrailingHorizontalRulerWidth)) and \
                cursor.atBlockEnd() and not cursor.hasSelection():
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
            self.setTextCursor(cursor)
            return True
        return False

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self.box._restyle()


# --- the control -----------------------------------------------------------------------------------

class MarkdownBox(_EditorSelection, _TextEditing, Control):
    """Markdown: its source with the syntax colored, a visual editor, or a
    rendered preview (``Mode``; the module's documentation)."""

    TypeName = "MarkdownBox"
    DefaultEvent = "Change"
    DefaultSize = (321, 201)
    Events = ("Change", "SelChange", "LinkClick", "Click", "DblClick", "GotFocus", "LostFocus",
              "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        P("Mode", "enum", MODE_SOURCE, enum_choices("Source", "Visual", "Preview"),
          description="Source: the Markdown with its syntax colored; Visual: edited as it "
                      "reads; Preview: rendered, read-only"),
        P("Text", "text", "", always=True, description="The contents, as Markdown"),
        *_geometry(*DefaultSize),
        P("Locked", "bool", False, description="Read-only: the text can't be edited"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A border around it"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def __init__(self, parent, Name: str = "", **props):
        # Pick the right editor up front instead of rebuilding it (like TextBox's MultiLine)
        self.__dict__["_values"] = {"Mode": int(props.get("Mode", MODE_SOURCE))}
        self.__dict__.update(_markdown="", _loading=False, _highlighter=None)
        super().__init__(parent, Name, **props)

    def _mode(self) -> int:
        return self._values.get("Mode", MODE_SOURCE)

    @property
    def _qss_type(self):
        return "QPlainTextEdit" if self._mode() == MODE_SOURCE else "QTextEdit"

    def _create_widget(self, parent):
        if self._mode() == MODE_SOURCE:
            widget = _SourceEdit(self, parent)
            self.__dict__["_highlighter"] = _MarkdownHighlighter(widget.document())
        else:
            widget = _VisualEdit(self, parent)
            widget.setAutoFormatting(QTextEdit.AutoBulletList)
            self.__dict__["_highlighter"] = None
            base = self._form._base_dir() if hasattr(self._form, "_base_dir") else ""
            if base:  # (pictures with relative paths: in the form's folder)
                widget.document().setBaseUrl(QUrl.fromLocalFile(base.rstrip("/") + "/"))
        widget.setTabChangesFocus(True)
        self._widget = widget
        self._restyle()
        return widget

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        self._widget.textChanged.connect(self._on_text_changed)
        self._connect_selection()
        self._apply_editing()

    def _on_text_changed(self):
        if self._mode() != MODE_SOURCE and not self._loading:
            self.__dict__["_markdown"] = markdown_of(self._widget.document())
        self._fire("Change")

    # -- looks ---------------------------------------------------------------------------------
    def _dark(self) -> bool:
        back = self._values.get("BackColor")
        color = colors.to_qcolor(back) if back is not None else \
            self._widget.palette().color(QPalette.Base)
        return color.lightness() < 128

    def _restyle(self) -> None:
        highlighter = self._highlighter
        if highlighter is not None and self._widget is not None and \
                highlighter.dark != self._dark():
            highlighter.set_dark(self._dark())
            highlighter.rehighlight()

    def _apply_colors(self, _=None):
        super()._apply_colors()
        self._restyle()

    _apply_BackColor = _apply_ForeColor = _apply_colors

    # -- properties ----------------------------------------------------------------------------
    def _apply_Mode(self, v):
        if isinstance(self._widget, _SourceEdit) != (v == MODE_SOURCE):
            self._rebuild_widget()
        else:
            self._apply_editing()

    def _apply_editing(self, _=None) -> None:
        widget = self._widget
        read_only = self._mode() == MODE_PREVIEW or bool(self._values.get("Locked"))
        widget.setReadOnly(read_only)
        if isinstance(widget, _VisualEdit):
            widget.setTextInteractionFlags(
                (Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard |
                 Qt.LinksAccessibleByMouse) if read_only else Qt.TextEditorInteraction)

    _apply_Locked = _apply_editing

    def _apply_BorderStyle(self, v):
        self._widget.setFrameShape(QFrame.StyledPanel if v else QFrame.NoFrame)

    def _read_Text(self):
        if isinstance(self._widget, _SourceEdit):
            return self._widget.toPlainText()
        return self._markdown

    def _apply_Text(self, v):
        v = str(v)
        if isinstance(self._widget, _SourceEdit):
            if self._widget.toPlainText() != v:
                self._widget.setPlainText(v)
            return
        if v == self._markdown and (v or self._widget.document().isEmpty()):
            return
        widget = self._widget
        bar = widget.verticalScrollBar()
        scrolled, caret = bar.value(), widget.textCursor().position()
        self.__dict__.update(_markdown=v, _loading=True)
        try:  # (Change fires: Text is already the new one)
            widget.document().setMarkdown(v)
        finally:
            self.__dict__["_loading"] = False
        cursor = widget.textCursor()  # (the caret and the view kept in place as it changes)
        cursor.setPosition(min(caret, widget.document().characterCount() - 1))
        widget.setTextCursor(cursor)
        bar.setValue(min(scrolled, bar.maximum()))

    @property
    def TextHTML(self) -> str:
        """The Markdown rendered as HTML (read-only)."""
        document = QTextDocument()
        document.setMarkdown(self.Text)
        return document.toHtml()

    # -- links ---------------------------------------------------------------------------------
    def _on_link(self, url: str) -> None:
        """LinkClick(URL), or without a handler, the browser opens it."""
        if self._handler("LinkClick") is not None:
            self._fire("LinkClick", url)
        else:
            QDesktopServices.openUrl(QUrl(url))

    # -- formatting ----------------------------------------------------------------------------
    def _format_key(self, event) -> bool:
        if not event.modifiers() & Qt.ControlModifier or \
                event.modifiers() & (Qt.AltModifier | Qt.ShiftModifier):
            return False
        format_ = {Qt.Key_B: BOLD, Qt.Key_I: ITALIC}.get(event.key())
        if format_ is None or self._widget.isReadOnly():
            return False
        self.ApplyFormat(format_)
        return True

    def ApplyFormat(self, Format: int) -> None:
        """Format the selection (or the caret's word or paragraph) in either
        editor, the same again undoing it: vpMarkdownBold, vpMarkdownItalic,
        vpMarkdownStrikeThru, vpMarkdownCode (the text); vpMarkdownHeading1 to
        3, vpMarkdownParagraph, vpMarkdownBulletList, vpMarkdownNumberedList,
        vpMarkdownQuote (its paragraphs). Nothing in the preview."""
        Format = int(Format)
        if self._mode() == MODE_PREVIEW or self._widget.isReadOnly():
            return
        if Format not in (*_MARKERS, PARAGRAPH, HEADING1, HEADING2, HEADING3, BULLETS,
                          NUMBERS, QUOTE):
            raise ValueError(f"MarkdownBox '{self.Name}': no format {Format} "
                             f"(vpMarkdownBold...)")
        cursor = self._widget.textCursor()
        cursor.beginEditBlock()
        try:
            if isinstance(self._widget, _SourceEdit):
                if Format in _MARKERS:
                    self._source_inline(cursor, _MARKERS[Format])
                else:
                    self._source_blocks(cursor, Format)
            elif Format in _MARKERS:
                self._visual_inline(cursor, Format)
            else:
                self._visual_blocks(cursor, Format)
        finally:
            cursor.endEditBlock()
        self._widget.setTextCursor(cursor)

    # (the source: markers around the text, prefixes before the lines)
    def _source_inline(self, cursor: QTextCursor, marker: str) -> None:
        text = self._widget.toPlainText()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        size = len(marker)
        selected = text[start:end]
        if len(selected) >= 2 * size and selected.startswith(marker) and \
                selected.endswith(marker):  # **text** selected: unwrap it
            cursor.insertText(selected[size:-size])
            cursor.setPosition(start)
            cursor.setPosition(end - 2 * size, QTextCursor.KeepAnchor)
            return
        if text[max(0, start - size):start] == marker and text[end:end + size] == marker and \
                (marker != "*" or text[start - 2:start] != "**" or text[start - 3:start] == "***"):
            cursor.setPosition(start - size)  # **[text]**: unwrap it
            cursor.setPosition(end + size, QTextCursor.KeepAnchor)
            cursor.insertText(selected)
            cursor.setPosition(start - size)
            cursor.setPosition(end - size, QTextCursor.KeepAnchor)
            return
        cursor.insertText(marker + selected + marker)
        cursor.setPosition(start + size)
        cursor.setPosition(end + size, QTextCursor.KeepAnchor)

    def _source_blocks(self, cursor: QTextCursor, format_: int) -> None:
        document = self._widget.document()
        first = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        blocks, block = [], first
        while block.isValid():
            blocks.append(block)
            if block == last:
                break
            block = block.next()
        prefixes = {HEADING1: "# ", HEADING2: "## ", HEADING3: "### ", BULLETS: "- ",
                    QUOTE: "> "}
        kinds = {HEADING1: r"# ", HEADING2: r"## ", HEADING3: r"### ", BULLETS: r"[-*+]\s+",
                 NUMBERS: r"\d+[.)]\s+", QUOTE: r">\s?"}
        prefix = re.compile(r"^(\s*)(#{1,6}\s+|>\s?|(?:[-*+]|\d+[.)])\s+)?")
        undo = format_ != PARAGRAPH and all(
            re.match(r"\s*" + kinds[format_], b.text()) for b in blocks)
        for number, block in enumerate(blocks, 1):
            match = prefix.match(block.text())
            line = QTextCursor(block)
            line.setPosition(block.position() + len(match.group(1)))
            line.setPosition(block.position() + match.end(), QTextCursor.KeepAnchor)
            line.insertText("" if undo or format_ == PARAGRAPH else
                            f"{number}. " if format_ == NUMBERS else prefixes[format_])
        cursor.setPosition(blocks[0].position())
        cursor.setPosition(blocks[-1].position() + blocks[-1].length() - 1,
                           QTextCursor.KeepAnchor)

    # (the visual editor: character and paragraph formats, as Qt's Markdown reader makes them)
    def _visual_inline(self, cursor: QTextCursor, format_: int) -> None:
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        test = {BOLD: lambda f: f.fontWeight() > QFont.Normal, ITALIC: QTextCharFormat.fontItalic,
                STRIKE: QTextCharFormat.fontStrikeOut, CODE: QTextCharFormat.fontFixedPitch}
        probe = QTextCursor(cursor.document())
        on = True
        for position in range(cursor.selectionStart() + 1, cursor.selectionEnd() + 1):
            probe.setPosition(position)
            if not test[format_](probe.charFormat()):
                on = False
                break
        if not cursor.hasSelection():  # (no word here: what is typed next)
            on = test[format_](self._widget.currentCharFormat())
        fmt = QTextCharFormat()
        if format_ == BOLD:
            fmt.setFontWeight(QFont.Normal if on else QFont.Bold)
        elif format_ == ITALIC:
            fmt.setFontItalic(not on)
        elif format_ == STRIKE:
            fmt.setFontStrikeOut(not on)
        else:
            fmt.setFontFixedPitch(not on)
            fmt.setFontFamilies([self._widget.document().defaultFont().family()] if on else
                                [QFontDatabase.systemFont(QFontDatabase.FixedFont).family()])
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self._widget.mergeCurrentCharFormat(fmt)

    def _visual_blocks(self, cursor: QTextCursor, format_: int) -> None:
        document = self._widget.document()
        first = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        blocks, block = [], first
        while block.isValid():
            blocks.append(block)
            if block == last:
                break
            block = block.next()
        level = {HEADING1: 1, HEADING2: 2, HEADING3: 3}.get(format_, 0)
        style = {BULLETS: QTextListFormat.ListDisc, NUMBERS: QTextListFormat.ListDecimal}
        if level and all(b.blockFormat().headingLevel() == level for b in blocks) or \
                format_ in style and all(b.textList() is not None and
                                         b.textList().format().style() == style[format_]
                                         for b in blocks) or \
                format_ == QUOTE and all(b.blockFormat().intProperty(QTextFormat.BlockQuoteLevel)
                                         for b in blocks):
            format_, level = PARAGRAPH, 0  # (the same again: undone)
        for block in blocks:
            line = QTextCursor(block)
            if block.textList() is not None:
                block.textList().remove(block)
            fmt = block.blockFormat()
            fmt.setIndent(0)
            fmt.setHeadingLevel(level)
            quote = format_ == QUOTE
            fmt.setProperty(QTextFormat.BlockQuoteLevel, 1 if quote else 0)
            fmt.setLeftMargin(_QUOTE_MARGIN if quote else 0)
            fmt.setRightMargin(_QUOTE_MARGIN if quote else 0)
            line.setBlockFormat(fmt)
            line.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            chars = QTextCharFormat()
            chars.setFontWeight(QFont.Bold if level else QFont.Normal)
            chars.setProperty(QTextFormat.FontSizeAdjustment,
                              _HEADING_SIZE - level if level else 0)
            line.mergeCharFormat(chars)
            if not block.text():
                line.mergeBlockCharFormat(chars)
        if format_ in style:
            list_cursor = QTextCursor(document)
            list_cursor.setPosition(blocks[0].position())
            list_cursor.setPosition(blocks[-1].position(), QTextCursor.KeepAnchor)
            list_cursor.createList(style[format_])
        cursor.setPosition(blocks[0].position())
        cursor.setPosition(blocks[-1].position() + blocks[-1].length() - 1,
                           QTextCursor.KeepAnchor)

    # -- files ---------------------------------------------------------------------------------
    def LoadFile(self, FileName) -> None:
        """Show a Markdown file."""
        with open(FileName, encoding="utf-8") as f:
            self.Text = f.read()

    def SaveFile(self, FileName) -> None:
        """Save the Markdown (Text) to a file."""
        with open(FileName, "w", encoding="utf-8") as f:
            f.write(self.Text)


_add_validation(MarkdownBox)
_add_mouse_members(MarkdownBox)

# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["MarkdownBox"] = MarkdownBox
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
