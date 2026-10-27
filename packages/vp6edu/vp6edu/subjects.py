"""Subjects as data: learning paths of books, chapters and lessons.

A subject is a folder holding ``subject.json`` (its title, its books in order
and its learning paths) and a folder per book with ``book.json`` (title,
authors, link, licence and the chapters with their sections). Each section is
a lesson, ``planned`` until it's written; a written lesson is the folder
``<book>/<chapter>/<section>/`` with ``lesson.md``, ``exercises.py`` and
``lab/``. A section that another book already has (the same OpenStax page) is
``shared``: it refers to that lesson instead of being written twice. A
chapter can end with lessons of another ``kind``: its ``review`` (numbered
``<chapter>-review``) and its ``test`` (``<chapter>-test``), after its
sections.

    from vp6edu import load_subjects
    math = load_subjects()["math"]
    lesson = math.lesson("math/prealgebra-2e/1.2")
    lesson.title, lesson.link, lesson.prerequisites, lesson.attribution

Nothing here is specific to one subject, and nothing needs Qt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SUBJECTS = Path(__file__).resolve().parent / "subjects"  # the subjects vp6edu comes with

STATES = ("planned", "written")
KINDS = ("section", "review", "test")  # a chapter's sections, then its review and test

_SUBJECT_KEYS = {"title", "description", "books", "paths"}
_PATH_KEYS = {"id", "title", "nodes", "edges"}
_BOOK_KEYS = {"title", "publisher", "authors", "link", "licence", "chapters"}
_CHAPTER_KEYS = {"number", "title", "sections"}
_SECTION_KEYS = {"number", "title", "page", "status", "shared", "requires", "kind"}


class SubjectError(ValueError):
    """A subject's data that can't be read: the file and what's wrong."""


@dataclass
class Licence:
    name: str
    url: str


@dataclass
class LearningPath:
    """A graph of books: an edge (a, b) means b follows a."""
    subject: Subject = field(repr=False)
    id: str
    title: str
    nodes: list[str]
    edges: list[tuple[str, str]]

    def predecessors(self, book: str) -> list[str]:
        return [a for a, b in self.edges if b == book]

    def successors(self, book: str) -> list[str]:
        return [b for a, b in self.edges if a == book]

    def roots(self) -> list[str]:
        return [n for n in self.nodes if not self.predecessors(n)]

    def books(self) -> list[Book]:
        return [self.subject.books[n] for n in self.nodes if n in self.subject.books]


