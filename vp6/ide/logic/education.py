"""Lessons in the IDE, without Qt: a vp6edu lesson as a VP6 project, its text
for the Lesson window, its exercises one after another, and the student's
progress.

* **Lesson projects:** ``create_lesson_project(lesson, folder)`` copies the
  lesson's ``lab/`` into the folder (as ``samples.create`` copies a sample)
  and saves a project whose ``lesson`` is the lesson's id and whose
  Description is its title; a folder that already has that lesson's project
  keeps it (``existing_project``). Lesson projects live under a root (by
  default ``VP6 Lessons`` in the projects' location), at
  ``<root>/<subject>/<book>/<section>`` (``project_folder``). A lab with a
  ``.vp6p`` of its own gives the project its forms, modules and startup;
  otherwise its ``.py`` files with a designer region are the forms (Form1
  first, starting the program) and the others its modules.
* **The path:** ``neighbour(lesson, ±1)`` is the written lesson before or
  after it along the subject's learning path (``path_lessons``: the books
  in the path's order, each after the books it follows).
* **Lesson text:** ``parse_lesson(markdown)`` splits ``lesson.md`` into the
  Lesson tab's parts (Markdown, and the Try Its' answer fields: a fenced
  block of language ``answer`` holding an answer of ``vp6edu.answers``, e.g.
  ``Number(Fraction(3, 4))``, read by ``try_it_answer``) and the Lab tab's
  text (the section headed ``## Lab``, to the next heading or ``---``).
* **Exercises:** ``ExerciseSession`` goes through the makers of the lesson's
  ``exercises.py`` one after another: Check, Hint, Show Solution, New
  Numbers, the score; ``graph_settings`` says when an answer is placed on a
  Graph.
* **Progress** per lesson (``Progress``: read; exercises right and tried;
  the lab run) is kept in the IDE's settings under
  ``education/progress/<lesson id>`` (``progress``, ``save_progress``,
  ``reset_progress``); ``Progress.state`` is "not started", "in progress" or
  "done".
"""

from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import asdict, dataclass, field
from fractions import Fraction

from . import settings as _settings

LESSONS_FOLDER = "VP6 Lessons"  # the lesson projects' root, in the projects' location
SUBJECT_ROOTS: list = []  # folders of subject folders; none: vp6edu's own (tests set it)
_IGNORED = ("__pycache__", ".DS_Store")

NOT_STARTED, IN_PROGRESS, DONE = "not started", "in progress", "done"
PROGRESS_KEY = "education/progress"


# --- lessons and their projects ----------------------------------------------------------------

def subjects() -> dict:
    """The subjects vp6edu has (or those in SUBJECT_ROOTS), by id."""
    from vp6edu import load_subjects

    return load_subjects(*SUBJECT_ROOTS)


def find_lesson(lesson_id: str):
    """The lesson with this id (``math/prealgebra-2e/1.2``), or None."""
    from vp6edu import SubjectError

    try:
        subject = subjects().get(lesson_id.split("/")[0])
        return subject.lesson(lesson_id) if subject else None
    except (SubjectError, KeyError):
        return None


def default_root(location: str) -> str:
    """Where lesson projects go in a projects' location."""
    return os.path.join(location, LESSONS_FOLDER)


def project_folder(root: str, lesson) -> str:
    """A lesson's project folder under the root: subject/book/section."""
    return os.path.join(root, lesson.subject.id, lesson.book.id, lesson.number)


def root_of(project_dir: str, lesson) -> str:
    """The root a lesson's project is under (where its neighbours' go): three
    folders up when it's at subject/book/section, else the folder above it."""
    parts = os.path.normpath(project_dir).split(os.sep)
    if parts[-3:] == [lesson.subject.id, lesson.book.id, lesson.number]:
        return os.sep.join(parts[:-3]) or os.sep
    return os.path.dirname(os.path.normpath(project_dir))


