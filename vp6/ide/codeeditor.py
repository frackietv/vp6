"""Code window: Python editor with the VB Object / Procedure dropdowns."""

from __future__ import annotations

import builtins
import keyword
import re

from PySide6.QtCore import QRect, QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QKeySequence, QPainter, QPalette, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QApplication, QComboBox, QCompleter, QHBoxLayout, QPlainTextEdit,
                               QTextEdit, QVBoxLayout, QWidget)

import vp6

from .. import formfile
from ..controls import CONTROL_TYPES, EVENT_ARGS, ControlArray
from ..form import Form
from .documents import Document, FormDocument
from .theme import Theme, TextStyle, theme_manager

INDENT = "    "
GENERAL = "(General)"
DECLARATIONS = "(Declarations)"

_VP6_NAMES = set(vp6.__all__)
_BUILTINS = {n for n in dir(builtins) if not n.startswith("_")} - set(keyword.kwlist)


def code_font() -> QFont:
    """The code font chosen in Tools > Options."""
    return theme_manager().font()


def _fmt(style: TextStyle) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(style.color))
    if style.bold:
        fmt.setFontWeight(QFont.Bold)
    if style.italic:
        fmt.setFontItalic(True)
    return fmt


class PythonHighlighter(QSyntaxHighlighter):
    """Python highlighting with colors from the current editor theme.

    With ``follow_theme=False`` (the Options preview) call ``set_theme``
    yourself."""

    IN_SINGLE, IN_DOUBLE, IN_REGION = 1, 2, 4

    def __init__(self, document, follow_theme: bool = True):
        super().__init__(document)
        self.formats: dict[str, QTextCharFormat] = {}
        self.region_background = QColor()
        self.set_theme(theme_manager().current(), rehighlight=False)
        if follow_theme:
            theme_manager().changed.connect(self._on_theme_changed)
        words = "|".join(keyword.kwlist + ["match", "case"])
        self.rules = [
            (re.compile(r"\b(?:%s)\b" % words), "keyword"),
            (re.compile(r"\b(?:%s)\b" % "|".join(sorted(_VP6_NAMES, key=len, reverse=True))),
             "vp6"),
            (re.compile(r"\b(?:%s)\b" % "|".join(_BUILTINS)), "builtin"),
            (re.compile(r"\bself\b"), "self"),
            (re.compile(r"\b(?:0[xX][0-9a-fA-F_]+|\d[\d_]*\.?\d*(?:[eE][+-]?\d+)?)\b"),
             "number"),
            (re.compile(r"^\s*@\w+"), "decorator"),
        ]
        self.def_re = re.compile(r"\b(?:def|class)\s+(\w+)")
        self.string_re = re.compile(
            r"""[rRbBuUfF]{0,2}("[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*')""")

    def set_theme(self, theme: Theme, rehighlight: bool = True) -> None:
        self.formats = {key: _fmt(style) for key, style in theme.syntax.items()}
        self.region_background = QColor(theme.colors["designer_region"])
        if rehighlight:
            self.rehighlight()

    def _on_theme_changed(self) -> None:
        self.set_theme(theme_manager().current())

    def highlightBlock(self, text: str) -> None:
        previous = max(self.previousBlockState(), 0)
        in_region = bool(previous & self.IN_REGION)
        if formfile._START_RE.match(text):
            in_region = True
        region_now = in_region
        if region_now:
            fmt = QTextCharFormat()
            fmt.setBackground(self.region_background)
            self.setFormat(0, len(text), fmt)
        next_region = in_region and not formfile._END_RE.match(text)

        for pattern, name in self.rules:
            for match in pattern.finditer(text):
                self._apply(match.start(), match.end() - match.start(), name, region_now)
        for match in self.def_re.finditer(text):
            self._apply(match.start(1), len(match.group(1)), "defname", region_now)

        # strings and comments (single-line), skipping inside triple quotes
        state = previous & (self.IN_SINGLE | self.IN_DOUBLE)
        index = 0
        if state:
            delimiter = "'''" if state == self.IN_SINGLE else '"""'
            end = text.find(delimiter)
            if end == -1:
                self._apply(0, len(text), "string", region_now)
                self.setCurrentBlockState(state | (self.IN_REGION if next_region else 0))
                return
            self._apply(0, end + 3, "string", region_now)
            index = end + 3
            state = 0
        while index < len(text):
            char = text[index]
            if char == "#":
                self._apply(index, len(text) - index, "comment", region_now)
                break
            if text.startswith(('"""', "'''"), index):
                delimiter = text[index:index + 3]
                end = text.find(delimiter, index + 3)
                if end == -1:
                    self._apply(index, len(text) - index, "string", region_now)
                    state = self.IN_SINGLE if delimiter == "'''" else self.IN_DOUBLE
                    break
                self._apply(index, end + 3 - index, "string", region_now)
                index = end + 3
                continue
            if char in "\"'":
                match = self.string_re.match(text, index)
                if match:
                    self._apply(index, match.end() - index, "string", region_now)
                    index = match.end()
                    continue
            index += 1
        self.setCurrentBlockState(state | (self.IN_REGION if next_region else 0))

    def _apply(self, start, length, name, region):
        fmt = QTextCharFormat(self.formats[name])
        if region:
            fmt.setBackground(self.region_background)
        self.setFormat(start, length, fmt)


