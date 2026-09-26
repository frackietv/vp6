"""Find and Replace in the code window, and Go to Line.

The search itself is plain Python (``SearchOptions``, ``compile_pattern``,
``find_in``, ``replacement``); ``find_as_you_type``, ``find_next``,
``replace_one`` and ``replace_all`` apply it to a ``CodeEditor``;
``FindReplaceDialog`` is the non-modal Edit > Find / Replace window (it
highlights the first match as you type) and ``ask_line`` the Go to Line box.

Options:

* *Match case*, *Whole word*.
* *Regular expressions*: Python ``re`` syntax, one match may span lines.
  Escape sequences such as ``\\n`` (new line) and ``\\t`` work in the find
  and the replace text; groups can be referred to in the find text
  (``(\\w+) \\1``) and in the replace text (``\\1``, ``\\g<1>``,
  ``\\g<name>``). ``^`` and ``$`` match at the start and end of every line.
  Without this option both texts are taken literally.

Replacing never changes the designer region of a form: matches in there are
found, but skipped when replacing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

_ASTRAL = re.compile("[\U00010000-\U0010FFFF]")


@dataclass
class SearchOptions:
    find: str
    replace: str = ""
    match_case: bool = False
    whole_word: bool = False
    regex: bool = False


def compile_pattern(options: SearchOptions) -> re.Pattern:
    """The pattern for these options. Raises re.error for a bad regex."""
    pattern = options.find if options.regex else re.escape(options.find)
    if options.whole_word:
        pattern = rf"(?<!\w)(?:{pattern})(?!\w)"
    flags = re.MULTILINE | (0 if options.match_case else re.IGNORECASE)
    return re.compile(pattern, flags)


def replacement(match: re.Match, options: SearchOptions) -> str:
    """The text replacing a match: a template (groups, escapes) for regular
    expressions, else the replace text as it is."""
    return match.expand(options.replace) if options.regex else options.replace


def find_in(text: str, pattern: re.Pattern, start: int, backward: bool = False,
            skip: tuple[int, int] | None = None) -> tuple[re.Match | None, bool]:
    """The next match from ``start`` (or the previous one before it), wrapping
    around the end of the text. ``skip`` is the current selection, which is
    not found again. Returns (match or None, whether the search wrapped)."""
    matches = list(pattern.finditer(text))

    def usable(match):
        return (match.start(), match.end()) != skip

    if backward:
        before = [m for m in matches if m.start() < start and usable(m)]
        if before:
            return before[-1], False
        after = [m for m in matches if m.start() >= start and usable(m)]
        return (after[-1], True) if after else (None, False)
    for match in matches:
        if match.start() >= start and usable(match):
            return match, False
    for match in matches:
        if match.start() < start and usable(match):
            return match, True
    return None, False


class _Positions:
    """Maps Python string indexes to Qt text positions, which count characters
    outside the Basic Multilingual Plane (e.g. emoji) as two."""

    def __init__(self, text: str):
        self.text = text
        self._wide = _ASTRAL.search(text) is not None

    def to_qt(self, index: int) -> int:
        if not self._wide:
            return index
        return len(self.text[:index].encode("utf-16-le")) // 2

    def from_qt(self, position: int) -> int:
        if not self._wide:
            return position
        count = 0
        for index, char in enumerate(self.text):
            if count >= position:
                return index
            count += 2 if ord(char) > 0xFFFF else 1
        return len(self.text)


# --- on a code editor ---------------------------------------------------------------------------

@dataclass
class Result:
    found: bool
    message: str = ""


def _selection(editor, positions: _Positions) -> tuple[int, int]:
    cursor = editor.textCursor()
    return positions.from_qt(cursor.selectionStart()), positions.from_qt(cursor.selectionEnd())


def find_next(editor, options: SearchOptions, backward: bool = False) -> Result:
    """Select the next (or previous) match in the editor."""
    if not options.find:
        return Result(False, "Enter the text to find")
    try:
        pattern = compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")
    text = editor.document().toPlainText()
    positions = _Positions(text)
    start, end = _selection(editor, positions)
    match, wrapped = find_in(text, pattern, start if backward else end, backward,
                             skip=(start, end))
    if match is None:
        if start != end and pattern.fullmatch(text, start, end):
            return Result(True, "This is the only match")
        return Result(False, f"'{options.find}' was not found")
    editor.select_range(positions.to_qt(match.start()), positions.to_qt(match.end()))
    if wrapped:
        where = "beginning" if backward else "end"
        return Result(True, f"Passed the {where} of the file, continued from the other end")
    return Result(True)


def find_as_you_type(editor, options: SearchOptions) -> Result:
    """Select the first match at or after the start of the selection (the
    cursor), wrapping around: called as the text to find is typed, so the
    match grows with it. Without a match (or text) nothing stays selected."""
    text = editor.document().toPlainText()
    positions = _Positions(text)
    cursor = editor.textCursor()
    start = positions.from_qt(cursor.selectionStart())

    def deselect():
        cursor.setPosition(cursor.selectionStart())
        editor.setTextCursor(cursor)

    if not options.find:
        deselect()
        return Result(False)
    try:
        pattern = compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")  # probably still typing
    match, _wrapped = find_in(text, pattern, start)
    if match is None:
        deselect()
        return Result(False, f"'{options.find}' was not found")
    editor.select_range(positions.to_qt(match.start()), positions.to_qt(match.end()))
    return Result(True)


def replace_one(editor, options: SearchOptions) -> Result:
    """Replace the selection if it is a match, then find the next one."""
    if not options.find:
        return Result(False, "Enter the text to find")
    try:
        pattern = compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")
    text = editor.document().toPlainText()
    positions = _Positions(text)
    start, end = _selection(editor, positions)
    match = pattern.fullmatch(text, start, end) if start != end else None
    if match is not None:
        qt_start, qt_end = positions.to_qt(start), positions.to_qt(end)
        if not editor.range_editable(qt_start, qt_end):
            return Result(False, "The designer region can't be changed here: "
                                 "use the designer and Properties window")
        try:
            new_text = replacement(match, options)
        except (re.error, IndexError) as exc:
            return Result(False, f"Invalid replacement: {exc}")
        cursor = editor.textCursor()
        cursor.insertText(new_text)
        editor.setTextCursor(cursor)  # the cursor is now after the replacement
    return find_next(editor, options)


def replace_all(editor, options: SearchOptions) -> Result:
    """Replace every match (as one undo step), except in the designer region."""
    if not options.find:
        return Result(False, "Enter the text to find")
    try:
        pattern = compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")
    text = editor.document().toPlainText()
    positions = _Positions(text)
    edits, skipped = [], 0
    try:
        for match in pattern.finditer(text):
            start, end = positions.to_qt(match.start()), positions.to_qt(match.end())
            if editor.range_editable(start, end):
                edits.append((start, end, replacement(match, options)))
            else:
                skipped += 1
    except (re.error, IndexError) as exc:
        return Result(False, f"Invalid replacement: {exc}")
    if edits:
        cursor = QTextCursor(editor.document())
        cursor.beginEditBlock()
        for start, end, new_text in reversed(edits):  # later ones first: positions stay valid
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.insertText(new_text)
        cursor.endEditBlock()
    count = len(edits)
    message = f"Replaced {count} occurrence{'s' if count != 1 else ''}"
    if skipped:
        message += f"; skipped {skipped} in the designer region"
    if not edits and not skipped:
        return Result(False, f"'{options.find}' was not found")
    return Result(bool(edits), message)


# --- the dialogs --------------------------------------------------------------------------------

class FindReplaceDialog(QDialog):
    """Edit > Find / Replace: stays open while you work in the code window.

    ``get_editor()`` returns the code editor to search (or None), so the
    dialog always works on the current code window."""

    def __init__(self, get_editor: Callable[[], object], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Find")
        self.setModal(False)
        self._get_editor = get_editor

        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        self.replace_label = QLabel("Re&place with:")
        self.replace_label.setBuddy(self.replace_edit)
        find_label = QLabel("Fi&nd what:")
        find_label.setBuddy(self.find_edit)
        self.match_case = QCheckBox("Match &case")
        self.whole_word = QCheckBox("Find whole &word only")
        self.regex = QCheckBox("Use regular e&xpressions")
        self.regex.setToolTip("Python regular expressions: \\n, \\t and other escapes, "
                              "groups (\\1, \\g<name>) in the find and replace text")
        self.status = QLabel()
        self.status.setWordWrap(True)

        self.find_next_button = QPushButton("&Find Next")
        self.find_previous_button = QPushButton("Find Pre&vious")
        self.replace_button = QPushButton("&Replace")
        self.replace_all_button = QPushButton("Replace &All")
        close_button = QPushButton("Close")
        self.find_next_button.setDefault(True)
        self.find_next_button.clicked.connect(self.find_next)
        self.find_previous_button.clicked.connect(self.find_previous)
        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        close_button.clicked.connect(self.close)

        fields = QGridLayout()
        fields.addWidget(find_label, 0, 0)
        fields.addWidget(self.find_edit, 0, 1)
        fields.addWidget(self.replace_label, 1, 0)
        fields.addWidget(self.replace_edit, 1, 1)
        left = QVBoxLayout()
        left.addLayout(fields)
        for box in (self.match_case, self.whole_word, self.regex):
            left.addWidget(box)
        left.addWidget(self.status)
        left.addStretch(1)
        buttons = QVBoxLayout()
        for button in (self.find_next_button, self.find_previous_button, self.replace_button,
                       self.replace_all_button, close_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(buttons)
        self.find_edit.textChanged.connect(self._on_find_text_changed)
        for box in (self.match_case, self.whole_word, self.regex):
            box.toggled.connect(self._on_option_toggled)
        self.resize(520, 0)

    def _on_find_text_changed(self, _text: str) -> None:
        self._run(find_as_you_type)  # highlight the first match while typing

    def _on_option_toggled(self, _checked: bool) -> None:
        if self.find_edit.text():
            self._run(find_as_you_type)

    def options(self) -> SearchOptions:
        return SearchOptions(self.find_edit.text(), self.replace_edit.text(),
                             self.match_case.isChecked(), self.whole_word.isChecked(),
                             self.regex.isChecked())

    def show_find(self, replace: bool = False) -> None:
        """Open as Find, or as Replace; the selected text (one line) is the
        text to find."""
        self.setWindowTitle("Replace" if replace else "Find")
        for widget in (self.replace_label, self.replace_edit, self.replace_button,
                       self.replace_all_button):
            widget.setVisible(replace)
        self.status.clear()
        editor = self._get_editor()
        if editor is not None:
            selected = editor.textCursor().selectedText()
            if selected and " " not in selected:  # Qt's paragraph separator
                self.find_edit.setText(re.escape(selected) if self.regex.isChecked()
                                       else selected)
        self.show()
        self.raise_()
        self.activateWindow()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def _run(self, action) -> Result:
        editor = self._get_editor()
        if editor is None:
            result = Result(False, "Open a code window to search in")
        else:
            result = action(editor, self.options())
        self.status.setText(result.message)
        return result

    def find_next(self) -> Result:
        return self._run(find_next)

    def find_previous(self) -> Result:
        return self._run(lambda editor, options: find_next(editor, options, backward=True))

    def replace(self) -> Result:
        return self._run(replace_one)

    def replace_all(self) -> Result:
        return self._run(replace_all)


def ask_line(editor, parent: QWidget | None = None) -> int | None:
    """Edit > Go to Line: ask for a line number (the current line is
    suggested). Returns it, or None if cancelled."""
    count = editor.document().blockCount()
    line, ok = QInputDialog.getInt(parent, "Go to Line", f"Line number (1 - {count}):",
                                   editor.current_line(), 1, count, 1)
    return line if ok else None
