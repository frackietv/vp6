"""Open files. Each document owns a QTextDocument that is the single source of
truth for the file's text; for forms the designer edits the designer region
inside that text."""

from __future__ import annotations

import copy
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QPlainTextDocumentLayout

from .. import formfile
from ..formfile import FormDef, FormFileError


class Document(QObject):
    kind = "module"
    modifiedChanged = Signal(bool)

    def __init__(self, path: str, text: str | None = None):
        super().__init__()
        self.path = os.path.abspath(path)
        if text is None:
            with open(self.path, encoding="utf-8") as f:
                text = f.read()
        self.text_document = QTextDocument(self)
        self.text_document.setDocumentLayout(QPlainTextDocumentLayout(self.text_document))
        self.text_document.setPlainText(text)
        self.text_document.setModified(False)
        self.text_document.modificationChanged.connect(self.modifiedChanged)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def name(self) -> str:
        return os.path.splitext(self.filename)[0]

    @property
    def text(self) -> str:
        return self.text_document.toPlainText()

    @property
    def modified(self) -> bool:
        return self.text_document.isModified()

    def save(self) -> None:
        text = self.text
        if not text.endswith("\n"):
            text += "\n"
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)
        self.text_document.setModified(False)


class FormDocument(Document):
    """A form file. ``form_def`` mirrors the designer region."""

    kind = "form"
    # Emitted when the region changed from the text side (undo in the code
    # window, file reload): the designer must rebuild itself.
    designReloaded = Signal()
    parseError = Signal(str)

    def __init__(self, path: str, text: str | None = None):
        super().__init__(path, text)
        self._updating = False
        self.form_def: FormDef = formfile.parse(self.text)
        self.text_document.contentsChanged.connect(self._on_text_changed)

    @property
    def name(self) -> str:
        return formfile.find_form_class(self.text) or self.form_def.class_name

    def region_range(self) -> tuple[int, int] | None:
        """(first_block, last_block) of the designer region."""
        try:
            return formfile.find_region(self.text)
        except FormFileError:
            return None

    def set_form_def(self, form_def: FormDef) -> None:
        """Regenerate the designer region from ``form_def``."""
        self.form_def = copy.deepcopy(form_def)
        region = self.region_range()
        if region is None:
            return
        start, end = region
        indent = self.text_document.findBlockByNumber(start).text()
        indent = indent[:len(indent) - len(indent.lstrip())] or "    "
        new_text = formfile.generate_region(self.form_def, indent)
        first = self.text_document.findBlockByNumber(start)
        last = self.text_document.findBlockByNumber(end)
        cursor = QTextCursor(self.text_document)
        cursor.setPosition(first.position())
        cursor.setPosition(last.position() + last.length() - 1, QTextCursor.KeepAnchor)
        if cursor.selectedText().replace(" ", "\n") == new_text:
            return
        self._updating = True
        try:
            cursor.beginEditBlock()
            cursor.insertText(new_text)
            cursor.endEditBlock()
        finally:
            self._updating = False

    def replace_text(self, text: str) -> None:
        """Replace the whole text as one undoable edit (used for renames)."""
        if text == self.text:
            return
        cursor = QTextCursor(self.text_document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(text)
        cursor.endEditBlock()

    def _on_text_changed(self) -> None:
        if self._updating:
            return
        try:
            parsed = formfile.parse(self.text)
        except FormFileError as exc:
            self.parseError.emit(str(exc))
            return
        if parsed != self.form_def:
            self.form_def = parsed
            self.designReloaded.emit()


def open_document(path: str) -> Document:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if formfile.is_form_source(text):
        return FormDocument(path, text)
    return Document(path, text)
