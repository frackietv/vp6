"""The Lesson window: a vp6edu lesson beside its lab project, in the MDI area.

Opening a lesson's project (one whose ``lesson`` is a lesson's id) opens it,
with three tabs:

* **Lesson:** ``lesson.md`` with its maths (vp6help's Markdown, the formulas
  drawn by ``texdraw``), its Try Its' answers checked in place, the
  attribution footer and a link to the section on openstax.org; scrolled to
  the end, the lesson counts as read.
* **Exercises:** the makers of ``exercises.py`` one after another, answered
  in a field or on a Graph (``education.graph_settings``), with Check,
  Hint, Show Solution, New Numbers, Next Exercise and the score.
* **Lab:** the lesson's ``## Lab`` section, Run the Lab (F5) and the lab's
  forms (a double click opens one's designer).

Previous Lesson and Next Lesson go along the learning path
(``lessonRequested``); Reset Progress forgets the lesson's progress. What
needs no Qt is in ``logic/education.py``.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette, QTextOption
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import icons
from .logic import education
from .terminalpanel import _PanelHost
from .theme import theme_manager


def _colors() -> dict:
    dark = theme_manager().app_is_dark()
    return {"right": "#5cc96b" if dark else "#1e7d32",
            "wrong": "#ff8a65" if dark else "#c0471a",
            "dim": "#9a9a9a" if dark else "#707070",
            "link": "#6cb6ff" if dark else "#1f5fbf"}


class MarkdownView(QTextBrowser):
    """Markdown with maths, as tall as its text (the page around it scrolls);
    links open in the browser, pictures are found in ``folder``."""

    def __init__(self, text: str = "", folder: str = "", parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.viewport().setAutoFillBackground(False)
        if folder:
            self.setSearchPaths([folder])
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.markdown = ""
        self._html = None  # (set_html's, made again when the theme changes)
        self._link_color()
        self.set_markdown(text)
        theme_manager().changed.connect(self._theme_changed)

    def set_markdown(self, text: str) -> None:
        from vp6help.markdown import to_html

        self.markdown, self._html = text, None
        self.setHtml(to_html(text) if text.strip() else "")
        if "vp6math:" in self.toHtml():
            from vp6help import texdraw
            texdraw.install(self.document())
        self._fit()

    def set_html(self, make) -> None:
        """Text from ``make()``, HTML (made again with the theme's colours)."""
        self.markdown, self._html = "", make
        self.setHtml(make())
        self._fit()

    def _link_color(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.Link, QColor(_colors()["link"]))
        self.setPalette(palette)

    def _theme_changed(self) -> None:
        self._link_color()  # (links take their colour when the text is set)
        if self._html is not None:
            self.set_html(self._html)
        else:
            self.set_markdown(self.markdown)

    def _fit(self, *_):
        document = self.document()
        document.setTextWidth(max(1, self.viewport().width()))
        height = int(document.size().height()) + 2 * self.frameWidth() + 2
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class TryIt(QWidget):
    """A Try It's answer field in the lesson, checked in place."""

    def __init__(self, source: str, parent=None):
        super().__init__(parent)
        self.answer = None
        self._shown = None
        theme_manager().changed.connect(self._theme_changed)
        try:
            self.answer = education.try_it_answer(source)
        except ValueError as error:
            self.problem = str(error)
        else:
            self.problem = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 8)
        self.field = QLineEdit()
        self.field.setPlaceholderText("Your answer")
        self.field.returnPressed.connect(self.check)
        self.button = QPushButton("Check")
        self.button.clicked.connect(self.check)
        self.result = QLabel()
        self.result.setWordWrap(True)
        layout.addWidget(QLabel("Try it:"))
        layout.addWidget(self.field, 2)
        layout.addWidget(self.button)
        layout.addWidget(self.result, 3)
        if self.problem:  # (the lesson's mistake: shown where the field would be)
            self.field.setEnabled(False)
            self.button.setEnabled(False)
            self._show(f"This Try It's answer can't be read: {self.problem}", "wrong")

    def _show(self, text: str, kind: str) -> None:
        self._shown = (text, kind)
        self.result.setText(f"<span style='color:{_colors()[kind]}'>{html.escape(text)}</span>")

    def _theme_changed(self) -> None:
        if self._shown:
            self._show(*self._shown)

    def check(self):
        if self.answer is None:
            return None
        result = self.answer.check(self.field.text())
        self._show(result.message or result.status, "right" if result.right else "wrong")
        return result


