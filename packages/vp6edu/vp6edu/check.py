"""vp6edu-check: the validator of subjects, their outlines and written lessons.

    vp6edu-check                       # vp6edu's own subjects
    vp6edu-check --subjects DIR        # the subjects in DIR (a folder of subject folders)
    vp6edu-check --attribution ID      # the attribution line lesson ID's lesson.md needs

It checks the data (books on the paths, the paths without cycles, chapters
and sections numbered in order, openstax.org page names, shared lessons and
required ones pointing at lessons that exist, no prerequisite cycles), and
every written lesson's files: ``lesson.md`` with its attribution line,
``exercises.py`` that compiles, a ``lab/`` with files in it; and that no
folder is left that isn't a lesson's. Exits with 1 when something is wrong.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .subjects import (STATES, Lesson, Subject, SubjectError, load_subject, load_subjects,
                       subject_folders)

_PAGE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


@dataclass
class Problem:
    where: str
    message: str
    warning: bool = False

    def __str__(self):
        return f"{self.where}: {'warning: ' if self.warning else ''}{self.message}"


def check(*roots) -> list[Problem]:
    """The problems of every subject in these folders (vp6edu's own by default)."""
    problems = []
    seen = {}
    for folder in subject_folders(*roots):
        try:
            subject = load_subject(folder)
        except SubjectError as error:
            problems.append(Problem(folder.name, str(error)))
            continue
        if subject.id in seen:
            problems.append(Problem(subject.id, f"also in {seen[subject.id]}"))
        seen[subject.id] = folder
        problems += check_subject(subject)
    return problems


def check_subject(subject: Subject) -> list[Problem]:
    problems = []

    def problem(where, message, warning=False):
        problems.append(Problem(where, message, warning))

    _check_paths(subject, problem)
    for book in subject.books.values():
        where = f"{subject.id}/{book.id}"
        if not book.authors:
            problem(where, "no authors")
        if not book.link.startswith("https://"):
            problem(where, f"link {book.link!r} isn't https")
        for i, chapter in enumerate(book.chapters, 1):
            if chapter.number != i:
                problem(where, f"chapter {chapter.number} where {i} was expected")
            if not chapter.title.strip():
                problem(where, f"chapter {chapter.number} has no title")
            if not chapter.lessons:
                problem(where, f"chapter {chapter.number} has no sections")
            for j, lesson in enumerate(chapter.lessons, 1):
                if lesson.number != f"{chapter.number}.{j}":
                    problem(lesson.id, f"numbered where {chapter.number}.{j} was expected")
                _check_lesson(lesson, problem)
        _check_folders(book, problem)
    _check_cycles(subject, problem)
    return problems


def _check_paths(subject: Subject, problem):
    on_a_path = set()
    ids = set()
    for path in subject.paths:
        where = f"{subject.id}: path {path.id}"
        if path.id in ids:
            problem(where, "a second path with this id")
        ids.add(path.id)
        for node in path.nodes:
            if node not in subject.books:
                problem(where, f"{node} isn't one of the subject's books")
        if len(set(path.nodes)) != len(path.nodes):
            problem(where, "a book twice in its nodes")
        on_a_path |= set(path.nodes)
        for a, b in path.edges:
            if a not in path.nodes or b not in path.nodes:
                problem(where, f"edge {a} → {b} leaves its nodes")
        roots = path.roots()
        if len(roots) > 1:
            problem(where, f"more than one first book: {', '.join(roots)}", warning=True)
        # (cycles: Kahn's algorithm, taking books once nothing comes before them)
        incoming = {n: len(path.predecessors(n)) for n in path.nodes}
        ready = [n for n, count in incoming.items() if not count]
        done = 0
        while ready:
            node = ready.pop()
            done += 1
            for after in path.successors(node):
                if after in incoming:
                    incoming[after] -= 1
                    if not incoming[after]:
                        ready.append(after)
        if done < len(path.nodes):
            problem(where, "has a cycle")
    for book in subject.books:
        if book not in on_a_path:
            problem(f"{subject.id}/{book}", "on no learning path", warning=True)


def _check_lesson(lesson: Lesson, problem):
    where = lesson.id
    if not lesson.title.strip():
        problem(where, "no title")
    prefix = lesson.number.replace(".", "-") + "-"
    if not _PAGE.fullmatch(lesson.page) or not lesson.page.startswith(prefix):
        problem(where, f"page {lesson.page!r} isn't an openstax.org page name "
                       f"starting {prefix!r}")
    if lesson.own_status not in STATES:
        problem(where, f"status {lesson.own_status!r} isn't one of {', '.join(STATES)}")
    for ref in lesson.requires:
        try:
            required = lesson.subject.lesson(ref)
        except KeyError:
            problem(where, f"requires {ref}, which isn't a lesson")
            continue
        if required is lesson:
            problem(where, "requires itself")
    if lesson.shared:
        try:
            source = lesson.subject.lesson(lesson.shared)
        except KeyError:
            problem(where, f"shares {lesson.shared}, which isn't a lesson")
            return
        if source.shared:
            problem(where, f"shares {source.id}, which shares {source.shared}: "
                           "share the lesson written")
        elif source.book is lesson.book:
            problem(where, f"shares {source.id} of its own book")
        if lesson.own_status != "planned":
            problem(where, "a shared lesson takes its status from the one it shares")
        if source.title != lesson.title:
            problem(where, f"shares {source.id} titled {source.title!r}", warning=True)
        return
    if lesson.own_status == "written":
        _check_written(lesson, problem)


def _check_written(lesson: Lesson, problem):
    where = lesson.id
    if not lesson.lesson_md.is_file():
        problem(where, "written, but has no lesson.md")
    else:
        text = lesson.lesson_md.read_text(encoding="utf-8")
        if not text.lstrip().startswith("# "):
            problem(where, "lesson.md doesn't start with a # heading")
        if " ".join(lesson.attribution.split()) not in " ".join(text.split()):
            problem(where, f"lesson.md lacks its attribution: {lesson.attribution}")
    if not lesson.exercises.is_file():
        problem(where, "written, but has no exercises.py")
    else:
        try:
            compile(lesson.exercises.read_bytes(), str(lesson.exercises), "exec",
                    dont_inherit=True)
        except SyntaxError as error:
            problem(where, f"exercises.py line {error.lineno}: {error.msg}")
    if not lesson.lab.is_dir() or not any(p.is_file() for p in lesson.lab.rglob("*")):
        problem(where, "written, but its lab/ has no files")


def _check_folders(book, problem):
    """Folders under the book that aren't its chapters' or lessons' own."""
    if not book.folder.is_dir():
        return
    chapters = {str(c.number): c for c in book.chapters}
    for entry in sorted(book.folder.iterdir()):
        if entry.name in ("book.json", "__pycache__") or entry.name.startswith("."):
            continue
        where = f"{book.subject.id}/{book.id}/{entry.name}"
        if entry.name not in chapters or not entry.is_dir():
            problem(where, "isn't a chapter's folder")
            continue
        lessons = {lesson.number: lesson for lesson in chapters[entry.name].lessons}
        for folder in sorted(entry.iterdir()):
            if folder.name == "__pycache__" or folder.name.startswith("."):
                continue
            lesson = lessons.get(folder.name)
            if lesson is None or not folder.is_dir():
                problem(f"{where}/{folder.name}", "isn't a lesson's folder")
            elif lesson.shared:
                problem(lesson.id, f"shared, but has a folder of its own "
                                   f"(its files go in {lesson.shared}'s)")


def _check_cycles(subject: Subject, problem):
    state = {}  # lesson: 1 while visiting, 2 when done

    def visit(lesson, trail):
        state[lesson] = 1
        try:
            before = lesson.prerequisites
        except KeyError:
            before = []  # (reported as a missing required lesson)
        for each in before:
            if state.get(each) == 1:
                cycle = trail[trail.index(each):] + [each]
                problem(lesson.id, "prerequisites go round: "
                        + " → ".join(item.id for item in cycle))
            elif each not in state:
                visit(each, trail + [each])
        state[lesson] = 2

    for lesson in subject.lessons():
        if lesson not in state:
            visit(lesson, [lesson])


def summary(subject: Subject) -> str:
    lessons = subject.lessons()
    written = sum(1 for lesson in lessons if lesson.own_status == "written")
    shared = sum(1 for lesson in lessons if lesson.shared)
    return (f"{subject.id}: {len(subject.books)} books, {len(lessons)} lessons "
            f"({written} written, {shared} shared, "
            f"{len(lessons) - written - shared} planned)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="vp6edu-check", description="Check vp6edu's subjects and written lessons.")
    parser.add_argument("--subjects", metavar="DIR", action="append", type=Path,
                        help="a folder of subject folders (vp6edu's own by default; "
                             "may be given more than once)")
    parser.add_argument("--attribution", metavar="ID",
                        help="print the attribution line lesson ID needs, and stop")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="print only the problems")
    args = parser.parse_args(argv)
    roots = args.subjects or []
    if args.attribution:
        try:
            subjects = load_subjects(*roots)
            subject = subjects[args.attribution.split("/")[0]]
            print(subject.lesson(args.attribution).attribution)
        except (SubjectError, KeyError) as error:
            print(f"vp6edu-check: {error}", file=sys.stderr)
            return 1
        return 0
    problems = check(*roots)
    for each in problems:
        print(each)
    if not args.quiet:
        try:
            for subject in load_subjects(*roots).values():
                print(summary(subject))
        except SubjectError:
            pass
    errors = [each for each in problems if not each.warning]
    if not args.quiet:
        print(f"{len(errors)} problems, {len(problems) - len(errors)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