class _LineNumbers(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)

    def mousePressEvent(self, event):
        self.editor.gutter_clicked(event.position().toPoint())


class CodeEditor(QPlainTextEdit):
    """Python editor with auto-indent, completion and a protected, foldable
    designer region."""

    def __init__(self, document: Document, completion_provider=None, parent=None,
                 follow_theme: bool = True):
        super().__init__(parent)
        self.doc = document
        self.setDocument(document.text_document)
        if getattr(document, "highlighter", None) is None:
            document.highlighter = PythonHighlighter(document.text_document, follow_theme)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.gutter = _LineNumbers(self)
        self.theme: Theme = theme_manager().current()
        self.apply_theme(self.theme, theme_manager().font())
        if follow_theme:
            theme_manager().changed.connect(self._on_theme_changed)
        self.region_folded = True
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_gutter_width()
        self._highlight_current_line()

        self.completion_provider = completion_provider
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setModel(QStringListModel([], self.completer))
        self.completer.activated.connect(self._insert_completion)

        if isinstance(document, FormDocument):
            self.document().contentsChange.connect(self._on_contents_change)
            QTimer.singleShot(0, self, self.apply_fold)  # cancelled if deleted

    # -- theme -------------------------------------------------------------------------------
    def apply_theme(self, theme: Theme, font: QFont) -> None:
        self.theme = theme
        colors = theme.colors
        palette = self.palette()
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            palette.setColor(group, QPalette.Base, QColor(colors["background"]))
            palette.setColor(group, QPalette.Text, QColor(colors["foreground"]))
            palette.setColor(group, QPalette.Highlight, QColor(colors["selection_background"]))
            palette.setColor(group, QPalette.HighlightedText,
                             QColor(colors["selection_foreground"]))
        self.setPalette(palette)
        self.viewport().setPalette(palette)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self._update_gutter_width()
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(),
                                      rect.height()))
        self._highlight_current_line()
        self.gutter.update()
        self.viewport().update()

    def _on_theme_changed(self) -> None:
        self.apply_theme(theme_manager().current(), theme_manager().font())

    # -- gutter -----------------------------------------------------------------------------
    def gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 18 + self.fontMetrics().horizontalAdvance("9") * max(digits, 3)

    def _update_gutter_width(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(),
                                      rect.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        colors = self.theme.colors
        painter.fillRect(event.rect(), QColor(colors["gutter_background"]))
        region = self._region_blocks()
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(self.blockBoundingRect(block).height())
            if block.isVisible() and bottom >= event.rect().top():
                number = block.blockNumber()
                painter.setPen(QColor(colors["gutter_foreground"]))
                painter.drawText(0, top, self.gutter.width() - 14, height, Qt.AlignRight,
                                 str(number + 1))
                if region and number == region[0]:
                    box = QRect(self.gutter.width() - 12, top + (height - 9) // 2, 9, 9)
                    painter.setPen(QColor(colors["fold_marker"]))
                    painter.setBrush(QColor(colors["gutter_background"]))
                    painter.drawRect(box)
                    c = box.center()
                    painter.drawLine(c.x() - 2, c.y(), c.x() + 2, c.y())
                    if self.region_folded:
                        painter.drawLine(c.x(), c.y() - 2, c.x(), c.y() + 2)
            block = block.next()
            top = bottom

    def gutter_clicked(self, pos):
        region = self._region_blocks()
        if not region:
            return
        cursor = self.cursorForPosition(pos)
        if cursor.blockNumber() == region[0]:
            self.region_folded = not self.region_folded
            self.apply_fold()

    def _highlight_current_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(self.theme.colors["current_line"]))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    # -- designer region: folding and protection ----------------------------------------------------
    def _region_blocks(self) -> tuple[int, int] | None:
        if isinstance(self.doc, FormDocument):
            return self.doc.region_range()
        return None

    def apply_fold(self):
        region = self._region_blocks()
        if not region:
            return
        document = self.document()
        start, end = region
        changed = False
        for number in range(start + 1, end + 1):
            block = document.findBlockByNumber(number)
            if block.isVisible() == self.region_folded:
                block.setVisible(not self.region_folded)
                changed = True
        if changed:
            first = document.findBlockByNumber(start)
            last = document.findBlockByNumber(end)
            document.markContentsDirty(first.position(),
                                       last.position() + last.length() - first.position())
            self.viewport().update()
            self.gutter.update()
            self.ensureCursorVisible()

    def _on_contents_change(self, *_):
        if self.region_folded:
            QTimer.singleShot(0, self, self.apply_fold)  # cancelled if deleted

    def _region_span(self) -> tuple[int, int] | None:
        region = self._region_blocks()
        if not region:
            return None
        document = self.document()
        first = document.findBlockByNumber(region[0])
        last = document.findBlockByNumber(region[1])
        return first.position(), last.position() + last.length() - 1

    def _edit_allowed(self, key: int | None = None) -> bool:
        span = self._region_span()
        if span is None:
            return True
        start, end = span
        cursor = self.textCursor()
        a, b = cursor.selectionStart(), cursor.selectionEnd()
        if a == b:
            if key == Qt.Key_Backspace:
                a -= 1
            elif key == Qt.Key_Delete:
                b += 1
            elif key in (Qt.Key_Return, Qt.Key_Enter) and a in (start, end):
                return True  # a new line before/after the region is harmless
        return b < start or a > end

    def range_editable(self, start: int, end: int) -> bool:
        """Whether text between these positions may be changed (it isn't in
        the protected designer region)."""
        span = self._region_span()
        return span is None or end < span[0] or start > span[1]

    def _reject_edit(self):
        QApplication.beep()
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(
                "The designer region is maintained by the form designer - "
                "use the designer and Properties window to change it.", 4000)

    def insertFromMimeData(self, source):
        if self._edit_allowed():
            super().insertFromMimeData(source)
        else:
            self._reject_edit()

    def cut(self):
        if self._edit_allowed():
            super().cut()
        else:
            self._reject_edit()

    def paste(self):
        if self._edit_allowed():
            super().paste()
        else:
            self._reject_edit()

    # -- keyboard -------------------------------------------------------------------------------------------
    def keyPressEvent(self, event):
        popup = self.completer.popup()
        if popup.isVisible() and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab,
                                                 Qt.Key_Escape, Qt.Key_Backtab):
            if event.key() == Qt.Key_Escape:
                popup.hide()
            else:
                index = popup.currentIndex()
                if index.isValid():
                    self._insert_completion(index.data())
                popup.hide()
            return

        key = event.key()
        modifies = bool(event.text()) or key in (Qt.Key_Backspace, Qt.Key_Delete) or \
            event.matches(QKeySequence.Cut) or event.matches(QKeySequence.Paste)
        is_navigation = event.modifiers() & Qt.ControlModifier and not (
            event.matches(QKeySequence.Cut) or event.matches(QKeySequence.Paste))
        if modifies and not is_navigation and not self._edit_allowed(key):
            self._reject_edit()
            return

        if event.matches(QKeySequence.Undo) or event.matches(QKeySequence.Redo):
            super().keyPressEvent(event)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self._newline_with_indent()
            return
        if key == Qt.Key_Tab and not event.modifiers():
            self._indent(True)
            return
        if key == Qt.Key_Backtab:
            self._indent(False)
            return
        if key == Qt.Key_Backspace and self._smart_backspace():
            return
        if key == Qt.Key_Slash and event.modifiers() & Qt.ControlModifier:
            self.toggle_comment()
            return
        if key == Qt.Key_Space and event.modifiers() & Qt.ControlModifier:
            self._show_completions(force=True)
            return

        super().keyPressEvent(event)
        if event.text() and (event.text().isalnum() or event.text() in "._"):
            self._show_completions(force=False)
        elif popup.isVisible():
            popup.hide()

    def _newline_with_indent(self):
        cursor = self.textCursor()
        line = cursor.block().text()[:cursor.positionInBlock()]
        indent = line[:len(line) - len(line.lstrip())]
        stripped = line.strip()
        if stripped.endswith(":"):
            indent += INDENT
        elif stripped.split(" ")[0] in ("return", "pass", "break", "continue", "raise") \
                and len(indent) >= len(INDENT):
            indent = indent[:-len(INDENT)]
        cursor.insertText("\n" + indent)
        self.ensureCursorVisible()

    def _indent(self, forward: bool):
        cursor = self.textCursor()
        if not cursor.hasSelection() and forward:
            column = cursor.positionInBlock()
            cursor.insertText(" " * (len(INDENT) - column % len(INDENT)))
            return
        start = self.document().findBlock(cursor.selectionStart()).blockNumber()
        end_cursor = QTextCursor(self.document())
        end_cursor.setPosition(cursor.selectionEnd())
        end = end_cursor.blockNumber()
        if cursor.hasSelection() and end_cursor.positionInBlock() == 0 and end > start:
            end -= 1
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        for number in range(start, end + 1):
            block = self.document().findBlockByNumber(number)
            edit.setPosition(block.position())
            if forward:
                edit.insertText(INDENT)
            else:
                text = block.text()
                remove = len(text) - len(text.lstrip(" "))
                remove = min(remove, len(INDENT))
                edit.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, remove)
                edit.removeSelectedText()
        edit.endEditBlock()

    def _smart_backspace(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        before = cursor.block().text()[:cursor.positionInBlock()]
        if before and not before.strip(" ") and len(before) % len(INDENT) == 0:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(INDENT))
            cursor.removeSelectedText()
            return True
        return False

    def toggle_comment(self):
        cursor = self.textCursor()
        start = self.document().findBlock(cursor.selectionStart()).blockNumber()
        end = self.document().findBlock(cursor.selectionEnd()).blockNumber()
        blocks = [self.document().findBlockByNumber(n) for n in range(start, end + 1)]
        if not self._edit_allowed():
            self._reject_edit()
            return
        texts = [b.text() for b in blocks if b.text().strip()]
        uncomment = texts and all(t.lstrip().startswith("#") for t in texts)
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        indent = min((len(t) - len(t.lstrip()) for t in texts), default=0)
        for block in blocks:
            text = block.text()
            if not text.strip():
                continue
            edit.setPosition(block.position())
            if uncomment:
                offset = text.index("#")
                edit.setPosition(block.position() + offset)
                length = 2 if text[offset:offset + 2] == "# " else 1
                edit.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, length)
                edit.removeSelectedText()
            else:
                edit.setPosition(block.position() + indent)
                edit.insertText("# ")
        edit.endEditBlock()

    # -- completion ------------------------------------------------------------------------------------------
    def _show_completions(self, force: bool):
        if self.completion_provider is None:
            return
        cursor = self.textCursor()
        line = cursor.block().text()[:cursor.positionInBlock()]
        match = re.search(r"([\w.]*?)(\w*)$", line)
        context, prefix = match.group(1), match.group(2)
        if not force and not context.endswith(".") and len(prefix) < 3:
            self.completer.popup().hide()
            return
        words = self.completion_provider(context, self.doc)
        if not words:
            self.completer.popup().hide()
            return
        self.completer.model().setStringList(sorted(set(words), key=str.lower))
        self.completer.setCompletionPrefix(prefix)
        if self.completer.completionCount() == 0 or (
                self.completer.completionCount() == 1 and
                self.completer.currentCompletion() == prefix):
            self.completer.popup().hide()
            return
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(self.completer.popup().sizeHintForColumn(0) +
                      self.completer.popup().verticalScrollBar().sizeHint().width() + 24)
        self.completer.complete(rect)

    def _insert_completion(self, word: str):
        cursor = self.textCursor()
        prefix = self.completer.completionPrefix()
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
        cursor.insertText(word)
        self.setTextCursor(cursor)

    def _unfold_for(self, block_number: int) -> None:
        """Unfold the designer region if the block is hidden in it."""
        region = self._region_blocks()
        if region and region[0] < block_number <= region[1] and self.region_folded:
            self.region_folded = False
            self.apply_fold()

    def goto_line(self, line: int):
        block = self.document().findBlockByNumber(max(line - 1, 0))
        self._unfold_for(block.blockNumber())
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()

    def select_range(self, start: int, end: int) -> None:
        """Select the text between two positions and scroll to it (unfolding
        the designer region if it's in there)."""
        document = self.document()
        for position in (start, end):
            self._unfold_for(document.findBlock(position).blockNumber())
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

    def current_line(self) -> int:
        """The 1-based line of the cursor."""
        return self.textCursor().blockNumber() + 1


