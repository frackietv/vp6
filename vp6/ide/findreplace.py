"""Find and Replace in the code window or the whole project, and Go to Line.

The search itself is plain Python (``SearchOptions``, ``compile_pattern``,
``find_in``, ``replacement``); ``find_as_you_type``, ``find_next``,
``replace_one`` and ``replace_all`` apply it to a ``CodeEditor``;
``find_next_in_project``, ``find_all``, ``replace_one_in_project`` and
``replace_all_in_project`` to every code file of the project (a
``ProjectFiles``: its documents, and a code window for one when a match is
shown); ``FindReplaceDialog`` is the non-modal Edit > Find / Replace window (it
highlights the first match as you type; Search: Current module or Current
project, as VB's; Find All lists the matches) and ``ask_line`` the Go to Line
box.

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

import os
import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QRadioButton, QVBoxLayout, QWidget)

from .. import formfile

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
    result = _replace_selection(editor, options)
    return result if result is not None else find_next(editor, options)


def _replace_selection(editor, options: SearchOptions) -> Result | None:
    """Replace the editor's selection if it is a match; a Result when that
    can't be done (else None: go on to the next match)."""
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
    return None


def replace_all(editor, options: SearchOptions) -> Result:
    """Replace every match (as one undo step), except in the designer region."""
    if not options.find:
        return Result(False, "Enter the text to find")
    try:
        pattern = compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")
    try:
        count, skipped = _replace_in_document(editor.document(), pattern, options,
                                              editor.range_editable)
    except (re.error, IndexError) as exc:
        return Result(False, f"Invalid replacement: {exc}")
    message = f"Replaced {count} occurrence{'s' if count != 1 else ''}"
    if skipped:
        message += f"; skipped {skipped} in the designer region"
    if not count and not skipped:
        return Result(False, f"'{options.find}' was not found")
    return Result(bool(count), message)


def _replace_in_document(document: QTextDocument, pattern: re.Pattern, options: SearchOptions,
                         editable: Callable[[int, int], bool]) -> tuple[int, int]:
    """Replace every match where ``editable(start, end)`` allows, as one undo
    step. Returns (replaced, skipped). Raises re.error / IndexError for a bad
    replacement (before changing anything)."""
    text = document.toPlainText()
    positions = _Positions(text)
    edits, skipped = [], 0
    for match in pattern.finditer(text):
        start, end = positions.to_qt(match.start()), positions.to_qt(match.end())
        if editable(start, end):
            edits.append((start, end, replacement(match, options)))
        else:
            skipped += 1
    if edits:
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        for start, end, new_text in reversed(edits):  # later ones first: positions stay valid
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.insertText(new_text)
        cursor.endEditBlock()
    return len(edits), skipped


# --- in the whole project ----------------------------------------------------------------------

class ProjectFiles:
    """What a project-wide search needs of the IDE (the main window gives one):
    ``documents()``, the project's code files as (path, QTextDocument) in the
    project's order; ``current_path()``, the file of the current code window
    (or None); ``editor_for(path)``, its code window's editor (opened and
    shown)."""

    def documents(self) -> list[tuple[str, QTextDocument]]:
        raise NotImplementedError

    def current_path(self) -> str | None:
        raise NotImplementedError

    def editor_for(self, path: str):
        raise NotImplementedError


@dataclass
class Found:
    """A match in a file: its Qt positions, line (from 1) and that line's text."""
    path: str
    start: int
    end: int
    line: int
    text: str


def region_span(document: QTextDocument) -> tuple[int, int] | None:
    """The Qt positions of a form's designer region in a document, or None."""
    try:
        region = formfile.find_region(document.toPlainText())
    except formfile.FormFileError:
        return None
    if region is None:
        return None
    first = document.findBlockByNumber(region[0])
    last = document.findBlockByNumber(region[1])
    return first.position(), last.position() + last.length() - 1


def _matches(path: str, document: QTextDocument, pattern: re.Pattern) -> list[Found]:
    text = document.toPlainText()
    positions = _Positions(text)
    found = []
    for match in pattern.finditer(text):
        start, end = positions.to_qt(match.start()), positions.to_qt(match.end())
        block = document.findBlock(start)
        found.append(Found(path, start, end, block.blockNumber() + 1, block.text().strip()))
    return found


def _pattern_or_result(options: SearchOptions):
    if not options.find:
        return Result(False, "Enter the text to find")
    try:
        return compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")


