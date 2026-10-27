"""New Project, Project Properties, Make Executable and About dialogs."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStyle, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

import vp6

from ..project import SUB_MAIN, Project
from . import icons
from .logic import education
from .logic import settings as _settings
from .logic.projects import (COLOR_SCHEME_CHOICES, DEFAULT_LOCATION, TEMPLATES,  # noqa: F401
                             TYPE_CHOICES, categories, next_free_name)
from .theme import theme_manager

# The logo: a copy of images/vp6logo.png scaled to 720 pixels wide, shown at
# half that (sharp on high-DPI screens)
LOGO_PATH = os.path.join(os.path.dirname(__file__), "images", "vp6logo.png")
LOGO_WIDTH = 360

FOLDER_ROLE = Qt.UserRole + 1  # a folder item's category
TAB_NAMES = ("new", "existing", "recent", "education")
TAB_KEY = "newproject/tab"  # (the tab last used)


class NewProjectDialog(QDialog):
    """VB6's New Project dialog: New / Existing / Recent tabs, and Education:
    a subject's learning path (``LearningPathView``), a book's chapters and
    lessons with their states, a lesson's description.

    After exec(): ``result_action`` is "new", "open" or "lesson"; for "new"
    see ``template``, ``project_name``, ``location``; for "open"
    ``open_path``; for "lesson" ``lesson`` (a ``vp6edu.Lesson``) and
    ``lesson_root`` (where lesson projects go). ``tab`` ("education"...)
    opens on that tab, by default the one last used.
    """

    def __init__(self, recent: list[str], parent=None, show_new_only=False,
                 tab: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.result_action = None
        self.open_path = ""
        self.lesson = None
        self.lesson_root = ""
        self.tabs = QTabWidget()

        # New: the categories (folders) on the left, a category's templates and
        # folders on the right
        new_tab = QWidget()
        self.categories = QTreeWidget()
        self.categories.setHeaderHidden(True)
        self.categories.setRootIsDecorated(True)
        self._category_items: dict[str, QTreeWidgetItem] = {}
        top = QTreeWidgetItem(self.categories, ["Projects"])
        top.setIcon(0, icons.icon("Project"))
        top.setData(0, FOLDER_ROLE, "")
        self._category_items[""] = top
        for path in categories():
            parent, _, title = path.rpartition("/")
            item = QTreeWidgetItem(self._category_items[parent], [title])
            item.setIcon(0, icons.icon("Project"))
            item.setData(0, FOLDER_ROLE, path)
            self._category_items[path] = item
        self.categories.expandAll()
        self.categories.setMaximumWidth(170)
        self.categories.currentItemChanged.connect(
            lambda item, _: item is not None and self._show_category(item.data(0, FOLDER_ROLE)))
        self.category = None
        self.templates = QListWidget()
        self.templates.setViewMode(QListWidget.IconMode)
        self.templates.setIconSize(QSize(48, 48))
        self.templates.setGridSize(QSize(150, 96))
        self.templates.setMovement(QListWidget.Static)
        self.templates.setResizeMode(QListWidget.Adjust)
        self.templates.setWordWrap(True)
        self.templates.itemDoubleClicked.connect(self._open_item)
        self.templates.currentItemChanged.connect(self._template_changed)
        self.template_help = QLabel()
        self.template_help.setWordWrap(True)
        self.location = QLineEdit(DEFAULT_LOCATION)
        self.name = QLineEdit(next_free_name("Project", DEFAULT_LOCATION))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_location)
        location_row = QHBoxLayout()
        location_row.addWidget(self.location)
        location_row.addWidget(browse)
        form = QFormLayout()
        form.addRow("Name:", self.name)
        form.addRow("Location:", location_row)
        new_layout = QVBoxLayout(new_tab)
        lists = QHBoxLayout()
        lists.addWidget(self.categories)
        lists.addWidget(self.templates, 1)
        new_layout.addLayout(lists, 1)
        new_layout.addWidget(self.template_help)
        new_layout.addLayout(form)
        self.tabs.addTab(new_tab, "New")

        # Existing
        existing_tab = QWidget()
        open_button = QPushButton("Browse for a project…")
        open_button.clicked.connect(self._browse_existing)
        existing_layout = QVBoxLayout(existing_tab)
        existing_layout.addWidget(QLabel("Open a VP6 project file (*.vp6p)."))
        existing_layout.addWidget(open_button)
        existing_layout.addStretch(1)
        self.tabs.addTab(existing_tab, "Existing")

        # Recent
        recent_tab = QWidget()
        self.recent = QListWidget()
        for path in recent:
            if os.path.exists(path):
                item = QListWidgetItem(icons.icon("Project"),
                                       f"{os.path.basename(path)}  —  {os.path.dirname(path)}")
                item.setData(Qt.UserRole, path)
                self.recent.addItem(item)
        self.recent.itemDoubleClicked.connect(self._accept_recent)
        recent_layout = QVBoxLayout(recent_tab)
        recent_layout.addWidget(self.recent)
        self.tabs.addTab(recent_tab, "Recent")
        self.tabs.addTab(self._education_tab(), "Education")
        if show_new_only:
            self.tabs.setTabEnabled(1, False)
            self.tabs.setTabEnabled(2, False)
        elif self.recent.count():
            self.recent.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)
        self.resize(740, 640)
        self.categories.setCurrentItem(top)  # (the top level: Standard EXE chosen)
        tab = tab or str(_settings.settings().value(TAB_KEY, "new") or "new")
        if tab in TAB_NAMES and self.tabs.isTabEnabled(TAB_NAMES.index(tab)):
            self.tabs.setCurrentIndex(TAB_NAMES.index(tab))

    def done(self, result):
        _settings.settings().setValue(TAB_KEY, TAB_NAMES[self.tabs.currentIndex()])
        super().done(result)

    # -- Education ---------------------------------------------------------------------------
    def _education_tab(self) -> QWidget:
        from .learningpath import LearningPathView
        from .lessonwindow import MarkdownView

        page = QWidget()
        self.subject_box = QComboBox()
        self.subjects: dict = {}
        self.education_problem = ""
        try:
            self.subjects = education.subjects()
        except ValueError as error:  # (vp6edu.SubjectError: a subject's data)
            self.education_problem = str(error)
        for subject in self.subjects.values():
            self.subject_box.addItem(subject.title, subject.id)
        self.path_view = LearningPathView()
        self.path_view.bookChosen.connect(self._show_book)
        self.path_scroll = QScrollArea()
        self.path_scroll.setWidget(self.path_view)
        self.path_scroll.setFrameShape(QFrame.StyledPanel)
        self.path_scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lessons = QTreeWidget()
        self.lessons.setHeaderLabels(["Lesson", "State"])
        self.lessons.setColumnWidth(0, 470)
        self.lessons.currentItemChanged.connect(lambda *_: self._lesson_changed())
        self.lessons.itemDoubleClicked.connect(
            lambda item, _: item.data(0, Qt.UserRole) and self._accept_lesson())
        self.lesson_text = MarkdownView()
        self.lesson_text.setMinimumHeight(60)
        about = QScrollArea()
        about.setWidget(self.lesson_text)
        about.setWidgetResizable(True)
        about.setFrameShape(QFrame.NoFrame)
        about.setFixedHeight(104)
        self.lesson_location = QLineEdit(education.default_root(DEFAULT_LOCATION))
        self.lesson_location.setToolTip("Lesson projects go here, in folders by subject, "
                                        "book and section")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_lesson_location)
        self.lesson_message = QLabel()
        self.lesson_message.setWordWrap(True)
        self.lesson_message.hide()
        top = QHBoxLayout()
        top.addWidget(QLabel("Subject:"))
        top.addWidget(self.subject_box, 1)
        location_row = QHBoxLayout()
        location_row.addWidget(QLabel("Location:"))
        location_row.addWidget(self.lesson_location, 1)
        location_row.addWidget(browse)
        column = QVBoxLayout(page)
        column.addLayout(top)
        column.addWidget(self.path_scroll)
        column.addWidget(self.lessons, 1)
        column.addWidget(about)
        column.addWidget(self.lesson_message)
        column.addLayout(location_row)
        self.subject_box.currentIndexChanged.connect(lambda *_: self._show_subject())
        theme_manager().changed.connect(self._fill_lessons)
        remembered = education.remembered()
        at = self.subject_box.findData(remembered.get("subject"))
        self.subject_box.setCurrentIndex(max(at, 0))
        self._show_subject(remembered.get("book"))
        if self.education_problem:
            self._lesson_problem(f"The courses can't be read: {self.education_problem}")
        return page

    @property
    def subject(self):
        """The subject shown on the Education tab (a ``vp6edu.Subject``)."""
        return self.subjects.get(self.subject_box.currentData())

    @property
    def book(self):
        subject = self.subject
        return subject.books.get(self.path_view.selected) if subject else None

    def _show_subject(self, book: str | None = None) -> None:
        subject = self.subject
        path = subject.paths[0] if subject and subject.paths else None
        self.path_view.set_path(path)
        height = self.path_view.height() + 2 * self.path_scroll.frameWidth()
        style = self.path_scroll.style()  # (no room for a scroll bar drawn over it: macOS)
        bar = 0 if style.styleHint(QStyle.SH_ScrollBar_Transient, None, self.path_scroll) \
            else style.pixelMetric(QStyle.PM_ScrollBarExtent, None, self.path_scroll)
        self.path_scroll.setFixedHeight(height + bar)
        nodes = list(self.path_view.places)
        if book not in nodes:
            book = nodes[0] if nodes else (next(iter(subject.books)) if subject else None)
        self._show_book(book)

    def _show_book(self, book: str | None) -> None:
        """A book of the subject: chosen on the path, its lessons listed (the
        one to go on with chosen)."""
        if book:
            self.path_view.select(book)
            node = self.path_view.node_rect(book) if book in self.path_view.places else None
            if node is not None:
                self.path_scroll.ensureVisible(int(node.center().x()), int(node.center().y()),
                                               int(node.width() / 2) + 12, 0)
        subject = self.subject
        if subject is not None and self.book is not None:
            education.remember(subject.id, self.book.id)
        going_on = education.first_lesson(self.book) if self.book is not None else None
        self._fill_lessons(going_on.id if going_on else None)

    def _fill_lessons(self, chosen: str | None = None) -> None:
        """The book's chapters and lessons, with the lessons' states (planned
        ones greyed out)."""
        if chosen is None and self.chosen_lesson is not None:
            chosen = self.chosen_lesson.id
        self.lessons.clear()
        book = self.book
        if book is None:
            self._lesson_changed()
            return
        palette = self.lessons.palette()
        dim = palette.color(palette.ColorGroup.Disabled, palette.ColorRole.Text)
        done = QColor("#5cc96b" if theme_manager().app_is_dark() else "#2e9e44")
        current = None
        for chapter in book.chapters:
            top = QTreeWidgetItem(self.lessons, [f"{chapter.number}  {chapter.title}"])
            top.setFirstColumnSpanned(True)
            open_chapter = False
            for lesson in chapter.lessons:
                state = education.lesson_state(lesson)
                name = f"{lesson.number}  {lesson.title}" if lesson.kind == "section" \
                    else lesson.title
                item = QTreeWidgetItem(top, [name, state])
                item.setData(0, Qt.UserRole, lesson.id)
                item.setToolTip(0, lesson.heading)
                if state == "planned":
                    for c in (0, 1):
                        item.setForeground(c, dim)
                else:
                    open_chapter = True
                    item.setIcon(0, icons.icon("Lesson"))
                    if state == education.DONE:
                        item.setText(1, "✓ done")
                        item.setForeground(1, done)
                if lesson.id == chosen:
                    current = item
            top.setExpanded(open_chapter or (current is not None and current.parent() is top))
        if current is None and self.lessons.topLevelItemCount():
            current = self.lessons.topLevelItem(0).child(0)
        if current is not None:
            current.parent().setExpanded(True)
            self.lessons.setCurrentItem(current)
            self.lessons.scrollToItem(current)
        self._lesson_changed()

    @property
    def chosen_lesson(self):
        """The lesson chosen in the tree (None when a chapter is)."""
        item = self.lessons.currentItem()
        lesson_id = item.data(0, Qt.UserRole) if item is not None else None
        subject = self.subject
        if not lesson_id or subject is None:
            return None
        try:
            return subject.lesson(lesson_id)
        except KeyError:
            return None

    def _lesson_changed(self) -> None:
        lesson = self.chosen_lesson
        self.lesson_message.clear()
        self.lesson_message.hide()
        self.lesson_text.set_markdown(education.lesson_description(lesson)
                                      if lesson is not None else "")

    def _lesson_problem(self, text: str) -> None:
        self.lesson_message.setText(f"<font color='#c0392b'>{text}</font>")
        self.lesson_message.show()

    def _browse_lesson_location(self):
        path = QFileDialog.getExistingDirectory(self, "Location", self.lesson_location.text())
        if path:
            self.lesson_location.setText(path)

    def _accept_lesson(self):
        lesson = self.chosen_lesson
        if lesson is None:
            self._lesson_problem("Choose a lesson.")
            return
        if lesson.planned:
            self._lesson_problem(f"{lesson.heading} isn't written yet: choose one that isn't "
                                 "greyed out.")
            return
        if not self.lesson_location.text().strip():
            self._lesson_problem("Choose where lesson projects go (the Location).")
            return
        self.result_action = "lesson"
        self.lesson = lesson
        self.lesson_root = self.lesson_location.text().strip()
        self.accept()

    # -- categories --------------------------------------------------------------------------
    def _show_category(self, path: str) -> None:
        """Show a category: its templates, then its folders."""
        self.category = path
        self.templates.clear()
        for key, title, icon_name, tip, category in TEMPLATES:
            if category == path:
                item = QListWidgetItem(icons.large_icon(icon_name), title)
                item.setData(Qt.UserRole, key)
                item.setToolTip(tip)
                self.templates.addItem(item)
        for folder in categories():
            if folder.rpartition("/")[0] == path:  # (its folders, not theirs)
                item = QListWidgetItem(icons.large_icon("Project"), folder.rpartition("/")[2])
                item.setData(FOLDER_ROLE, folder)
                item.setToolTip(f"{folder}: double-click to open")
                self.templates.addItem(item)
        # The first template chosen, else the first folder
        rows = [i for i in range(self.templates.count())
                if self.templates.item(i).data(Qt.UserRole)]
        self.templates.setCurrentRow(rows[0] if rows else 0)
        self._template_changed()

    def select_category(self, path: str) -> None:
        """Show a category ("" the top level, "Sample Projects/Graphics")."""
        self.categories.setCurrentItem(self._category_items[path])

    def select_template(self, key: str) -> None:
        """Choose a template, in its category."""
        category = next(t[4] for t in TEMPLATES if t[0] == key)
        self.select_category(category)
        for i in range(self.templates.count()):
            if self.templates.item(i).data(Qt.UserRole) == key:
                self.templates.setCurrentRow(i)

    def _open_item(self, item) -> None:
        """Double-click: a folder opens, a template makes the project."""
        folder = item.data(FOLDER_ROLE)
        if folder is not None:
            self.select_category(folder)
        else:
            self._accept_new()

    def _template_changed(self, *_):
        item = self.templates.currentItem()
        if item is not None and item.data(FOLDER_ROLE) is not None:
            names = [t[1] for t in TEMPLATES if t[4] == item.data(FOLDER_ROLE) or
                     t[4].startswith(item.data(FOLDER_ROLE) + "/")]
            self.template_help.setText(f"{item.text()}: {', '.join(names)}.")
            return
        key = item.data(Qt.UserRole) if item else None
        self.template_help.setText(next((t[3] for t in TEMPLATES if t[0] == key), ""))

    @property
    def template(self) -> str | None:
        """The template chosen (None when a folder is)."""
        item = self.templates.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    @property
    def project_name(self) -> str:
        return self.name.text().strip()

    @property
    def project_location(self) -> str:
        return self.location.text().strip()

    def _browse_location(self):
        path = QFileDialog.getExistingDirectory(self, "Location", self.location.text())
        if path:
            self.location.setText(path)

    def _browse_existing(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", DEFAULT_LOCATION,
                                              "VP6 projects (*.vp6p)")
        if path:
            self.result_action, self.open_path = "open", path
            self.accept()

    def _accept_recent(self, item):
        self.result_action, self.open_path = "open", item.data(Qt.UserRole)
        self.accept()

    def _accept_new(self):
        item = self.templates.currentItem()
        if item is not None and item.data(FOLDER_ROLE) is not None:
            self.select_category(item.data(FOLDER_ROLE))  # (Open on a folder opens it)
            return
        if self.template is None:
            return
        name = self.project_name
        if not name.isidentifier():
            self.template_help.setText("<font color='#c0392b'>The project name must be a valid "
                                       "identifier (letters, digits, _).</font>")
            return
        target = os.path.join(self.project_location, name)
        if os.path.exists(target) and os.listdir(target):
            self.template_help.setText(f"<font color='#c0392b'>{target} already exists and is "
                                       "not empty.</font>")
            return
        self.result_action = "new"
        self.accept()

    def _accept(self):
        tab = self.tabs.currentIndex()
        if tab == 0:
            self._accept_new()
        elif tab == 1:
            self._browse_existing()
        elif tab == 3:
            self._accept_lesson()
        elif self.recent.currentItem() is not None:
            self._accept_recent(self.recent.currentItem())


class ProjectPropertiesDialog(QDialog):
    def __init__(self, project: Project, form_names: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{project.name} - Project Properties")
        self.name = QLineEdit(project.name)
        self.type = QComboBox()
        for value, label in TYPE_CHOICES:
            self.type.addItem(label, value)
        self.type.setCurrentIndex(max(self.type.findData(project.type), 0))
        self.startup = QComboBox()
        for name in form_names + [SUB_MAIN]:
            self.startup.addItem(name)
        self.startup.setCurrentIndex(max(self.startup.findText(project.startup), 0))
        self.color_scheme = QComboBox()
        for value, label in COLOR_SCHEME_CHOICES:
            self.color_scheme.addItem(label, value)
        self.color_scheme.setCurrentIndex(
            max(self.color_scheme.findData(project.color_scheme), 0))
        self.color_scheme.setToolTip("Used by every form whose ColorScheme property is "
                                     "'0 - Project Default'.")
        # VB's Make tab: the version and descriptions App reports, and the command line
        self.version = []
        version = QHBoxLayout()
        for label, number in zip(("Major", "Minor", "Revision"), project.version_numbers()):
            box = QSpinBox()
            box.setRange(0, 9999)
            box.setValue(number)
            box.setToolTip(f"App.{label}")
            self.version.append(box)
            version.addWidget(box)
        self.product_name = QLineEdit(project.product_name)
        self.product_name.setPlaceholderText(project.name)
        self.company_name = QLineEdit(project.company_name)
        self.description = QLineEdit(project.description)
        self.arguments = QLineEdit(project.arguments)
        self.arguments.setToolTip("What the program gets when the IDE runs it: Command(), "
                                  "sys.argv[1:].")
        self.arguments_help = QPlainTextEdit(project.arguments_help)
        self.arguments_help.setPlaceholderText("--open FILE    open FILE at the start")
        self.arguments_help.setToolTip("The program's own arguments, one per line, as "
                                       "--help lists them.")
        self.arguments_help.setFixedHeight(64)
        self.package = QLineEdit(project.package)
        found = project.found_package()
        self.package.setPlaceholderText(f"none (its folders make {found})" if found else "none")
        self.package.setToolTip("The Python package the project's folder is (e.g. myapp.gui): "
                                "its files are imported by package name.")
        self.command = QLineEdit(project.command)
        self.command.setPlaceholderText(project.name)
        self.command.setToolTip("The command its wheel installs (vp6-make).")
        form = QFormLayout()
        form.addRow("Project Name:", self.name)
        form.addRow("Project Type:", self.type)
        form.addRow("Startup Object:", self.startup)
        form.addRow("Color Scheme:", self.color_scheme)
        form.addRow("Version:", version)
        form.addRow("Product Name:", self.product_name)
        form.addRow("Company Name:", self.company_name)
        form.addRow("Description:", self.description)
        form.addRow("Command Line Arguments:", self.arguments)
        form.addRow("Arguments Help:", self.arguments_help)
        form.addRow("Package:", self.package)
        form.addRow("Command:", self.command)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply(self, project: Project) -> None:
        if self.name.text().strip().isidentifier():
            project.name = self.name.text().strip()
        project.type = self.type.currentData()
        project.startup = self.startup.currentText()
        project.color_scheme = self.color_scheme.currentData()
        project.version = ".".join(str(box.value()) for box in self.version)
        project.product_name = self.product_name.text().strip()
        project.company_name = self.company_name.text().strip()
        project.description = self.description.text().strip()
        project.arguments = self.arguments.text().strip()
        project.arguments_help = self.arguments_help.toPlainText().strip("\n")
        package, old = self.package.text().strip(), project.package
        project.package = package
        if project.package_problem():  # (not the package it is in: unchanged)
            project.package = old
        command = self.command.text().strip()
        if all(c.isalnum() or c in "-_." for c in command):
            project.command = command


ABOUT_HTML = f"""
<h2>VP6 {vp6.__version__}</h2>
<p>A VB6 style IDE and framework for Python.</p>
<p>Draw forms with the Toolbox, set properties in the Properties window,
double-click a control to write its event handler, press <b>F5</b> (or <b>Cmd+Enter</b> on macOS, <b>Ctrl+Enter</b> elsewhere) to run.</p>
<p>Handlers are ordinary methods named <code>ControlName_EventName</code>, e.g.
<code>def Command1_Click(self):</code>. Return <code>True</code> from
<code>Form_Unload</code> to cancel closing, return <code>0</code> from
<code>KeyPress</code> to swallow a key.</p>
"""


def logo_pixmap(width: int = LOGO_WIDTH, ratio: float = 2.0) -> QPixmap:
    """The VP6 logo, ``width`` pixels wide on screen (an empty pixmap if the
    file is missing)."""
    pixmap = QPixmap(LOGO_PATH)
    if pixmap.isNull():
        return pixmap
    pixmap = pixmap.scaledToWidth(round(width * ratio), Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class AboutDialog(QDialog):
    """About VP6: the logo, the version and a few words on how it works (Help >
    About VP6, and the application menu on macOS)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About VP6")
        self.logo = QLabel()
        self.logo.setPixmap(logo_pixmap())
        self.logo.setAlignment(Qt.AlignCenter)
        self.text = QLabel(ABOUT_HTML)
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        self.text.setFixedWidth(LOGO_WIDTH + 80)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.addWidget(self.logo)
        layout.addWidget(self.text)
        layout.addWidget(buttons)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)


