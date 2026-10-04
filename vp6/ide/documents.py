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
    breakpointsChanged = Signal()
    executionChanged = Signal()  # (where the program is paused: execution_line)

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
        # Breakpoints keep a cursor at the start of their lines: they follow the edits
        self._breakpoints: list[_Breakpoint] = []
        # Where the program is paused: a cursor too (edited in break mode, it follows)
        self._execution: QTextCursor | None = None
        self.execution_error = False  # (paused there by an error)

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

    def replace_text(self, text: str) -> None:
        """Replace the whole text as one undoable edit (used for renames)."""
        if text == self.text:
            return
        breakpoints = self.breakpoints()  # (the lines stay: a rename keeps them)
        cursor = QTextCursor(self.text_document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        if breakpoints:
            self._breakpoints = []
            for line, enabled in breakpoints:
                self.set_breakpoint(line, True, notify=False, enabled=enabled)
            self.breakpointsChanged.emit()

    # -- breakpoints and the execution point ------------------------------------------------
    def breakpoints(self) -> list[tuple[int, bool]]:
        """(line (1-based), enabled) of each breakpoint, in line order (one a
        line: lines joined by an edit keep the first's)."""
        lines: dict[int, bool] = {}
        for breakpoint in self._breakpoints:
            lines.setdefault(breakpoint.line, breakpoint.enabled)
        return sorted(lines.items())

    def breakpoint_lines(self, enabled_only: bool = False) -> list[int]:
        """The lines (1-based) with a breakpoint (enabled ones only: those the
        program stops at)."""
        return [line for line, enabled in self.breakpoints() if enabled or not enabled_only]

    def has_breakpoint(self, line: int) -> bool:
        return line in self.breakpoint_lines()

    def breakpoint_enabled(self, line: int) -> bool:
        return dict(self.breakpoints()).get(line, False)

    def set_breakpoint(self, line: int, on: bool, notify: bool = True,
                       enabled: bool = True) -> None:
        block = self.text_document.findBlockByNumber(line - 1)
        if not block.isValid():
            return
        self._breakpoints = [b for b in self._breakpoints if b.line != line]
        if on:
            self._breakpoints.append(_Breakpoint(QTextCursor(block), enabled))
        if notify:
            self.breakpointsChanged.emit()

    def enable_breakpoint(self, line: int, enabled: bool) -> None:
        """Enable or disable a line's breakpoint (a disabled one stays, but
        the program doesn't stop there)."""
        changed = False
        for breakpoint in self._breakpoints:
            if breakpoint.line == line and breakpoint.enabled != enabled:
                breakpoint.enabled = enabled
                changed = True
        if changed:
            self.breakpointsChanged.emit()

    def toggle_breakpoint(self, line: int) -> bool:
        """Set or clear the breakpoint on a line; True if it now has one."""
        on = not self.has_breakpoint(line)
        self.set_breakpoint(line, on)
        return on

    def clear_breakpoints(self) -> None:
        if self._breakpoints:
            self._breakpoints = []
            self.breakpointsChanged.emit()

    def can_break_at(self, line: int) -> bool:
        """Whether a line is code a breakpoint can stop at (not blank, not a
        comment)."""
        block = self.text_document.findBlockByNumber(line - 1)
        text = block.text().strip() if block.isValid() else ""
        return bool(text) and not text.startswith("#")

    @property
    def execution_line(self) -> int | None:
        """The line (1-based) where the program is paused, as it moves with the
        edits; None when it isn't paused in this file."""
        return None if self._execution is None else self._execution.blockNumber() + 1

    def set_execution_line(self, line: int | None, error: bool = False) -> None:
        if (line, error) == (self.execution_line, self.execution_error):
            return
        block = self.text_document.findBlockByNumber(line - 1) if line else None
        self._execution = QTextCursor(block) if block is not None and block.isValid() \
            else None
        self.execution_error = error
        self.executionChanged.emit()

    def save(self) -> None:
        text = self.text
        if not text.endswith("\n"):
            text += "\n"
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)
        self.text_document.setModified(False)


class _Breakpoint:
    """A breakpoint: a cursor at the start of its line, and whether it is on."""

    __slots__ = ("cursor", "enabled")

    def __init__(self, cursor: QTextCursor, enabled: bool = True):
        self.cursor, self.enabled = cursor, enabled

    @property
    def line(self) -> int:
        return self.cursor.blockNumber() + 1


class FormDocument(Document):
    """A form's (or a user control's) file. ``form_def`` mirrors the designer
    region."""
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
    def kind(self) -> str:
        """"form", or "usercontrol" for a UserControl's file."""
        return self.form_def.kind

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
        imports = self._missing_imports()
        if cursor.selectedText().replace(" ", "\n") == new_text and not imports:
            return
        self._updating = True
        try:
            cursor.beginEditBlock()
            cursor.insertText(new_text)
            for line, statement in sorted(imports, reverse=True):  # (above the region)
                block = self.text_document.findBlockByNumber(line)
                at = QTextCursor(self.text_document)
                if block.isValid():
                    at.setPosition(block.position())
                    at.insertText(statement + "\n")
                else:
                    at.movePosition(QTextCursor.End)
                    at.insertText("\n" + statement)
            cursor.endEditBlock()
        finally:
            self._updating = False

    def _missing_imports(self) -> list[tuple[int, str]]:
        """The imports the file needs for the user controls on it (each from
        its own module), with the lines they go to."""
        from ..controls import CONTROL_TYPES
        from ..usercontrol import UserControl

        insertions, text = [], self.text
        for type_name in dict.fromkeys(c.type for c in self.form_def.controls):
            cls = CONTROL_TYPES.get(type_name)
            if cls is None or not issubclass(cls, UserControl):
                continue
            insertion = formfile.import_insertion(text, cls.__module__, type_name)
            if insertion is not None and insertion[1] not in (s for _, s in insertions):
                insertions.append(insertion)
        return insertions

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