def find_all(files: ProjectFiles, options: SearchOptions,
             only: str | None = None) -> tuple[list[Found], Result]:
    """Every match in the project's code files (or in the file ``only``)."""
    pattern = _pattern_or_result(options)
    if isinstance(pattern, Result):
        return [], pattern
    found = []
    for path, document in files.documents():
        if only is None or path == only:
            found += _matches(path, document, pattern)
    if not found:
        return [], Result(False, f"'{options.find}' was not found")
    count = len({f.path for f in found})
    return found, Result(True, f"{len(found)} match{'es' if len(found) != 1 else ''} in "
                               f"{count} file{'s' if count != 1 else ''}")


def show_found(files: ProjectFiles, found: Found) -> None:
    """Open the match's code window and select it."""
    editor = files.editor_for(found.path)
    if editor is not None:
        length = editor.document().characterCount() - 1
        editor.select_range(min(found.start, length), min(found.end, length))


def find_next_in_project(files: ProjectFiles, options: SearchOptions,
                         backward: bool = False) -> Result:
    """The next (or previous) match: in the current code window after (before)
    the selection, then in the project's other code files in turn, then
    round to the start (end) of the current one."""
    pattern = _pattern_or_result(options)
    if isinstance(pattern, Result):
        return pattern
    documents = files.documents()
    if not documents:
        return Result(False, "The project has no code files")
    by_path = dict(documents)
    paths = list(by_path)
    current = files.current_path()

    def pick(found):
        return found[-1] if backward else found[0]

    if current not in by_path:  # no code window of the project: from its first (last) file
        for path in (reversed(paths) if backward else paths):
            found = _matches(path, by_path[path], pattern)
            if found:
                show_found(files, pick(found))
                return Result(True)
        return Result(False, f"'{options.find}' was not found in the project")
    cursor = files.editor_for(current).textCursor()
    selection = (cursor.selectionStart(), cursor.selectionEnd())
    here = [f for f in _matches(current, by_path[current], pattern)
            if (f.start, f.end) != selection]
    onward = [f for f in here if f.end <= selection[0]] if backward else \
        [f for f in here if f.start >= selection[1]]
    if onward:
        show_found(files, pick(onward))
        return Result(True)
    index = paths.index(current)
    order = list(reversed(paths[:index])) + list(reversed(paths[index + 1:])) if backward \
        else paths[index + 1:] + paths[:index]
    where = "beginning" if backward else "end"
    wrapped = Result(True, f"Passed the {where} of the project, continued from the other end")
    for path in order:
        found = _matches(path, by_path[path], pattern)
        if found:
            show_found(files, pick(found))
            # (past the last file, or before the first: round the project)
            return wrapped if (paths.index(path) > index) == backward else Result(True)
    if here:  # round to the other end of this file
        show_found(files, pick(here))
        return wrapped
    if selection[0] != selection[1]:
        text = by_path[current].toPlainText()
        positions = _Positions(text)
        if pattern.fullmatch(text, positions.from_qt(selection[0]),
                             positions.from_qt(selection[1])):
            return Result(True, "This is the only match")
    return Result(False, f"'{options.find}' was not found in the project")


def replace_one_in_project(files: ProjectFiles, options: SearchOptions) -> Result:
    """Replace the selection in the current code window if it is a match, then
    find the next match in the project."""
    path = files.current_path()
    if path is not None:
        editor = files.editor_for(path)
        result = _replace_selection(editor, options)
        if result is not None:
            return result
    return find_next_in_project(files, options)


def replace_all_in_project(files: ProjectFiles, options: SearchOptions) -> Result:
    """Replace every match in the project's code files (each file one undo
    step, the files left unsaved), except in forms' designer regions."""
    pattern = _pattern_or_result(options)
    if isinstance(pattern, Result):
        return pattern
    count = skipped = changed = 0
    for path, document in files.documents():
        span = region_span(document)
        try:
            done, missed = _replace_in_document(
                document, pattern, options,
                lambda start, end: span is None or end < span[0] or start > span[1])
        except (re.error, IndexError) as exc:
            return Result(False, f"Invalid replacement: {exc}")
        count, skipped = count + done, skipped + missed
        changed += bool(done)
    if not count and not skipped:
        return Result(False, f"'{options.find}' was not found in the project")
    message = (f"Replaced {count} occurrence{'s' if count != 1 else ''} in {changed} "
               f"file{'s' if changed != 1 else ''}")
    if skipped:
        message += f"; skipped {skipped} in designer regions"
    return Result(bool(count), message)


# --- the dialogs --------------------------------------------------------------------------------

