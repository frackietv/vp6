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
    assert len(math.lessons()) == 566  # (564 sections, chapter 1's review and test)
    book = math.books["prealgebra-2e"]
    assert book.chapters[0].title == "Whole Numbers"
    assert [lesson.title for lesson in book.chapters[0].lessons] == [
        "Introduction to Whole Numbers", "Add Whole Numbers", "Subtract Whole Numbers",
        "Multiply Whole Numbers", "Divide Whole Numbers", "Review Exercises", "Practice Test"]
    assert book.authors == ["Lynn Marecek", "MaryAnne Anthony-Smith", "Andrea Honeycutt Mathis"]
    assert book.licence.name == "CC BY-NC-SA 4.0"
    assert math.books["introductory-statistics-2e"].chapters[-1].title == \
        "F Distribution and One-Way ANOVA"
    # every lesson is planned until it's written: Prealgebra 2e's chapter 1 is
    assert [lesson for lesson in math.lessons() if not lesson.planned] == \
        book.chapters[0].lessons


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
    assert earlier == [lesson for lesson in math.books["prealgebra-2e"].lessons()
                       if lesson.kind == "section"]  # (not the chapters' reviews and tests)
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


EXERCISES = """\
from vp6edu.answers import Exercise, Number


def _maker(n):
    def make(rng):
        a = rng.randint(1, 9)
        return Exercise(f"Add ${a} + {n}$.", Number(a + n))
    make.__name__ = f"add_{n}"
    return make


for _n in range(10):
    globals()[f"add_{_n}"] = _maker(_n)
"""


def write_lesson(subject, ref, attribution=True):
    lesson = subject.lesson(ref)
    text = (f"# {lesson.title}\n\n## Learning Objectives\n\n- Start.\n\n## Be Prepared\n\n"
            f"Nothing.\n\nOur own words.\n\n## Key Concepts\n\n- None.\n")
    if attribution:
        text += "\n---\n\n" + lesson.attribution + "\n"
    write(lesson.lesson_md, text)
    write(lesson.exercises, EXERCISES)
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


def test_a_chapters_review_and_test(tmp_path):
    folder = make_subject(tmp_path, first=[
        section("1.1", "Start"), section("1.2", "Go On"),
        {"number": "1-review", "title": "Review Exercises", "page": "1-review-exercises",
         "kind": "review"},
        {"number": "1-test", "title": "Practice Test", "page": "1-practice-test", "kind": "test"}])
    physics = load_subject(folder)
    review, test = physics.lesson("mechanics/1-review"), physics.lesson("mechanics/1-test")
    assert (review.kind, test.kind, physics.lesson("mechanics/1.2").kind) == \
        ("review", "test", "section")
    assert review.label == "Chapter 1 Review" and test.label == "Chapter 1 Test"
    assert physics.lesson("mechanics/1.2").label == "Lesson 1.2"
    assert review.heading == "Chapter 1: Review Exercises"
    assert physics.lesson("mechanics/1.2").heading == "1.2 Go On"
    assert review.attribution.startswith('Adapted from "Chapter 1: Review Exercises" in *Mechanics*')
    # the review follows the last section, the test the review; the next book's first lesson
    # follows the book's last lesson
    assert review.prerequisites == [physics.lesson("mechanics/1.2")]
    assert test.prerequisites == [review]
    assert physics.lesson("waves/1.1").prerequisites == [test]
    assert messages(tmp_path) == []
    # out of order, misnumbered, of an unknown kind
    make_subject(tmp_path, first=[
        section("1.1", "Start"),
        {"number": "1-test", "title": "Practice Test", "page": "1-practice-test", "kind": "test"},
        {"number": "1-review", "title": "Review", "page": "2-review", "kind": "review"},
        section("1.2", "Go On"),
        {"number": "1-quiz", "title": "Quiz", "page": "1-quiz", "kind": "quiz"}])
    assert messages(tmp_path) == [
        "physics/mechanics/1-review: page '2-review' isn't an openstax.org page name "
        "starting '1-'",
        "physics/mechanics/1-quiz: kind 'quiz' isn't one of section, review, test",
        "physics/mechanics: chapter 1's review and test aren't after its sections",
        "physics/mechanics: chapter 1 ends with test, review, quiz: a review, then a test"]


LESSON_TEXT = """\
# 1.1 Start

## Learning Objectives

- Start.

## Be Prepared

Go back to [the start](lesson:physics/mechanics/1.1) or [nowhere](lesson:mechanics/9.9).

$\\frac{1}{2}$ is fine; $\\frac{1}{2$ isn't.

```answer
Number(5)
```

```answer
Number(
```

```answer
Choice("Z", ["a", "b"])
```

## Key Concepts

- None.
"""


