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
"""

from __future__ import annotations

import codecs

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
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
        P("WorkingDirectory", "str", "",
          description="Where the program runs (relative to the form's folder); empty: here"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.update(_process=None, _exit_code=-1, _decoders=None)
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

    # -- running it ---------------------------------------------------------------------------
    def Start(self, CommandLine=None) -> None:
        """Start the program: CommandLine (which it keeps), else the CommandLine
        property. Its output, exit and errors come as events."""
        if self.Running:
            raise RuntimeError(f"Process '{self.Name}' is already running a program")
        if CommandLine is not None:
            self._values["CommandLine"] = CommandLine if isinstance(CommandLine, str) \
                else " ".join(_quoted(p) for p in split_command(CommandLine))
        parts = split_command(CommandLine if CommandLine is not None else self.CommandLine)
        if not parts:
            raise ValueError(f"Process '{self.Name}': no CommandLine to run")
        process = QProcess(self._form._widget)  # (it goes with the form)
        folder = self._values.get("WorkingDirectory", "")
        if folder:
            process.setWorkingDirectory(resolve_path(self._form, folder))
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
