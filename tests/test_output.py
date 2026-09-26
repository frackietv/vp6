"""The Output window: the IDE's own stdout/stderr, captured at the file
descriptor level so library output (Qt, C code) is included."""

import os
import subprocess
import sys

from conftest import wait_for

from vp6.ide.outputcapture import OutputCapture
from vp6.ide.panels import OutputWindow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_capture_tees_replays_and_restores(qapp, tmp_path):
    terminal = tmp_path / "terminal.txt"  # stands in for the terminal
    fd = os.open(terminal, os.O_WRONLY | os.O_CREAT)
    capture = OutputCapture(((fd, "err"),))
    encoded = "early é\n".encode()
    os.write(fd, encoded[:7])  # splits the two-byte 'é' across writes
    os.write(fd, encoded[7:])
    received = []
    capture.attach(lambda text, kind: received.append((text, kind)))  # replays "early"
    os.write(fd, b"late\n")
    wait_for(lambda: "late" in "".join(text for text, _ in received))
    capture.stop()
    assert "".join(text for text, _ in received) == "early é\nlate\n"
    assert {kind for _, kind in received} == {"err"}
    assert terminal.read_text() == "early é\nlate\n"  # still reached the "terminal"
    os.write(fd, b"after\n")  # restored: goes straight to the file
    os.close(fd)
    assert terminal.read_text().endswith("after\n")
    assert "after" not in "".join(text for text, _ in received)


def test_capture_includes_python_c_level_and_qt_output(tmp_path):
    """Real descriptors 1 and 2, in a separate process so pytest's own
    capturing isn't disturbed."""
    result_file = tmp_path / "captured.txt"
    script = f"""
import os, sys
from vp6.ide.outputcapture import OutputCapture
capture = OutputCapture()                     # before Qt, like the IDE's main()
from PySide6.QtCore import QCoreApplication, QDeadlineTimer, qWarning
app = QCoreApplication(sys.argv)
received = []
capture.attach(lambda text, kind: received.append((kind, text)))
print("python stdout")
os.write(2, b"c-level stderr\\n")                # like a C library
qWarning("qt warning")                         # Qt's own messages
deadline = QDeadlineTimer(5000)
while "qt warning" not in "".join(t for _, t in received) and not deadline.hasExpired():
    app.processEvents()
capture.stop()
open({str(result_file)!r}, "w").write(repr(received))
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=ROOT)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            timeout=60, env=env)
    assert result.returncode == 0, result.stderr
    received = eval(result_file.read_text())  # noqa: S307 - our own repr
    out = "".join(text for kind, text in received if kind == "out")
    err = "".join(text for kind, text in received if kind == "err")
    assert "python stdout" in out
    assert "c-level stderr" in err and "qt warning" in err
    # ...and it all still reached the process's real stdout/stderr (the terminal)
    assert "python stdout" in result.stdout
    assert "c-level stderr" in result.stderr and "qt warning" in result.stderr


def test_output_window_context_menu(qapp):
    window = OutputWindow()
    menu = window._context_menu()
    assert [a.text() for a in menu.actions()] == ["Select All", "Copy", "", "Clear"]
    assert not any(a.isEnabled() for a in menu.actions() if a.text())  # empty window
    window.append("hello\n")
    window.append("problem\n", "err")
    actions = {a.text(): a for a in window._context_menu().actions()}
    assert actions["Select All"].isEnabled() and actions["Clear"].isEnabled()
    assert not actions["Copy"].isEnabled()  # nothing selected yet
    actions["Select All"].trigger()
    assert window.output.textCursor().selectedText().replace("\u2029", "\n") == \
        "hello\nproblem\n"
    actions = {a.text(): a for a in window._context_menu().actions()}
    assert actions["Copy"].isEnabled()
    actions["Copy"].trigger()
    assert qapp.clipboard().text().startswith("hello")
    actions["Clear"].trigger()
    assert window.output.toPlainText() == ""


def test_ide_main_shows_its_output_in_the_output_window(tmp_path):
    """End to end: the real vp6.ide main() captures its stdout/stderr and the
    Output window shows it (the window's text is written to a file)."""
    result_file = tmp_path / "output_window.txt"
    script = f"""
import os, sys
from PySide6.QtCore import QTimer, qWarning
from PySide6.QtWidgets import QApplication
from vp6.ide import mainwindow

app = QApplication(sys.argv)

def exercise():
    window = next(w for w in app.topLevelWidgets() if isinstance(w, mainwindow.MainWindow))
    print("hello from the IDE")                  # Python stdout
    os.write(2, b"library message\\n")            # a library writing to fd 2
    qWarning("qt says hi")
    def dump():
        with open({str(result_file)!r}, "w") as f:
            f.write(window.output.output.toPlainText())
        window.close()
    QTimer.singleShot(500, dump)

QTimer.singleShot(1500, exercise)
sys.exit(mainwindow.main([sys.argv[0], {str(tmp_path / 'Demo' / 'Demo.vp6p')!r}]))
"""
    from vp6.ide.mainwindow import create_project
    create_project(str(tmp_path), "Demo", "exe")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=ROOT,
               VP6_SETTINGS_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            timeout=60, env=env)
    assert result.returncode == 0, result.stderr
    shown = result_file.read_text()
    for text in ("hello from the IDE", "library message", "qt says hi"):
        assert text in shown
        assert text in result.stdout + result.stderr  # and still in the terminal