class FindReplaceDialog(QDialog):
    """Edit > Find / Replace: stays open while you work in the code window.

    ``get_editor()`` returns the code editor to search (or None), so the
    dialog always works on the current code window; ``files`` (a
    ProjectFiles) gives the project's code files for Search: Current project
    (without it, only Current module)."""

    def __init__(self, get_editor: Callable[[], object], parent: QWidget | None = None,
                 files: ProjectFiles | None = None):
        super().__init__(parent)
        self.setWindowTitle("Find")
        self.setModal(False)
        self._get_editor = get_editor
        self._files = files

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
        # VB's Search: where Find Next, Replace and Replace All look
        self.scope_module = QRadioButton("Current &module")
        self.scope_project = QRadioButton("Current pro&ject")
        self.scope_module.setChecked(True)
        self.scope_project.setEnabled(files is not None)
        scope = QGroupBox("Search")
        scope_layout = QVBoxLayout(scope)
        scope_layout.addWidget(self.scope_module)
        scope_layout.addWidget(self.scope_project)
        # Find All: every match, listed; double-click (or Enter) on one goes there
        self.results = QListWidget()
        self.results.setVisible(False)
        self.results.itemActivated.connect(self._show_result)
        self.found: list[Found] = []

        self.find_next_button = QPushButton("&Find Next")
        self.find_previous_button = QPushButton("Find Pre&vious")
        self.replace_button = QPushButton("&Replace")
        self.replace_all_button = QPushButton("Replace &All")
        self.find_all_button = QPushButton("Find A&ll")
        self.find_all_button.setToolTip("List every match (in the module or the project)")
        close_button = QPushButton("Close")
        self.find_next_button.setDefault(True)
        self.find_next_button.clicked.connect(self.find_next)
        self.find_previous_button.clicked.connect(self.find_previous)
        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.find_all_button.clicked.connect(self.find_all)
        close_button.clicked.connect(self.close)

        fields = QGridLayout()
        fields.addWidget(find_label, 0, 0)
        fields.addWidget(self.find_edit, 0, 1)
        fields.addWidget(self.replace_label, 1, 0)
        fields.addWidget(self.replace_edit, 1, 1)
        left = QVBoxLayout()
        left.addLayout(fields)
        options = QHBoxLayout()
        boxes = QVBoxLayout()
        for box in (self.match_case, self.whole_word, self.regex):
            boxes.addWidget(box)
        boxes.addStretch(1)
        options.addLayout(boxes, 1)
        options.addWidget(scope)
        left.addLayout(options)
        left.addWidget(self.status)
        left.addStretch(1)
        buttons = QVBoxLayout()
        for button in (self.find_next_button, self.find_previous_button, self.find_all_button,
                       self.replace_button, self.replace_all_button, close_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        top = QHBoxLayout()
        top.addLayout(left, 1)
        top.addLayout(buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.results, 1)
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

    def in_project(self) -> bool:
        """Search: Current project (else Current module)."""
        return self._files is not None and self.scope_project.isChecked()

    def _run(self, action, project_action=None) -> Result:
        if project_action is not None and self.in_project():
            result = project_action(self._files, self.options())
        else:
            editor = self._get_editor()
            if editor is None:
                result = Result(False, "Open a code window to search in")
            else:
                result = action(editor, self.options())
        self.status.setText(result.message)
        return result

    def find_next(self) -> Result:
        return self._run(find_next, find_next_in_project)

    def find_previous(self) -> Result:
        return self._run(lambda editor, options: find_next(editor, options, backward=True),
                         lambda files, options: find_next_in_project(files, options,
                                                                     backward=True))

    def replace(self) -> Result:
        return self._run(replace_one, replace_one_in_project)

    def replace_all(self) -> Result:
        return self._run(replace_all, replace_all_in_project)

    def find_all(self) -> Result:
        """List every match (the module's, or the project's) under the dialog."""
        self.results.clear()
        if self._files is None:
            result = Result(False, "Find All needs a project")
            self.found = []
        else:
            only = None if self.in_project() else self._files.current_path()
            if not self.in_project() and only is None:
                self.found, result = [], Result(False, "Open a code window to search in")
            else:
                self.found, result = find_all(self._files, self.options(), only)
        for found in self.found:
            name = os.path.basename(found.path)
            item = QListWidgetItem(f"{name}:{found.line}:  {found.text}")
            item.setToolTip(found.path)
            self.results.addItem(item)
        self.results.setVisible(bool(self.found))
        if self.found and self.height() < 460:  # (room for the list)
            self.resize(max(self.width(), 640), 460)
        self.status.setText(result.message)
        return result

    def _show_result(self, item: QListWidgetItem) -> None:
        found = self.found[self.results.row(item)]
        show_found(self._files, found)


def ask_line(editor, parent: QWidget | None = None) -> int | None:
    """Edit > Go to Line: ask for a line number (the current line is
    suggested). Returns it, or None if cancelled."""
    count = editor.document().blockCount()
    line, ok = QInputDialog.getInt(parent, "Go to Line", f"Line number (1 - {count}):",
                                   editor.current_line(), 1, count, 1)
    return line if ok else None
