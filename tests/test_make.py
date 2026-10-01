"""Packaging projects (vp6.make, vp6-make): wheels (the default, Project > Build
Wheel) and standalone executables (--exe, File > Make Executable...)."""

import ast
import os
import subprocess
import sys
import zipfile

import pytest

from conftest import wait_for
from vp6 import make
from vp6.ide.mainwindow import MainWindow, create_project
from vp6.project import SUB_MAIN, Project


@pytest.fixture
def project(tmp_path):
    """A console project with a module in a subfolder, a data file, and things
    that stay out of the executable."""
    path = create_project(str(tmp_path), "Hello", "console")
    folder = os.path.dirname(path)
    for sub in ("lib", "data", "dist/old", "build", "__pycache__", ".git"):
        os.makedirs(os.path.join(folder, sub))
    files = {
        "lib/Greeting.py": "def greeting():\n    return 'Hello from a subfolder module'\n",
        "data/message.txt": "and a data file\n",
        "Module1.py": ("import csv\nimport io\nimport os.path\n\n"
                       "from Greeting import greeting\n\n\n"
                       "def Main():\n    print(greeting())\n"
                       "    print(open('data/message.txt').read().strip())\n"
                       "    print('csv says', next(csv.reader(io.StringIO('a,b'))))\n"
                       "    return 7\n"),
        "Broken.py": "def (:\n",  # not imported by anything: skipped by the import scan
        "Unused.py": "import json\nfrom . import sibling\n",  # (never run)
        "dist/old/Hello": "an old build", "build/x.txt": "", "__pycache__/m.pyc": "",
        ".git/HEAD": "", ".env": "", "Module1.pyc": "",
    }
    for name, text in files.items():
        with open(os.path.join(folder, name), "w") as f:
            f.write(text)
    project = Project.load(path)
    project.modules.append("lib/Greeting.py")
    project.save()
    return project


def test_what_goes_in(project):
    assert make.project_files(project) == [
        "Broken.py", "Form1.py", "Hello.vp6p", "Module1.py", "Unused.py", "data/message.txt",
        "lib/Greeting.py"]
    # What the code imports, but not its own forms and modules (nor relative imports)
    assert make.imported_modules(project) == ["csv", "io", "json", "os", "vp6"]


def test_the_launcher(project):
    source = make.launcher_source(project)
    ast.parse(source)
    assert "run_project(os.path.join(folder, 'Hello.vp6p'))" in source
    assert 'getattr(sys, "_MEIPASS"' in source


def test_where_it_goes(project):
    windowed = Project(name="Calc", type="exe", startup=SUB_MAIN)
    assert make.output_path(windowed, "/d", False, "darwin") == "/d/Calc.app"
    assert make.output_path(windowed, "/d", True, "darwin") == "/d/Calc.app"  # apps: folders
    assert not make.can_be_one_file(windowed, "darwin") and make.can_be_one_file(windowed, "linux")
    assert make.output_path(windowed, "/d", False, "win32") == os.path.join("/d", "Calc",
                                                                            "Calc.exe")
    assert make.output_path(windowed, "/d", True, "win32") == os.path.join("/d", "Calc.exe")
    assert make.output_path(windowed, "/d", False, "linux") == os.path.join("/d", "Calc", "Calc")
    assert make.output_path(project, "/d", True, "darwin") == os.path.join("/d", "Hello")


def test_the_pyinstaller_command(project, monkeypatch):
    command = make.pyinstaller_command(project, "/w/launcher.py", "/d", "/w", onefile=True,
                                       platform="linux")
    assert command[:3] == [sys.executable, "-m", "PyInstaller"]
    assert "--console" in command and "--onefile" in command and command[-1] == "/w/launcher.py"
    assert command[command.index("--name") + 1] == "Hello"
    data = [command[i + 1] for i, arg in enumerate(command) if arg == "--add-data"]
    assert f"{project.abspath('lib/Greeting.py')}{os.pathsep}lib" in data  # same folders
    assert f"{project.abspath('Hello.vp6p')}{os.pathsep}." in data
    ours = [d.split(os.pathsep)[0] for d in data if d.startswith(project.directory)]
    assert len(ours) == len(make.project_files(project))  # (dist, build...: not in)
    assert any(d.endswith(f"{os.pathsep}vp6/images") for d in data)  # VP6's own icon
    hidden = [command[i + 1] for i, arg in enumerate(command) if arg == "--hidden-import"]
    assert {"csv", "vp6"} <= set(hidden)
    vp6_folder = os.path.dirname(os.path.dirname(os.path.abspath(make.__file__)))
    # VP6's folder only when PyInstaller can't find it itself (an editable install)
    assert make.vp6_search_path(site_folders=["/elsewhere"]) == vp6_folder  # (editable)
    assert make.vp6_search_path(site_folders=[vp6_folder]) is None  # installed
    assert ("--paths" in command) == (make.vp6_search_path() is not None)
    # The executable's icon: the project's largest (with Pillow), else VP6's
    monkeypatch.setattr(make.importlib.util, "find_spec", lambda name: object())
    assert project.icon == [] and make.icon_file(project) == make.VP6_ICON_FILES[-1]
    for name in ("logo-32.png", "logo-256.png"):
        open(project.abspath(name), "wb").close()
    project.icon = ["logo-32.png", "logo-256.png"]
    assert make.icon_file(project) == project.icon_paths()[-1]
    windowed = Project(name="Calc", type="exe", path=project.path)
    command = make.pyinstaller_command(windowed, "/w/l.py", "/d", "/w", onefile=True,
                                       platform="darwin")
    assert "--windowed" in command and "--onefile" not in command
    assert command[command.index("--icon") + 1] == make.VP6_ICON_FILES[-1]  # no icon: VP6's
    monkeypatch.setattr(make.importlib.util, "find_spec", lambda name: None)  # no Pillow
    assert make.icon_file(project) is None


