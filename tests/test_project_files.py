"""Project files: File > Save Project As (a copy of the project in a new
folder) and renaming and deleting files from the Project Explorer's Project
view."""

import os
import shutil

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from vp6.ide.mainwindow import MainWindow, create_project
from vp6.project import EXTENSION, Project, copy_destination, copy_project


@pytest.fixture
def window(qapp):
    w = MainWindow()
    w.show()
    yield w
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


@pytest.fixture
def project(tmp_path):
    """A project with a picture in a subfolder, things that aren't copied, and
    code of its own in its project file."""
    path = create_project(str(tmp_path / "work"), "Demo", "exe")
    folder = os.path.dirname(path)
    os.makedirs(os.path.join(folder, "art"))
    with open(os.path.join(folder, "art", "logo.png"), "wb") as f:
        f.write(b"png")
    for name in ("dist/Demo.whl", "__pycache__/x.pyc", ".git/HEAD"):
        os.makedirs(os.path.dirname(os.path.join(folder, name)), exist_ok=True)
        open(os.path.join(folder, name), "w").close()
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n# my own note\n")
    loaded = Project.load(path)
    loaded.icon = ["art/logo.png"]
    loaded.version = "2.1.0"
    loaded.save()
    return loaded


# --- Save Project As ---------------------------------------------------------------------------

def test_where_the_copy_goes(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert copy_destination(str(empty / "Calc.vp6p")) == (str(empty), str(empty / "Calc.vp6p"))
    new = tmp_path / "new"  # (made when copying)
    assert copy_destination(str(new / "Calc.vp6p"))[0] == str(new)
    (tmp_path / "other.txt").write_text("")  # a folder with other things: a folder of its own
    assert copy_destination(str(tmp_path / "Calc.vp6p")) == \
        (str(tmp_path / "Calc"), str(tmp_path / "Calc" / "Calc.vp6p"))


def test_copy_project(project, tmp_path):
    texts = {"Module1.py": "# changed in the IDE\n"}
    copy = copy_project(project, str(tmp_path / "copies" / "Demo2.vp6p"), texts)
    folder = tmp_path / "copies"  # (a new folder: used as it is)
    assert copy.path == str(folder / "Demo2.vp6p") and copy.name == "Demo2"
    assert (copy.version, copy.icon, copy.forms) == ("2.1.0", ["art/logo.png"], ["Form1.py"])
    assert (folder / "art" / "logo.png").read_bytes() == b"png"
    assert (folder / "Module1.py").read_text() == "# changed in the IDE\n"  # (unsaved text)
    assert (folder / "Form1.py").read_text() == open(project.abspath("Form1.py")).read()
    assert not (folder / "dist").exists() and not (folder / ".git").exists()
    assert not (folder / "Demo.vp6p").exists()
    text = (folder / "Demo2.vp6p").read_text()
    assert "# my own note" in text and '"name": "Demo2"' in text
    assert Project.load(str(folder / "Demo2.vp6p")) == copy
    # The original: untouched
    assert open(project.abspath("Module1.py")).read() != "# changed in the IDE\n"
    assert Project.load(project.path).name == "Demo"


def test_copy_project_errors(project, tmp_path):
    with pytest.raises(ValueError, match="not a valid project name"):
        copy_project(project, str(tmp_path / "x" / "my project.vp6p"))
    with pytest.raises(ValueError, match="folder of its own"):
        copy_project(project, os.path.join(os.path.dirname(project.directory), "Demo.vp6p"))
    with pytest.raises(ValueError, match="folder of its own"):  # (nor in it)
        copy_project(project, project.path)
    taken = tmp_path / "taken"
    (taken / "Calc").mkdir(parents=True)
    (taken / "Calc" / "x.txt").write_text("")
    (taken / "y.txt").write_text("")
    with pytest.raises(ValueError, match="isn't empty"):
        copy_project(project, str(taken / "Calc.vp6p"))


def test_save_project_as_in_the_ide(window, project, tmp_path, monkeypatch):
    window.open_project(project.path)
    file_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&File")
    assert window.act_save_as in file_menu.actions() and window.act_save_as.isEnabled()
    module1 = project.abspath("Module1.py")
    window.documents[module1].replace_text("# edited, not saved\n")  # (unsaved)
    target = tmp_path / "copies" / "Demo2"
    monkeypatch.setattr("vp6.ide.mainwindow.QFileDialog.getSaveFileName",
                        lambda *args: (str(target), ""))  # (no extension: added)
    window.act_save_as.trigger()
    assert window.project.path == str(tmp_path / "copies" / ("Demo2" + EXTENSION))
    assert window.project.name == "Demo2" and window.windowTitle().startswith("Demo2")
    copied = os.path.join(window.project.directory, "Module1.py")
    assert window.documents[copied].text == "# edited, not saved\n"
    assert not window.documents[copied].modified
    assert open(module1).read() != "# edited, not saved\n"  # (the original: as saved)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    assert not window.save_project_as(window.project.path)  # (its own folder: no)
    assert "couldn't be copied" in warnings[0]


# --- renaming and deleting in the Project view ------------------------------------------------

def test_rename_and_delete_in_the_project_view(window, tmp_path, monkeypatch):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = window.project.directory
    explorer = window.explorer
    assert not explorer.files_mode

    def actions(path):
        item = explorer._find(lambda i: i.data(0, 0x0100) == path)
        explorer.tree.setCurrentItem(item)
        return {a.text(): a for a in explorer.context_menu(item).actions()}

    module1 = os.path.join(folder, "Module1.py")
    menu = actions(module1)
    assert "Rename File…" in menu and "Delete File…" in menu
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kw: ("Helpers.py", True))
    menu["Rename File…"].trigger()  # the file, and the imports of it
    helpers = os.path.join(folder, "Helpers.py")
    assert os.path.isfile(helpers) and not os.path.exists(module1)
    assert "Helpers.py" in window.project.modules and helpers in window.documents
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(MainWindow, "_move_to_trash", staticmethod(
        lambda path: (shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)) or True))
    actions(helpers)["Delete File…"].trigger()  # to the Trash, out of the project
    assert not os.path.exists(helpers) and "Helpers.py" not in window.project.modules
    assert helpers not in window.documents
    form1 = os.path.join(folder, "Form1.py")
    assert "Rename File…" in actions(form1)  # (a form's file too)
