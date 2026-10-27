"""Lesson projects and the Lesson window (vp6/ide/logic/education.py,
vp6/ide/lessonwindow.py): a stand-in subject in a temporary folder, its
lessons made into projects from their labs, their text, exercises and
progress, and the window in the IDE."""

import json
import os
import textwrap

import pytest

from vp6 import formfile
from vp6.ide.logic import education, settings
from vp6.project import EXTENSION, Project
from vp6edu import load_subject

LESSON_MD = """\
# {number} {title}

## Learning Objectives

- Add whole numbers.

Add $2 + 3$.

```answer
Number(5)
```

Some code that isn't a section:

```text
## Lab
```

## Key Terms

**sum**: what adding gives.

## Lab

Change `Form1` so that it adds three numbers, then press F5.

---

{attribution}
"""

EXERCISES = '''\
from vp6edu.answers import Exercise, Number, Point


def add_whole_numbers(rng):
    a, b = rng.randint(1, 9), rng.randint(1, 9)
    return Exercise(f"Add ${a} + {b}$.", Number(a + b),
                    hints=["Count on from the first number.", "Or use a number line."],
                    solution=f"${a} + {b} = {a + b}$")


def plot_a_point(rng):
    x, y = rng.randint(-4, 4), rng.randint(-4, 4)
    return Exercise(f"Plot the point $({x}, {y})$.", Point(x, y))
'''


def _section(number, title, status="planned", **more):
    return {"number": number, "title": title,
            "page": f"{number.replace('.', '-')}-{title.lower().replace(' ', '-')}",
            "status": status, **more}


