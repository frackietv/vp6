"""vp6edu, the courses (packages/vp6edu): the subjects' data, lessons and their
prerequisites, shared lessons, attribution, and vp6edu-check."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import vp6edu
from vp6edu import SUBJECTS, SubjectError, load_subject, load_subjects
from vp6edu import check as edu_check

ROOT = Path(__file__).resolve().parent.parent

BOOKS = ["prealgebra-2e", "elementary-algebra-2e", "intermediate-algebra-2e",
         "algebra-and-trigonometry-2e", "precalculus-2e", "calculus-volume-1",
         "calculus-volume-2", "calculus-volume-3", "introductory-statistics-2e"]


@pytest.fixture(scope="module")
def math():
    return load_subjects()["math"]


# --- vp6edu's own subjects ------------------------------------------------------------------

def test_the_mathematics_outline(math):
    assert math.title == "Mathematics" and list(math.books) == BOOKS
    chapters = {book.id: len(book.chapters) for book in math.books.values()}
    assert chapters == {"prealgebra-2e": 11, "elementary-algebra-2e": 10,
                        "intermediate-algebra-2e": 12, "algebra-and-trigonometry-2e": 13,
                        "precalculus-2e": 12, "calculus-volume-1": 6, "calculus-volume-2": 7,
                        "calculus-volume-3": 7, "introductory-statistics-2e": 13}
    assert len(math.lessons()) == 564
    book = math.books["prealgebra-2e"]
    assert book.chapters[0].title == "Whole Numbers"
    assert [lesson.title for lesson in book.chapters[0].lessons] == [
        "Introduction to Whole Numbers", "Add Whole Numbers", "Subtract Whole Numbers",
        "Multiply Whole Numbers", "Divide Whole Numbers"]
    assert book.authors == ["Lynn Marecek", "MaryAnne Anthony-Smith", "Andrea Honeycutt Mathis"]
    assert book.licence.name == "CC BY-NC-SA 4.0"
    assert math.books["introductory-statistics-2e"].chapters[-1].title == \
        "F Distribution and One-Way ANOVA"
    # every lesson is planned until it's written
    assert all(lesson.planned for lesson in math.lessons())


def test_the_learning_path(math):
    path, = math.paths
    assert path.nodes == BOOKS and path.roots() == ["prealgebra-2e"]
    assert path.successors("intermediate-algebra-2e") == [
        "algebra-and-trigonometry-2e", "introductory-statistics-2e"]
    assert path.successors("introductory-statistics-2e") == []
    assert [book.id for book in path.books()] == BOOKS


def test_lesson_ids_and_links(math):
    lesson = math.lesson("math/prealgebra-2e/1.2")
    assert lesson is math.lesson("prealgebra-2e/1.2")
    assert lesson.id == "math/prealgebra-2e/1.2" and lesson.title == "Add Whole Numbers"
    assert lesson.link == "https://openstax.org/books/prealgebra-2e/pages/1-2-add-whole-numbers"
    assert lesson.folder == SUBJECTS / "math" / "prealgebra-2e" / "1" / "1.2"
    assert lesson.lesson_md.name == "lesson.md" and lesson.exercises.name == "exercises.py"
    assert lesson.lab.name == "lab"
    for missing in ("math/prealgebra-2e/1.9", "math/nonesuch/1.1", "physics/prealgebra-2e/1.1",
                    "1.1"):
        with pytest.raises(KeyError):
            math.lesson(missing)


def test_prerequisites_follow_the_path(math):
    ids = lambda lessons: [lesson.id for lesson in lessons]  # noqa: E731
    assert ids(math.lesson("prealgebra-2e/1.1").prerequisites) == []
    assert ids(math.lesson("prealgebra-2e/1.2").prerequisites) == ["math/prealgebra-2e/1.1"]
    # a chapter's first section follows the chapter before's last
    assert ids(math.lesson("prealgebra-2e/2.1").prerequisites) == ["math/prealgebra-2e/1.5"]
    # a book's first follows the last of the book before it; Statistics branches
    assert ids(math.lesson("introductory-statistics-2e/1.1").prerequisites) == \
        ["math/intermediate-algebra-2e/12.4"]
    assert ids(math.lesson("algebra-and-trigonometry-2e/1.1").prerequisites) == \
        ["math/intermediate-algebra-2e/12.4"]
    earlier = math.all_prerequisites(math.lesson("elementary-algebra-2e/1.1"))
    assert earlier == math.books["prealgebra-2e"].lessons()
    # Statistics needs the algebra before it but not trigonometry or calculus
    books = {lesson.book.id for lesson in
             math.all_prerequisites(math.lesson("introductory-statistics-2e/2.1"))}
    assert books == {"prealgebra-2e", "elementary-algebra-2e", "intermediate-algebra-2e",
                     "introductory-statistics-2e"}


def test_shared_lessons_are_referenced(math):
    shared = {lesson.id: lesson.source.id for lesson in math.lessons() if lesson.shared}
    assert len(shared) == 60
    # Precalculus 2e takes most of its chapters from Algebra and Trigonometry 2e
    assert shared["math/precalculus-2e/4.1"] == "math/algebra-and-trigonometry-2e/6.1"
    assert shared["math/precalculus-2e/11.7"] == "math/algebra-and-trigonometry-2e/13.7"
    # (chapters 1-3, 5 and 7 are OpenStax pages of their own: lessons of their own)
    assert "math/precalculus-2e/1.1" not in shared
    # Calculus Volume 2's chapters 1-2 are Volume 1's 5-6; Volume 3's 1 is Volume 2's 7
    assert shared["math/calculus-volume-2/1.1"] == "math/calculus-volume-1/5.1"
    assert shared["math/calculus-volume-2/2.9"] == "math/calculus-volume-1/6.9"
    assert shared["math/calculus-volume-3/1.5"] == "math/calculus-volume-2/7.5"
    assert sum(1 for lesson in shared if "/calculus-volume-2/" in lesson) == 16
    lesson = math.lesson("calculus-volume-3/1.1")
    assert lesson.folder == math.lesson("calculus-volume-2/7.1").folder
    assert lesson.attribution == math.lesson("calculus-volume-2/7.1").attribution
    assert lesson.link.endswith("/calculus-volume-3/pages/1-1-parametric-equations")


def test_the_attribution(math):
    lesson = math.lesson("prealgebra-2e/1.2")
    assert lesson.attribution == (
        'Adapted from "1.2 Add Whole Numbers" in *Prealgebra 2e* by Lynn Marecek, '
        "MaryAnne Anthony-Smith and Andrea Honeycutt Mathis (OpenStax), "
        "<https://openstax.org/books/prealgebra-2e/pages/1-2-add-whole-numbers>, licensed "
        "under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).")
    assert "by Jay Abramson (OpenStax)" in math.lesson("precalculus-2e/1.1").attribution


def test_vp6edu_own_subjects_pass_the_check():
    assert edu_check.check() == []


# --- a stand-in subject ---------------------------------------------------------------------

def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def section(number, title, **more):
    page = number.replace(".", "-") + "-" + title.lower().replace(" ", "-")
    return {"number": number, "title": title, "page": page, **more}


def make_subject(root: Path, name="physics", first=None, second=None, paths=None):
    folder = root / name
    write(folder / "subject.json", {
        "title": "Physics", "books": ["mechanics", "waves"],
        "paths": paths or [{"id": "main", "title": "Physics", "nodes": ["mechanics", "waves"],
                            "edges": [["mechanics", "waves"]]}]})
    for book, sections in (("mechanics", first), ("waves", second)):
        write(folder / book / "book.json", {
            "title": book.title(), "publisher": "Us", "authors": ["A. Author", "B. Author"],
            "link": f"https://example.org/{book}",
            "licence": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
            "chapters": [{"number": 1, "title": "One", "sections": sections or [
                section("1.1", "Start"), section("1.2", "Go On")]}]})
    return folder


def write_lesson(subject, ref, attribution=True):
    lesson = subject.lesson(ref)
    text = f"# {lesson.title}\n\nOur own words.\n"
    if attribution:
        text += "\n---\n\n" + lesson.attribution + "\n"
    write(lesson.lesson_md, text)
    write(lesson.exercises, "def exercises(random):\n    return []\n")
    write(lesson.lab / "Lab.vp6p", "{}")
    return lesson


def messages(root):
    return [str(problem) for problem in edu_check.check(root)]


def test_a_subject_of_ones_own(tmp_path):
    make_subject(tmp_path)
    subjects = load_subjects(tmp_path)
    assert list(subjects) == ["physics"]
    physics = subjects["physics"]
    assert physics.lesson("physics/waves/1.1").prerequisites == [
        physics.lesson("mechanics/1.2")]
    assert messages(tmp_path) == []


def test_a_written_lesson(tmp_path):
    folder = make_subject(tmp_path, first=[section("1.1", "Start", status="written"),
                                           section("1.2", "Go On")])
    physics = load_subject(folder)
    assert messages(tmp_path) == [
        "physics/mechanics/1.1: written, but has no lesson.md",
        "physics/mechanics/1.1: written, but has no exercises.py",
        "physics/mechanics/1.1: written, but its lab/ has no files"]
    lesson = write_lesson(physics, "mechanics/1.1")
    assert lesson.status == "written" and not lesson.planned
    assert messages(tmp_path) == []
    # its attribution is required, reflowed or not
    text = lesson.lesson_md.read_text().replace(" licensed under", "\nlicensed under")
    lesson.lesson_md.write_text(text)
    assert messages(tmp_path) == []
    write_lesson(physics, "mechanics/1.1", attribution=False)
    assert messages(tmp_path) == [
        f"physics/mechanics/1.1: lesson.md lacks its attribution: {lesson.attribution}"]
    write_lesson(physics, "mechanics/1.1")
    lesson.exercises.write_text("def exercises(:\n")
    assert messages(tmp_path) == ["physics/mechanics/1.1: exercises.py line 1: invalid syntax"]
    # a planned lesson's folder is a draft: fine
    write_lesson(physics, "mechanics/1.1")
    write_lesson(physics, "mechanics/1.2", attribution=False)
    assert messages(tmp_path) == []


def test_shared_and_required_lessons(tmp_path):
    folder = make_subject(tmp_path, first=[section("1.1", "Start", status="written")],
                          second=[section("1.1", "Start", shared="mechanics/1.1"),
                                  section("1.2", "More", requires=["physics/mechanics/1.1"])])
    physics = load_subject(folder)
    write_lesson(physics, "mechanics/1.1")
    assert messages(tmp_path) == []
    shared = physics.lesson("waves/1.1")
    assert shared.status == "written" and shared.source is physics.lesson("mechanics/1.1")
    assert physics.lesson("waves/1.2").prerequisites == [physics.lesson("mechanics/1.1"), shared]
    # a shared lesson's files are its source's
    write(physics.lesson("waves/1.1").chapter.folder / "1.1" / "lesson.md", "# x\n")
    assert messages(tmp_path) == [
        "physics/waves/1.1: shared, but has a folder of its own (its files go in "
        "mechanics/1.1's)"]


def test_mistakes_in_the_data(tmp_path):
    make_subject(tmp_path, first=[
        section("1.1", "Start", requires=["mechanics/1.9"]),
        section("1.3", "Skipped", status="done"),
        {"number": "1.3", "title": "Bad Page", "page": "Bad Page"},
        section("1.4", "Shares", shared="waves/1.1"),
        section("1.5", "Self", requires=["mechanics/1.5"])],
        second=[section("1.1", "Waves", shared="mechanics/1.4"),
                section("1.2", "Back", shared="mechanics/1.1")])
    write(tmp_path / "physics" / "mechanics" / "2" / "2.1" / "lesson.md", "# x\n")
    write(tmp_path / "physics" / "mechanics" / "1" / "1.7" / "lesson.md", "# x\n")
    assert messages(tmp_path) == [
        "physics/mechanics/1.1: requires mechanics/1.9, which isn't a lesson",
        "physics/mechanics/1.3: numbered where 1.2 was expected",
        "physics/mechanics/1.3: status 'done' isn't one of planned, written",
        "physics/mechanics/1.3: page 'Bad Page' isn't an openstax.org page name starting '1-3-'",
        "physics/mechanics/1.4: shares physics/waves/1.1, which shares mechanics/1.4: "
        "share the lesson written",
        "physics/mechanics/1.4: warning: shares physics/waves/1.1 titled 'Waves'",
        "physics/mechanics/1.5: requires itself",
        "physics/mechanics/1/1.7: isn't a lesson's folder",
        "physics/mechanics/2: isn't a chapter's folder",
        "physics/waves/1.1: shares physics/mechanics/1.4, which shares waves/1.1: "
        "share the lesson written",
        "physics/waves/1.1: warning: shares physics/mechanics/1.4 titled 'Shares'",
        "physics/waves/1.2: warning: shares physics/mechanics/1.1 titled 'Start'",
        "physics/mechanics/1.5: prerequisites go round: physics/mechanics/1.5 → "
        "physics/mechanics/1.5"]


def test_paths_and_files_that_are_wrong(tmp_path):
    make_subject(tmp_path, paths=[{"id": "main", "title": "Round",
                                   "nodes": ["mechanics", "waves", "optics"],
                                   "edges": [["mechanics", "waves"], ["waves", "mechanics"],
                                             ["waves", "sound"]]}])
    assert messages(tmp_path) == [
        "physics: path main: optics isn't one of the subject's books",
        "physics: path main: edge waves → sound leaves its nodes",
        "physics: path main: has a cycle",
        # (and so do the lessons along it)
        "physics/mechanics/1.2: prerequisites go round: physics/mechanics/1.1 → "
        "physics/waves/1.2 → physics/waves/1.1 → physics/mechanics/1.2 → physics/mechanics/1.1"]
    write(tmp_path / "physics" / "subject.json", {"title": "Physics", "books": ["mechanics"],
                                                  "paths": [], "colour": "red"})
    assert messages(tmp_path) == [
        f"physics: {tmp_path / 'physics' / 'subject.json'}: unknown keys colour"]
    with pytest.raises(SubjectError):
        load_subjects(tmp_path)
    write(tmp_path / "physics" / "subject.json", "{not json")
    assert "subject.json" in messages(tmp_path)[0]
    write(tmp_path / "physics" / "subject.json", {"title": "Physics", "books": ["mechanics"],
                                                  "paths": []})
    assert messages(tmp_path) == ["physics/mechanics: warning: on no learning path"]
    shutil.rmtree(tmp_path / "physics" / "mechanics")
    assert messages(tmp_path)[0].endswith("book.json: missing")


def test_the_command(tmp_path, capsys):
    folder = make_subject(tmp_path)
    assert edu_check.main(["--subjects", str(tmp_path)]) == 0
    assert capsys.readouterr().out == (
        "physics: 2 books, 4 lessons (0 written, 0 shared, 4 planned)\n0 problems, 0 warnings\n")
    assert edu_check.main(["--subjects", str(tmp_path), "--attribution", "physics/waves/1.2"]) == 0
    assert capsys.readouterr().out.startswith('Adapted from "1.2 Go On" in *Waves* by A. Author '
                                              "and B. Author (Us)")
    assert edu_check.main(["--subjects", str(tmp_path), "--attribution", "physics/x/1"]) == 1
    write(folder / "waves" / "stray.txt", "")
    assert edu_check.main(["--subjects", str(tmp_path), "-q"]) == 1
    assert capsys.readouterr().out == "physics/waves/stray.txt: isn't a chapter's folder\n"
    # the installed command, the default subjects
    result = subprocess.run([sys.executable, "-m", "vp6edu.check", "-q"], capture_output=True,
                            text=True, cwd=tmp_path)
    assert result.returncode == 0 and result.stdout == ""


def test_the_project():
    tomllib = pytest.importorskip("tomllib")
    root = ROOT / "packages" / "vp6edu"
    project = tomllib.loads((root / "pyproject.toml").read_text())
    assert project["project"]["name"] == "vp6edu"
    assert project["project"]["version"] == vp6edu.__version__
    assert project["project"]["scripts"] == {"vp6edu-check": "vp6edu.check:main"}
    assert project["project"]["dependencies"] == []  # (no Qt)
    assert project["tool"]["setuptools"]["package-data"] == {"vp6edu": ["subjects/**/*"]}
    assert "CC BY-NC-SA 4.0" in (root / "LICENSE").read_text()
    # its code doesn't import Qt
    for path in (root / "vp6edu").glob("*.py"):
        assert "PySide6" not in path.read_text(), path