def project_name(lesson) -> str:
    """The lesson project's name (an identifier): Lesson1_2 for section 1.2."""
    return "Lesson" + "".join(c if c.isalnum() else "_" for c in lesson.number)


def existing_project(folder: str, lesson_id: str) -> str | None:
    """The project file in the folder that is this lesson's, or None."""
    from vp6.project import EXTENSION, ProjectFileError, parse

    if not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name.endswith(EXTENSION) and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    if parse(f.read()).get("lesson") == lesson_id:
                        return path
            except (OSError, UnicodeDecodeError, ProjectFileError):
                continue
    return None


def create_lesson_project(lesson, folder: str) -> str:
    """The lesson's project in the folder: the one there (reopened, not made
    again), or a new one from the lesson's lab. Returns its .vp6p path;
    FileExistsError when the folder holds other files, OSError when the lab
    can't be copied."""
    from vp6 import formfile
    from vp6.project import EXTENSION, SUB_MAIN, Project

    found = existing_project(folder, lesson.id)
    if found:
        return found
    if os.path.isdir(folder) and any(n not in _IGNORED for n in os.listdir(folder)):
        raise FileExistsError(f"{folder} already holds files that aren't this lesson's")
    lab = str(lesson.lab)
    if not os.path.isdir(lab):
        raise FileNotFoundError(f"{lesson.id} has no lab")
    name = project_name(lesson)
    path = os.path.join(folder, name + EXTENSION)
    shutil.copytree(lab, folder, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*_IGNORED, "*" + EXTENSION))
    own = sorted(n for n in os.listdir(lab) if n.endswith(EXTENSION))
    if own:  # (the lab's own project: its files, startup and groups)
        project = Project.load(os.path.join(lab, own[0]))
        project.path = ""
    else:
        forms, modules = [], []
        for root, dirs, files in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if d not in _IGNORED)
            for filename in sorted(files):
                if not filename.endswith(".py"):
                    continue
                full = os.path.join(root, filename)
                relative = os.path.relpath(full, folder).replace(os.sep, "/")
                with open(full, encoding="utf-8") as f:
                    source = f.read()
                (forms if formfile.is_form_source(source) else modules).append(relative)
        forms.sort(key=lambda p: (p != "Form1.py", p))
        main = next((m for m in modules if "def Main(" in _read(os.path.join(folder, m))),
                    None)
        startup = SUB_MAIN if main or not forms else \
            formfile.find_form_class(_read(os.path.join(folder, forms[0])))
        project = Project(forms=forms, modules=modules, startup=startup)
    project.name = name
    project.description = lesson.title
    project.lesson = lesson.id
    project.save(path)
    return path


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def path_lessons(subject) -> list:
    """The subject's lessons along its first learning path: each book after
    the books it follows, in the path's order where there's a choice (then
    the books on no path)."""
    order: list[str] = []
    if subject.paths:
        path = subject.paths[0]
        waiting = {n: len([a for a in path.predecessors(n) if a in path.nodes])
                   for n in path.nodes}
        while len(order) < len(path.nodes):
            ready = [n for n in path.nodes if n not in order and not waiting[n]]
            if not ready:  # (a cycle: vp6edu-check reports it)
                ready = [n for n in path.nodes if n not in order]
            order.append(ready[0])
            for after in path.successors(ready[0]):
                if after in waiting:
                    waiting[after] -= 1
    order += [b for b in subject.books if b not in order]
    return [lesson for b in order if b in subject.books
            for lesson in subject.books[b].lessons()]


def neighbour(lesson, step: int):
    """The written lesson ``step`` (1 or -1) along the path from this one, or
    None at the path's end."""
    lessons = path_lessons(lesson.subject)
    at = next(i for i, each in enumerate(lessons) if each is lesson)
    at += step
    while 0 <= at < len(lessons):
        if not lessons[at].planned:
            return lessons[at]
        at += step
    return None


# --- the lesson's text -------------------------------------------------------------------------