# --- completion data --------------------------------------------------------------------------

def _members(cls) -> list[str]:
    names = set(getattr(cls, "_specs", {}))
    for klass in cls.__mro__:
        for name in vars(klass):
            if name[:1].isupper() and not name.startswith("_"):
                names.add(name)
    return sorted(names)


def complete(context: str, document: Document) -> list[str]:
    """Completion candidates for the text before the cursor.

    ``self.``          -> the form's controls and members
    ``self.Command1.`` -> the members of a CommandButton
    anything else      -> vp6 names, keywords, builtins and words in the file
    """
    form_def = document.form_def if isinstance(document, FormDocument) else None
    if context == "self.":
        names = _members(Form)
        if form_def:
            names += list(dict.fromkeys(c.name for c in form_def.controls))
        return names
    # self.Command1. or, for a control array, self.cmdDigit. / self.cmdDigit[i]. / (i).
    match = re.fullmatch(r"self\.(\w+)(\[[^\]]*\]|\([^)]*\))?\.", context)
    if match and form_def:
        elements = form_def.elements(match.group(1))
        if not elements:
            return []
        if form_def.is_array(match.group(1)) and not match.group(2):
            return _members(ControlArray)
        return _members(CONTROL_TYPES[elements[0].type])
    if context.endswith("."):
        return []
    words = set(re.findall(r"\b[A-Za-z_]\w{2,}\b", document.text))
    return sorted(_VP6_NAMES | set(keyword.kwlist) | _BUILTINS | words)


