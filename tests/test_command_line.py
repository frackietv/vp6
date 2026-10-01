"""--help on the command line: the IDE (vp6), the runner (vp6-run) and VP6
programs (the project file, a made executable), which list the project's
ArgumentsHelp."""

import os
import subprocess
import sys

import pytest

import vp6
from vp6 import runner
from vp6.ide import mainwindow
from vp6.ide.dialogs import ProjectPropertiesDialog
from vp6.project import Project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_ide(capsys):
    with pytest.raises(SystemExit) as exit_:
        mainwindow.main(["vp6", "--help"])
    assert exit_.value.code == 0
    out = capsys.readouterr().out
    for text in ("usage: vp6", "PROJECT.vp6p", "--no-splash", "--help", vp6.__version__,
                 "VP6_NO_OUTPUT_CAPTURE", "VP6_SETTINGS_DIR", "vp6-run", "vp6-make"):
        assert text in out
    # (arguments it doesn't know are Qt's)
    assert mainwindow.parse_arguments(["vp6", "-style", "fusion", "--no-splash"]) == \
        (None, False)


def test_the_runner(capsys):
    with pytest.raises(SystemExit) as exit_:
        runner.main(["--help"])
    assert exit_.value.code == 0
    out = capsys.readouterr().out
    for text in ("usage: vp6-run", "PROJECT.vp6p", "ARGUMENTS", "VP6_NO_ERROR_DIALOG"):
        assert text in out
    with pytest.raises(SystemExit) as exit_:  # no project
        runner.main([])
    assert exit_.value.code == 2


def test_program_help(monkeypatch):
    project = Project(name="Calc", version="2.1.0", description="Adds up")
    monkeypatch.setattr(sys, "argv", ["/apps/Calc.vp6p"])  # (run by its project file)
    text = runner.program_help(project, "Calc.vp6p")
    assert text.startswith("Calc 2.1.0 - Adds up\n")
    assert "usage: Calc.vp6p [--help] [ARGUMENTS...]" in text and "Command()" in text
    assert "VP6_PYTHON" in text and text.endswith(f"Made with VP6 {vp6.__version__}.")
    project.product_name = "Calculator"
    project.arguments_help = "--sum A B    adds A and B\n--quiet      no window"
    monkeypatch.setattr(sys, "argv", ["/usr/bin/Calc"])  # (installed from a wheel, or made)
    text = runner.program_help(project, "Calc")
    assert "VP6_PYTHON" not in text
    assert text.startswith("Calculator 2.1.0 - Adds up\n")
    assert "arguments:\n  --sum A B    adds A and B\n  --quiet      no window\n" in text


def test_program_help_without_a_console(monkeypatch):
    # A windowed executable on Windows has no stdout: a message box instead
    shown = []
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr("vp6.dialogs.MsgBox", lambda *args: shown.append(args))
    runner.show_help("the help")
    assert shown == [("the help", vp6.vpInformation, "Help")]


def test_a_program_shows_its_help_and_ends(tmp_path):
    (tmp_path / "Module1.py").write_text("def Main():\n    print('started')\n")
    project = Project(name="Tool", type="console", startup="Sub Main", forms=[],
                      modules=["Module1.py"], description="Does things",
                      arguments_help="--fast    quickly")
    project.save(str(tmp_path / "Tool.vp6p"))
    env = dict(os.environ, PYTHONPATH=ROOT, QT_QPA_PLATFORM="offscreen")
    for command in ([sys.executable, str(tmp_path / "Tool.vp6p"), "x", "--help"],
                    [sys.executable, "-m", "vp6.runner", str(tmp_path / "Tool.vp6p"), "--help"]):
        out = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert out.stdout.startswith("Tool 1.0.0 - Does things\n")
        assert "--fast    quickly" in out.stdout and "started" not in out.stdout
    out = subprocess.run([sys.executable, str(tmp_path / "Tool.vp6p"), "--fast"], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "started"  # (other arguments are the program's)


def test_arguments_help_in_the_ide(qapp, tmp_path):
    project = Project(name="P", arguments_help="--a    one")
    path = str(tmp_path / "P.vp6p")
    project.save(path)
    assert Project.load(path).arguments_help == "--a    one"
    dialog = ProjectPropertiesDialog(project, ["Form1"])
    assert dialog.arguments_help.toPlainText() == "--a    one"
    dialog.arguments_help.setPlainText("--a    one\n--b    two\n")
    dialog.apply(project)
    assert project.arguments_help == "--a    one\n--b    two"
