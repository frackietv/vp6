"""Toolbox, Project Explorer, Immediate window and Output window."""

from __future__ import annotations

import os
import re

from PySide6.QtCore import (
    QFileInfo, QFileSystemWatcher, QItemSelectionModel, QProcess, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFileIconProvider, QGridLayout, QHBoxLayout, QLineEdit, QMenu,
    QPlainTextEdit, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..controls import CONTROL_TYPES
from ..project import SUB_MAIN, Project
from . import icons
from .theme import theme_manager


class Toolbox(QWidget):
    """The General tab of the VB toolbox."""

    toolSelected = Signal(object)  # control type name or None for the pointer
    toolActivated = Signal(str)  # double-click: add the control to the form

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(4, 4, 4, 4)
        self.buttons: dict[str | None, QToolButton] = {}
        tools = [None, *(name for name, cls in CONTROL_TYPES.items() if cls.InToolbox)]
        for index, type_name in enumerate(tools):
            button = QToolButton()
            button.setIcon(icons.icon(type_name or "Pointer"))
            button.setIconSize(QSize(24, 24))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(type_name or "Pointer")
            button.setFixedSize(34, 34)
            button.clicked.connect(lambda _=False, t=type_name: self.toolSelected.emit(t))
            if type_name:
                button.mouseDoubleClickEvent = \
                    lambda event, t=type_name: self.toolActivated.emit(t)
            self.group.addButton(button)
            self.buttons[type_name] = button
            grid.addWidget(button, index // 2, index % 2)
        self.buttons[None].setChecked(True)
        self.grid = grid
        self.user_buttons: list[str] = []  # the project's user controls, after the others
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(grid)
        layout.addStretch(1)

    def set_user_controls(self, names: list[str]) -> None:
        """Show the project's user controls (their class names) after the built-in tools."""
        for name in self.user_buttons:
            button = self.buttons.pop(name)
            if button.isChecked():
                self.reset()
            self.group.removeButton(button)
            self.grid.removeWidget(button)
            button.deleteLater()
        self.user_buttons = []
        start = len(self.buttons)
        for offset, name in enumerate(names):
            button = QToolButton()
            button.setIcon(icons.icon("UserControl"))
            button.setIconSize(QSize(24, 24))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(f"{name} (a user control of the project)")
            button.setFixedSize(34, 34)
            button.clicked.connect(lambda _=False, t=name: self.toolSelected.emit(t))
            button.mouseDoubleClickEvent = lambda event, t=name: self.toolActivated.emit(t)
            self.group.addButton(button)
            self.buttons[name] = button
            self.user_buttons.append(name)
            index = start + offset
            self.grid.addWidget(button, index // 2, index % 2)

    def refresh_icons(self) -> None:
        """Redraw the icons after switching between light and dark."""
        for type_name, button in self.buttons.items():
            button.setIcon(icons.icon("UserControl" if type_name in self.user_buttons
                                      else type_name or "Pointer"))

    def reset(self) -> None:
        self.buttons[None].setChecked(True)
        self.toolSelected.emit(None)


class _ProjectTree(QTreeWidget):
    """The Project panel's tree: dropping the selected items on a group (or on
    a file in it, or the project) asks to move them there; the project is
    changed, and the tree refilled, by the main window. Several items can be
    selected (Ctrl/Cmd- and Shift-click) and dragged at once."""

    def __init__(self, explorer: "ProjectExplorer"):
        super().__init__()
        self._explorer = explorer
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dropEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        event.ignore()  # Qt doesn't move anything itself
        if target is not None:
            self._explorer._request_move(self.selectedItems(), target)


class ProjectExplorer(QWidget):
    """The project's forms and modules, organized in groups (see
    Project.groups): the groups have nothing to do with folders on disk.
    The Files view shows the project's folder as it is on disk instead:
    folders and all files, hidden ones only if asked."""

    openObject = Signal(str)  # path -> designer
    openCode = Signal(str)  # path -> code window
    removeFile = Signal(str)
    setStartup = Signal(str)
    addForm = Signal()
    addModule = Signal()
    addUserControl = Signal()
    projectSelected = Signal()  # the project (root) item became current
    fileSelected = Signal(str)  # a form or module item became current
    sortChanged = Signal(bool, bool)  # the user chose the order: descending, groups first
    # Organizing, done by the main window: a group's path is a tuple of names
    # (() is the project); an item is a file's relative path or a group's path
    newGroup = Signal(object)  # the group (path) to make it in
    renameGroup = Signal(object)  # the group
    deleteGroup = Signal(object)  # the group
    moveItems = Signal(object, object)  # a list of items, the group to move them to
    viewChanged = Signal(bool, bool)  # the user chose: the Files view, hidden files shown
    # The Files view's changes on disk, done by the main window (absolute paths)
    newFolder = Signal(str)  # the folder to make it in
    renamePath = Signal(str)  # a file or folder
    deletePath = Signal(str)  # a file or folder
    movePaths = Signal(object, str)  # a list of files and folders, the folder to move them into

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_code = QToolButton()
        self.view_code.setText("View Code")
        self.view_object = QToolButton()
        self.view_object.setText("View Object")
        self.view_code.clicked.connect(self._on_view_code)
        self.view_object.clicked.connect(self._on_view_object)
        # Project view (groups) or Files view (the folder on disk)
        self.files_mode = False
        self.show_hidden = False
        # Groups, forms and modules are listed by name: A to Z, or Z to A
        self.sort_descending = False
        self.groups_first = True  # subgroups before the files, or among them
        self._shown: tuple = (None, {})  # the last populate() arguments, to re-sort
        self.sort_button = QToolButton()
        self.sort_button.setAutoRaise(True)
        self.sort_button.clicked.connect(self.toggle_sort)
        self._update_sort_button()
        # + expands every group, - collapses them (the project item stays open)
        self.expand_button = QToolButton()
        self.expand_button.setAutoRaise(True)
        self.expand_button.clicked.connect(self.toggle_expanded)
        # Groups (tuples) and folders (paths) kept collapsed when repopulating,
        # for each view; _shown_files: the view the tree shows
        self._collapsed: dict[bool, set] = {False: set(), True: set()}
        self._shown_files = False
        self.project_button = QToolButton()
        self.project_button.setText("Project")
        self.project_button.setToolTip("The forms and modules, in their groups")
        self.files_button = QToolButton()
        self.files_button.setText("Files")
        self.files_button.setToolTip("The project's folder as it is on disk")
        self._view_buttons = QButtonGroup(self)
        for button in (self.project_button, self.files_button):
            button.setCheckable(True)
            button.setAutoRaise(True)
            self._view_buttons.addButton(button)
        self.project_button.setChecked(True)
        self.project_button.clicked.connect(lambda: self._choose_view(False, self.show_hidden))
        self.files_button.clicked.connect(lambda: self._choose_view(True, self.show_hidden))
        self.hidden_button = QToolButton()
        self.hidden_button.setText("Hidden")
        self.hidden_button.setToolTip("Show hidden files and folders (such as .git)")
        self.hidden_button.setCheckable(True)
        self.hidden_button.setAutoRaise(True)
        self.hidden_button.setVisible(False)
        self.hidden_button.clicked.connect(
            lambda checked: self._choose_view(self.files_mode, checked))
        self.new_folder_button = QToolButton()
        self.new_folder_button.setText("New Folder")
        self.new_folder_button.setToolTip("A new folder in the selected folder (or the selected "
                                          "file's folder)")
        self.new_folder_button.setAutoRaise(True)
        self.new_folder_button.setVisible(False)
        self.new_folder_button.clicked.connect(
            lambda: self.newFolder.emit(self.selected_folder()))
        # The Files view follows the disk: a change refills it (once per burst)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._schedule_refresh)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(150)
        self._refresh_timer.timeout.connect(self.refresh)
        self._icon_provider = QFileIconProvider()
        self.tree = _ProjectTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.currentItemChanged.connect(self._update_buttons)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        # The project item stays open: no arrow (top-level items aren't
        # decorated; the groups are), and collapsing it (a double-click, the
        # Left or minus key) is undone in _keep_project_expanded
        self.tree.setRootIsDecorated(False)
        self.tree.itemCollapsed.connect(self._keep_project_expanded)
        self.tree.itemCollapsed.connect(self._update_expand_button)
        self.tree.itemExpanded.connect(self._update_expand_button)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.view_code)
        buttons.addWidget(self.view_object)
        buttons.addStretch(1)
        view = QHBoxLayout()  # what is shown, and how
        view.setContentsMargins(0, 0, 0, 0)
        view.setSpacing(0)
        view.addWidget(self.project_button)
        view.addWidget(self.files_button)
        view.addSpacing(6)
        view.addWidget(self.hidden_button)
        view.addWidget(self.new_folder_button)
        view.addStretch(1)
        view.addWidget(self.expand_button)
        view.addWidget(self.sort_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(buttons)
        layout.addLayout(view)
        layout.addWidget(self.tree)
        self._update_buttons()
        self._update_expand_button()

    # Item data: UserRole = a form's or module's absolute path; +1 = "form",
    # "module", "group", "project", or in the Files view "folder" or "file"
    # (any other file); +2 = its name; +3 = a file's relative path or a group's
    # path (a list of names: Qt keeps a string list itself, while a tuple would
    # be a Python object inside Qt, which crashed when the tree was cleared),
    # or in the Files view the absolute path of every item
    # The Name button cycles through four orders: A to Z with the groups first,
    # A to Z with the groups among the files, then the same two Z to A
    SORT_ORDERS = ((False, True), (False, False), (True, True), (True, False))

    def set_sort(self, descending: bool, groups_first: bool = True) -> None:
        """List by name A to Z (False) or Z to A (True), in every group (or
        folder), with its subgroups first or sorted in among the files."""
        self.sort_descending = bool(descending)
        self.groups_first = bool(groups_first)
        self._update_sort_button()
        self.refresh()

    def refresh(self) -> None:
        """Fill the tree again from the last populate(), keeping the selection."""
        project, names = self._shown
        if project is not None:
            selected = self._selection()
            self.populate(project, names)
            self._restore_selection(selected)

    # -- the Project and Files views -----------------------------------------------------------
    def set_view(self, files: bool, hidden: bool = False) -> None:
        """The Project view (groups) or the Files view (the folder on disk,
        hidden files and folders only with ``hidden``). A selected form or
        module stays selected."""
        files, hidden = bool(files), bool(hidden)
        self.project_button.setChecked(not files)
        self.files_button.setChecked(files)
        self.hidden_button.setChecked(hidden)
        self.hidden_button.setVisible(files)
        self.new_folder_button.setVisible(files)
        if (files, hidden) == (self.files_mode, self.show_hidden):
            return
        switching = files != self.files_mode
        self.files_mode, self.show_hidden = files, hidden
        self._update_sort_button()
        project, names = self._shown
        if project is None:
            return
        if not switching:  # hidden files shown or not: the same kind of selection
            self.refresh()
            return
        path, _kind = self._current()
        was_project = self.project_selected()
        self.populate(project, names)
        if path is not None:
            self.select_path(path)
        elif was_project:
            self.select_project()

    def _choose_view(self, files: bool, hidden: bool) -> None:
        """The view buttons: the user's choice (remembered by the main window)."""
        self.set_view(files, hidden)
        self.viewChanged.emit(self.files_mode, self.show_hidden)

    def _schedule_refresh(self, *_) -> None:
        self._refresh_timer.start()

    def toggle_sort(self) -> None:
        """The next order in SORT_ORDERS."""
        orders = self.SORT_ORDERS
        index = orders.index((self.sort_descending, self.groups_first))
        self.set_sort(*orders[(index + 1) % len(orders)])
        self.sortChanged.emit(self.sort_descending, self.groups_first)

    def _update_sort_button(self) -> None:
        arrow = "▼" if self.sort_descending else "▲"
        groups = "Folders" if self.files_mode else "Groups"
        files = "files" if self.files_mode else "forms and modules"
        self.sort_button.setText(f"{groups}, Name {arrow}" if self.groups_first
                                 else f"Name {arrow}")
        order = "Z to A" if self.sort_descending else "A to Z"
        self.sort_button.setToolTip(
            (f"{groups} first, then {files}, by name {order}" if self.groups_first
             else f"{groups} and {files} together, by name {order}") +
            " (click for the next order)")

    def populate(self, project: Project | None, names: dict[str, str]) -> None:
        """names maps absolute path -> display name (form class / module name)."""
        if project is None or self._shown[0] is None or project.path != self._shown[0].path:
            self._collapsed = {False: set(), True: set()}  # another project: all open
        else:
            self._collapsed[self._shown_files] = self._collapsed_containers()
        self._shown = (project, names)
        self._shown_files = self.files_mode
        self.tree.clear()
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        if project is None:
            self._update_expand_button()
            return
        if self.files_mode:
            directory = project.directory
            root = QTreeWidgetItem([os.path.basename(directory) or directory])
            root.setToolTip(0, directory)
        else:
            root = QTreeWidgetItem([f"{project.name} ({os.path.basename(project.path)})"])
        root.setIcon(0, icons.icon("Project"))
        root.setData(0, Qt.UserRole + 1, "project")
        root.setData(0, Qt.UserRole + 3, [])
        root.setFlags(root.flags() & ~Qt.ItemIsDragEnabled)
        self.tree.addTopLevelItem(root)
        if self.files_mode:
            folders = [project.directory]
            self._add_folder(root, project.directory, project, names, folders)
            self._watcher.addPaths(folders)
        else:
            self._add_entries(root, project.tree(), (), project, names)
        self.tree.expandAll()
        collapsed = self._collapsed[self.files_mode]
        for item in self._container_items():  # what was collapsed stays collapsed
            if self._container_key(item) in collapsed:
                item.setExpanded(False)
        self._update_expand_button()

    # -- expanding and collapsing ----------------------------------------------------------------
    def _container_items(self) -> list:
        """The groups, or in the Files view the folders."""
        return [item for item in self.items()
                if item.data(0, Qt.UserRole + 1) in ("group", "folder")]

    @staticmethod
    def _container_key(item):
        ref = item.data(0, Qt.UserRole + 3)
        return tuple(ref) if item.data(0, Qt.UserRole + 1) == "group" else ref

    def _collapsed_containers(self) -> set:
        return {self._container_key(item) for item in self._container_items()
                if not item.isExpanded()}

    def all_expanded(self) -> bool:
        """Whether every group (or folder) is expanded (the project item
        always is)."""
        return all(item.isExpanded() for item in self._container_items())

    def expand_all(self) -> None:
        self.tree.expandAll()
        self._update_expand_button()

    def collapse_all(self) -> None:
        """Collapse every group (or folder); the project item stays open,
        showing the top level."""
        for item in self._container_items():
            item.setExpanded(False)
        self._update_expand_button()

    def toggle_expanded(self) -> None:
        """The + / - button: expand everything if anything is collapsed,
        else collapse every group."""
        if self.all_expanded():
            self.collapse_all()
        else:
            self.expand_all()

    def _update_expand_button(self, *_) -> None:
        expanded = self.all_expanded()
        what = "folders" if self.files_mode else "groups"
        self.expand_button.setText("-" if expanded else "+")
        self.expand_button.setToolTip(f"Collapse all {what}" if expanded
                                      else f"Expand all {what}")
        self.expand_button.setEnabled(bool(self._container_items()))

    def _keep_project_expanded(self, item) -> None:
        if item.parent() is None:
            item.setExpanded(True)

    def _sorted(self, listed: list) -> list:
        """(sort key, is a group or folder, ...) tuples in the chosen order."""
        listed.sort(key=lambda e: e[0], reverse=self.sort_descending)
        if self.groups_first:  # a stable sort: each part stays in its order
            listed.sort(key=lambda e: not e[1])
        return listed

    def _add_entries(self, parent, entries, path, project, names) -> None:
        listed = []  # (sort key, is a group, name, entry)
        for entry in entries:
            if isinstance(entry, dict):
                name = entry["group"]
                listed.append(((name.lower(), ""), True, name, entry))
            else:
                name = names.get(project.abspath(entry), os.path.splitext(entry)[0])
                listed.append(((name.lower(), entry.lower()), False, name, entry))
        for _key, is_group, name, entry in self._sorted(listed):
            if is_group:
                self._add_group(parent, entry, path, project, names)
            else:
                self._add_file(parent, name, entry, project)

    # Never in the Files view, hidden files shown or not: Git's folder (or its
    # .git file, in a submodule or worktree) and Python's bytecode caches
    NEVER_SHOWN = {".git", "__pycache__"}

    def _never_shown(self, name: str, path: str) -> bool:
        """What the Files view leaves out whatever the Hidden button says:
        the project file (it can't be moved, renamed or deleted from here)
        and NEVER_SHOWN."""
        return name in self.NEVER_SHOWN or self._is_project_file(path)

    @staticmethod
    def _is_hidden(path: str) -> bool:
        """A dot file or folder, or one hidden by the system (Windows)."""
        return os.path.basename(path).startswith(".") or QFileInfo(path).isHidden()

    def _add_folder(self, parent, directory, project, names, folders) -> None:
        """The Files view: a folder's folders and files (``folders`` collects
        the folders shown, for the watcher). Symbolic links to folders are
        listed, not followed."""
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        listed = []  # (sort key, is a folder, name, path)
        for entry in entries:
            if self._never_shown(entry.name, entry.path) or \
                    (not self.show_hidden and self._is_hidden(entry.path)):
                continue
            try:
                is_folder = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_folder = False
            listed.append(((entry.name.lower(), entry.name), is_folder, entry.name, entry.path))
        for _key, is_folder, name, path in self._sorted(listed):
            if is_folder:
                item = QTreeWidgetItem([name])
                item.setIcon(0, icons.icon("Project"))
                item.setData(0, Qt.UserRole + 1, "folder")
                item.setData(0, Qt.UserRole + 2, name)
                item.setData(0, Qt.UserRole + 3, path)
                parent.addChild(item)
                folders.append(path)
                self._add_folder(item, path, project, names, folders)
                continue
            relative = os.path.relpath(path, project.directory).replace(os.sep, "/")
            kind = project.kind_of(relative)
            if kind is not None:  # a form or module: as in the Project view
                shown = names.get(path, os.path.splitext(name)[0])
                item = self._add_file(parent, shown, relative, project, label=name)
                item.setData(0, Qt.UserRole + 3, path)
                continue
            item = QTreeWidgetItem([name])
            item.setIcon(0, self._icon_provider.icon(QFileInfo(path)))
            item.setToolTip(0, path)
            item.setData(0, Qt.UserRole + 1, "file")
            item.setData(0, Qt.UserRole + 2, name)
            item.setData(0, Qt.UserRole + 3, path)
            item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
            if self._is_project_file(path):  # the project file stays where it is
                item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)
            parent.addChild(item)

    def _add_group(self, parent, group, path, project, names) -> None:
        item = QTreeWidgetItem([group["group"]])
        item.setIcon(0, icons.icon("Project"))
        item.setData(0, Qt.UserRole + 1, "group")
        item.setData(0, Qt.UserRole + 2, group["group"])
        item.setData(0, Qt.UserRole + 3, list(path + (group["group"],)))
        item.setToolTip(0, "A group: it organizes the Project panel, not folders on disk")
        parent.addChild(item)
        self._add_entries(item, group["items"], path + (group["group"],), project, names)

    def _add_file(self, parent, name, relative, project, label=None) -> QTreeWidgetItem:
        full = project.abspath(relative)
        kind = project.kind_of(relative)
        item = QTreeWidgetItem([label or f"{name} ({relative})"])
        if label:
            item.setToolTip(0, f"{name} ({relative})")
        item.setIcon(0, icons.icon({"form": "Form", "usercontrol": "UserControl"}.get(kind,
                                                                                    "Module")))
        item.setData(0, Qt.UserRole, full)
        item.setData(0, Qt.UserRole + 1, kind)
        item.setData(0, Qt.UserRole + 2, name)
        item.setData(0, Qt.UserRole + 3, relative)
        item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
        is_startup = (kind == "form" and name == project.startup) or \
            (project.startup == SUB_MAIN and kind == "module"
             and re.search(r"^def Main\(", open(full, encoding="utf-8").read(), re.M)
             if os.path.exists(full) else False)
        if is_startup:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        parent.addChild(item)
        return item

    # -- selection ------------------------------------------------------------------------------
    def select_path(self, path: str | None) -> None:
        """Select the item of a file (e.g. the one in the active window)
        without opening anything; in the Files view any file or folder."""
        if path is None:
            return
        item = self._find(lambda i: i.data(0, Qt.UserRole) == path or (
            self.files_mode and i.data(0, Qt.UserRole + 3) == path))
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _select_all(self, items: list) -> None:
        """Select these items (the first one current)."""
        if not items:
            return
        self.tree.setCurrentItem(items[0])
        for item in items[1:]:
            item.setSelected(True)
        self.tree.scrollToItem(items[0])

    def select_paths(self, paths: list) -> None:
        """Select the items of these files (and in the Files view folders)."""
        wanted = set(paths)
        self._select_all([i for i in self.items() if i.parent() is not None and (
            i.data(0, Qt.UserRole) in wanted or
            (self.files_mode and i.data(0, Qt.UserRole + 3) in wanted))])

    def select_refs(self, refs: list) -> None:
        """Select the items of these files (relative paths) and groups (paths)
        in the Project view."""
        wanted = {tuple(ref) if isinstance(ref, (tuple, list)) else ref for ref in refs}
        self._select_all([i for i in self.items() if i.parent() is not None and
                          self._ref(i) in wanted])

    def select_group(self, group) -> None:
        item = self._find(lambda i: i.data(0, Qt.UserRole + 1) == "group" and
                          tuple(i.data(0, Qt.UserRole + 3)) == tuple(group))
        if item is not None:
            self.tree.setCurrentItem(item)

    def items(self):
        """Every item of the tree, parents before their children. (A walk by
        child(), not QTreeWidgetItemIterator: its items' Python wrappers could
        crash the next clear() when the tree was filled again.)"""
        def walk(item):
            yield item
            for i in range(item.childCount()):
                yield from walk(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            yield from walk(self.tree.topLevelItem(i))

    def _find(self, test):
        return next((item for item in self.items() if test(item)), None)

    def select_project(self) -> None:
        root = self.tree.topLevelItem(0)
        if root is not None:
            self.tree.setCurrentItem(root)

    def project_selected(self) -> bool:
        item = self.tree.currentItem()
        return item is not None and item.parent() is None

    def selected_group(self, kind: str | None = None):
        """The group a new file goes in: the selected group, or the group of
        the selected file if it's of the same ``kind`` ("form", "module"; any
        with None). None otherwise (the project, nothing, or a file of the
        other kind selected): the project then puts it where that kind goes."""
        item = self.tree.currentItem()
        if item is None or item.parent() is None or self.files_mode:
            return None
        if item.data(0, Qt.UserRole + 1) == "group":
            return tuple(item.data(0, Qt.UserRole + 3))
        if kind is not None and item.data(0, Qt.UserRole + 1) != kind:
            return None
        return self._group_path(item.parent())

    # -- the Files view: folders --------------------------------------------------------------
    def project_folder(self) -> str | None:
        project = self._shown[0]
        return project.directory if project is not None else None

    def _item_path(self, item) -> str | None:
        """In the Files view: the file or folder an item shows (the project's
        folder for the top item)."""
        if item.data(0, Qt.UserRole + 1) == "project":
            return self.project_folder()
        return item.data(0, Qt.UserRole + 3)

    def selected_folder(self) -> str | None:
        """In the Files view, the folder a new file goes in: the selected
        folder, or the selected file's folder, else the project's folder.
        None in the Project view."""
        if not self.files_mode or self._shown[0] is None:
            return None
        item = self.tree.currentItem()
        if item is None:
            return self.project_folder()
        path = self._item_path(item)
        if item.data(0, Qt.UserRole + 1) in ("folder", "project"):
            return path
        return os.path.dirname(path)

    def _folders(self) -> list[tuple[str, str]]:
        """(path, label) of the project's folder and every folder shown, for
        the Move to menu."""
        top = self.project_folder()
        folders = [(top, "(Project folder)")]
        for item in self.items():
            if item.data(0, Qt.UserRole + 1) == "folder":
                path = item.data(0, Qt.UserRole + 3)
                folders.append((path, os.path.relpath(path, top).replace(os.sep, "/")))
        return folders

    def _is_project_file(self, path) -> bool:
        project = self._shown[0]
        return project is not None and path == os.path.abspath(project.path)

    def _files_menu(self, menu, item) -> None:
        """The Files view's part of the context menu: folders, renaming,
        deleting and moving files and folders (not the project file)."""
        if item is None:
            top = self.project_folder()
            menu.addAction("New Folder…", lambda: self.newFolder.emit(top))
            return
        kind = item.data(0, Qt.UserRole + 1)
        path = self._item_path(item)
        # In a folder (or the project's folder), or next to a file
        here = path if kind in ("folder", "project") else os.path.dirname(path)
        menu.addAction("New Folder…", lambda: self.newFolder.emit(here))
        if kind == "project" or self._is_project_file(path):
            return
        menu.addAction("Rename…", lambda: self.renamePath.emit(path))
        menu.addAction("Delete", lambda: self.deletePath.emit(path))
        sources = self.move_sources(item)  # the selection, if the item is in it
        paths = [ref for _kind, ref, _place in sources]
        move = menu.addMenu("Move to" if len(sources) < 2 else f"Move {len(sources)} Items to")
        for folder, label in self._folders():
            if self._can_move_to(sources, folder):
                move.addAction(label, lambda f=folder: self.movePaths.emit(paths, f))
        move.setEnabled(not move.isEmpty())

    @staticmethod
    def _group_path(item) -> tuple:
        return tuple(item.data(0, Qt.UserRole + 3)) if item.parent() is not None else ()

    def _selection(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.UserRole + 1), item.data(0, Qt.UserRole + 3)

    def _restore_selection(self, selected) -> None:
        if selected is None:
            return
        kind, ref = selected
        if kind == "project":
            self.select_project()
        elif kind == "group":
            self.select_group(ref)
        else:
            item = self._find(lambda i: i.data(0, Qt.UserRole + 3) == ref)
            if item is not None:
                self.tree.setCurrentItem(item)

    def _on_current_changed(self, item, _previous) -> None:
        if item is None:
            return
        if item.parent() is None:
            self.projectSelected.emit()
        elif item.data(0, Qt.UserRole):
            self.fileSelected.emit(item.data(0, Qt.UserRole))

    def _current(self):
        item = self.tree.currentItem()
        if item is None or item.data(0, Qt.UserRole) is None:
            return None, None
        return item.data(0, Qt.UserRole), item.data(0, Qt.UserRole + 1)

    def _update_buttons(self, *_):
        path, kind = self._current()
        self.view_code.setEnabled(path is not None)
        self.view_object.setEnabled(kind in ("form", "usercontrol"))

    # -- actions --------------------------------------------------------------------------------
    def _on_view_code(self):
        path, _ = self._current()
        if path:
            self.openCode.emit(path)

    def _on_view_object(self):
        path, kind = self._current()
        if path and kind in ("form", "usercontrol"):
            self.openObject.emit(path)

    def _on_double_click(self, item, _column):
        path, kind = item.data(0, Qt.UserRole), item.data(0, Qt.UserRole + 1)
        if path:
            (self.openObject if kind in ("form", "usercontrol") else self.openCode).emit(path)

    @staticmethod
    def _ref(item):
        """What moveItems moves: a file's relative path, or a group's path."""
        ref = item.data(0, Qt.UserRole + 3)
        return tuple(ref) if item.data(0, Qt.UserRole + 1) == "group" else ref

    # -- moving several items ------------------------------------------------------------------
    def _movable(self, item) -> bool:
        kind = item.data(0, Qt.UserRole + 1)
        if self.files_mode:
            return kind in ("folder", "file", "form", "module") and \
                not self._is_project_file(self._item_path(item))
        return kind in ("group", "form", "module")

    def _source(self, item) -> tuple:
        """(kind, what to move, where it is): in the Project view a file's
        relative path or a group's path, and its group; in the Files view a
        path and its folder."""
        kind = item.data(0, Qt.UserRole + 1)
        if self.files_mode:
            path = self._item_path(item)
            return kind, path, os.path.dirname(path)
        return kind, self._ref(item), self._group_path(item.parent())

    def move_sources(self, item=None) -> list[tuple]:
        """What a move moves (see _source): the selected items, or ``item``
        alone when it isn't one of them; only those that can move, and not
        what is inside a selected group or folder (it moves with it)."""
        items = self.tree.selectedItems()
        if item is not None and not item.isSelected():
            items = [item]
        return self._sources_of(items)

    def _sources_of(self, items) -> list[tuple]:
        items = [i for i in items if self._movable(i)]
        chosen = {self._source(i)[:2] for i in items}

        def inside_chosen(item) -> bool:  # below a selected group or folder
            parent = item.parent()
            while parent is not None and parent.parent() is not None:  # (not the project)
                if self._source(parent)[:2] in chosen:
                    return True
                parent = parent.parent()
            return False

        return [self._source(i) for i in items if not inside_chosen(i)]

    def _can_move_to(self, sources, target) -> bool:
        """Whether moving ``sources`` to a group (a path) or folder means
        something: not all already there, and not into one of them."""
        if not sources or all(place == target for _kind, _ref, place in sources):
            return False
        for kind, ref, _place in sources:
            if kind == "group" and target[:len(ref)] == ref:
                return False
            if kind == "folder" and (target == ref or target.startswith(ref + os.sep)):
                return False
        return True

    def _request_move(self, sources, target) -> None:
        """Drag and drop of ``sources`` (items, or one item): onto a group
        (into it), a file (into its group) or the project (to the top level).
        In the Files view: onto a folder, a file (into its folder) or the
        project (into the project's folder). What is there already stays."""
        if isinstance(sources, QTreeWidgetItem):
            sources = [sources]
        found = self._sources_of(sources)
        kind = target.data(0, Qt.UserRole + 1)
        if self.files_mode:
            folder = self._item_path(target) if kind in ("folder", "project") else \
                os.path.dirname(self._item_path(target))
            if self._can_move_to(found, folder):
                self.movePaths.emit([ref for _k, ref, place in found if place != folder],
                                    folder)
            return
        group = self._group_path(target if kind in ("group", "project") else target.parent())
        if self._can_move_to(found, group):
            self.moveItems.emit([ref for _k, ref, place in found if place != group], group)

    def _groups(self):
        """(path, label) of every group, for the Move to menu."""
        paths = [tuple(item.data(0, Qt.UserRole + 3)) for item in self.items()
                 if item.data(0, Qt.UserRole + 1) == "group"]
        return [(path, " / ".join(path)) for path in paths]

    def context_menu(self, item) -> QMenu:
        """The context menu for an item (None: the empty space)."""
        menu = QMenu(self)
        kind = item.data(0, Qt.UserRole + 1) if item is not None else None
        if item is not None and item.data(0, Qt.UserRole):
            path = item.data(0, Qt.UserRole)
            menu.addAction("View Code", lambda: self.openCode.emit(path))
            if kind == "form":
                menu.addAction("View Object", lambda: self.openObject.emit(path))
                name = item.data(0, Qt.UserRole + 2)  # (not the item: gone once repopulated)
                menu.addAction("Set as Start Up", lambda: self.setStartup.emit(name))
            menu.addSeparator()
            menu.addAction(f"Remove {os.path.basename(path)}" +
                           (" from the Project" if self.files_mode else ""),
                           lambda: self.removeFile.emit(path))
            if not self.files_mode:  # (the Files view has its own Rename and Delete)
                menu.addAction("Rename File…", lambda: self.renamePath.emit(path))
                menu.addAction("Delete File…", lambda: self.deletePath.emit(path))
        if kind == "group":
            group = tuple(item.data(0, Qt.UserRole + 3))
            menu.addAction("Rename Group…", lambda: self.renameGroup.emit(group))
            menu.addAction("Delete Group (keeps what is in it)",
                           lambda: self.deleteGroup.emit(group))
        if kind in ("form", "module", "group") and not self.files_mode:
            # Move to: the project or another group (the selection, if the
            # item is in it)
            sources = self.move_sources(item)
            refs = [ref for _kind, ref, _place in sources]
            move = menu.addMenu("Move to" if len(sources) < 2 else f"Move {len(sources)} Items to")
            for target, label in [((), "(Project)")] + self._groups():
                if self._can_move_to(sources, target):
                    move.addAction(label, lambda t=target: self.moveItems.emit(refs, t))
            move.setEnabled(not move.isEmpty())
        if self.files_mode:
            menu.addSeparator()
            self._files_menu(menu, item)
        menu.addSeparator()
        if not self.files_mode:  # groups are the Project view's
            menu.addAction("New Group…", lambda: self.newGroup.emit(
                self.selected_group() if item is not None else None))
        menu.addAction("Add Form", self.addForm.emit)
        menu.addAction("Add Module", self.addModule.emit)
        menu.addAction("Add User Control", self.addUserControl.emit)
        return menu

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is not None:
            if item.isSelected():  # in a selection of several: keep it
                self.tree.setCurrentItem(item, 0, QItemSelectionModel.NoUpdate)
            else:
                self.tree.setCurrentItem(item)
        menu = self.context_menu(item)
        menu.exec(self.tree.viewport().mapToGlobal(pos))
        menu.deleteLater()


class _OutputPane(QWidget):
    """A read-only, themed text pane for program output. Text is appended with
    a kind (out, err, info, in) that picks its color; the kind is stored on
    the text, so a theme change recolors what's already there."""

    _KIND = QTextFormat.UserProperty + 1  # char format property: output kind

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(20000)
        self.output.setContextMenuPolicy(Qt.CustomContextMenu)
        self.output.customContextMenuRequested.connect(self._on_context_menu)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self.output)

    def _start_theming(self) -> None:
        """Call at the end of the subclass constructor."""
        self.apply_theme()
        theme_manager().changed.connect(self.apply_theme)

    def _themed_widgets(self) -> list[QWidget]:
        return [self.output]

    def apply_theme(self) -> None:
        theme = theme_manager().current()
        colors = theme.colors
        font = theme_manager().font()
        font.setPointSize(max(font.pointSize() - 1, 6))
        for widget in self._themed_widgets():
            palette = widget.palette()
            for group in (QPalette.Active, QPalette.Inactive):
                palette.setColor(group, QPalette.Base, QColor(colors["background"]))
                palette.setColor(group, QPalette.Text, QColor(colors["foreground"]))
                palette.setColor(group, QPalette.Highlight,
                                 QColor(colors["selection_background"]))
                palette.setColor(group, QPalette.HighlightedText,
                                 QColor(colors["selection_foreground"]))
            dimmed = QColor(colors["foreground"])
            dimmed.setAlpha(130)
            palette.setColor(QPalette.Disabled, QPalette.Base, QColor(colors["background"]))
            palette.setColor(QPalette.Disabled, QPalette.Text, dimmed)
            for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
                palette.setColor(group, QPalette.PlaceholderText, dimmed)
            widget.setPalette(palette)
            widget.setFont(font)
        # Recolor what's already in the window
        document = self.output.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                kind = fragment.charFormat().property(self._KIND)
                if kind:
                    cursor = QTextCursor(document)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(),
                                       QTextCursor.KeepAnchor)
                    cursor.setCharFormat(self._format(kind))
                iterator += 1
            block = block.next()

    def _format(self, kind: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        role = {"err": "output_error", "info": "output_info", "in": "output_input"}.get(kind)
        if role:
            fmt.setForeground(QColor(theme_manager().current().colors[role]))
            fmt.setProperty(self._KIND, kind)
        if kind == "info":
            fmt.setFontItalic(True)
        return fmt

    def clear(self) -> None:
        self.output.clear()

    def append(self, text: str, kind: str = "out") -> None:
        # Keep following the end only if the user was already there
        scrollbar = self.output.verticalScrollBar()
        at_end = scrollbar.value() >= scrollbar.maximum() - 2
        cursor = QTextCursor(self.output.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text, self._format(kind))
        if at_end:
            scrollbar.setValue(scrollbar.maximum())

    def _context_menu(self) -> QMenu:
        raise NotImplementedError

    def _on_context_menu(self, pos) -> None:
        menu = self._context_menu()
        menu.exec(self.output.viewport().mapToGlobal(pos))
        menu.deleteLater()


class ImmediateWindow(_OutputPane):
    """Program output (stdout/stderr, Debug.Print) plus a line for stdin."""

    openLocation = Signal(str, int)  # path, line
    inputSubmitted = Signal(str)

    _LOCATION_RE = re.compile(r'File "([^"]+)", line (\d+)')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output.mouseDoubleClickEvent = self._on_double_click
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type input for the running program and press Enter")
        self.input.returnPressed.connect(self._submit)
        self.input.setEnabled(False)
        self._layout.addWidget(self.input)
        self._start_theming()

    def _themed_widgets(self) -> list[QWidget]:
        return [self.output, self.input]

    def set_running(self, running: bool) -> None:
        self.input.setEnabled(running)
        if running:
            self.input.setFocus()

    def _submit(self) -> None:
        text = self.input.text()
        self.input.clear()
        self.append(text + "\n", "in")
        self.inputSubmitted.emit(text)

    def _context_menu(self) -> QMenu:
        """Qt's standard text menu (Copy, Select All) plus Clear."""
        menu = self.output.createStandardContextMenu()
        menu.addSeparator()
        clear = menu.addAction("Clear", self.clear)
        clear.setEnabled(not self.output.document().isEmpty())
        return menu

    def _on_double_click(self, event) -> None:
        cursor = self.output.cursorForPosition(event.position().toPoint())
        line = cursor.block().text()
        match = self._LOCATION_RE.search(line)
        if match:
            self.openLocation.emit(match.group(1), int(match.group(2)))
        else:
            QPlainTextEdit.mouseDoubleClickEvent(self.output, event)


class OutputWindow(_OutputPane):
    """The IDE's own stdout and stderr, including libraries such as Qt (see
    ``outputcapture.OutputCapture``). Hidden by default; View > Output Window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_theming()

    def _context_menu(self) -> QMenu:
        menu = QMenu(self.output)
        select_all = menu.addAction("Select All", self.output.selectAll)
        copy = menu.addAction("Copy", self.output.copy)
        menu.addSeparator()
        clear = menu.addAction("Clear", self.clear)
        empty = self.output.document().isEmpty()
        select_all.setEnabled(not empty)
        copy.setEnabled(self.output.textCursor().hasSelection())
        clear.setEnabled(not empty)
        return menu


def pump_process_output(process: QProcess, window: ImmediateWindow) -> None:
    process.readyReadStandardOutput.connect(
        lambda: window.append(bytes(process.readAllStandardOutput()).decode("utf-8", "replace")))
    process.readyReadStandardError.connect(
        lambda: window.append(bytes(process.readAllStandardError()).decode("utf-8", "replace"),
                              "err"))
