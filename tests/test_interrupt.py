"""Ctrl+C (SIGINT) in the terminal ends a VP6 program like closing its forms.

Each test runs a real program in its own process and sends it SIGINT, which
is what pressing Ctrl+C in the terminal does.
"""

import os
import signal
import subprocess
import sys
import time

import pytest

from vp6.ide.mainwindow import create_project

pytestmark = pytest.mark.skipif(os.name == "nt", reason="SIGINT from another process is POSIX")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(tmp_path):
    return dict(os.environ, QT_QPA_PLATFORM="offscreen", VP6_NO_ERROR_DIALOG="1",
                PYTHONPATH=ROOT, MARKER=str(tmp_path / "marker.txt"))


def _project_with(tmp_path, form_code: str) -> str:
    """A new Standard EXE whose Form1 has the given handlers. The helper
    `mark(text)` appends a line to the marker file the test watches."""
    path = create_project(str(tmp_path), "Demo", "exe")
    form1 = tmp_path / "Demo" / "Form1.py"
    source = form1.read_text().replace("from vp6 import *\n", """from vp6 import *
import os


def mark(text):
    with open(os.environ["MARKER"], "a") as f:
        f.write(text + "\\n")
""", 1)
    source = source.replace("    def Form_Load(self):\n        pass\n", form_code)
    form1.write_text(source)
    return path


def _marks(tmp_path) -> list[str]:
    marker = tmp_path / "marker.txt"
    return marker.read_text().splitlines() if marker.exists() else []


def _wait_for_mark(tmp_path, process, text, timeout=20):
    deadline = time.monotonic() + timeout
    while text not in _marks(tmp_path):
        assert process.poll() is None, process.communicate()[1]
        assert time.monotonic() < deadline, f"no {text!r} mark: {_marks(tmp_path)}"
        time.sleep(0.05)
    time.sleep(0.3)  # let the event loop settle


LOAD_UNLOAD = """    def Form_Load(self):
        mark("loaded")

    def Form_Unload(self):
        mark("unloaded")
"""


def test_ctrl_c_closes_the_forms_of_a_project(tmp_path):
    path = _project_with(tmp_path, LOAD_UNLOAD)
    process = subprocess.Popen([sys.executable, path], env=_env(tmp_path),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_for_mark(tmp_path, process, "loaded")
    process.send_signal(signal.SIGINT)
    _out, err = process.communicate(timeout=20)
    assert process.returncode == 0, err
    assert "Traceback" not in err and "KeyboardInterrupt" not in err
    assert _marks(tmp_path) == ["loaded", "unloaded"]  # Form_Unload ran, like a close


def test_ctrl_c_in_a_form_run_on_its_own(tmp_path):
    _project_with(tmp_path, LOAD_UNLOAD)
    process = subprocess.Popen([sys.executable, str(tmp_path / "Demo" / "Form1.py")],
                               cwd=str(tmp_path / "Demo"), env=_env(tmp_path),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_for_mark(tmp_path, process, "loaded")
    process.send_signal(signal.SIGINT)
    _out, err = process.communicate(timeout=20)
    assert process.returncode == 0, err
    assert _marks(tmp_path) == ["loaded", "unloaded"]


def test_form_unload_can_cancel_ctrl_c(tmp_path):
    path = _project_with(tmp_path, """    def Form_Load(self):
        self.asked = 0
        mark("loaded")

    def Form_Unload(self):
        self.asked += 1
        mark(f"unload {self.asked}")
        return self.asked == 1  # cancel the first time, like answering No
""")
    process = subprocess.Popen([sys.executable, path], env=_env(tmp_path),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_for_mark(tmp_path, process, "loaded")
    process.send_signal(signal.SIGINT)
    _wait_for_mark(tmp_path, process, "unload 1")
    assert process.poll() is None  # still running: Form_Unload cancelled
    process.send_signal(signal.SIGINT)
    _out, err = process.communicate(timeout=20)
    assert process.returncode == 0, err
    assert _marks(tmp_path) == ["loaded", "unload 1", "unload 2"]


def test_ctrl_c_closes_an_open_message_box_first(tmp_path):
    path = _project_with(tmp_path, """    def Form_Load(self):
        self.tmrAsk = Timer(self, Interval=100)

    def tmrAsk_Timer(self):
        self.tmrAsk.Enabled = False
        mark("asking")
        answer = MsgBox("Still there?", vpYesNo)  # modal: blocks until closed
        mark(f"answer {answer}")

    def Form_Unload(self):
        mark("unloaded")
""")
    process = subprocess.Popen([sys.executable, path], env=_env(tmp_path),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_for_mark(tmp_path, process, "asking")
    process.send_signal(signal.SIGINT)
    _out, err = process.communicate(timeout=20)
    assert process.returncode == 0, err
    marks = _marks(tmp_path)
    assert marks[0] == "asking" and marks[-1] == "unloaded"
    assert marks[1].startswith("answer ")  # the box was closed, then the form


def test_ctrl_c_ends_a_console_program_quietly(tmp_path):
    path = create_project(str(tmp_path), "Hello", "console")  # Main() waits at input()
    # Start it with SIGINT at its default, like a terminal does. If pytest itself
    # runs with SIGINT ignored (e.g. as a background job), the child would inherit
    # that and Python wouldn't raise KeyboardInterrupt at all.
    process = subprocess.Popen([sys.executable, path], env=_env(tmp_path),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    os.set_blocking(process.stdout.fileno(), False)
    shown, deadline = b"", time.monotonic() + 20
    while b"What is your name?" not in shown:  # really waiting at the prompt
        assert process.poll() is None and time.monotonic() < deadline, shown
        shown += process.stdout.read() or b""
        time.sleep(0.05)
    process.send_signal(signal.SIGINT)
    # Keep stdin open until it has exited: closing it could let input() see
    # end-of-input (EOFError) before Python handles the signal
    assert process.wait(timeout=20) == 130
    process.stdin.close()
    err = process.stderr.read().decode()
    assert "Traceback" not in err and "KeyboardInterrupt" not in err


def test_programs_keep_the_default_ctrl_c_when_they_do_not_create_the_app(qapp):
    """ensure_app() only installs its handler when it creates the application,
    so the IDE and the test suite keep their own Ctrl+C behavior."""
    before = signal.getsignal(signal.SIGINT)
    from vp6 import Form

    form = Form()  # uses the existing QApplication
    form.Unload()
    assert signal.getsignal(signal.SIGINT) is before
