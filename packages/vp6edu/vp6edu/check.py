"""vp6edu-check: the validator of subjects, their outlines and written lessons.

    vp6edu-check                       # vp6edu's own subjects
    vp6edu-check --subjects DIR        # the subjects in DIR (a folder of subject folders)
    vp6edu-check --attribution ID      # the attribution line lesson ID's lesson.md needs
    vp6edu-check --labs                # and run every written lesson's lab (needs VP6)

It checks the data (books on the paths, the paths without cycles, chapters
and sections numbered in order, a chapter's review and test after them,
openstax.org page names, shared lessons and required ones pointing at
lessons that exist, no prerequisite cycles), and every written lesson:

* ``lesson.md``: its ``# `` heading and attribution line, its formulas
  (laid out by vp6help's TeX, when vp6help is installed), its Try Its'
  answers (each one's own answer checks right), its links to other lessons
  (``lesson:<id>``) and, for a section, its parts (Learning Objectives, Be
  Prepared, Key Concepts: warnings);
* ``exercises.py``: it loads, has 10–20 makers (a warning otherwise), and
  over ``--seeds`` seeds (50) every exercise has a prompt whose formulas lay
  out and an answer whose own text checks right;
* ``lab/``: it has files; with ``--labs`` its forms are loaded with VP6,
  shown offscreen and unloaded, any run-time error being a problem.

And that no folder is left that isn't a lesson's. Exits with 1 when
something is wrong.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .subjects import (KINDS, STATES, Lesson, Subject, SubjectError, load_subject, load_subjects,
                       subject_folders)

_PAGE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_LESSON_LINK = re.compile(r"\]\(lesson:([^)\s]+)\)")
_ANSWER_BLOCK = re.compile(r"^ {0,3}```answer[ \t]*\n(.*?)^ {0,3}```", re.M | re.S)
SEEDS = 50  # the seeds each exercise maker is tried with
EXERCISES = (10, 20)  # how many makers a section's exercises.py should have
SECTION_PARTS = ("Learning Objectives", "Be Prepared", "Key Concepts")


@dataclass
class Problem:
    where: str
    message: str
    warning: bool = False

    def __str__(self):
        return f"{self.where}: {'warning: ' if self.warning else ''}{self.message}"


def check(*roots, seeds: int = SEEDS, labs: bool = False) -> list[Problem]:
    """The problems of every subject in these folders (vp6edu's own by
    default); ``labs`` runs the written lessons' labs too (with VP6)."""
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
        problems += check_subject(subject, seeds, labs)
    return problems


def check_subject(subject: Subject, seeds: int = SEEDS, labs: bool = False) -> list[Problem]:
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
            sections = [each for each in chapter.lessons if each.kind == "section"]
            ends = [each for each in chapter.lessons if each.kind != "section"]
            for lesson in chapter.lessons:
                expected = f"{chapter.number}.{sections.index(lesson) + 1}" \
                    if lesson in sections else f"{chapter.number}-{lesson.kind}"
                if lesson.number != expected:
                    problem(lesson.id, f"numbered where {expected} was expected")
                _check_lesson(lesson, problem, seeds, labs)
            if chapter.lessons != sections + ends:
                problem(where, f"chapter {chapter.number}'s review and test aren't after its "
                               "sections")
            if [e.kind for e in ends] not in ([], ["review"], ["test"], ["review", "test"]):
                problem(where, f"chapter {chapter.number} ends with "
                               f"{', '.join(e.kind for e in ends)}: a review, then a test")

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


def _check_lesson(lesson: Lesson, problem, seeds: int = SEEDS, labs: bool = False):
    where = lesson.id
    if not lesson.title.strip():
        problem(where, "no title")
    if lesson.kind not in KINDS:
        problem(where, f"kind {lesson.kind!r} isn't one of {', '.join(KINDS)}")
    prefix = lesson.number.replace(".", "-") + "-" if lesson.kind == "section" \
        else f"{lesson.chapter.number}-"
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
        _check_written(lesson, problem, seeds, labs)


