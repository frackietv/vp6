"""Find and Replace without an editor: the search options, the pattern, the
next match in a text, and the project-wide search over the project's texts
(Find All, the next match in the project, Replace All).

Positions are those of a code editor: UTF-16 units (a character outside the
Basic Multilingual Plane, e.g. an emoji, counts two), as Qt's documents and
the CodeBox count them; ``Positions`` turns them into Python's string indexes
and back. Lines count from 1.

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

_ASTRAL = re.compile("[\U00010000-\U0010FFFF]")


@dataclass
class SearchOptions:
    find: str
    replace: str = ""
    match_case: bool = False
    whole_word: bool = False
    regex: bool = False


@dataclass
class Result:
    found: bool
    message: str = ""


@dataclass
class Found:
    """A match in a file: its positions (UTF-16 units), line (from 1) and that
    line's text."""
    path: str
    start: int
    end: int
    line: int
    text: str


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
    around the end of the text (Python indexes). ``skip`` is the current
    selection, which is not found again. Returns (match or None, whether the
    search wrapped)."""
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


class Positions:
    """Maps Python string indexes to an editor's positions (UTF-16 units),
    which count characters outside the Basic Multilingual Plane (e.g. emoji)
    as two."""

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


def pattern_or_result(options: SearchOptions):
    """The options' pattern, or a Result saying what is wrong with them."""
    if not options.find:
        return Result(False, "Enter the text to find")
    try:
        return compile_pattern(options)
    except re.error as exc:
        return Result(False, f"Invalid regular expression: {exc}")


# --- in a text --------------------------------------------------------------------------------

def region_span(text: str) -> tuple[int, int] | None:
    """The positions of a form's designer region in its text (the start of its
    first line to the end of its last line), or None."""
    from vp6 import formfile

    try:
        region = formfile.find_region(text)
    except formfile.FormFileError:
        return None
    if region is None:
        return None
    lines = text.split("\n")
    first, last = region
    start = sum(len(line) + 1 for line in lines[:first])
    end = sum(len(line) + 1 for line in lines[:last]) + len(lines[last])
    positions = Positions(text)
    return positions.to_qt(start), positions.to_qt(end)


def matches(path: str, text: str, pattern: re.Pattern) -> list[Found]:
    """Every match of ``pattern`` in a file's text."""
    positions = Positions(text)
    lines = text.split("\n")
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    found, row = [], 0
    for match in pattern.finditer(text):
        while row + 1 < len(starts) and starts[row + 1] <= match.start():
            row += 1
        found.append(Found(path, positions.to_qt(match.start()), positions.to_qt(match.end()),
                           row + 1, lines[row].strip()))
    return found


def replace_in_text(text: str, options: SearchOptions,
                    editable: Callable[[int, int], bool] = lambda start, end: True
                    ) -> tuple[str, int, int]:
    """(the new text, replaced, skipped): every match replaced where
    ``editable(start, end)`` (positions) allows. Raises re.error / IndexError
    for a bad pattern or replacement (before changing anything)."""
    pattern = compile_pattern(options)
    positions = Positions(text)
    parts, last, replaced, skipped = [], 0, 0, 0
    for match in pattern.finditer(text):
        if editable(positions.to_qt(match.start()), positions.to_qt(match.end())):
            parts += [text[last:match.start()], replacement(match, options)]
            last = match.end()
            replaced += 1
        else:
            skipped += 1
    parts.append(text[last:])
    return "".join(parts), replaced, skipped


def outside_region(text: str) -> Callable[[int, int], bool]:
    """Where a replacement may go in a file: anywhere but its designer region."""
    span = region_span(text)
    return lambda start, end: span is None or end < span[0] or start > span[1]


# --- in the whole project ----------------------------------------------------------------------

def find_all(files: list[tuple[str, str]], options: SearchOptions,
             only: str | None = None) -> tuple[list[Found], Result]:
    """Every match in the project's files, (path, text) in the project's order
    (or in the file ``only``)."""
    pattern = pattern_or_result(options)
    if isinstance(pattern, Result):
        return [], pattern
    found = []
    for path, text in files:
        if only is None or path == only:
            found += matches(path, text, pattern)
    if not found:
        return [], Result(False, f"'{options.find}' was not found")
    count = len({f.path for f in found})
    return found, Result(True, f"{len(found)} match{'es' if len(found) != 1 else ''} in "
                               f"{count} file{'s' if count != 1 else ''}")


def next_in_project(files: list[tuple[str, str]], current: str | None,
                    selection: tuple[int, int], options: SearchOptions,
                    backward: bool = False) -> tuple[Found | None, Result]:
    """The next (or previous) match in the project: in the current file
    after (before) the selection, then in the project's other files in turn,
    then round to the start (end) of the current one. (The match to show, or
    None; what to say.)"""
    pattern = pattern_or_result(options)
    if isinstance(pattern, Result):
        return None, pattern
    if not files:
        return None, Result(False, "The project has no code files")
    by_path = dict(files)
    paths = list(by_path)

    def pick(found):
        return found[-1] if backward else found[0]

    if current not in by_path:  # no file of the project shown: from its first (last) file
        for path in (reversed(paths) if backward else paths):
            found = matches(path, by_path[path], pattern)
            if found:
                return pick(found), Result(True)
        return None, Result(False, f"'{options.find}' was not found in the project")
    here = [f for f in matches(current, by_path[current], pattern)
            if (f.start, f.end) != tuple(selection)]
    onward = [f for f in here if f.end <= selection[0]] if backward else \
        [f for f in here if f.start >= selection[1]]
    if onward:
        return pick(onward), Result(True)
    index = paths.index(current)
    order = list(reversed(paths[:index])) + list(reversed(paths[index + 1:])) if backward \
        else paths[index + 1:] + paths[:index]
    where = "beginning" if backward else "end"
    wrapped = Result(True, f"Passed the {where} of the project, continued from the other end")
    for path in order:
        found = matches(path, by_path[path], pattern)
        if found:  # (past the last file, or before the first: round the project)
            return pick(found), wrapped if (paths.index(path) > index) == backward \
                else Result(True)
    if here:  # round to the other end of this file
        return pick(here), wrapped
    if selection[0] != selection[1]:
        text = by_path[current]
        positions = Positions(text)
        if pattern.fullmatch(text, positions.from_qt(selection[0]),
                             positions.from_qt(selection[1])):
            return None, Result(True, "This is the only match")
    return None, Result(False, f"'{options.find}' was not found in the project")


def replace_all_in_project(files: list[tuple[str, str]], options: SearchOptions
                           ) -> tuple[dict[str, str], Result]:
    """Every match in the project's files replaced, except in forms' designer
    regions: ({path: its new text} for the files changed, what to say)."""
    pattern = pattern_or_result(options)
    if isinstance(pattern, Result):
        return {}, pattern
    changed: dict[str, str] = {}
    count = skipped = 0
    for path, text in files:
        try:
            new_text, done, missed = replace_in_text(text, options, outside_region(text))
        except (re.error, IndexError) as exc:
            return {}, Result(False, f"Invalid replacement: {exc}")
        count, skipped = count + done, skipped + missed
        if done:
            changed[path] = new_text
    if not count and not skipped:
        return {}, Result(False, f"'{options.find}' was not found in the project")
    message = (f"Replaced {count} occurrence{'s' if count != 1 else ''} in {len(changed)} "
               f"file{'s' if len(changed) != 1 else ''}")
    if skipped:
        message += f"; skipped {skipped} in designer regions"
    return changed, Result(bool(count), message)
