"""New Project, Project Properties and About dialogs."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

import vp6

from ..project import SUB_MAIN, Project
from . import icons
from .projectprops import COLOR_SCHEME_CHOICES, TYPE_CHOICES

DEFAULT_LOCATION = os.path.join(os.path.expanduser("~"), "VP6 Projects")

TEMPLATES = [
    ("exe", "Standard EXE", "Form", "A windowed application with a startup form."),
    ("console", "Console Application", "Console",
     "A text-mode program that starts in Sub Main and uses print() / input()."),
]


def next_free_name(base: str, location: str) -> str:
    i = 1
    while os.path.exists(os.path.join(location, f"{base}{i}")):
        i += 1
    return f"{base}{i}"


class NewProjectDialog(QDialog):
    """VB6's New Project dialog: New / Existing / Recent tabs.

    After exec(): ``result_action`` is "new" or "open"; for "new" see
    ``template``, ``project_name``, ``location``; for "open" ``open_path``.
    """

    def __init__(self, recent: list[str], parent=None, show_new_only=False):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.result_action = None
        self.open_path = ""
        self.tabs = QTabWidget()

        # New
        new_tab = QWidget()
        self.templates = QListWidget()
        self.templates.setViewMode(QListWidget.IconMode)
        self.templates.setIconSize(QSize(48, 48))
        self.templates.setGridSize(QSize(150, 96))
        self.templates.setMovement(QListWidget.Static)
        self.templates.setResizeMode(QListWidget.Adjust)
        self.templates.setWordWrap(True)
        for key, title, icon_name, tip in TEMPLATES:
            item = QListWidgetItem(icons.large_icon(icon_name), title)
            item.setData(Qt.UserRole, key)
            item.setToolTip(tip)
            self.templates.addItem(item)
        self.templates.setCurrentRow(0)
        self.templates.itemDoubleClicked.connect(lambda _: self._accept_new())
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
        new_layout.addWidget(self.templates)
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
        self.resize(520, 420)
        self._template_changed()

    def _template_changed(self, *_):
        item = self.templates.currentItem()
        key = item.data(Qt.UserRole) if item else None
        self.template_help.setText(next((t[3] for t in TEMPLATES if t[0] == key), ""))

    @property
    def template(self) -> str:
        return self.templates.currentItem().data(Qt.UserRole)

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
        form = QFormLayout()
        form.addRow("Project Name:", self.name)
        form.addRow("Project Type:", self.type)
        form.addRow("Startup Object:", self.startup)
        form.addRow("Color Scheme:", self.color_scheme)
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


ABOUT_HTML = f"""
<h2>VP6 {vp6.__version__}</h2>
<p>A Visual Basic 6 style IDE and framework for Python.</p>
<p>Draw forms with the Toolbox, set properties in the Properties window,
double-click a control to write its event handler, press <b>F5</b> (or <b>Cmd+Enter</b> on macOS, <b>Ctrl+Enter</b> elsewhere) to run.</p>
<p>Handlers are ordinary methods named <code>ControlName_EventName</code>, e.g.
<code>def Command1_Click(self):</code>. Return <code>True</code> from
<code>Form_Unload</code> to cancel closing, return <code>0</code> from
<code>KeyPress</code> to swallow a key.</p>
"""
