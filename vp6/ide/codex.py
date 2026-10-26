"""Codex in the IDE: OpenAI's Codex CLI (the ``codex`` command) does the work.

The IDE talks to ``codex app-server``: JSON-RPC, one message per line on its
standard input and output (``CodexServer``). One server serves the Codex
window (the login, the folder's sessions) and every chat; its notifications
name their thread, so each chat takes its own.

Codex keeps its own login (``auth.json`` in its folder, ``$CODEX_HOME`` or
``~/.codex``), so one login lasts across projects, IDE sessions and restarts.
It keeps each conversation (a *thread*) itself and lists them by folder; the
IDE lists, names, deletes and resumes them through the server, so sessions
started with ``codex`` in a terminal (or Codex's app) are listed too.

A chat (``CodexChat``) starts a thread for its first message (or resumes
one), starts a *turn* for each message and follows the turn's items (Codex's
messages, the commands it runs, the files it changes) until it completes.
Codex asks before running a command or changing files outside what the
chat's mode allows: a server request answered with a decision.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal

from .claude import environment
from .logic.codex import (_PLACES, _SANDBOX_MODES, _WRITE, CODEX_ENV,  # noqa: F401
                          COMMAND_KEY, MODE_KEY, MODES, SOURCE_KINDS, CodexChatCore, CodexSession,
                          JsonRpc, codex_home, default_mode, describe_account, find_codex,
                          initialize_params, last_line, list_params, mode_policies, session_of,
                          user_text)
from .theme import ide_settings  # noqa: F401 - (the settings the shared logic uses)


# -- the server -----------------------------------------------------------------------------

class CodexServer(QObject):
    """``codex app-server``, started when first asked something and kept
    running. ``request`` sends a request and calls back with its result (or
    an error's message); requests made before the server answered
    ``initialize`` wait for it (the messages: ``logic.codex.JsonRpc``)."""

    notification = Signal(str, dict)  # method, params
    serverRequest = Signal(object, str, dict)  # id, method, params: answer with respond()
    stopped = Signal(str)  # it ended (what it said, if anything)

    def __init__(self, command: str | None = None, parent=None):
        super().__init__(parent)
        self.command = command
        self.process: QProcess | None = None
        self.generation = 0  # (one more each time it starts: threads are loaded again)
        self.rpc = JsonRpc(self._write)
        self.rpc.notification.connect(self.notification.emit)
        self.rpc.serverRequest.connect(self.serverRequest.emit)
        self._errors = b""

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    @property
    def ready(self) -> bool:
        return self.rpc.ready

    def request(self, method: str, params: dict, callback=None, error=None) -> int | None:
        """Ask the server (starting it if need be). ``callback(result)`` when it
        answers, ``error(message)`` if it can't (or isn't there)."""
        if not self.running and not self._start(error):
            return None
        return self.rpc.request(method, params, callback, error)

    def respond(self, request_id, result: dict) -> None:
        """Answer one of the server's requests."""
        self.rpc.respond(request_id, result)

    def respond_error(self, request_id, message: str) -> None:
        self.rpc.respond_error(request_id, message)

    def end(self) -> None:
        """End the server, and wait for it (its threads can be resumed)."""
        process = self.process
        if process is None:
            return
        if process.state() != QProcess.NotRunning:
            process.closeWriteChannel()
            if not process.waitForFinished(1500):
                process.kill()
                process.waitForFinished(3000)
        self._finished_process(process)

    # -- the process ------------------------------------------------------------------------------
    def _start(self, error=None) -> bool:
        command = self.command or find_codex()
        if not command:
            if error is not None:
                error("Codex isn't installed (the codex command wasn't found).")
            return False
        process = self.process = QProcess(self)
        process.setProcessEnvironment(environment(command))
        process.readyReadStandardOutput.connect(self._read)
        process.readyReadStandardError.connect(self._read_errors)
        process.finished.connect(self._on_finished)  # (bound: gone with the server)
        self.rpc.reset()
        self._errors = b""
        process.start(command, ["app-server"])
        if not process.waitForStarted(10000):
            self.process = None
            process.deleteLater()
            if error is not None:
                error(f"Codex couldn't be started: {process.errorString()}")
            return False
        self.generation += 1
        self.request("initialize", initialize_params(), lambda _result: self.rpc.initialized(),
                     lambda message: None)
        return True

    def _write(self, data: bytes) -> None:
        if self.running:
            self.process.write(data)

    def _read(self) -> None:
        if self.process is not None:
            self.rpc.feed(bytes(self.process.readAllStandardOutput()))

    def _read_errors(self) -> None:
        if self.process is not None:
            self._errors = (self._errors + bytes(self.process.readAllStandardError()))[-8000:]

    def _on_finished(self, *_):
        if self.process is not None and self.sender() is self.process:
            self._finished_process(self.process)

    def _finished_process(self, process: QProcess) -> None:
        if process is not self.process:
            return
        self._read()
        self._read_errors()
        self.process = None
        process.deleteLater()
        message = last_line(self._errors.decode("utf-8", "replace").strip())
        self.rpc.fail_all(message)
        self.stopped.emit(message)


# -- a chat ---------------------------------------------------------------------------------

class CodexChat(QObject):
    """A conversation with Codex in ``folder``, through ``server``: a thread
    started for the first message (or ``session_id`` resumed by ``open``),
    a turn for each message (``logic.codex.CodexChatCore``)."""

    message = Signal(dict)  # the thread's notifications: {"method": ..., "params": ...}
    sessionChanged = Signal(str)  # the thread's id, once Codex gives it
    busyChanged = Signal(bool)  # working on a message, or done
    permissionRequested = Signal(str, str, dict)  # request id, what it wants to use, details
    failed = Signal(str)  # it couldn't be started, or a request failed
    resumed = Signal(dict)  # the resumed thread (its turns: what was said before)

    def __init__(self, server: CodexServer, folder: str, session_id: str | None = None,
                 mode: str = "auto", parent=None):
        super().__init__(parent)
        self.core = core = CodexChatCore(server, folder, session_id, mode)
        for name in ("message", "sessionChanged", "busyChanged", "permissionRequested",
                     "failed", "resumed"):
            getattr(core, name).connect(getattr(self, name).emit)
        server.notification.connect(self._notified)
        server.serverRequest.connect(self._asked)
        server.stopped.connect(self._server_stopped)

    def __getattr__(self, name):  # (the core's state and methods: session_id, busy, send...)
        core = self.__dict__.get("core")
        if core is None:
            raise AttributeError(name)
        return getattr(core, name)

    def __setattr__(self, name, value):
        if name in ("session_id", "mode", "model", "busy", "turn_id", "folder") and \
                "core" in self.__dict__:
            setattr(self.core, name, value)
        else:
            super().__setattr__(name, value)

    @property
    def running(self) -> bool:
        return self.core.running

    def _notified(self, method: str, params: dict) -> None:
        self.core.notified(method, params)

    def _asked(self, server_id, method: str, params: dict) -> None:
        self.core.asked(server_id, method, params)

    def _server_stopped(self, message: str) -> None:
        self.core.server_stopped(message)