def _book(title, sections):
    return {"title": title, "publisher": "OpenStax", "authors": ["A. Author", "B. Author"],
            "link": "https://openstax.org/details/books/x",
            "licence": {"name": "CC BY-NC-SA 4.0",
                        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"},
            "chapters": [{"number": 1, "title": "Whole Numbers", "sections": sections}]}


def make_subject(root):
    """A subject "edu": books a, b and c (a → b, a → c), some lessons written."""
    folder = root / "edu"
    for book in ("book-a", "book-b", "book-c"):
        (folder / book).mkdir(parents=True)
    (folder / "subject.json").write_text(json.dumps({
        "title": "Education", "books": ["book-a", "book-b", "book-c"],
        "paths": [{"id": "main", "title": "A to B", "nodes": ["book-a", "book-b", "book-c"],
                   "edges": [["book-a", "book-b"], ["book-a", "book-c"]]}]}))
    (folder / "book-a" / "book.json").write_text(json.dumps(_book("Book A", [
        _section("1.1", "Adding", "written"), _section("1.2", "Subtracting"),
        _section("1.3", "Multiplying", "written")])))
    (folder / "book-b" / "book.json").write_text(json.dumps(_book("Book B", [
        _section("1.1", "Dividing", "written")])))
    (folder / "book-c" / "book.json").write_text(json.dumps(_book("Book C", [
        _section("1.1", "Counting", "written")])))
    subject = load_subject(folder)
    for lesson in subject.lessons():
        if lesson.planned:
            continue
        lesson.lab.mkdir(parents=True)
        lesson.lesson_md.write_text(LESSON_MD.format(number=lesson.number, title=lesson.title,
                                                     attribution=lesson.attribution))
        lesson.exercises.write_text(EXERCISES)
        (lesson.lab / "Form1.py").write_text(formfile.new_form_source("Form1", "Adding"))
        (lesson.lab / "Helpers.py").write_text("def add(a, b):\n    return a + b\n")
    return subject


@pytest.fixture
def subject(tmp_path, monkeypatch):
    root = tmp_path / "subjects"
    made = make_subject(root)
    monkeypatch.setattr(education, "SUBJECT_ROOTS", [root])
    return made


@pytest.fixture
def memory_settings():
    store = settings.MemorySettings()
    settings.use(lambda: store)
    yield store
    settings.use(None)


# --- lesson projects ----------------------------------------------------------------------

def test_a_lesson_project_is_made_from_its_lab(subject, tmp_path):
    lesson = subject.lesson("book-a/1.1")
    folder = education.project_folder(str(tmp_path / "lessons"), lesson)
    assert folder == str(tmp_path / "lessons" / "edu" / "book-a" / "1.1")
    path = education.create_lesson_project(lesson, folder)
    assert path == os.path.join(folder, "Lesson1_1" + EXTENSION)
    project = Project.load(path)
    assert project.lesson == "edu/book-a/1.1" and project.description == "Adding"
    assert project.forms == ["Form1.py"] and project.modules == ["Helpers.py"]
    assert project.startup == "Form1" and project.name == "Lesson1_1"
    assert sorted(os.listdir(folder)) == ["Form1.py", "Helpers.py", "Lesson1_1.vp6p"]
    # Made once: opened again, the student's changes stay
    with open(os.path.join(folder, "Helpers.py"), "a") as f:
        f.write("# mine\n")
    assert education.create_lesson_project(lesson, folder) == path
    assert "# mine" in open(os.path.join(folder, "Helpers.py")).read()
    assert education.existing_project(folder, "edu/book-a/1.3") is None


def test_a_lesson_project_needs_a_folder_of_its_own(subject, tmp_path):
    folder = tmp_path / "taken"
    folder.mkdir()
    (folder / "notes.txt").write_text("mine")
    with pytest.raises(FileExistsError):
        education.create_lesson_project(subject.lesson("book-a/1.1"), str(folder))


def test_a_lab_with_a_project_of_its_own(subject, tmp_path):
    lesson = subject.lesson("book-b/1.1")
    (lesson.lab / "Main.py").write_text("def Main():\n    pass\n")
    Project(name="Lab", forms=["Form1.py"], modules=["Main.py", "Helpers.py"],
            startup="Sub Main").save(str(lesson.lab / "Lab.vp6p"))
    path = education.create_lesson_project(lesson, str(tmp_path / "b"))
    project = Project.load(path)
    assert os.path.basename(path) == "Lesson1_1.vp6p"
    assert not os.path.exists(tmp_path / "b" / "Lab.vp6p")
    assert project.startup == "Sub Main" and project.modules == ["Main.py", "Helpers.py"]
    assert project.lesson == "edu/book-b/1.1"


def test_the_lesson_key_is_kept_in_the_project_file(tmp_path):
    path = str(tmp_path / "P.vp6p")
    Project(name="P", lesson="math/prealgebra-2e/1.2").save(path)
    assert '"lesson": "math/prealgebra-2e/1.2",' in open(path).read()
    assert Project.load(path).lesson == "math/prealgebra-2e/1.2"
    Project(name="Q").save(str(tmp_path / "Q.vp6p"))
    assert Project.load(str(tmp_path / "Q.vp6p")).lesson == ""


def test_lessons_along_the_path(subject):
    ids = [lesson.id for lesson in education.path_lessons(subject)]
    assert ids == ["edu/book-a/1.1", "edu/book-a/1.2", "edu/book-a/1.3", "edu/book-b/1.1",
                   "edu/book-c/1.1"]
    first, third = subject.lesson("book-a/1.1"), subject.lesson("book-a/1.3")
    assert education.neighbour(first, 1) is third  # (1.2 is only planned)
    assert education.neighbour(third, -1) is first
    assert education.neighbour(first, -1) is None
    assert education.neighbour(third, 1) is subject.lesson("book-b/1.1")
    assert education.neighbour(subject.lesson("book-c/1.1"), 1) is None
    assert education.find_lesson("edu/book-b/1.1") is subject.lesson("book-b/1.1") or \
        education.find_lesson("edu/book-b/1.1").title == "Dividing"
    assert education.find_lesson("edu/book-b/9.9") is None
    assert education.find_lesson("nothing/a/1.1") is None


def test_where_the_neighbours_go(subject, tmp_path):
    lesson = subject.lesson("book-a/1.1")
    root = str(tmp_path / "VP6 Lessons")
    assert education.root_of(education.project_folder(root, lesson), lesson) == root
    assert education.root_of(str(tmp_path / "elsewhere" / "Mine"), lesson) == \
        str(tmp_path / "elsewhere")
    assert education.default_root("/x") == os.path.join("/x", "VP6 Lessons")


# --- the lesson's text --------------------------------------------------------------------

def test_a_lesson_is_split_into_parts():
    text = education.parse_lesson(textwrap.dedent("""\
        # 1.1 Adding

        Add $2 + 3$.

        ```answer
        Number(5)
        ```

        ```text
        ## Lab
        ```

        ## Lab

        Run it.

        ```python
        print(1)
        ```

        ## Key Terms

        sum

        ## Lab

        More.

        ---

        Attributed.
        """))
    assert text.title == "1.1 Adding"
    assert [p.kind for p in text.parts] == ["text", "answer", "text"]
    assert text.parts[0].text == "# 1.1 Adding\n\nAdd $2 + 3$."
    assert text.parts[1].text == "Number(5)"
    assert "## Lab" in text.parts[2].text and "## Key Terms" in text.parts[2].text
    assert "Run it." not in text.parts[2].text
    assert text.lab == "Run it.\n\n```python\nprint(1)\n```\n\nMore."
    assert text.parts[2].text.endswith("sum\n\n---\n\nAttributed.")


def test_try_it_answers():
    answer = education.try_it_answer("Number(Fraction(3, 4), form='simplest')")
    assert answer.check("3/4").right and not answer.check("6/8").right
    assert education.try_it_answer("Point(1, 2)").check("(1, 2)").right
    with pytest.raises(ValueError, match="isn't an answer"):
        education.try_it_answer("5")
    with pytest.raises(ValueError, match="NameError"):
        education.try_it_answer("Nothing(5)")


# --- progress and exercises ---------------------------------------------------------------

def test_progress_is_kept_in_the_settings(memory_settings):
    assert education.progress("edu/a/1.1") == education.Progress()
    assert education.Progress().state == education.NOT_STARTED
    record = education.Progress(read=True, exercises=2)
    assert record.state == education.IN_PROGRESS
    education.save_progress("edu/a/1.1", record)
    assert json.loads(memory_settings.values["education/progress/edu/a/1.1"])["read"]
    record.lab_run = True
    record.right = ["a", "b"]
    assert record.state == education.DONE
    education.save_progress("edu/a/1.1", record)
    assert education.progress("edu/a/1.1").state == education.DONE
    education.reset_progress("edu/a/1.1")
    assert education.progress("edu/a/1.1") == education.Progress()
    memory_settings.setValue("education/progress/edu/a/1.2", "not json")
    assert education.progress("edu/a/1.2") == education.Progress()


def test_exercises_one_after_another(subject):
    record = education.Progress()
    changes = []
    session = education.ExerciseSession.of_lesson(subject.lesson("book-a/1.1"), record,
                                                  lambda: changes.append(1), seed=3)
    assert [m.__name__ for m in session.makers] == ["add_whole_numbers", "plot_a_point"]
    assert record.exercises == 2 and changes
    assert session.name == "add_whole_numbers"
    assert education.graph_settings(session.exercise) is None
    assert session.check("nonsense +").status == "unreadable" and record.tried == []
    assert not session.check("100").right and record.tried == ["add_whole_numbers"]
    assert session.check(session.exercise.answer.text).right
    assert record.right == ["add_whole_numbers"]
    assert session.score_text() == "1 of 2 right (1 tried)"
    assert session.hint() == "Count on from the first number."
    session.new_numbers(seed=11)
    first = session.exercise.prompt
    session.new_numbers(seed=11)
    assert session.exercise.prompt == first
    session.go(1)
    assert session.name == "plot_a_point"
    assert education.graph_settings(session.exercise) == {"PlaceMode": 1}
    assert "The answer: (" in session.solution()
    assert session.check(session.exercise.answer.text).right
    assert record.right == ["add_whole_numbers"]  # (not counted: the solution was shown)
    session.go(2)
    assert session.index == 0


def test_graph_settings_for_the_answers():
    from vp6edu.answers import Exercise, Inequality, Line, Number

    assert education.graph_settings(Exercise("p", Line("y = x"))) == {"PlaceMode": 2}
    assert education.graph_settings(Exercise("p", Inequality("x > 1"))) is None
    assert education.graph_settings(Exercise("p", Inequality("x > 1"), graph={"XMin": -2})) \
        == {"XMin": -2, "Mode": 1, "PlaceMode": 3}
    assert education.graph_settings(Exercise("p", Number(1), graph={})) == {}


# --- the Lesson window --------------------------------------------------------------------

@pytest.fixture
def window(qapp):
    from vp6.ide.mainwindow import MainWindow

    w = MainWindow()
    w.show()
    yield w
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()
    w.deleteLater()


def test_opening_a_lesson_project_opens_the_lesson_window(window, subject, tmp_path):
    from vp6.ide.lessonwindow import LessonWindow

    root = str(tmp_path / "VP6 Lessons")
    assert window.open_lesson(subject.lesson("book-a/1.1"), root)
    assert window.project.lesson == "edu/book-a/1.1"
    lesson = window.lesson_window()
    assert isinstance(lesson, LessonWindow)
    assert window.act_view_lesson.isEnabled()
    assert [lesson.tabs.tabText(i) for i in range(3)] == ["Lesson", "Exercises", "Lab"]
    assert lesson.title == "Lesson 1.1: Adding"
    # The Lesson tab: Markdown with maths, a Try It, the link to the section
    assert len(lesson.try_its) == 1
    try_it = lesson.try_its[0]
    try_it.field.setText("6")
    assert not try_it.check().right
    try_it.field.setText("5")
    assert try_it.check().right and "Right" in try_it.result.text()
    assert "openstax.org/books/book-a/pages/1-1-adding" in lesson.footer.toPlainText()
    assert "Change" not in "".join(v.toPlainText() for v in lesson.lesson_views)
    # The Exercises tab
    session = lesson.session
    lesson.answer_field.setText(session.exercise.answer.text)
    assert lesson.check().right
    assert lesson.record.right == ["add_whole_numbers"]
    assert lesson.hint() == "Count on from the first number."
    assert "Hint 1" in lesson.feedback.toPlainText()
    lesson.next_exercise()
    assert lesson.graph is not None and lesson.answer_field.isHidden()
    assert lesson.check() is None  # (nothing placed yet)
    lesson.graph._place(*session.exercise.answer.values)
    assert lesson.check().right
    assert lesson.score_label.text() == "2 of 2 right (2 tried)"
    # The Lab tab
    assert "adds three numbers" in lesson.lab_view.toPlainText()
    assert lesson.forms.count() == 1
    opened = []
    lesson.formRequested.connect(opened.append)
    lesson.forms.itemDoubleClicked.emit(lesson.forms.item(0))
    assert opened == [os.path.join(window.project.directory, "Form1.py")]
    lesson.lab_ran()
    # Progress: in the IDE's settings
    record = education.progress("edu/book-a/1.1")
    assert record.lab_run and record.right == ["add_whole_numbers", "plot_a_point"]
    record.read = True
    assert record.state == education.DONE
    lesson.reset_progress(ask=False)
    assert education.progress("edu/book-a/1.1").right == []
    assert lesson.record.exercises == 2


def test_previous_and_next_go_along_the_path(window, subject, tmp_path):
    root = str(tmp_path / "VP6 Lessons")
    assert window.open_lesson(subject.lesson("book-a/1.1"), root)
    lesson = window.lesson_window()
    assert not lesson.previous_button.isEnabled()
    assert lesson.next_lesson.id == "edu/book-a/1.3"
    assert window.open_lesson(lesson.next_lesson)  # (beside the first one)
    assert window.project.lesson == "edu/book-a/1.3"
    assert window.project.directory == os.path.join(root, "edu", "book-a", "1.3")
    assert len(window.lesson_windows()) == 1
    assert window.lesson_window().previous_lesson.id == "edu/book-a/1.1"


def test_a_lesson_project_without_its_lesson(window, tmp_path, subject):
    path = str(tmp_path / "P" / "P.vp6p")
    os.makedirs(os.path.dirname(path))
    with open(os.path.join(os.path.dirname(path), "Form1.py"), "w") as f:
        f.write(formfile.new_form_source("Form1"))
    Project(name="P", forms=["Form1.py"], lesson="edu/book-z/1.1").save(path)
    assert window.open_project(path)
    assert window.lesson_window() is None
    window.close_project()
    assert not window.act_view_lesson.isEnabled()


def test_running_the_lab_counts(window, subject, tmp_path, monkeypatch):
    from PySide6.QtCore import QProcess

    assert window.open_lesson(subject.lesson("book-b/1.1"), str(tmp_path / "L"))
    monkeypatch.setattr(QProcess, "start", lambda *a, **k: None)
    window.run_project()
    assert education.progress("edu/book-b/1.1").lab_run
    window.process = None
    window._end_debugging()