@dataclass
class Lesson:
    chapter: Chapter = field(repr=False)
    number: str                 # "1.2", as the book numbers its sections
    title: str
    page: str                   # the openstax.org page's name
    own_status: str = "planned"
    shared: str | None = None   # the id of the lesson this one is
    requires: list[str] = field(default_factory=list)  # ids of lessons of its own
    kind: str = "section"       # "review" or "test": the chapter's, after its sections

    @property
    def book(self) -> Book:
        return self.chapter.book

    @property
    def subject(self) -> Subject:
        return self.chapter.book.subject

    @property
    def id(self) -> str:
        return f"{self.subject.id}/{self.book.id}/{self.number}"

    @property
    def link(self) -> str:
        return f"https://openstax.org/books/{self.book.id}/pages/{self.page}"

    @property
    def label(self) -> str:
        """How it's called: "Lesson 1.2", "Chapter 1 Review", "Chapter 1 Test"."""
        if self.kind == "section":
            return f"Lesson {self.number}"
        return f"Chapter {self.chapter.number} {self.kind.capitalize()}"

    @property
    def heading(self) -> str:
        """Its number and title, as the book has them: "1.2 Add Whole Numbers",
        "Chapter 1: Review Exercises"."""
        if self.kind == "section":
            return f"{self.number} {self.title}"
        return f"Chapter {self.chapter.number}: {self.title}"

    @property
    def source(self) -> Lesson:
        """The lesson written for this one: itself, or the one it shares."""
        return self.subject.lesson(self.shared) if self.shared else self

    @property
    def status(self) -> str:
        return self.source.own_status

    @property
    def planned(self) -> bool:
        return self.status == "planned"

    @property
    def folder(self) -> Path:
        """Where the lesson's files are (a shared lesson's are its source's)."""
        source = self.source
        return source.chapter.folder / source.number

    @property
    def lesson_md(self) -> Path:
        return self.folder / "lesson.md"

    @property
    def exercises(self) -> Path:
        return self.folder / "exercises.py"

    @property
    def lab(self) -> Path:
        return self.folder / "lab"

    @property
    def prerequisites(self) -> list[Lesson]:
        """The lessons this one follows: the section before it on its path
        (the last sections of the books before, for a book's first) and the
        lessons it requires of its own. A chapter's review follows its last
        section, its test the review; sections pass over reviews and tests."""
        found = [self.subject.lesson(ref) for ref in self.requires]
        lessons = self.book.lessons()
        at = lessons.index(self)
        before = [each for each in lessons[:at]
                  if self.kind == "test" or each.kind == "section"]
        if before:
            found.append(before[-1])
        else:
            for path in self.subject.paths:
                for before in path.predecessors(self.book.id):
                    if before in self.subject.books and self.subject.books[before].lessons():
                        found.append(self.subject.books[before].lessons()[-1])
        unique = []
        for lesson in found:
            if lesson not in unique:
                unique.append(lesson)
        return unique

    @property
    def attribution(self) -> str:
        """The line every written lesson carries (its source's, when shared)."""
        source = self.source
        book = source.book
        authors = ", ".join(book.authors[:-1]) + " and " + book.authors[-1] \
            if len(book.authors) > 1 else "".join(book.authors)
        return (f'Adapted from "{source.heading}" in *{book.title}* by '
                f"{authors} ({book.publisher}), <{source.link}>, licensed under "
                f"[{book.licence.name}]({book.licence.url}).")

    def __eq__(self, other):
        return self is other

    __hash__ = object.__hash__


@dataclass
class Chapter:
    book: Book = field(repr=False)
    number: int
    title: str
    lessons: list[Lesson] = field(default_factory=list)

    @property
    def folder(self) -> Path:
        return self.book.folder / str(self.number)


@dataclass
class Book:
    subject: Subject = field(repr=False)
    id: str
    title: str
    publisher: str
    authors: list[str]
    link: str
    licence: Licence
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def folder(self) -> Path:
        return self.subject.folder / self.id

    def lessons(self) -> list[Lesson]:
        return [lesson for chapter in self.chapters for lesson in chapter.lessons]


@dataclass
class Subject:
    id: str
    title: str
    description: str
    folder: Path
    books: dict[str, Book] = field(default_factory=dict)   # in the subject's order
    paths: list[LearningPath] = field(default_factory=list)

    def lessons(self) -> list[Lesson]:
        return [lesson for book in self.books.values() for lesson in book.lessons()]

    def lesson(self, ref: str) -> Lesson:
        """A lesson by id (``math/prealgebra-2e/1.2``), or by ``book/section``
        within the subject. KeyError when there's none."""
        parts = ref.split("/")
        if len(parts) == 3 and parts[0] == self.id:
            parts = parts[1:]
        if len(parts) == 2 and parts[0] in self.books:
            for lesson in self.books[parts[0]].lessons():
                if lesson.number == parts[1]:
                    return lesson
        raise KeyError(f"no lesson {ref} in {self.id}")

    def all_prerequisites(self, lesson: Lesson) -> list[Lesson]:
        """Every lesson before this one on its paths, in the subject's order."""
        seen, stack = set(), list(lesson.prerequisites)
        while stack:
            before = stack.pop()
            if before not in seen and before is not lesson:
                seen.add(before)
                stack.extend(before.prerequisites)
        return [each for each in self.lessons() if each in seen]


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SubjectError(f"{path}: missing") from None
    except (OSError, ValueError) as error:
        raise SubjectError(f"{path}: {error}") from None
    if not isinstance(data, dict):
        raise SubjectError(f"{path}: not a JSON object")
    return data


