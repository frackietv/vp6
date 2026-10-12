"""Running other programs: the ``Process`` control and VB's ``Shell``.

A ``Process`` (invisible at run time, like a Timer) runs a program and talks
with it while the form keeps working::

    self.prcBuild.Start('python3 -u build.py --all')   # or a list: [program, arg...]

    def prcBuild_Output(self, Text):                    # what it prints, as it prints it
        self.txtLog.SelText = Text

    def prcBuild_Exited(self, ExitCode):
        self.lblStatus.Caption = f"Done ({ExitCode})"

* ``Start(CommandLine)`` starts it (the CommandLine property when left out):
  the program and its arguments, split as a command line (double quotes
  group words: ``"C:\\Program Files\\x.exe" "a b"``), or a list of them.
  ``WorkingDirectory`` is where it runs (relative to the form's folder).
  ``Arguments`` (a list) come after the command line's, each one as it is:
  paths with spaces or quotes need no quoting there.
* ``Environment``: the variables the program gets, the system's to start
  with: ``Environment("PATH")`` reads one, ``Environment["LANG"] = "C"`` (or
  ``Add``) sets one, ``Remove`` drops one, ``Reset()`` goes back to the
  system's; what it holds when ``Start`` runs is what the program gets.
* Events: ``Output(Text)`` and ``ErrorOutput(Text)``, what it writes to its
  standard output and error, as it comes (decoded as UTF-8); ``Exited
  (ExitCode)`` when it ends (-1 when it was killed or crashed); ``Error
  (Description)`` when it can't be started.
* ``Write(Text)`` / ``WriteLine(Text)`` send it input (its standard input),
  ``CloseInput()`` ends that; ``Terminate()`` asks it to end, ``Kill()`` ends
  it; ``WaitForExit(Timeout)`` waits (ms; -1: as long as it takes).
  ``Running``, ``ExitCode`` and ``ProcessID`` tell how it is.
* A Process still running when its form unloads is killed.

``Shell(PathName, WindowStyle)`` is VB's: it starts a program on its own (not
followed: no events) and returns its process ID; WindowStyle is accepted for
VB's sake (programs open their windows themselves).

``ShellExecute(File, Operation)`` opens a URL, document or folder with what
the system uses for it (VB programs called Windows' ShellExecute): a web
page in the browser, a document in its program, a folder in Finder or
Explorer; Operation ``"show"`` shows a file in its folder instead.
"""

from __future__ import annotations

import codecs
import os
import re
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ._props import P
from .controls import CONTROL_TYPES, EVENT_ARGS, Control, resolve_path

EVENT_ARGS.update({"Output": "Text", "ErrorOutput": "Text", "Exited": "ExitCode",
                   "Error": "Description"})


def split_command(command) -> list[str]:
    """A command line as [program, arguments...] (a list: as it is)."""
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command]
    return QProcess.splitCommand(str(command or ""))


class _Environment:
    """A Process's Environment: the variables its program gets, by name
    (the system's to start with). ``Environment("HOME")`` or ``["HOME"]``
    reads one ("" when it isn't set), ``Environment["LANG"] = "C"`` sets one,
    ``del Environment["X"]`` or ``Remove("X")`` drops it; ``in``, ``len`` and
    iterating (the names) work as on a dict."""

    def __init__(self):
        self._vars = dict(os.environ)

    def __call__(self, Name) -> str:
        return self[Name]

    def __getitem__(self, name) -> str:
        return self._vars.get(str(name), "")

    def __setitem__(self, name, value) -> None:
        name = str(name)
        if not name or "=" in name:
            raise ValueError(f"Not an environment variable's name: {name!r}")
        self._vars[name] = str(value)

    def __delitem__(self, name) -> None:
        self._vars.pop(str(name), None)

    def __contains__(self, name) -> bool:
        return str(name) in self._vars

    def __iter__(self):
        return iter(sorted(self._vars))

    def __len__(self) -> int:
        return len(self._vars)

    def __repr__(self):
        return f"<Environment: {len(self._vars)} variables>"

    @property
    def Count(self) -> int:
        return len(self._vars)

    def Item(self, Name) -> str:
        return self[Name]

    def Add(self, Name, Value) -> None:
        """Set a variable (a new one, or a new value)."""
        self[Name] = Value

    def Remove(self, Name) -> None:
        """Drop a variable (the program doesn't get it at all)."""
        del self[Name]

    def Clear(self) -> None:
        """No variables at all (add the ones the program needs)."""
        self._vars.clear()

    def Reset(self) -> None:
        """The system's variables again, as at first."""
        self._vars = dict(os.environ)

    def _qt(self) -> QProcessEnvironment:
        environment = QProcessEnvironment()
        for name, value in self._vars.items():
            environment.insert(name, value)
        return environment


