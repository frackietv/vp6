"""Running other programs: the Process control (Start, its Output, ErrorOutput,
Exited and Error events, Write and WriteLine to its input, CloseInput, Kill,
Terminate, WaitForExit, Running, ExitCode, ProcessID, WorkingDirectory, ended
with its form) and VB's Shell; in the IDE (the Toolbox, the designer)."""

import os
import sys

import pytest

import vp6
from conftest import wait_for
from vp6 import Form, Process, Shell, formfile
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.process import split_command

ECHO = ("import os, sys\n"
        "print('cwd', os.path.basename(os.getcwd()), flush=True)\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if line == 'quit':\n"
        "        sys.exit(5)\n"
        "    print(line.upper(), flush=True)\n"
        "    print('err ' + line, file=sys.stderr, flush=True)\n"
        "print('input closed', flush=True)\n")


class Runner(Form):
    def InitializeComponent(self):
        self.prc = Process(self)
        self.log = []

    def prc_Output(self, Text):
        self.log.append(("out", Text))

    def prc_ErrorOutput(self, Text):
        self.log.append(("err", Text))

    def prc_Exited(self, ExitCode):
        self.log.append(("exit", ExitCode))

    def prc_Error(self, Description):
        self.log.append(("error", Description))


@pytest.fixture
def form(qapp):
    form = Runner()
    form.Show()
    yield form
    form.Unload()


def text(form, kind="out"):
    return "".join(t for k, t in form.log if k == kind)


def test_running_and_talking(form, tmp_path):
    prc = form.prc
    assert not prc.Running and prc.ExitCode == -1 and prc.ProcessID == 0
    (tmp_path / "here").mkdir()
    prc.WorkingDirectory = str(tmp_path / "here")
    prc.Start([sys.executable, "-u", "-c", ECHO])
    assert prc.Running and prc.ProcessID > 0 and sys.executable in prc.CommandLine
    wait_for(lambda: "cwd here" in text(form))  # (its WorkingDirectory)
    prc.WriteLine("héllo wörld")  # (UTF-8 both ways)
    wait_for(lambda: "HÉLLO WÖRLD" in text(form) and "err héllo wörld" in text(form, "err"))
    with pytest.raises(RuntimeError, match="already running"):
        prc.Start([sys.executable, "-c", "pass"])
    prc.Write("qu")
    prc.Write("it\n")
    assert prc.WaitForExit(10000)
    wait_for(lambda: ("exit", 5) in form.log)
    assert prc.ExitCode == 5 and not prc.Running and prc.ProcessID == 0
    with pytest.raises(RuntimeError, match="isn't running"):
        prc.Write("x")


def test_close_input_kill_and_terminate(form):
    prc = form.prc
    prc.Start([sys.executable, "-u", "-c", ECHO])
    prc.CloseInput()  # its input ends: it goes on to its end
    wait_for(lambda: "input closed" in text(form))
    wait_for(lambda: ("exit", 0) in form.log)
    prc.Start([sys.executable, "-c", "import time; time.sleep(60)"])
    wait_for(lambda: prc.ProcessID > 0)
    prc.Kill()
    wait_for(lambda: form.log[-1] == ("exit", -1))  # (killed)
    prc.Start([sys.executable, "-c", "import time; time.sleep(60)"])
    wait_for(lambda: prc.ProcessID > 0)
    prc.Terminate()
    assert prc.WaitForExit(10000)
    assert not prc.Running
    assert prc.WaitForExit() is True  # (not running: at once)


def test_a_command_line_and_errors(form):
    prc = form.prc
    prc.CommandLine = f'"{sys.executable}" -c "print(12 * 3)"'  # (quotes group words)
    prc.Start()
    wait_for(lambda: ("exit", 0) in form.log)
    assert text(form).strip() == "36"
    prc.Start("no-such-program-at-all --x")
    wait_for(lambda: form.log[-1][0] == "error")
    assert "couldn't be started" in form.log[-1][1] and not prc.Running
    prc.CommandLine = ""
    with pytest.raises(ValueError, match="no CommandLine"):
        prc.Start()
    assert split_command('a "b c" d') == ["a", "b c", "d"]
    assert split_command(["x y", 3]) == ["x y", "3"]


def test_ended_with_its_form(qapp):
    form = Runner()
    form.Show()
    form.prc.Start([sys.executable, "-c", "import time; time.sleep(60)"])
    wait_for(lambda: form.prc.ProcessID > 0)
    form.Unload()
    assert not form.prc.Running


def test_shell(qapp, tmp_path):
    marker = tmp_path / "ran.txt"
    pid = Shell([sys.executable, "-c", f"open({str(marker)!r}, 'w').write('yes')"],
                vp6.vpNormalFocus)
    assert pid > 0
    wait_for(lambda: marker.exists() and marker.read_text() == "yes", timeout_ms=10000)
    with pytest.raises(FileNotFoundError):
        Shell("no-such-program-at-all")
    with pytest.raises(ValueError):
        Shell("")


def test_in_the_ide(qapp, tmp_path):
    from vp6.ide import icons
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument
    from vp6.ide.panels import Toolbox

    assert "Process" in Toolbox().buttons and CONTROL_TYPES["Process"] is Process
    assert list(CONTROL_TYPES)[-1] == "Menu" and not icons.icon("Process").isNull()
    assert Process.DefaultEvent == "Output" and EVENT_ARGS["Exited"] == "ExitCode"
    assert "Width" not in Process._specs  # (an icon in the designer, like a Timer)
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    name = designer.create_control("Process", None, None)
    assert name == "Process1"
    assert designer.set_property("CommandLine", "python3 -V") is None
    assert "self.Process1 = Process(self, Left=" in designer.document.text
    assert "CommandLine='python3 -V'" in designer.document.text
    designer.close()
    assert os.path.exists(str(path))