def _keys(data: dict, allowed: set, required: set, where: str):
    if not isinstance(data, dict):
        raise SubjectError(f"{where}: not a JSON object")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise SubjectError(f"{where}: unknown keys {', '.join(unknown)}")
    missing = sorted(required - set(data))
    if missing:
        raise SubjectError(f"{where}: missing {', '.join(missing)}")


def _strings(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SubjectError(f"{where}: not a list of strings")
    return value


def load_subject(folder) -> Subject:
    """One subject from its folder (its id is the folder's name)."""
    folder = Path(folder)
    where = folder / "subject.json"
    data = _read_json(where)
    _keys(data, _SUBJECT_KEYS, {"title", "books", "paths"}, str(where))
    subject = Subject(folder.name, data["title"], data.get("description", ""), folder)
    for book_id in _strings(data["books"], f"{where}: books"):
        if book_id in subject.books:
            raise SubjectError(f"{where}: books: {book_id} twice")
        subject.books[book_id] = _load_book(subject, book_id)
    if not isinstance(data["paths"], list):
        raise SubjectError(f"{where}: paths: not a list")
    for i, path in enumerate(data["paths"]):
        at = f"{where}: paths[{i}]"
        _keys(path, _PATH_KEYS, _PATH_KEYS, at)
        edges = path["edges"]
        if not isinstance(edges, list) or not all(
                isinstance(e, list) and len(e) == 2 and all(isinstance(n, str) for n in e)
                for e in edges):
            raise SubjectError(f"{at}: edges: not a list of [from, to] pairs")
        subject.paths.append(LearningPath(subject, path["id"], path["title"],
                                          _strings(path["nodes"], f"{at}: nodes"),
                                          [tuple(e) for e in edges]))
    return subject


def _load_book(subject: Subject, book_id: str) -> Book:
    where = subject.folder / book_id / "book.json"
    data = _read_json(where)
    _keys(data, _BOOK_KEYS, _BOOK_KEYS, str(where))
    licence = data["licence"]
    _keys(licence, {"name", "url"}, {"name", "url"}, f"{where}: licence")
    book = Book(subject, book_id, data["title"], data["publisher"],
                _strings(data["authors"], f"{where}: authors"), data["link"],
                Licence(licence["name"], licence["url"]))
    if not isinstance(data["chapters"], list):
        raise SubjectError(f"{where}: chapters: not a list")
    for i, chapter_data in enumerate(data["chapters"]):
        at = f"{where}: chapters[{i}]"
        _keys(chapter_data, _CHAPTER_KEYS, _CHAPTER_KEYS, at)
        if not isinstance(chapter_data["number"], int):
            raise SubjectError(f"{at}: number: not a whole number")
        chapter = Chapter(book, chapter_data["number"], chapter_data["title"])
        if not isinstance(chapter_data["sections"], list):
            raise SubjectError(f"{at}: sections: not a list")
        for j, section in enumerate(chapter_data["sections"]):
            here = f"{at}.sections[{j}]"
            _keys(section, _SECTION_KEYS, {"number", "title", "page"}, here)
            for key in ("number", "title", "page", "status", "shared", "kind"):
                if key in section and not isinstance(section[key], str):
                    raise SubjectError(f"{here}: {key}: not a string")
            chapter.lessons.append(Lesson(
                chapter, section["number"], section["title"], section["page"],
                section.get("status", "planned"), section.get("shared"),
                _strings(section.get("requires", []), f"{here}: requires"),
                section.get("kind", "section")))
        book.chapters.append(chapter)
    return book


def subject_folders(*roots) -> list[Path]:
    """The subjects' folders in these folders (vp6edu's own by default)."""
    return [folder for root in (roots or (SUBJECTS,))
            for folder in sorted(Path(root).iterdir())
            if (folder / "subject.json").is_file()]


def load_subjects(*roots) -> dict[str, Subject]:
    """Every subject in these folders (vp6edu's own by default), by id."""
    subjects = {}
    for folder in subject_folders(*roots):
        subject = load_subject(folder)
        if subject.id in subjects:
            raise SubjectError(f"{folder}: a second subject {subject.id}")
        subjects[subject.id] = subject
    return subjects
