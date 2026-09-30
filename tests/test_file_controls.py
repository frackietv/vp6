"""DriveListBox, DirListBox and FileListBox."""

import os
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from vp6 import DirListBox, DriveListBox, FileListBox, Form
from vp6.controls import CONTROL_TYPES, file_matches, user_drives
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Browser(Form):
    def InitializeComponent(self):
        self.drv = DriveListBox(self)
        self.dir = DirListBox(self)
        self.fil = FileListBox(self, Pattern="*.txt")

    def Form_Load(self):
        self.events = []

    def drv_Change(self):
        self.events.append("drv_Change")

    def dir_Change(self):
        self.events.append("dir_Change")
        self.fil.Path = self.dir.Path

    def dir_Click(self):
        self.events.append(f"dir_Click {self.dir.ListIndex}")

    def fil_PathChange(self):
        self.events.append("fil_PathChange")

    def fil_PatternChange(self):
        self.events.append(f"fil_PatternChange {self.fil.Pattern}")

    def fil_Click(self):
        self.events.append(f"fil_Click {self.fil.FileName}")


@pytest.fixture
def folder(tmp_path):
    """b/, a/, .hidden/ and some files."""
    for name in ("b", "a", ".hidden"):
        (tmp_path / name).mkdir()
    for name in ("Read me.TXT", "notes.txt", "photo.png", "Makefile", ".secret.txt"):
        (tmp_path / name).write_text("x")
    (tmp_path / "a" / "deep.txt").write_text("x")
    return tmp_path


@pytest.fixture
def form(qapp):
    form = Browser()
    form.Load()
    return form


def test_patterns():
    assert file_matches("Notes.TXT", "*.txt") and not file_matches("notes.txt", "*.png")
    assert file_matches("Makefile", "*.*") and file_matches("a.b", "*.*")  # *.* is all
    assert file_matches("x.jpg", "*.png; *.jpg") and file_matches("a1.py", "a?.py")
    assert file_matches("x", "") and not file_matches("x", ";")


def test_drives(form):
    drives = user_drives()
    assert drives and form.drv.List == [label for _root, label in drives]
    assert form.drv.ListCount == len(drives)
    root = os.path.abspath(os.sep) if sys.platform != "win32" else os.getcwd()[:2].lower() + "\\"
    form.drv.Drive = os.getcwd()  # any path on it: its drive
    assert os.path.normcase(os.getcwd()).startswith(os.path.normcase(form.drv.Drive.rstrip(os.sep)))
    assert form.drv.Drive in [d[0] for d in drives] and root in [d[0] for d in drives]
    with pytest.raises(FileNotFoundError):
        form.drv.Drive = os.path.join(os.getcwd(), "no such folder")
    form.drv.Refresh()  # (the same drive stays chosen)
    assert form.drv.Drive in [d[0] for d in drives] and not form.events


def test_dir_list_box(form, folder):
    box = form.dir
    assert box.Path == os.getcwd() and box.List(-1) == box.Path
    box.Path = str(folder)
    assert form.events == ["dir_Change", "fil_PathChange"]
    assert list(box.List) == [str(folder / "a"), str(folder / "b")] and box.ListCount == 2
    assert box.List(-1) == str(folder) and box.List[-2] == str(folder.parent)
    assert box.List(-len(folder.parts)) == os.path.abspath(os.sep)  # up to the root
    assert box.ListIndex == -1
    with pytest.raises(IndexError):
        box.List(2)
    box.ListIndex = 1  # selecting fires Click, not Change
    assert box.ListIndex == 1 and form.events[-1] == "dir_Click 1"
    box.ListIndex = -2
    assert form.events[-1] == "dir_Click -2" and box.Path == str(folder)
    box.ShowHidden = True
    assert box.ListCount == 3 and box.List(0) == str(folder / ".hidden")
    (folder / "c").mkdir()
    box.Refresh()
    assert box.ListCount == 4
    form.events.clear()
    box.Path = str(folder)  # the same folder: no Change
    assert form.events == []
    # Double-clicking a folder opens it
    tree = box._widget
    item = tree.currentItem().child(1)  # "a" (after .hidden)
    tree.itemDoubleClicked.emit(item, 0)
    assert box.Path == str(folder / "a") and form.events[0] == "dir_Change"
    assert form.fil.Path == str(folder / "a") and form.fil.List == ["deep.txt"]
    with pytest.raises(FileNotFoundError):
        box.Path = str(folder / "missing")


def test_file_list_box(form, folder):
    files = form.fil
    assert files.Pattern == "*.txt" and form.events == []  # (the designer's: no event)
    files.Path = str(folder)
    assert files.List == ["notes.txt", "Read me.TXT"] and files.ListCount == 2
    assert form.events == ["fil_PathChange"]
    files.Pattern = "*.*"
    assert files.List == ["Makefile", "notes.txt", "photo.png", "Read me.TXT"]
    assert form.events[-1] == "fil_PatternChange *.*"
    files.Hidden = True
    assert ".secret.txt" in files.List
    files.Hidden = False
    files.FileName = "PHOTO.png"  # a listed name selects it (Click)
    assert files.FileName == files.Text == "photo.png" and files.ListIndex == 2
    assert form.events[-1] == "fil_Click photo.png"
    files.FileName = "*.png;*.txt"  # a pattern sets Pattern
    assert files.Pattern == "*.png;*.txt" and files.List == ["notes.txt", "photo.png",
                                                             "Read me.TXT"]
    files.FileName = str(folder / "a")  # a folder sets Path
    assert files.Path == str(folder / "a") and files.List == ["deep.txt"]
    files.FileName = os.path.join(str(folder), "*.png")  # both
    assert files.Path == str(folder) and files.List == ["photo.png"]
    with pytest.raises(FileNotFoundError):
        files.FileName = "nothing.png"
    files.ListIndex = 0
    (folder / "zebra.png").write_text("x")
    files.Refresh()  # the new file, the same one selected
    assert files.List == ["photo.png", "zebra.png"] and files.FileName == "photo.png"
    for method in (files.Clear, files.RemoveItem, files.AddItem):
        with pytest.raises(AttributeError, match="set Path and Pattern"):
            method(0)
    files.MultiSelect = 2  # a ListBox otherwise
    files.Selected[0] = files.Selected[1] = True
    assert files.SelCount == 2


def test_clicking_files(form, folder):
    form.fil.Path = str(folder)
    form.Show()
    view = form.fil._widget
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     view.visualItemRect(view.item(1)).center())
    assert form.events[-1] == "fil_Click Read me.TXT"
    form.Unload()


def test_toolbox_and_icons(qapp):
    for name in ("DriveListBox", "DirListBox", "FileListBox"):
        assert name in Toolbox().buttons and name in CONTROL_TYPES
        assert not icon(name).isNull()
    assert list(CONTROL_TYPES).index("DriveListBox") == list(CONTROL_TYPES).index("Timer") + 1
