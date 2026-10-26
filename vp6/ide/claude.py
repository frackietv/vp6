"""Claude in the IDE: Claude Code (the ``claude`` command) does the work.

Claude Code keeps its own login (in the system's keychain or its config
folder), so one login lasts across projects, IDE sessions and restarts. It
keeps each conversation as a JSON-lines transcript in
``<config>/projects/<the folder, every other character a dash>/<id>.jsonl``;
the IDE lists those for the project's folder and resumes them.

A chat runs ``claude -p`` with JSON lines both ways (``stream-json``): the
user's messages go to its standard input, its messages come back one per
line, and so do its questions about using a tool (``--permission-prompt-tool
stdio``: a ``control_request`` answered with a ``control_response``).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .logic.claude import (_PLACES, CLAUDE_ENV, COMMAND_KEY, MODE_KEY,  # noqa: F401
                           PERMISSION_MODES, TITLES_KEY, ClaudeProtocol, SessionInfo, _cache,
                           config_dir, default_mode, delete_session, describe_time, find_claude,
                           list_sessions, load_transcript, message_text, parse_auth_status,
                           project_key, rename_session, runnable, search_path, session_title,
                           sessions_folder, shell_quote)
from .theme import ide_settings  # noqa: F401 - (the settings the shared logic uses)

_runnable = runnable  # (its old name)


def environment(command: str) -> QProcessEnvironment:
    """The IDE's environment, with the command's folder (and Homebrew's) on the
    PATH: an npm-installed claude runs under ``env node``."""
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PATH", search_path(command, env.value("PATH", "")))
    return env


# -- login ----------------------------------------------------------------------------------

class AuthStatus(QObject):
    """``claude auth status``, asked without waiting for it: ``checked(logged
    in, text)`` when it answers."""

    checked = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process: QProcess | None = None

    def check(self, command: str) -> None:
        if self.process is not None:
            return  # (already asking)
        process = self.process = QProcess(self)
        process.setProcessEnvironment(environment(command))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        process.start(command, ["auth", "status"])

    def cancel(self) -> None:
        """Stop asking (the IDE closing)."""
        process, self.process = self.process, None
        if process is not None:
            process.finished.disconnect(self._finished)
            process.kill()
            process.waitForFinished(2000)
            process.deleteLater()

    def _finished(self, code, _status=None):
        process, self.process = self.process, None
        if process is None:
            return
        output = bytes(process.readAll()).decode("utf-8", "replace")
        process.deleteLater()
        self.checked.emit(*parse_auth_status(code, output))

    def _error(self, error):
        if error == QProcess.FailedToStart and self.process is not None:
            process, self.process = self.process, None
            process.deleteLater()
            self.checked.emit(False, "Claude Code couldn't be started")


def log_out(command: str) -> bool:
    """``claude auth logout`` (waited for)."""
    process = QProcess()
    process.setProcessEnvironment(environment(command))
    process.start(command, ["auth", "logout"])
    return process.waitForFinished(15000) and process.exitCode() == 0



# -- a chat ---------------------------------------------------------------------------------

class ClaudeChat(QObject):
    """A conversation with Claude Code in ``folder``: ``claude -p`` started for
    the first message (resuming ``session_id``, if any) and kept running for
    the next ones (its messages: ``logic.claude.ClaudeProtocol``)."""

    message = Signal(dict)  # each of Claude Code's messages (system, assistant, user, result)
    sessionChanged = Signal(str)  # the session's id, once Claude Code gives it
    busyChanged = Signal(bool)  # working on a message, or done
    permissionRequested = Signal(str, str, dict)  # request id, tool name, its input
    failed = Signal(str)  # it couldn't be started, or ended with an error

    def __init__(self, folder: str, session_id: str | None = None, command: str | None = None,
                 mode: str = "default", parent=None):
        super().__init__(parent)
        self.folder = folder
        self.command = command
        self.protocol = ClaudeProtocol(self._write_line, session_id, mode)
        self.protocol.message.connect(self.message.emit)
        self.protocol.sessionChanged.connect(self.sessionChanged.emit)
        self.protocol.permissionRequested.connect(self.permissionRequested.emit)
        self.protocol.result.connect(self._answered)
        self.process: QProcess | None = None
        self.busy = False
        self._errors = b""
        self._stopping = False  # (stopped or ended: its end isn't a failure)
        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.setInterval(3000)
        self._stop_timer.timeout.connect(self._kill)

    # (the protocol's state, as the chat's)
    session_id = property(lambda self: self.protocol.session_id,
                          lambda self, value: setattr(self.protocol, "session_id", value))
    mode = property(lambda self: self.protocol.mode,
                    lambda self, value: setattr(self.protocol, "mode", value))
    allowed = property(lambda self: self.protocol.allowed)

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def arguments(self) -> list[str]:
        return self.protocol.arguments()

    def send(self, text: str) -> bool:
        """Send the user's message (starting Claude Code if it isn't running)."""
        if not self.running and not self._start():
            return False
        self.protocol.send(text)
        self._set_busy(True)
        return True

    def set_mode(self, mode: str) -> None:
        """A new permission mode: from the next message on (Claude Code is
        started again with it, resuming the session)."""
        if mode != self.mode:
            self.mode = mode
            if self.running and not self.busy:
                self.end()

    def answer(self, request_id: str, allow: bool, tool_input: dict | None = None,
               always: str | None = None) -> None:
        """Answer a question about using a tool (``always``: that tool's name, to
        allow it from now on without asking)."""
        self.protocol.answer(request_id, allow, tool_input, always)

    def stop(self) -> None:
        """Stop what Claude is doing (asked; ended if it doesn't within 3 s)."""
        if not self.running or not self.busy:
            return
        self._stopping = True
        self.protocol.interrupt()
        self._stop_timer.start()

    def end(self) -> None:
        """End Claude Code (the session can be resumed), and wait for it."""
        process = self.process
        if process is None:
            return
        self._stop_timer.stop()
        self._stopping = True
        if process.state() != QProcess.NotRunning:
            process.closeWriteChannel()
            if not process.waitForFinished(1500):
                process.kill()
                process.waitForFinished(3000)
        self._finished_process(process)

    # -- the process ------------------------------------------------------------------------------
    def _start(self) -> bool:
        command = self.command or find_claude()
        if not command:
            self.failed.emit("Claude Code isn't installed (the claude command wasn't found).")
            return False
        self.command = command
        process = self.process = QProcess(self)
        process.setWorkingDirectory(self.folder)
        process.setProcessEnvironment(environment(command))
        process.readyReadStandardOutput.connect(self._read)
        process.readyReadStandardError.connect(self._read_errors)
        process.finished.connect(self._on_finished)  # (bound: gone with the chat)
        self.protocol.lines.clear()
        self._errors = b""
        self._stopping = False
        process.start(command, self.arguments())
        if not process.waitForStarted(10000):
            self.failed.emit(f"Claude Code couldn't be started: {process.errorString()}")
            self.process = None
            process.deleteLater()
            return False
        return True

    def _write_line(self, data: bytes) -> None:
        if self.running:
            self.process.write(data)

    def _read(self) -> None:
        if self.process is not None:
            self.protocol.feed(bytes(self.process.readAllStandardOutput()))

    def _read_errors(self) -> None:
        if self.process is not None:
            self._errors += bytes(self.process.readAllStandardError())

    def _answered(self) -> None:
        self._stop_timer.stop()
        self._stopping = False
        self._set_busy(False)

    def _kill(self) -> None:
        if self.running and self.busy:
            self.process.kill()

    def _on_finished(self, *_):
        if self.process is not None and self.sender() is self.process:
            self._finished_process(self.process)

    def _finished_process(self, process: QProcess) -> None:
        if process is not self.process:
            return
        self._read()
        self._read_errors()
        self.process = None
        errors = self._errors.decode("utf-8", "replace").strip()
        code = process.exitCode()
        process.deleteLater()
        was_busy = self.busy
        self._set_busy(False)
        if was_busy and (code or errors) and not self._stopping:
            self.failed.emit(errors or f"Claude Code ended (exit code {code}).")
        self._stop_timer.stop()
        self._stopping = False

    def _set_busy(self, busy: bool) -> None:
        if busy != self.busy:
            self.busy = busy
            self.busyChanged.emit(busy)