class Process(Control):
    """Runs a program, its output and exit as events (the module's
    documentation)."""

    TypeName = "Process"
    DefaultEvent = "Output"
    DefaultSize = (32, 32)
    Events = ("Output", "ErrorOutput", "Exited", "Error")
    Properties = (
        P("Left", "int", 0, always=True, description="Position in the designer only"),
        P("Top", "int", 0, always=True, description="Position in the designer only"),
        P("CommandLine", "str", "",
          description="The program and its arguments, as a command line (double quotes "
                      "group words): what Start runs"),
        P("Arguments", "list", [],
          description="Arguments after the CommandLine's, one per line, each passed as it is "
                      "(spaces and quotes need no quoting)"),
        P("WorkingDirectory", "str", "",
          description="Where the program runs (relative to the form's folder); empty: here"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.update(_process=None, _exit_code=-1, _decoders=None,
                             _environment=_Environment())
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        if self._design_mode:
            return _process_design_widget(parent)
        return None

    def _read_Width(self):
        return 32

    def _read_Height(self):
        return 32

    # -- what it is ------------------------------------------------------------------------------
    @property
    def Running(self) -> bool:
        """Whether the program is running (or starting)."""
        process = self._process
        return process is not None and process.state() != QProcess.NotRunning

    @property
    def ExitCode(self) -> int:
        """The program's exit code once it has ended (-1 before, or when it was
        killed or crashed)."""
        return self._exit_code

    @property
    def ProcessID(self) -> int:
        """The program's process ID while it runs, else 0."""
        return int(self._process.processId()) if self.Running else 0

    @property
    def Environment(self) -> _Environment:
        """The variables the program gets (the system's to start with); changes
        count from the next Start."""
        return self._environment

    # -- running it ---------------------------------------------------------------------------
    def Start(self, CommandLine=None) -> None:
        """Start the program: CommandLine (which it keeps), else the CommandLine
        property, then the Arguments, each as it is. Its output, exit and errors
        come as events."""
        if self.Running:
            raise RuntimeError(f"Process '{self.Name}' is already running a program")
        if CommandLine is not None:
            self._values["CommandLine"] = CommandLine if isinstance(CommandLine, str) \
                else " ".join(_quoted(p) for p in split_command(CommandLine))
        parts = split_command(CommandLine if CommandLine is not None else self.CommandLine)
        parts += [str(argument) for argument in self._values.get("Arguments") or ()]
        if not parts:
            raise ValueError(f"Process '{self.Name}': no CommandLine to run")
        process = QProcess(self._form._widget)  # (it goes with the form)
        folder = self._values.get("WorkingDirectory", "")
        if folder:
            process.setWorkingDirectory(resolve_path(self._form, folder))
        process.setProcessEnvironment(self._environment._qt())
        process.setProgram(parts[0])
        process.setArguments(parts[1:])
        process.readyReadStandardOutput.connect(lambda p=process: self._read(p, False))
        process.readyReadStandardError.connect(lambda p=process: self._read(p, True))
        process.finished.connect(lambda code, status, p=process: self._finished(p, code, status))
        process.errorOccurred.connect(lambda error, p=process: self._error(p, error))
        decoder = codecs.getincrementaldecoder("utf-8")
        self.__dict__.update(_process=process, _exit_code=-1,
                             _decoders=(decoder(errors="replace"), decoder(errors="replace")))
        process.start()

    def _read(self, process, error: bool) -> None:
        if process is not self._process:
            return
        data = process.readAllStandardError() if error else process.readAllStandardOutput()
        text = self._decoders[error].decode(bytes(data))
        if text:
            self._fire("ErrorOutput" if error else "Output", text)

    def _finished(self, process, code: int, status) -> None:
        if process is not self._process:
            return
        for error in (False, True):  # (what is left, then the rest of a character)
            self._read(process, error)
            rest = self._decoders[error].decode(b"", final=True)
            if rest:
                self._fire("ErrorOutput" if error else "Output", rest)
        self.__dict__["_exit_code"] = int(code) if status == QProcess.NormalExit else -1
        self._fire("Exited", self._exit_code)

    def _error(self, process, error) -> None:
        if process is not self._process or error != QProcess.FailedToStart:
            return  # (a crash ends with Exited(-1))
        self._fire("Error", f"The program couldn't be started: {process.errorString()}")

    def Write(self, Text) -> None:
        """Send text to the program's standard input."""
        if not self.Running:
            raise RuntimeError(f"Process '{self.Name}' isn't running a program")
        self._process.write(str(Text).encode("utf-8"))

    def WriteLine(self, Text="") -> None:
        """Send a line (the text and a new line) to its standard input."""
        self.Write(f"{Text}\n")

    def CloseInput(self) -> None:
        """End its standard input (a program reading it to the end then goes on)."""
        if self._process is not None:
            self._process.closeWriteChannel()

    def Terminate(self) -> None:
        """Ask the program to end (it may tidy up first)."""
        if self.Running:
            self._process.terminate()

    def Kill(self) -> None:
        """End the program at once."""
        if self.Running:
            self._process.kill()

    def WaitForExit(self, Timeout: int = -1) -> bool:
        """Wait for the program to end (its events still fire): Timeout in
        milliseconds, -1 as long as it takes. True if it has ended."""
        if not self.Running:
            return True
        return bool(self._process.waitForFinished(int(Timeout)))

    def _form_unloaded(self) -> None:
        """Its form unloads: a program still running is ended."""
        if self.Running:
            self._process.kill()
            self._process.waitForFinished(2000)


def _quoted(part: str) -> str:
    return f'"{part}"' if (" " in part or not part) and '"' not in part else part


def _process_design_widget(parent: QWidget) -> QLabel:
    """The icon the designer shows for a Process: a console window."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.2))
    painter.setBrush(QColor("#2b2b2b"))
    painter.drawRect(3, 5, 20, 16)
    painter.setPen(QPen(QColor("#7CFC00"), 1.6))
    painter.drawLine(6, 10, 9, 13)
    painter.drawLine(9, 13, 6, 16)
    painter.drawLine(11, 16, 16, 16)
    painter.end()
    label = QLabel(parent)
    label.setFixedSize(32, 32)
    label.setAlignment(Qt.AlignCenter)
    label.setFrameStyle(QFrame.Panel | QFrame.Raised)
    label.setPixmap(pixmap)
    return label


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["Process"] = Process
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")


def Shell(PathName, WindowStyle: int = 1) -> int:
    """Start a program on its own (VB's Shell): a command line (or a list), not
    followed; returns its process ID. Raises FileNotFoundError when it can't
    be started. WindowStyle (vpNormalFocus...) is accepted for VB's sake."""
    parts = split_command(PathName)
    if not parts:
        raise ValueError("Shell: no program to start")
    started, pid = QProcess.startDetached(parts[0], parts[1:])
    if not started:
        raise FileNotFoundError(f"File not found: {parts[0]}")
    return int(pid)


# How ShellExecute opens a URL and shows a file in its folder (tests replace them)
_open_url = QDesktopServices.openUrl
_start_detached = QProcess.startDetached


def _as_url(target: str) -> QUrl:
    """A URL as it is (http:, mailto:...); anything else a file or folder."""
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]+:", target) and not re.match(r"[A-Za-z]:[\\/]",
                                                                         target):
        return QUrl(target)
    return QUrl.fromLocalFile(os.path.abspath(os.path.expanduser(target)))


def ShellExecute(File, Operation: str = "open") -> bool:
    """Open a URL, document or folder with what the system uses for it (VB's
    ShellExecute): a web page or mailto: in the browser or mail program, a
    document in its program, a folder in Finder or Explorer. Operation
    "show" shows a file selected in its folder (Finder, Explorer) instead.
    Returns whether it could be opened."""
    target = str(File)
    if not target:
        raise ValueError("ShellExecute: nothing to open")
    operation = str(Operation or "open").lower()
    if operation not in ("open", "show", "explore"):
        raise ValueError(f"ShellExecute: Operation is \"open\" or \"show\", not {Operation!r}")
    url = _as_url(target)
    if url.isLocalFile() and not os.path.exists(url.toLocalFile()):
        return False
    if operation == "open" or not url.isLocalFile():
        return bool(_open_url(url))
    path = url.toLocalFile()
    if os.path.isdir(path) or operation == "explore":
        return bool(_open_url(QUrl.fromLocalFile(path if os.path.isdir(path) else
                                                 os.path.dirname(path))))
    if sys.platform == "darwin":
        return bool(_start_detached("open", ["-R", path])[0])
    if sys.platform == "win32":
        return bool(_start_detached("explorer", ["/select," + os.path.normpath(path)])[0])
    return bool(_open_url(QUrl.fromLocalFile(os.path.dirname(path))))