def _check_written(lesson: Lesson, problem, seeds: int = SEEDS, labs: bool = False):
    where = lesson.id
    if not lesson.lesson_md.is_file():
        problem(where, "written, but has no lesson.md")
    else:
        text = lesson.lesson_md.read_text(encoding="utf-8")
        if not text.lstrip().startswith("# "):
            problem(where, "lesson.md doesn't start with a # heading")
        if " ".join(lesson.attribution.split()) not in " ".join(text.split()):
            problem(where, f"lesson.md lacks its attribution: {lesson.attribution}")
        _check_lesson_text(lesson, text, problem)
    if not lesson.exercises.is_file():
        problem(where, "written, but has no exercises.py")
    else:
        try:
            compile(lesson.exercises.read_bytes(), str(lesson.exercises), "exec",
                    dont_inherit=True)
        except SyntaxError as error:
            problem(where, f"exercises.py line {error.lineno}: {error.msg}")
        else:
            _check_exercises(lesson, problem, seeds)
    if not lesson.lab.is_dir() or not any(p.is_file() for p in lesson.lab.rglob("*")):
        problem(where, "written, but its lab/ has no files")
    elif labs:
        for message in check_lab(lesson):
            problem(where, f"lab: {message}")


def _formula_problems(text: str) -> list[str]:
    """The formulas in Markdown that vp6help's TeX can't lay out (none
    without vp6help)."""
    try:
        from vp6help import tex
    except ImportError:
        return []
    found = []
    for span in tex.math_spans(text):
        try:
            tex.layout(span.tex, tex.Metrics(), span.display)
        except (tex.TexError, RecursionError) as error:
            found.append(f"${span.tex}$: {error or 'too deep'}")
    return found


def _check_lesson_text(lesson: Lesson, text: str, problem):
    from .answers import answer_of

    where = f"{lesson.id} lesson.md"
    for message in _formula_problems(text):
        problem(where, f"a formula that can't be laid out: {message}")
    for block in _ANSWER_BLOCK.findall(text):
        try:
            answer = answer_of(block.strip())
        except ValueError as error:
            problem(where, f"a Try It's answer that can't be read: {error}")
            continue
        result = answer.check(answer.text)
        if not result.right:
            problem(where, f"the Try It answer {block.strip()}: its own text "
                           f"{answer.text!r} checks {result.status}")
        if _unlisted_choice(answer):
            problem(where, f"the Try It answer {block.strip()}: a Choice without options "
                           "(they're shown as buttons)", warning=True)
    for ref in _LESSON_LINK.findall(text):
        try:
            lesson.subject.lesson(ref)
        except KeyError:
            problem(where, f"links to lesson {ref}, which isn't one")
    if lesson.kind == "section":
        headings = {line[3:].strip().lower() for line in text.splitlines()
                    if line.startswith("## ")}
        for part in SECTION_PARTS:
            if part.lower() not in headings:
                problem(where, f"has no ## {part}", warning=True)


def _unlisted_choice(answer) -> bool:
    from .answers import Choice

    return isinstance(answer, Choice) and not answer.options


def _check_exercises(lesson: Lesson, problem, seeds: int):
    from .answers import generators, load_exercises, make, verify

    where = f"{lesson.id} exercises.py"
    try:
        makers = generators(load_exercises(lesson.exercises))
    except Exception as error:  # noqa: BLE001 (the lesson's code)
        problem(where, f"can't be loaded: {type(error).__name__}: {error}")
        return
    low, high = EXERCISES
    if lesson.kind == "section" and not low <= len(makers) <= high:
        problem(where, f"has {len(makers)} exercises, not {low}–{high}", warning=True)
    if not makers:
        problem(where, "has no exercises")
    for maker in makers:
        found = verify(maker, range(seeds))
        for message in found[:3]:
            problem(where, message)
        if found:
            continue
        if _unlisted_choice(make(maker, 0).answer):
            problem(where, f"{maker.__name__}: a Choice without options (they're shown "
                           "as buttons)", warning=True)
        for seed in range(seeds):
            exercise = make(maker, seed)
            text = "\n\n".join([exercise.prompt, exercise.solution, *exercise.hints])
            bad = _formula_problems(text)
            if bad:
                problem(where, f"{maker.__name__}, seed {seed}: a formula that can't be "
                               f"laid out: {bad[0]}")
                break


def check_lab(lesson: Lesson) -> list[str]:
    """What goes wrong running a lesson's lab with VP6 (``vp6.runner.try_forms``
    on a copy of it): each form made, shown offscreen and unloaded."""
    try:
        from vp6.runner import try_forms
    except ImportError:
        return ["VP6 isn't installed, so the lab can't be run"]
    folder = tempfile.mkdtemp(prefix="vp6edu-lab-")
    try:
        shutil.copytree(lesson.lab, folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
        return try_forms(folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


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
    parser.add_argument("--labs", action="store_true",
                        help="also run every written lesson's lab offscreen (needs VP6)")
    parser.add_argument("--seeds", metavar="N", type=int, default=SEEDS,
                        help=f"the seeds each exercise is tried with ({SEEDS})")
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
    problems = check(*roots, seeds=args.seeds, labs=args.labs)
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