class _GraphHost(_PanelHost):
    """What the Graph an exercise is answered on needs of its form."""

    def __init__(self, widget: QWidget):
        self._widget = widget
        self._controls: list = []

    def _container_widget(self) -> QWidget:
        return self._widget

    def _base_dir(self) -> str:
        return ""


class LessonWindow(QWidget):
    """A lesson (``vp6edu.Lesson``) and its lab project (``vp6.project.Project``)."""

    lessonRequested = Signal(object)  # Previous/Next: the lesson to open
    runRequested = Signal()  # Run the Lab
    formRequested = Signal(str)  # a lab form to open in its designer (its path)
    progressChanged = Signal()

    def __init__(self, lesson, project, parent=None):
        super().__init__(parent)
        self.lesson = lesson
        self.project = project
        self.record = education.progress(lesson.id)
        folder = str(lesson.folder)
        try:
            source = lesson.lesson_md.read_text(encoding="utf-8")
        except OSError:
            source = f"# {lesson.number} {lesson.title}\n\nThis lesson isn't written yet."
        self.text = education.parse_lesson(source)
        self.title = f"Lesson {lesson.number}: {lesson.title}"
        self.setWindowTitle(self.title)

        header = QLabel(f"<b>{html.escape(lesson.book.title)}</b> · "
                        f"{html.escape(lesson.chapter.title)}")
        self.state_label = QLabel()
        self.lab_state = QLabel()  # (the Lab tab's, set as progress is saved)
        top = QHBoxLayout()
        top.addWidget(header, 1)
        top.addWidget(self.state_label)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._lesson_tab(folder), "Lesson")
        self.tabs.addTab(self._exercises_tab(), "Exercises")
        self.tabs.addTab(self._lab_tab(folder), "Lab")
        self.tabs.currentChanged.connect(lambda *_: self._check_read())

        self.previous_lesson = education.neighbour(lesson, -1)
        self.next_lesson = education.neighbour(lesson, 1)
        self.previous_button = QPushButton("◀ Previous Lesson")
        self.previous_button.setEnabled(self.previous_lesson is not None)
        self.previous_button.clicked.connect(
            lambda: self.lessonRequested.emit(self.previous_lesson))
        self.next_button = QPushButton("Next Lesson ▶")
        self.next_button.setEnabled(self.next_lesson is not None)
        self.next_button.clicked.connect(lambda: self.lessonRequested.emit(self.next_lesson))
        for button, other in ((self.previous_button, self.previous_lesson),
                              (self.next_button, self.next_lesson)):
            if other is not None:
                button.setToolTip(f"{other.number} {other.title} ({other.book.title})")
        self.reset_button = QPushButton("Reset Progress")
        self.reset_button.clicked.connect(lambda: self.reset_progress())
        bottom = QHBoxLayout()
        bottom.addWidget(self.previous_button)
        bottom.addStretch(1)
        bottom.addWidget(self.reset_button)
        bottom.addStretch(1)
        bottom.addWidget(self.next_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)
        self._update_state()
        theme_manager().changed.connect(self._update_state)

    # -- the Lesson tab ---------------------------------------------------------------------
    def _lesson_tab(self, folder: str) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(8, 8, 8, 8)
        self.lesson_views: list[MarkdownView] = []
        self.try_its: list[TryIt] = []
        for part in self.text.parts:
            if part.kind == "answer":
                widget = TryIt(part.text)
                self.try_its.append(widget)
            else:
                widget = MarkdownView(part.text, folder)
                self.lesson_views.append(widget)
            column.addWidget(widget)
        lesson = self.lesson
        footer = (f"*{lesson.number} {lesson.title}* on openstax.org: <{lesson.link}>")
        if lesson.attribution not in "\n".join(p.text for p in self.text.parts):
            footer = lesson.attribution + "\n\n" + footer  # (an unwritten lesson's)
        self.footer = MarkdownView(footer, folder)
        column.addWidget(self.footer)
        column.addStretch(1)
        self.lesson_scroll = QScrollArea()
        self.lesson_scroll.setWidgetResizable(True)
        self.lesson_scroll.setFrameShape(QFrame.NoFrame)
        self.lesson_scroll.setWidget(page)
        bar = self.lesson_scroll.verticalScrollBar()
        bar.valueChanged.connect(lambda *_: self._check_read())
        bar.rangeChanged.connect(lambda *_: self._check_read())
        return self.lesson_scroll

    def _check_read(self) -> None:
        """Scrolled to the lesson's end (or all of it showing): read."""
        if self.record.read or self.tabs.currentIndex() != 0 or not self.isVisible():
            return
        bar = self.lesson_scroll.verticalScrollBar()
        if self.lesson_scroll.widget().height() > 0 and bar.value() >= bar.maximum():
            self.record.read = True
            self._save()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_read()

    # -- the Exercises tab ------------------------------------------------------------------
    def _exercises_tab(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(8, 8, 8, 8)
        self.exercise_label = QLabel()
        self.score_label = QLabel()
        heading = QHBoxLayout()
        heading.addWidget(self.exercise_label, 1)
        heading.addWidget(self.score_label)
        column.addLayout(heading)
        self.prompt = MarkdownView(folder=str(self.lesson.folder))
        column.addWidget(self.prompt)
        self.answer_field = QLineEdit()
        self.answer_field.setPlaceholderText("Your answer")
        self.answer_field.returnPressed.connect(lambda: self.check())
        column.addWidget(self.answer_field)
        self.graph_box = QWidget()
        self.graph_box.setMinimumHeight(280)
        QVBoxLayout(self.graph_box).setContentsMargins(0, 0, 0, 0)
        self.graph = None
        column.addWidget(self.graph_box)
        buttons = QHBoxLayout()
        self.check_button = QPushButton("Check")
        self.check_button.setDefault(True)
        self.check_button.clicked.connect(lambda: self.check())
        self.hint_button = QPushButton("Hint")
        self.hint_button.clicked.connect(lambda: self.hint())
        self.solution_button = QPushButton("Show Solution")
        self.solution_button.clicked.connect(lambda: self.show_solution())
        self.new_button = QPushButton("New Numbers")
        self.new_button.clicked.connect(lambda: self.new_numbers())
        self.next_exercise_button = QPushButton("Next Exercise ▶")
        self.next_exercise_button.clicked.connect(lambda: self.next_exercise())
        for button in (self.check_button, self.hint_button, self.solution_button,
                       self.new_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.next_exercise_button)
        column.addLayout(buttons)
        self.feedback = MarkdownView(folder=str(self.lesson.folder))
        column.addWidget(self.feedback)
        column.addStretch(1)
        self.session = None
        self.exercise_problem = ""
        try:
            self.session = education.ExerciseSession.of_lesson(self.lesson, self.record,
                                                               self._save)
        except Exception as error:  # noqa: BLE001 (the lesson's exercises.py)
            self.exercise_problem = f"The exercises can't be loaded: {type(error).__name__}: " \
                                    f"{error}"
        self._show_exercise()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _show_exercise(self) -> None:
        session = self.session
        ready = bool(session and session.makers)
        for widget in (self.answer_field, self.check_button, self.hint_button,
                       self.solution_button, self.new_button, self.next_exercise_button):
            widget.setEnabled(ready)
        self.feedback.set_markdown("")
        self._set_graph(None)
        if not ready:
            self.exercise_label.setText("")
            self.prompt.set_markdown(self.exercise_problem or "This lesson has no exercises yet.")
            self.answer_field.hide()
            self.score_label.setText("")
            return
        exercise = session.exercise
        self.exercise_label.setText(f"<b>Exercise {session.index + 1} of "
                                    f"{len(session.makers)}</b> · "
                                    f"{html.escape(exercise.skill)}")
        self.prompt.set_markdown(exercise.prompt)
        self.answer_field.clear()
        graph = education.graph_settings(exercise)
        self._set_graph(graph)
        self.answer_field.setVisible(graph is None)
        self.hint_button.setEnabled(exercise.hints_left > 0)
        self.score_label.setText(session.score_text())

    def _set_graph(self, values: dict | None) -> None:
        if self.graph is not None:
            self.graph._widget.hide()
            self.graph._widget.deleteLater()
            self.graph = None
        self.graph_box.setVisible(values is not None)
        if values is None:
            return
        from ..graph import Graph

        self.graph = Graph(_GraphHost(self.graph_box), "grfAnswer", **values)
        self.graph_box.layout().addWidget(self.graph._widget)
        self.graph._widget.show()

    def check(self):
        """Check the answer given (typed, or placed on the graph)."""
        if not (self.session and self.session.makers):
            return None
        if self.graph is not None:
            response = self.graph.Answer
            if response is None or response == []:
                self._feedback("Place your answer on the graph first.", "wrong")
                return None
        else:
            response = self.answer_field.text()
        result = self.session.check(response)
        message = result.message or result.status
        if result.right and self.session.solution_shown:
            message += " (Not counted, as the solution was shown: try New Numbers.)"
        self._feedback(message, "right" if result.right else "wrong")
        self.score_label.setText(self.session.score_text())
        return result

    def _feedback(self, text: str, kind: str) -> None:
        self.feedback.set_html(
            lambda: f"<p style='color:{_colors()[kind]}'>{html.escape(text)}</p>")

    def hint(self) -> str | None:
        text = self.session.hint() if self.session and self.session.makers else None
        if text is not None:
            exercise = self.session.exercise
            shown = exercise.hints[:exercise.hints_shown]
            self.feedback.set_markdown("\n\n".join(f"**Hint {i}.** {h}"
                                                   for i, h in enumerate(shown, 1)))
            self.hint_button.setEnabled(exercise.hints_left > 0)
        return text

    def show_solution(self) -> str:
        text = self.session.solution()
        self.feedback.set_markdown("**Solution.** " + text)
        return text

    def new_numbers(self, seed: int | None = None) -> None:
        self.session.new_numbers(seed)
        self._show_exercise()

    def next_exercise(self) -> None:
        self.session.go(self.session.index + 1)
        self._show_exercise()

    # -- the Lab tab ------------------------------------------------------------------------
    def _lab_tab(self, folder: str) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(8, 8, 8, 8)
        text = self.text.lab or ("The lab is this project: change its forms and code, and "
                                 "run it to see what they do.")
        self.lab_view = MarkdownView(text, folder)
        column.addWidget(self.lab_view)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run the Lab (F5)")
        self.run_button.setIcon(icons.icon("Run"))
        self.run_button.clicked.connect(lambda: self.runRequested.emit())
        row.addWidget(self.run_button)
        row.addWidget(self.lab_state, 1)
        column.addLayout(row)
        column.addWidget(QLabel("The lab's forms (double-click one to open it):"))
        self.forms = QListWidget()
        for relative in self.project.forms:
            item = QListWidgetItem(icons.icon("Form"), relative)
            item.setData(Qt.UserRole, self.project.abspath(relative))
            self.forms.addItem(item)
        self.forms.setMaximumHeight(140)
        self.forms.itemDoubleClicked.connect(
            lambda item: self.formRequested.emit(item.data(Qt.UserRole)))
        column.addWidget(self.forms)
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def lab_ran(self) -> None:
        """The lab project was run (from the IDE, F5)."""
        if not self.record.lab_run:
            self.record.lab_run = True
            self._save()

    # -- progress ---------------------------------------------------------------------------
    def _save(self) -> None:
        education.save_progress(self.lesson.id, self.record)
        self._update_state()
        self.progressChanged.emit()

    def _update_state(self) -> None:
        record = self.record
        dim = _colors()["dim"]
        marks = [("read" if record.read else "not read yet"),
                 (f"exercises {len(set(record.right))}/{record.exercises}"),
                 ("lab run" if record.lab_run else "lab not run yet")]
        self.state_label.setText(f"<span style='color:{dim}'>{record.state.capitalize()}: "
                                 f"{', '.join(marks)}</span>")
        self.lab_state.setText(f"<span style='color:{dim}'>"
                               f"{'You have run the lab.' if record.lab_run else ''}</span>")

    def reset_progress(self, ask: bool = True) -> None:
        if ask and QMessageBox.question(
                self, "Reset Progress", f"Forget your progress in {self.title}?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        education.reset_progress(self.lesson.id)
        self.record = education.progress(self.lesson.id)
        if self.session is not None:
            self.session.record = self.record
            self.record.exercises = len(self.session.makers)
        self._update_state()
        self._show_exercise()
        self.progressChanged.emit()
