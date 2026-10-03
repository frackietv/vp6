"""App, Screen and settings: SaveSetting / GetSetting / GetAllSettings /
DeleteSetting, App's version and descriptions from the project, PrevInstance,
Command(), Screen.Fonts, Screen.FixedFonts and Screen.FontCount."""

import os
import subprocess
import sys
import textwrap

import pytest
from PySide6.QtGui import QFontDatabase

import vp6
from vp6 import (App, Command, DeleteSetting, GetAllSettings, GetSetting, SaveSetting, Screen,
                 app)
from vp6.ide.dialogs import ProjectPropertiesDialog
from vp6.project import Project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_DIR", str(tmp_path))
    return tmp_path


def test_save_get_and_delete_settings(settings_dir):
    assert GetSetting("Demo", "Startup", "Left") == ""
    assert GetSetting("Demo", "Startup", "Left", "100") == "100"  # the Default
    SaveSetting("Demo", "Startup", "Left", 250)  # stored as text, as in VB
    SaveSetting("Demo", "Startup", "Top", "40")
    SaveSetting("Demo", "Recent", "File1", "a b.txt")
    assert GetSetting("Demo", "Startup", "Left") == "250"
    assert GetAllSettings("Demo", "Startup") == [("Left", "250"), ("Top", "40")]
    assert GetAllSettings("Demo", "Nothing") == []
    assert GetSetting("Other", "Startup", "Left") == ""  # per program
    assert (settings_dir / "Demo.ini").exists()
    DeleteSetting("Demo", "Startup", "Left")  # a setting
    assert GetAllSettings("Demo", "Startup") == [("Top", "40")]
    DeleteSetting("Demo", "Startup")  # a section
    assert GetAllSettings("Demo", "Startup") == [] and GetSetting("Demo", "Recent", "File1")
    DeleteSetting("Demo")  # everything
    assert GetSetting("Demo", "Recent", "File1") == ""
    with pytest.raises(ValueError):
        SaveSetting("", "a", "b", "c")


def test_app_from_the_project(monkeypatch):
    for name in ("_title", "Major", "Minor", "Revision", "ProductName", "CompanyName",
                 "FileDescription"):
        monkeypatch.setattr(type(App), name, getattr(App, name))
    assert (App.Major, App.Minor, App.Revision) == (1, 0, 0)  # VB's default
    App._title = ""
    assert App.Title == App.EXEName == os.path.splitext(os.path.basename(sys.argv[0]))[0]
    project = Project(name="Notes", version="2.10.3", company_name="Acme",
                      description="Takes notes")
    App._set_project(project)
    assert (App.Title, App.Major, App.Minor, App.Revision) == ("Notes", 2, 10, 3)
    assert (App.ProductName, App.CompanyName, App.FileDescription) == \
        ("Notes", "Acme", "Takes notes")  # ProductName: the name unless given
    project.product_name = "Notes Pro"
    project.version = "3"
    App._set_project(project)
    assert App.ProductName == "Notes Pro" and (App.Major, App.Minor, App.Revision) == (3, 0, 0)


def test_project_file_round_trip(tmp_path):
    project = Project(name="P", forms=["Form1.py"], version="1.2.0", product_name="Pro",
                      company_name="Co", description="D", arguments="-v x")
    path = str(tmp_path / "P.vp6p")
    project.save(path)
    assert Project.load(path) == project
    text = open(path).read()
    assert '"version": "1.2.0",' in text and '"arguments": "-v x",' in text
    old = tmp_path / "Old.vp6p"  # a project from before: the defaults
    old.write_text("PROJECT = {'name': 'Old', 'forms': ['Form1.py']}\n")
    loaded = Project.load(str(old))
    assert (loaded.version, loaded.product_name, loaded.arguments) == ("1.0.0", "", "")


def test_command(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["Project1.vp6p"])
    assert Command() == ""
    monkeypatch.setattr(sys, "argv", ["Project1.vp6p", "--open", "a file.txt"])
    assert Command() == ("--open \"a file.txt\"" if os.name == "nt" else "--open 'a file.txt'")


def test_screen_fonts(qapp):
    fonts = Screen.Fonts
    assert len(fonts) == Screen.FontCount > 0
    assert fonts(0) == fonts[0] and fonts == sorted(fonts, key=str.casefold)
    assert not any(name.startswith(".") for name in fonts)  # (not the system's private ones)
    fixed = Screen.FixedFonts
    assert fixed and set(fixed) <= set(fonts) and fixed == sorted(fixed, key=str.casefold)
    assert fixed(0) == fixed[0]
    assert all(QFontDatabase.isFixedPitch(name) for name in fixed)


def test_project_properties_dialog(qapp):
    project = Project(name="P", version="1.4.2", company_name="Co", arguments="x")
    dialog = ProjectPropertiesDialog(project, ["Form1"])
    assert [box.value() for box in dialog.version] == [1, 4, 2]
    assert dialog.product_name.placeholderText() == "P" and dialog.arguments.text() == "x"
    dialog.version[1].setValue(5)
    dialog.description.setText(" A program ")
    dialog.arguments.setText("-q")
    dialog.apply(project)
    assert (project.version, project.description, project.arguments, project.company_name) == \
        ("1.5.2", "A program", "-q", "Co")


# --- in programs of their own -----------------------------------------------------------------

def _python(code, *args, **kwargs):
    env = dict(os.environ, PYTHONPATH=ROOT, QT_QPA_PLATFORM="offscreen")
    return subprocess.Popen([sys.executable, "-c", textwrap.dedent(code), *args], env=env,
                            stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True,
                            cwd=kwargs.get("cwd"))


def test_prev_instance(tmp_path):
    # Two copies of one program: the second sees the first (it holds the lock until it ends)
    code = """
        import sys
        from vp6 import App
        from vp6.app import ensure_app
        App.Title = "PrevInstanceTest"
        ensure_app()
        print(App.PrevInstance, flush=True)
        sys.stdin.readline()
    """
    first = _python(code, cwd=str(tmp_path))
    assert first.stdout.readline().strip() == "False"
    second = _python(code, cwd=str(tmp_path))
    assert second.stdout.readline().strip() == "True"
    second.communicate("\n")
    first.communicate("\n")
    third = _python(code, cwd=str(tmp_path))  # the first has ended
    assert third.stdout.readline().strip() == "False"
    third.communicate("\n")


def test_runner_passes_the_arguments(tmp_path):
    (tmp_path / "Module1.py").write_text(textwrap.dedent("""
        import sys
        from vp6 import App, Command

        def Main():
            print(repr(Command()), sys.argv[1:], App.Major, App.ProductName, flush=True)
    """))
    project = Project(name="Args", type="console", startup="Sub Main", forms=[],
                      modules=["Module1.py"], version="4.1.0")
    project.save(str(tmp_path / "Args.vp6p"))
    env = dict(os.environ, PYTHONPATH=ROOT, QT_QPA_PLATFORM="offscreen")
    for command in ([sys.executable, str(tmp_path / "Args.vp6p"), "-x", "a b"],
                    [sys.executable, "-m", "vp6.runner", str(tmp_path / "Args.vp6p"), "-x",
                     "a b"]):
        out = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        assert out.stdout.strip() == f"{_joined()!r} ['-x', 'a b'] " \
                                     "4 Args", out.stderr


def _joined():
    return '-x "a b"' if os.name == "nt" else "-x 'a b'"


def test_exported():
    for name in ("Command", "SaveSetting", "GetSetting", "GetAllSettings", "DeleteSetting"):
        assert name in vp6.__all__