def test_without_pyinstaller(project, monkeypatch, capsys):
    monkeypatch.setattr(make.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(make.MakeError, match="needs PyInstaller"):
        make.make(project.path)
    assert make.main([project.path, "--exe"]) == 1
    assert 'pip install "vp6[make]"' in capsys.readouterr().err


def test_make_runs_pyinstaller(project, monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, command, **kwargs):
            calls.append(command)
            out = make.output_path(project, os.path.join(project.directory, "dist"), False)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "w").close()
            self.stdout = iter(["building...\n"])
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(make.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(make.subprocess, "Popen", FakePopen)
    lines = []
    path = make.make(project.path, log=lines.append)
    assert path == os.path.join(project.directory, "dist", "Hello", "Hello" +
                                (".exe" if sys.platform == "win32" else ""))
    assert "building..." in lines and lines[-1] == f"Made {path}"
    launcher = calls[0][-1]
    assert not os.path.exists(launcher)  # the work folder is gone


def test_make_in_the_ide(qapp, project, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    shown, warned = [], []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args[2]))
    window = MainWindow()
    window.open_project(project.path)
    assert window.act_make.isEnabled() and window.act_make.text() == "&Make Executable…"
    script = tmp_path / "fake_make.py"
    script.write_text("import sys\nprint('making...')\nprint('Made /x/Hello')\n"
                      "sys.exit(int(sys.argv[1]))\n")
    monkeypatch.setattr(window, "_make_command",
                        lambda onefile, wheel=False: (sys.executable, [str(script), "0"]))
    window.start_make()
    assert window.make_process is not None and not window.act_make.isEnabled()
    wait_for(lambda: window.make_process is None, timeout_ms=10000)
    assert shown == ["Made /x/Hello"] and window.act_make.isEnabled()
    assert "making..." in window.output.output.toPlainText()
    monkeypatch.setattr(window, "_make_command",
                        lambda onefile, wheel=False: (sys.executable, [str(script), "1"]))
    window.start_make()
    wait_for(lambda: window.make_process is None, timeout_ms=10000)
    assert warned and "Output window" in warned[0]
    command = MainWindow._make_command(window, True)[1]
    assert command[-4:] == ["vp6.make", window.project.path, "--exe", "--onefile"]
    assert MainWindow._make_command(window, False, wheel=True)[1][-2:] == \
        ["vp6.make", window.project.path]
    window.close()