class MakeDialog(QDialog):
    """File > Make Executable...: what will be made, and where (the options of
    vp6.make)."""

    SYSTEMS = {"darwin": "macOS", "win32": "Windows"}

    def __init__(self, project: Project, parent=None):
        from ..make import can_be_one_file, output_path

        super().__init__(parent)
        self.setWindowTitle("Make Executable")
        self.project = project
        dist = os.path.join(project.directory, "dist")
        system = self.SYSTEMS.get(sys.platform, "Linux")
        intro = QLabel(
            f"Make <b>{project.name}</b> a standalone program for {system}: it runs "
            "without Python or VP6 installed. It goes in the project's <b>dist</b> "
            "folder.<br><br>For another system, make it on that system: executables are "
            "made for the system they are made on.")
        intro.setWordWrap(True)
        self.onefile = QCheckBox("One file instead of a folder (it starts more slowly)")
        if not can_be_one_file(project):
            self.onefile.setEnabled(False)
            self.onefile.setToolTip("On macOS a windowed program is an app, which is a folder")
        self.where = QLabel()
        self.where.setWordWrap(True)
        self.where.setTextInteractionFlags(Qt.TextSelectableByMouse)

        def show_where():
            path = output_path(project, dist, self.onefile.isChecked())
            self.where.setText(f"It will be: {path}")

        self.onefile.toggled.connect(show_where)
        show_where()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Make")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.onefile)
        layout.addWidget(self.where)
        layout.addWidget(buttons)
        # (as high as the wrapped labels need at that width: else they're cut short)
        self.resize(460, layout.totalHeightForWidth(460))