@dataclass
class Part:
    """A piece of the Lesson tab: ``kind`` "text" (Markdown) or "answer" (a
    Try It's answer, as Python: ``Number(5)``)."""
    kind: str
    text: str


@dataclass
class LessonText:
    title: str
    parts: list[Part] = field(default_factory=list)
    lab: str = ""  # the "## Lab" section's Markdown (without its heading)


def _fence(line: str) -> str | None:
    stripped = line.lstrip()
    for mark in ("```", "~~~"):
        if stripped.startswith(mark):
            return mark
    return None


_RULES = ("---", "***", "___")


def parse_lesson(markdown: str) -> LessonText:
    """``lesson.md`` split into the Lesson tab's parts and the Lab tab's text
    (the ``## Lab`` section, to the next heading or rule: ``---``)."""
    title, parts, labs = "", [], []
    text: list[str] = []
    in_lab = False
    lines = markdown.splitlines()
    i = 0

    def flush():
        body = "\n".join(text).strip("\n")
        if body.strip():
            parts.append(Part("text", body))
        text.clear()

    while i < len(lines):
        line = lines[i]
        mark = _fence(line)
        heading = line.startswith("#") and not mark
        if heading and line.startswith("# ") and not title:
            title = line[2:].strip()
        if in_lab and not mark and line.strip() in _RULES:  # (the lab's end)
            in_lab = False
        if heading and (line.startswith("# ") or line.startswith("## ")):
            in_lab = line.startswith("## ") and line[3:].strip().lower() == "lab"
            if in_lab:
                labs.append([])
                i += 1
                continue
        target = labs[-1] if in_lab else text
        if mark:
            info = line.lstrip()[len(mark):].strip().lower()
            block = []
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith(mark):
                block.append(lines[i])
                i += 1
            if info == "answer" and not in_lab:
                flush()
                parts.append(Part("answer", "\n".join(block).strip()))
            else:
                target += [line] + block + [mark]
            i += 1
            continue
        target.append(line)
        i += 1
    flush()
    lab = "\n\n".join("\n".join(each).strip("\n") for each in labs)
    return LessonText(title, parts, lab.strip("\n"))


def answer_names() -> dict:
    """What a Try It's answer is written with: vp6edu.answers' names,
    Fraction and math."""
    from vp6edu import answers

    names = {name: getattr(answers, name) for name in answers.__all__}
    names.update(Fraction=Fraction, math=math, pi=math.pi, inf=math.inf)
    return names


def try_it_answer(source: str):
    """A Try It's answer from its Python (``Number(Fraction(3, 4))``);
    ValueError (what's wrong) when it isn't one."""
    from vp6edu.answers import Answer

    try:
        value = eval(compile(source, "<answer>", "eval", dont_inherit=True),  # noqa: S307
                     {"__builtins__": __builtins__, **answer_names()})
    except Exception as error:  # noqa: BLE001 (the lesson's mistake, shown in its place)
        raise ValueError(f"{type(error).__name__}: {error}") from None
    if not isinstance(value, Answer):
        raise ValueError(f"{source!r} isn't an answer (Number(...), Choice(...)...)")
    return value


# --- progress ----------------------------------------------------------------------------------

@dataclass
class Progress:
    """A student's progress in a lesson: the lesson ``read``, the exercises
    (their makers' names) answered ``right`` and ``tried``, how many
    ``exercises`` it has, the lab run."""
    read: bool = False
    right: list[str] = field(default_factory=list)
    tried: list[str] = field(default_factory=list)
    exercises: int = 0
    lab_run: bool = False

    @property
    def state(self) -> str:
        if not (self.read or self.tried or self.lab_run):
            return NOT_STARTED
        if self.read and self.lab_run and len(set(self.right)) >= self.exercises:
            return DONE
        return IN_PROGRESS


def _key(lesson_id: str) -> str:
    return f"{PROGRESS_KEY}/{lesson_id}"