def test_build_wheel_in_the_ide(qapp, project, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    window = MainWindow()
    window.open_project(project.path)
    project_menu = [m for m in window.menuBar().actions() if m.text() == "&Project"][0].menu()
    assert window.act_wheel in project_menu.actions() and window.act_wheel.isEnabled()
    window.act_wheel.trigger()  # (the real vp6.make: a wheel takes a moment)
    assert window.make_process is not None and not window.act_wheel.isEnabled()
    wait_for(lambda: window.make_process is None, timeout_ms=30000)
    wheel = os.path.join(project.directory, "dist", "Hello-1.0.0-py3-none-any.whl")
    assert shown == [f"Made {wheel}"] and os.path.isfile(wheel)
    assert window._make_title == "Build Wheel"  # (the box's title; macOS shows none)
    assert "Building the wheel of Hello" in window.output.output.toPlainText()
    window.close()


# --- wheels ------------------------------------------------------------------------------

def test_the_wheel(project, tmp_path):
    project.version, project.description, project.company_name = "2.3", "Says hello", "Acme"
    project.save()
    lines = []
    path = make.make_wheel(project.path, log=lines.append)
    assert path == os.path.join(project.directory, "dist", "Hello-2.3.0-py3-none-any.whl")
    assert lines[-1] == f"Made {path}"
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        info = "Hello-2.3.0.dist-info"
        # The project's files (as in an executable) in the package "hello", and its launcher
        assert sorted(n for n in names if n.startswith("hello/")) == sorted(
            [f"hello/{f}" for f in make.project_files(project)] +
            ["hello/__init__.py", "hello/__main__.py"])
        metadata = wheel.read(f"{info}/METADATA").decode()
        assert "Name: Hello\nVersion: 2.3.0\nSummary: Says hello\nAuthor: Acme" in metadata
        from vp6 import __version__

        assert f"Requires-Dist: vp6>={__version__}" in metadata
        assert "csv" not in metadata  # (the standard library)
        entry = wheel.read(f"{info}/entry_points.txt").decode()
        assert entry == "[console_scripts]\nHello = hello.__main__:main\n"  # (console)
        assert "Tag: py3-none-any" in wheel.read(f"{info}/WHEEL").decode()
        record = wheel.read(f"{info}/RECORD").decode().splitlines()
        assert len(record) == len(names) and record[-1] == f"{info}/RECORD,,"
        ast.parse(wheel.read("hello/__main__.py"))
    windowed = Project.load(project.path)
    windowed.type = "exe"
    windowed.save()
    with zipfile.ZipFile(make.make_wheel(project.path, str(tmp_path), log=lambda s: None)) \
            as wheel:
        assert wheel.read("Hello-2.3.0.dist-info/entry_points.txt").startswith(b"[gui_scripts]")


def test_wheel_requirements(project, monkeypatch):
    monkeypatch.setattr(make, "imported_modules",
                        lambda p: ["csv", "PySide6", "vp6", "yaml", "nowhere"])
    monkeypatch.setattr(make.importlib.metadata, "packages_distributions",
                        lambda: {"yaml": ["PyYAML"]})
    notes = []
    from vp6 import __version__

    assert make.wheel_requirements(project, notes.append) == [f"vp6>={__version__}", "PyYAML"]
    assert notes and "'nowhere'" in notes[0]


def test_wheel_errors(project):
    with open(project.abspath("__main__.py"), "w") as f:
        f.write("")
    with pytest.raises(make.MakeError, match="__main__.py"):
        make.make_wheel(project.path)


def test_the_command_line(project, monkeypatch):
    calls = []
    monkeypatch.setattr(make, "make_wheel", lambda *args: calls.append(("wheel", args)))
    monkeypatch.setattr(make, "make", lambda *args: calls.append(("exe", args)))
    assert make.main([project.path]) == 0  # a wheel, by default
    assert make.main([project.path, "--exe"]) == 0
    assert make.main([project.path, "--onefile", "--dist", "/d"]) == 0  # (--exe implied)
    assert calls == [("wheel", (project.path, None)), ("exe", (project.path, None, False)),
                     ("exe", (project.path, "/d", True))]


def test_installed_from_the_wheel(project, tmp_path):
    # pip installs the wheel; its command and python -m run the program
    path = make.make_wheel(project.path, log=lambda line: None)
    site = tmp_path / "site"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps",
                    "--disable-pip-version-check", "--target", str(site), path],
                   check=True, timeout=120)
    root = os.path.dirname(os.path.dirname(os.path.abspath(make.__file__)))
    env = dict(os.environ, PYTHONPATH=f"{site}{os.pathsep}{root}", QT_QPA_PLATFORM="offscreen")
    script = site / "bin" / "Hello"
    commands = [[sys.executable, "-m", "hello"]] + ([[str(script)]] if script.exists() else [])
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env,
                                cwd=str(tmp_path))
        assert result.returncode == 7, result.stderr
        assert result.stdout.split("\n")[:2] == ["Hello from a subfolder module",
                                                  "and a data file"]


@pytest.mark.skipif(not os.environ.get("VP6_TEST_MAKE"),
                    reason="makes a real executable with PyInstaller (set VP6_TEST_MAKE=1)")
def test_a_real_executable(project):
    path = make.make(project.path, onefile=True, log=lambda line: None)
    env = {"HOME": os.path.expanduser("~"), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    result = subprocess.run([path], capture_output=True, text=True, timeout=120, env=env,
                            cwd=os.path.dirname(os.path.dirname(path)))
    assert result.returncode == 7, result.stderr
    assert result.stdout.split("\n")[:3] == ["Hello from a subfolder module", "and a data file",
                                             "csv says ['a', 'b']"]