class CodeWindow(QWidget):
    """The code window of a form or module."""

    statusMessage = Signal(str)

    def __init__(self, document: Document, parent=None):
        super().__init__(parent)
        self.doc = document
        self.object_combo = QComboBox()
        self.proc_combo = QComboBox()
        self.object_combo.setMinimumContentsLength(18)
        self.proc_combo.setMinimumContentsLength(18)
        self.editor = CodeEditor(document, complete)
        top = QHBoxLayout()
        top.setContentsMargins(2, 2, 2, 2)
        top.addWidget(self.object_combo, 1)
        top.addWidget(self.proc_combo, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(self.editor)

        self._syncing = False
        self.object_combo.activated.connect(self._on_object_chosen)
        self.proc_combo.activated.connect(self._on_proc_chosen)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self.refresh_combos)
        document.text_document.contentsChanged.connect(self._refresh_timer.start)
        self.editor.cursorPositionChanged.connect(self._sync_combos_to_cursor)
        self.refresh_combos()

    # -- objects and procedures ------------------------------------------------------------------
    def _objects(self) -> list[tuple[str, tuple[str, ...]]]:
        """(object name, events) - 'Form' for the form itself."""
        result = []
        if isinstance(self.doc, FormDocument):
            result.append(("Form", Form.Events))
            controls = {c.name: c for c in self.doc.form_def.controls}  # arrays: once
            for name in sorted(controls, key=str.lower):
                result.append((name, CONTROL_TYPES[controls[name].type].Events))
        return result

    def _events_of(self, obj: str) -> tuple[str, ...]:
        return next((events for name, events in self._objects() if name == obj), ())

    def _general_procs(self) -> list[str]:
        handlers = {f"{obj}_{event}" for obj, events in self._objects() for event in events}
        return [m for m in dict.fromkeys(formfile.defined_methods(self.doc.text) +
                                         re.findall(r"^def\s+(\w+)", self.doc.text, re.M))
                if m not in handlers and m != "InitializeComponent"]

    def refresh_combos(self) -> None:
        self._syncing = True
        current = self.object_combo.currentText() or GENERAL
        self.object_combo.clear()
        self.object_combo.addItem(GENERAL)
        for name, _ in self._objects():
            self.object_combo.addItem(name)
        index = self.object_combo.findText(current)
        self.object_combo.setCurrentIndex(max(index, 0))
        self._fill_procs()
        self._syncing = False
        self._sync_combos_to_cursor()

    def _fill_procs(self) -> None:
        obj = self.object_combo.currentText()
        current = self.proc_combo.currentText()
        self.proc_combo.clear()
        if obj == GENERAL:
            self.proc_combo.addItem(DECLARATIONS)
            for proc in self._general_procs():
                self.proc_combo.addItem(proc)
        else:
            existing = set(formfile.defined_methods(self.doc.text))
            bold = QFont(self.proc_combo.font())
            bold.setBold(True)
            for event in self._events_of(obj):
                self.proc_combo.addItem(event)
                if f"{obj}_{event}" in existing:
                    self.proc_combo.setItemData(self.proc_combo.count() - 1, bold, Qt.FontRole)
        index = self.proc_combo.findText(current)
        self.proc_combo.setCurrentIndex(max(index, 0))

    def _on_object_chosen(self, _index) -> None:
        self._syncing = True
        self._fill_procs()
        self._syncing = False
        obj = self.object_combo.currentText()
        if obj == GENERAL:
            return
        # Like VB: choosing an object jumps to (or creates) its default event
        existing = [e for e in self._events_of(obj)
                    if f"{obj}_{e}" in formfile.defined_methods(self.doc.text)]
        if existing:
            self.goto_event(obj, existing[0])
        else:
            default = Form.DefaultEvent if obj == "Form" else \
                CONTROL_TYPES[self.doc.form_def.elements(obj)[0].type].DefaultEvent
            self.goto_event(obj, default)

    def _on_proc_chosen(self, _index) -> None:
        obj, proc = self.object_combo.currentText(), self.proc_combo.currentText()
        if obj == GENERAL:
            if proc == DECLARATIONS:
                self.editor.goto_line(1)
            else:
                self._goto_def(proc)
        else:
            self.goto_event(obj, proc)

    def _goto_def(self, name: str) -> bool:
        match = re.search(rf"^[ \t]*def\s+{re.escape(name)}\s*\(", self.doc.text, re.M)
        if not match:
            return False
        line = self.doc.text.count("\n", 0, match.start()) + 1
        block = self.editor.document().findBlockByNumber(line)  # first body line
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor,
                            len(block.text()) - len(block.text().lstrip()))
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()
        self.editor.setFocus()
        return True

    def goto_event(self, obj: str, event: str) -> None:
        """Jump to ``obj_event`` - creating the handler stub if needed."""
        if not event:  # an object without events (a Line): nothing to jump to
            return
        handler = f"{obj}_{event}"
        if self._goto_def(handler):
            return
        if not isinstance(self.doc, FormDocument):
            return
        stub = formfile.event_stub(obj, event, EVENT_ARGS.get(event, ""),
                                   index=self.doc.form_def.is_array(obj))
        line = self._class_end_line()
        document = self.editor.document()
        block = document.findBlockByNumber(line)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.beginEditBlock()
        cursor.insertText("\n\n" + stub.rstrip("\n"))
        cursor.endEditBlock()
        # Select 'pass' so typing replaces it
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.NextWord)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()
        self.editor.setFocus()
        self.refresh_combos()

    def _class_end_line(self) -> int:
        """Index of the last non-blank line of the form class body."""
        lines = self.doc.text.split("\n")
        class_name = self.doc.name
        start = next((i for i, l in enumerate(lines)
                      if re.match(rf"class\s+{re.escape(class_name)}\b", l)), 0)
        last = start
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip() and not line[0].isspace() and not line.startswith("#"):
                break
            if line.strip():
                last = i
        return last

    def _sync_combos_to_cursor(self) -> None:
        if self._syncing:
            return
        block = self.editor.textCursor().block()
        name = None
        while block.isValid():
            match = re.match(r"^\s*def\s+(\w+)\s*\(", block.text())
            if match:
                name = match.group(1)
                break
            if block.text().strip() and not block.text()[0].isspace() and \
                    not block.text().startswith(("#", "@")):
                break  # reached module level code
            block = block.previous()
        obj, proc = GENERAL, DECLARATIONS
        if name:
            obj, proc = GENERAL, name
            for candidate, events in self._objects():
                prefix = candidate + "_"
                if name.startswith(prefix) and name[len(prefix):] in events:
                    obj, proc = candidate, name[len(prefix):]
                    break
        self._syncing = True
        if self.object_combo.currentText() != obj:
            self.object_combo.setCurrentIndex(max(self.object_combo.findText(obj), 0))
            self._fill_procs()
        index = self.proc_combo.findText(proc)
        if index >= 0:
            self.proc_combo.setCurrentIndex(index)
        self._syncing = False
