"""Watching files and folders: the ``FileWatcher`` control.

A FileWatcher (invisible at run time, like a Timer) tells when files or
folders change on disk, e.g. a document another program edited::

    self.fwDocs.Add("notes.txt")                        # relative to the form's folder
    self.fwDocs.Add(App.Path)                           # a folder: files added, removed...

    def fwDocs_FileChanged(self, Path):                 # changed, replaced or removed
        if os.path.exists(Path):
            self.txtNotes.Text = open(Path).read()

    def fwDocs_FolderChanged(self, Path):
        self.filFiles.Refresh()

* ``Add(Path)`` watches a file or folder (relative to the form's folder);
  ``Remove(Path)`` stops, ``Clear()`` stops them all; ``Files`` and
  ``Folders`` list what is watched (full paths).
* ``FileChanged(Path)`` fires when a file is written, replaced or removed;
  ``FolderChanged(Path)`` when something in a folder is added, removed or
  renamed. Enabled = False holds the events back.
* A file that an editor replaces (writing a new file and renaming it over
  the old one) is still watched; one that is removed is watched again when
  it comes back (and FileChanged says so).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ._props import P
from .controls import CONTROL_TYPES, EVENT_ARGS, Control, resolve_path

EVENT_ARGS.update({"FileChanged": "Path", "FolderChanged": "Path"})


class FileWatcher(Control):
    """Tells when files and folders change (the module's documentation)."""

    TypeName = "FileWatcher"
    DefaultEvent = "FileChanged"
    DefaultSize = (32, 32)
    Events = ("FileChanged", "FolderChanged")
    Properties = (
        P("Left", "int", 0, always=True, description="Position in the designer only"),
        P("Top", "int", 0, always=True, description="Position in the designer only"),
        P("Enabled", "bool", True,
          description="Whether its events fire (False: changes go unreported)"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        # (_files, _folders: what was asked for; _waiting: folder -> files gone from it)
        self.__dict__.update(_watcher=None, _files=[], _folders=[], _waiting={})
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        if self._design_mode:
            return _filewatcher_design_widget(parent)
        return None

    def _read_Width(self):
        return 32

    def _read_Height(self):
        return 32

    def _qt(self) -> QFileSystemWatcher:
        watcher = self._watcher
        if watcher is None:
            watcher = QFileSystemWatcher(self._form._widget)
            watcher.fileChanged.connect(self._on_file)
            watcher.directoryChanged.connect(self._on_folder)
            self.__dict__["_watcher"] = watcher
        return watcher

    def _path(self, Path) -> str:
        return os.path.normpath(resolve_path(self._form, os.path.expanduser(str(Path))))

    # -- what it watches -----------------------------------------------------------------------
    @property
    def Files(self) -> list[str]:
        """The files it watches (full paths), in the order added."""
        return list(self._files)

    @property
    def Folders(self) -> list[str]:
        """The folders it watches (full paths), in the order added."""
        return list(self._folders)

    def Add(self, Path) -> bool:
        """Watch a file or a folder (relative to the form's folder). False if
        there is none there (a file is watched once it is made)."""
        if self._design_mode:
            return False
        path = self._path(Path)
        if os.path.isdir(path):
            if path not in self._folders:
                self._folders.append(path)
            self._qt().addPath(path)
            return True
        if path not in self._files:
            self._files.append(path)
        if os.path.isfile(path):
            self._qt().addPath(path)
            return True
        self._wait_for(path)
        return False

    def Remove(self, Path) -> None:
        """Stop watching a file or folder."""
        path = self._path(Path)
        for paths in (self._files, self._folders):
            if path in paths:
                paths.remove(path)
        self._stop_waiting(path)
        if self._watcher is not None and path in self._watcher.files() + \
                self._watcher.directories() and path not in self._waiting:
            self._watcher.removePath(path)

    def Clear(self) -> None:
        """Stop watching everything."""
        self._files.clear()
        self._folders.clear()
        self._waiting.clear()
        watcher = self._watcher
        if watcher is not None:
            paths = watcher.files() + watcher.directories()
            if paths:
                watcher.removePaths(paths)

    # -- files that go and come back -----------------------------------------------------------
    def _wait_for(self, path: str) -> None:
        """A watched file isn't there (removed, or being replaced): watch its
        folder for it."""
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            return
        self._waiting.setdefault(folder, set()).add(path)
        self._qt().addPath(folder)

    def _stop_waiting(self, path: str) -> None:
        for folder, files in list(self._waiting.items()):
            files.discard(path)
            if not files:
                del self._waiting[folder]
                if folder not in self._folders and self._watcher is not None:
                    self._watcher.removePath(folder)

    def _on_file(self, path: str) -> None:
        if path not in self._files:
            return
        if os.path.isfile(path):
            if path not in self._watcher.files():  # (replaced: a new file, watched again)
                self._watcher.addPath(path)
        else:
            self._wait_for(path)
        self._report("FileChanged", path)

    def _on_folder(self, folder: str) -> None:
        waiting = self._waiting.get(folder)
        if waiting:
            for path in sorted(waiting):
                if os.path.isfile(path):  # (back again)
                    self._stop_waiting(path)
                    self._watcher.addPath(path)
                    self._report("FileChanged", path)
        if folder in self._folders:
            if not os.path.isdir(folder):
                self._watcher.removePath(folder)
            self._report("FolderChanged", folder)

    def _report(self, event: str, path: str) -> None:
        if self._values.get("Enabled", True):
            self._fire(event, path)

    def _form_unloaded(self) -> None:
        """Its form unloads: nothing is watched any more."""
        self.Clear()


def _filewatcher_design_widget(parent: QWidget) -> QLabel:
    """The icon the designer shows for a FileWatcher: a page with an eye."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.2))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRect(5, 2, 14, 19)
    painter.setBrush(QColor("#5b9bd5"))
    painter.drawEllipse(9, 14, 12, 8)
    painter.setBrush(QColor("#222222"))
    painter.drawEllipse(13, 16, 4, 4)
    painter.end()
    label = QLabel(parent)
    label.setFixedSize(32, 32)
    label.setAlignment(Qt.AlignCenter)
    label.setFrameStyle(QFrame.Panel | QFrame.Raised)
    label.setPixmap(pixmap)
    return label


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["FileWatcher"] = FileWatcher
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