def progress(lesson_id: str) -> Progress:
    """The lesson's progress, from the IDE's settings."""
    try:
        data = json.loads(_settings.settings().value(_key(lesson_id), "") or "{}")
        known = {k: data[k] for k in Progress.__dataclass_fields__ if k in data}
        return Progress(**known)
    except (TypeError, ValueError):
        return Progress()


def save_progress(lesson_id: str, value: Progress) -> None:
    _settings.settings().setValue(_key(lesson_id), json.dumps(asdict(value)))


def reset_progress(lesson_id: str) -> None:
    _settings.settings().remove(_key(lesson_id))


# --- exercises ---------------------------------------------------------------------------------

def graph_settings(exercise) -> dict | None:
    """The Graph an exercise is answered on (its properties, PlaceMode set
    from its answer's kind), or None when it is typed."""
    from vp6edu.answers import Inequality, Line, Point

    answer = exercise.answer
    if exercise.graph is None and not isinstance(answer, (Point, Line)):
        return None
    values = dict(exercise.graph or {})
    if isinstance(answer, Point):
        values.setdefault("PlaceMode", 1)  # (vp6.graph's PLACE_POINT)
    elif isinstance(answer, Line):
        values.setdefault("PlaceMode", 2)  # PLACE_LINE
    elif isinstance(answer, Inequality):
        values.setdefault("Mode", 1)  # NUMBER_LINE
        values.setdefault("PlaceMode", 3)  # PLACE_INTERVAL
    return values


class ExerciseSession:
    """The exercises of a lesson's ``exercises.py`` (its makers, made from
    seeds), one after another, recording right and tried ones in ``record``
    (a Progress; ``changed`` is called when it changes)."""

    def __init__(self, makers: list, record: Progress, changed=None, seed=None):
        import random

        self.makers = makers
        self.record = record
        self.changed = changed or (lambda: None)
        self._random = random.Random(seed)
        self.index = 0
        self.exercise = None
        self.solution_shown = False
        if record.exercises != len(makers):
            record.exercises = len(makers)
            self.changed()
        if makers:
            self.go(0)

    @classmethod
    def of_lesson(cls, lesson, record: Progress, changed=None, seed=None) -> "ExerciseSession":
        """The session of a lesson's exercises.py (none when it has none);
        errors in the file are raised."""
        from vp6edu.answers import generators, load_exercises

        makers = generators(load_exercises(lesson.exercises)) if lesson.exercises.is_file() \
            else []
        return cls(makers, record, changed, seed)

    @property
    def name(self) -> str:
        return self.makers[self.index].__name__ if self.makers else ""

    def go(self, index: int) -> None:
        """Exercise ``index`` (wrapping round), with new numbers."""
        self.index = index % len(self.makers)
        self.new_numbers()

    def new_numbers(self, seed: int | None = None) -> None:
        from vp6edu.answers import make

        if seed is None:
            seed = self._random.randrange(2 ** 32)
        self.exercise = make(self.makers[self.index], seed)
        self.solution_shown = False

    def check(self, response):
        """The Result of an answer to the exercise shown; a right one counts
        unless its solution was shown."""
        result = self.exercise.check(response)
        if result.status != "unreadable":
            name = self.name
            if name not in self.record.tried:
                self.record.tried.append(name)
            if result.right and not self.solution_shown and name not in self.record.right:
                self.record.right.append(name)
            self.changed()
        return result

    def hint(self) -> str | None:
        return self.exercise.hint()

    def solution(self) -> str:
        """The worked solution (or the answer), shown: a right answer after it
        doesn't count."""
        self.solution_shown = True
        exercise = self.exercise
        answer = f"The answer: {exercise.answer.text}"
        return f"{exercise.solution}\n\n{answer}" if exercise.solution.strip() else answer

    def score_text(self) -> str:
        right, tried = len(set(self.record.right)), len(set(self.record.tried))
        return f"{right} of {len(self.makers)} right ({tried} tried)"