def test_written_lessons_in_depth(tmp_path):
    folder = make_subject(tmp_path, first=[section("1.1", "Start", status="written"),
                                           section("1.2", "Go On")])
    physics = load_subject(folder)
    lesson = write_lesson(physics, "mechanics/1.1")
    assert messages(tmp_path) == []
    # its text: formulas, Try Its, links to lessons, its parts
    lesson.lesson_md.write_text(LESSON_TEXT + "\n" + lesson.attribution + "\n")
    found = messages(tmp_path)
    where = "physics/mechanics/1.1 lesson.md: "
    assert found[0].startswith(where + "a formula that can't be laid out: $\\frac{1}{2$")
    assert found[1].startswith(where + "a Try It's answer that can't be read: SyntaxError")
    assert found[2].startswith(where + "a Try It's answer that can't be read: Unreadable")
    assert found[3:] == [where + "links to lesson mechanics/9.9, which isn't one"]
    text = lesson.lesson_md.read_text().replace("## Be Prepared", "## Getting Ready")
    text = text.replace(" or [nowhere](lesson:mechanics/9.9)", "")
    lesson.lesson_md.write_text(text[:text.index("$")] + "\n## Key Concepts\n\n"
                                + lesson.attribution + "\n")
    assert messages(tmp_path) == [where + "warning: has no ## Be Prepared"]
    write_lesson(physics, "mechanics/1.1")
    # its exercises: how many, each over many seeds, their formulas
    lesson.exercises.write_text(EXERCISES.replace("range(10)", "range(3)").replace(
        "import Exercise, Number", "import Exercise, Number, Result") + '''

def broken(rng):
    if rng.random() < 0.5:
        raise ValueError("unlucky")
    return Exercise("$1 + 1$", Number(2))


class _Never(Number):
    def _judge(self, got):
        return Result("not yet", "Never.")


def wrong(rng):
    return Exercise("$1 + 1$", _Never(2))


def bad_formula(rng):
    return Exercise("Add.", Number(2), hints=[r"$\\frac{1$"])
''')
    found = messages(tmp_path)
    where = "physics/mechanics/1.1 exercises.py: "
    assert found[0] == where + "warning: has 6 exercises, not 10–20"
    assert found[1].startswith(where + "broken, seed ") and found[1].endswith(
        "ValueError: unlucky")
    assert any(f.startswith(where + "wrong, seed 0: its answer '2' checks") for f in found)
    assert found[-1].startswith(where + "bad_formula, seed 0: a formula that can't be laid out")
    lesson.exercises.write_text("import nothing_like_this\n")
    assert messages(tmp_path) == [
        where + "can't be loaded: ModuleNotFoundError: No module named 'nothing_like_this'"]


def test_try_its_answers():
    from vp6edu.answers import Number, answer_of

    assert isinstance(answer_of("Number(Fraction(3, 4))"), Number)
    assert answer_of("Pair((41, 8), names=('quotient', 'remainder'))").check("(41, 8)").right
    with pytest.raises(ValueError, match="isn't an answer"):
        answer_of("3 + 4")
    with pytest.raises(ValueError, match="NameError"):
        answer_of("Nmuber(3)")


def test_the_pilot_chapter(math):
    """Prealgebra 2e's chapter 1, written as the model for the others: five sections, a
    review and a test, each with its parts, 10–20 exercises and a lab."""
    from vp6edu.answers import generators, load_exercises

    chapter = math.books["prealgebra-2e"].chapters[0]
    assert [(lesson.number, lesson.kind, lesson.status) for lesson in chapter.lessons] == [
        ("1.1", "section", "written"), ("1.2", "section", "written"),
        ("1.3", "section", "written"), ("1.4", "section", "written"),
        ("1.5", "section", "written"), ("1-review", "review", "written"),
        ("1-test", "test", "written")]
    for lesson in chapter.lessons:
        text = lesson.lesson_md.read_text(encoding="utf-8")
        makers = generators(load_exercises(lesson.exercises))
        assert 10 <= len(makers) <= 20, lesson.id
        assert (lesson.lab / "Form1.py").is_file()
        assert "```answer" in text and "## Lab" in text
        before = [each for each in lesson.prerequisites if each.book is lesson.book]
        for each in before:  # (Be Prepared links back to the lessons it needs)
            assert f"(lesson:{each.id})" in text or lesson.kind != "section", lesson.id
    assert math.lesson("prealgebra-2e/1.2").prerequisites == [math.lesson("prealgebra-2e/1.1")]
    assert math.lesson("prealgebra-2e/2.1").prerequisites == [math.lesson("prealgebra-2e/1.5")]
    # and vp6edu-check passes it with many seeds (its labs are run by test_lessons.py)
    assert edu_check.check(seeds=200) == []


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
