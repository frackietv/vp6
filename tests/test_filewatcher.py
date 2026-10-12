"""The FileWatcher control (files and folders: changed, replaced, removed and made
again, Enabled, Remove, Clear) and the App's events and services for the IDE's
own needs: AppActivate / AppDeactivate, App.Active, App.RunOnMainThread,
App.ColorScheme and App.Style."""

import os
import threading
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from conftest import wait_for
from vp6 import (App, FileWatcher, Form, Label, vpSchemeDark, vpSchemeLight,
                 vpSchemeProjectDefault)
from vp6.controls import CONTROL_TYPES, EVENT_ARGS

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Watching(Form):
    def InitializeComponent(self):
        self.fw = FileWatcher(self)
        self.log = []

    def fw_FileChanged(self, Path):
        self.log.append(("file", os.path.basename(Path)))

    def fw_FolderChanged(self, Path):
        self.log.append(("folder", os.path.basename(Path)))


@pytest.fixture
def watching(qapp):
    form = Watching()
    form.Load()
    yield form
    form.Unload()


def test_files_and_folders(watching, tmp_path):
    fw, log = watching.fw, watching.log
    notes = tmp_path / "notes.txt"
    notes.write_text("one")
    folder = tmp_path / "docs"
    folder.mkdir()
    assert fw.Add(str(notes)) and fw.Add(str(folder))
    assert fw.Files == [str(notes)] and fw.Folders == [str(folder)]
    notes.write_text("two")
    wait_for(lambda: ("file", "notes.txt") in log)
    log.clear()
    # Replaced, as editors save: a new file renamed over it; still watched
    replacement = tmp_path / "notes.tmp"
    replacement.write_text("three")
    os.replace(replacement, notes)
    wait_for(lambda: ("file", "notes.txt") in log)
    log.clear()
    notes.write_text("four")
    wait_for(lambda: ("file", "notes.txt") in log)
    log.clear()
    # Removed, then made again: told both times
    notes.unlink()
    wait_for(lambda: ("file", "notes.txt") in log)
    log.clear()
    notes.write_text("five")
    wait_for(lambda: ("file", "notes.txt") in log)
    log.clear()
    (folder / "new.txt").write_text("x")
    wait_for(lambda: ("folder", "docs") in log)
    assert ("folder", tmp_path.name) not in log  # (its own folder watch isn't told)
    # Not there yet: watched once made
    later = tmp_path / "later.txt"
    assert not fw.Add(str(later)) and str(later) in fw.Files
    later.write_text("now")
    wait_for(lambda: ("file", "later.txt") in log)
    # Enabled = False holds the events back; Remove and Clear stop
    log.clear()
    fw.Enabled = False
    notes.write_text("six")
    time.sleep(0.2)
    QApplication.processEvents()
    assert log == []
    fw.Enabled = True
    fw.Remove(str(notes))
    assert fw.Files == [str(later)]
    fw.Clear()
    assert fw.Files == fw.Folders == [] and not fw._watcher.files()


def test_relative_to_the_form_and_unloading(qapp, tmp_path, monkeypatch):
    form = Watching()
    monkeypatch.setattr(form, "_base_dir", lambda: str(tmp_path))
    (tmp_path / "a.txt").write_text("x")
    assert form.fw.Add("a.txt") and form.fw.Files == [str(tmp_path / "a.txt")]
    form.Load()
    form.Unload()
    assert form.fw.Files == []


def test_the_application_becoming_active(qapp):
    from vp6.app import app_state_watcher

    class Active(Form):
        def InitializeComponent(self):
            self.log = []

        def Form_AppActivate(self):
            self.log.append("active")

        def Form_AppDeactivate(self):
            self.log.append("inactive")

    form = Active()
    form.Load()
    watcher = app_state_watcher()
    watcher.active = True
    watcher.changed(Qt.ApplicationInactive)
    watcher.changed(Qt.ApplicationHidden)  # (still not active: once)
    watcher.changed(Qt.ApplicationActive)
    assert form.log == ["inactive", "active"]
    form.Unload()
    watcher.changed(Qt.ApplicationInactive)
    assert form.log == ["inactive", "active"]  # (unloaded: no more)
    assert isinstance(App.Active, bool)
    assert {"AppActivate", "AppDeactivate"} <= set(Form.Events)
    assert EVENT_ARGS["AppActivate"] == ""


def test_running_on_the_main_thread(qapp):
    form = Watching()
    form.lbl = Label(form, Caption="")
    main = threading.get_ident()
    done = []

    def work():
        App.RunOnMainThread(setattr, form.lbl, "Caption", "from a thread")
        result = App.RunOnMainThread(lambda a, b: (threading.get_ident(), a + b), 2, 3,
                                     Wait=True)
        done.append(result)
        try:
            App.RunOnMainThread(lambda: 1 / 0, Wait=True)
        except ZeroDivisionError:
            done.append("raised")

    thread = threading.Thread(target=work)
    thread.start()
    wait_for(lambda: len(done) == 2)
    thread.join()
    assert form.lbl.Caption == "from a thread"
    assert done == [(main, 5), "raised"]
    assert App.RunOnMainThread(lambda: threading.get_ident(), Wait=True) == main
    form._widget.close()


def test_the_programs_color_scheme_and_style(qapp):
    class Follows(Form):
        def InitializeComponent(self):
            self.changes = []

        def Form_ColorSchemeChanged(self, Dark):
            self.changes.append(Dark)

    class Own(Form):
        def InitializeComponent(self):
            self.ColorScheme = vpSchemeLight

    form, own = Follows(), Own()
    form.Show()
    own.Show()
    App.ColorScheme = vpSchemeDark
    assert App.ColorScheme == vpSchemeDark and form.DarkMode and form.changes == [True]
    assert not own.DarkMode  # (its own scheme)
    App.ColorScheme = vpSchemeLight
    assert not form.DarkMode and form.changes == [True, False]
    App.ColorScheme = vpSchemeProjectDefault  # (the project's again)
    assert App.ColorScheme in (1, 2, 3, 4)
    with pytest.raises(ValueError):
        App.ColorScheme = 9
    native = App.Style
    assert native == "Native" and "Fusion" in App.Styles and App.Styles[0] == "Native"
    App.Style = "fusion"
    assert App.Style == "Fusion" and QApplication.style().name().lower() == "fusion"
    App.Style = "Native"
    assert App.Style == "Native"
    with pytest.raises(ValueError, match="no style"):
        App.Style = "Nonesuch"
    form.Unload()
    own.Unload()


def test_in_the_ide(qapp):
    assert CONTROL_TYPES["FileWatcher"] is FileWatcher and list(CONTROL_TYPES)[-1] == "Menu"
    assert EVENT_ARGS["FileChanged"] == EVENT_ARGS["FolderChanged"] == "Path"
    from vp6.ide.icons import icon
    from vp6.ide.panels import Toolbox

    assert "FileWatcher" in Toolbox().buttons and not icon("FileWatcher").isNull()
