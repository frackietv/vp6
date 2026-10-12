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

import json
import os
import shutil
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, Signal

from .claude import _runnable, environment
from .theme import ide_settings

CODEX_ENV = "VP6_CODEX"  # the codex command to run (before the setting and the PATH)
COMMAND_KEY = "codex/command"  # the setting: the codex command chosen in the IDE
MODE_KEY = "codex/mode"  # the setting: the mode of new chats

# What Codex may do without asking: (mode, what the IDE calls it, approval policy,
# sandbox policy)
_WRITE = {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False,
          "excludeTmpdirEnvVar": False, "excludeSlashTmp": False}
MODES = [
    ("auto", "Ask Outside the Folder", "on-request", _WRITE),
    ("untrusted", "Ask Before Running Commands", "untrusted", _WRITE),
    ("read-only", "Read Only", "on-request", {"type": "readOnly", "networkAccess": False}),
    ("full", "Full Access", "never", {"type": "dangerFullAccess"}),
]
_SANDBOX_MODES = {"workspaceWrite": "workspace-write", "readOnly": "read-only",
                  "dangerFullAccess": "danger-full-access"}

# The kinds of sessions listed (not Codex's subagents' own)
SOURCE_KINDS = ["cli", "vscode", "exec", "appServer"]

# Where installers put the command, for an IDE not started from a shell (its PATH short)
_PLACES = ["~/.local/bin/codex", "/opt/homebrew/bin/codex", "/usr/local/bin/codex",
           "~/.npm-global/bin/codex", "~/.bun/bin/codex", "~/.cargo/bin/codex",
           "/Applications/Codex.app/Contents/Resources/codex",
           "~/.codex/plugins/.plugin-appserver/codex-cli/bin/codex"]


def find_codex() -> str | None:
    """The codex command: $VP6_CODEX, else the one chosen in the IDE, else the
    one on the PATH or in an installer's usual place. None if there's none."""
    chosen = os.environ.get(CODEX_ENV)
    if chosen is None:
        chosen = ide_settings().value(COMMAND_KEY, "") or None
    if chosen is not None:
        return chosen if _runnable(chosen) else None
    found = shutil.which("codex")
    if found:
        return found
    for place in _PLACES:
        path = os.path.expanduser(place)
        if _runnable(path):
            return path
    return None


def codex_home() -> str:
    """Codex's folder: $CODEX_HOME, else ~/.codex."""
    return os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")


def mode_policies(mode: str) -> tuple[str, dict]:
    """A mode's (approval policy, sandbox policy)."""
    for name, _label, approval, sandbox in MODES:
        if name == mode:
            return approval, sandbox
    return MODES[0][2], MODES[0][3]


def default_mode() -> str:
    mode = ide_settings().value(MODE_KEY, "auto")
    return mode if mode in [m[0] for m in MODES] else "auto"


# -- the server -----------------------------------------------------------------------------

class CodexServer(QObject):
    """``codex app-server``, started when first asked something and kept
    running. ``request`` sends a request and calls back with its result (or
    an error's message); requests made before the server answered
    ``initialize`` wait for it."""

    notification = Signal(str, dict)  # method, params
    serverRequest = Signal(object, str, dict)  # id, method, params: answer with respond()
    stopped = Signal(str)  # it ended (what it said, if anything)

    def __init__(self, command: str | None = None, parent=None):
        super().__init__(parent)
        self.command = command
        self.process: QProcess | None = None
        self.generation = 0  # (one more each time it starts: threads are loaded again)
        self.ready = False
        self._waiting: list[bytes] = []  # sent once initialized
        self._callbacks: dict[int, tuple] = {}  # id: (on result, on error)
        self._next_id = 0
        self._buffer = b""
        self._errors = b""

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def request(self, method: str, params: dict, callback=None, error=None) -> int | None:
        """Ask the server (starting it if need be). ``callback(result)`` when it
        answers, ``error(message)`` if it can't (or isn't there)."""
        if not self.running and not self._start(error):
            return None
        self._next_id += 1
        request_id = self._next_id
        self._callbacks[request_id] = (callback, error)
        self._send({"id": request_id, "method": method, "params": params},
                   now=method == "initialize")
        return request_id

    def respond(self, request_id, result: dict) -> None:
        """Answer one of the server's requests."""
        self._send({"id": request_id, "result": result})

    def respond_error(self, request_id, message: str) -> None:
        self._send({"id": request_id, "error": {"code": -32601, "message": message}})

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
        self._buffer = self._errors = b""
        self._waiting = []
        self.ready = False
        process.start(command, ["app-server"])
        if not process.waitForStarted(10000):
            self.process = None
            process.deleteLater()
            if error is not None:
                error(f"Codex couldn't be started: {process.errorString()}")
            return False
        self.generation += 1
        from vp6 import __version__
        self.request("initialize", {
            "clientInfo": {"name": "vp6", "title": "VP6", "version": __version__},
            "capabilities": {"experimentalApi": False, "requestAttestation": False}},
            self._initialized, lambda message: None)
        return True

    def _initialized(self, _result) -> None:
        self._send({"method": "initialized"}, now=True)
        self.ready = True
        waiting, self._waiting = self._waiting, []
        for line in waiting:
            self.process.write(line)

    def _send(self, data: dict, now: bool = False) -> None:
        if not self.running:
            return
        line = (json.dumps(data) + "\n").encode()
        if self.ready or now:
            self.process.write(line)
        else:
            self._waiting.append(line)

    def _read(self) -> None:
        process = self.process
        if process is None:
            return
        self._buffer += bytes(process.readAllStandardOutput())
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                self._handle(data)

    def _read_errors(self) -> None:
        if self.process is not None:
            self._errors = (self._errors + bytes(self.process.readAllStandardError()))[-8000:]

    def _handle(self, data: dict) -> None:
        method = data.get("method")
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        if method and "id" in data:
            self.serverRequest.emit(data["id"], method, params)
        elif method:
            self.notification.emit(method, params)
        elif "id" in data:
            callback, error = self._callbacks.pop(data["id"], (None, None))
            if "error" in data:
                if error is not None:
                    problem = data["error"]
                    error(problem.get("message", "error") if isinstance(problem, dict)
                          else str(problem))
            elif callback is not None:
                result = data.get("result")
                callback(result if isinstance(result, dict) else {})

    def _on_finished(self, *_):
        if self.process is not None and self.sender() is self.process:
            self._finished_process(self.process)

    def _finished_process(self, process: QProcess) -> None:
        if process is not self.process:
            return
        self._read()
        self._read_errors()
        self.process = None
        self.ready = False
        process.deleteLater()
        errors = self._errors.decode("utf-8", "replace").strip()
        lines = [line for line in errors.splitlines() if line.strip()]
        message = lines[-1] if lines else "Codex ended."
        callbacks, self._callbacks = self._callbacks, {}
        for _callback, error in callbacks.values():
            if error is not None:
                error(message)
        self.stopped.emit(message)


# -- the login ------------------------------------------------------------------------------

def describe_account(result: dict) -> tuple[bool, str]:
    """(logged in, what to say) from ``account/read``'s result."""
    account = result.get("account")
    if isinstance(account, dict):
        kind = account.get("type")
        if kind == "chatgpt":
            who = account.get("email") or ""
            plan = account.get("planType") or ""
            return True, "Logged in" + (f" as {who}" if who else "") + \
                (f" (ChatGPT {plan})" if plan else " (ChatGPT)")
        if kind == "apiKey":
            return True, "Logged in with an API key"
        return True, f"Logged in ({kind})"
    if result.get("requiresOpenaiAuth") is False:
        return True, "No login needed (its model provider's own)"
    return False, "Not logged in"


# -- sessions ---------------------------------------------------------------------------------

@dataclass
class CodexSession:
    id: str
    path: str  # its rollout file (Codex's)
    title: str  # its name, else the first thing asked
    modified: float  # (seconds since the epoch)
    preview: str  # the first thing asked
    cwd: str


def session_of(thread: dict) -> CodexSession:
    preview = " ".join(str(thread.get("preview") or "").split())
    title = (thread.get("name") or "").strip() or preview[:120] or "(untitled)"
    modified = thread.get("updatedAt") or thread.get("createdAt") or 0
    return CodexSession(str(thread.get("id", "")), thread.get("path") or "", title,
                        float(modified), preview, thread.get("cwd") or "")


def list_params(folder: str, cursor: str | None = None) -> dict:
    params = {"cwd": os.path.abspath(folder), "limit": 100, "sourceKinds": SOURCE_KINDS,
              "sortKey": "updated_at"}
    if cursor:
        params["cursor"] = cursor
    return params


def user_text(item: dict) -> str:
    """The text of a userMessage item."""
    parts = [c.get("text", "") for c in item.get("content") or []
             if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


# -- a chat ---------------------------------------------------------------------------------

class CodexChat(QObject):
    """A conversation with Codex in ``folder``, through ``server``: a thread
    started for the first message (or ``session_id`` resumed by ``open``),
    a turn for each message."""

    message = Signal(dict)  # the thread's notifications: {"method": ..., "params": ...}
    sessionChanged = Signal(str)  # the thread's id, once Codex gives it
    busyChanged = Signal(bool)  # working on a message, or done
    permissionRequested = Signal(str, str, dict)  # request id, what it wants to use, details
    failed = Signal(str)  # it couldn't be started, or a request failed
    resumed = Signal(dict)  # the resumed thread (its turns: what was said before)

    def __init__(self, server: CodexServer, folder: str, session_id: str | None = None,
                 mode: str = "auto", parent=None):
        super().__init__(parent)
        self.server = server
        self.folder = folder
        self.session_id = session_id
        self.mode = mode
        self.model = ""
        self.busy = False
        self.turn_id: str | None = None
        self._loaded = 0  # the server's generation the thread was loaded in (0: not)
        self._loading = False
        self._pending: str | None = None  # a message waiting for the thread
        self._requests: dict[str, object] = {}  # request id shown: the server's id
        self._changes: dict[str, list[str]] = {}  # item id: the files it changes
        server.notification.connect(self._notified)
        server.serverRequest.connect(self._asked)
        server.stopped.connect(self._server_stopped)

    @property
    def running(self) -> bool:
        return bool(self._loaded) and self._loaded == self.server.generation and \
            self.server.running

    def open(self) -> None:
        """Resume the session (its turns come with ``resumed``)."""
        if self.session_id and not self.running and not self._loading:
            self._load()

    def send(self, text: str) -> bool:
        """Send the user's message (the thread started or resumed first)."""
        if self.busy:
            return False
        self._set_busy(True)
        if self.running:
            self._start_turn(text)
        else:
            self._pending = text
            if not self._loading:
                self._load()
        return self.busy

    def set_mode(self, mode: str) -> None:
        """A new mode: from the next message on."""
        self.mode = mode

    def answer(self, request_id: str, allow: bool, details: dict | None = None,
               always: str | None = None) -> None:
        """Answer a question (``always``: allowed for the rest of the session)."""
        server_id = self._requests.pop(request_id, None)
        if server_id is None:
            return
        decision = ("acceptForSession" if always else "accept") if allow else "decline"
        self.server.respond(server_id, {"decision": decision})

    def stop(self) -> None:
        """Stop what Codex is doing (the turn interrupted)."""
        if self.busy and self.running and self.turn_id:
            self.server.request("turn/interrupt", {"threadId": self.session_id,
                                                   "turnId": self.turn_id})
        elif self.busy and not self.turn_id:
            self._pending = None
            self._set_busy(False)

    def end(self) -> None:
        """Let go of the thread (the window closing; it can be resumed)."""
        if self.running:
            self.server.request("thread/unsubscribe", {"threadId": self.session_id})
        self._loaded = 0
        for server_id in self._requests.values():
            self.server.respond(server_id, {"decision": "cancel"})
        self._requests.clear()
        self._set_busy(False)

    # -- the thread -------------------------------------------------------------------------------
    def _load(self) -> None:
        approval, sandbox = mode_policies(self.mode)
        params = {"cwd": self.folder, "approvalPolicy": approval,
                  "sandbox": _SANDBOX_MODES[sandbox["type"]]}
        self._loading = True
        if self.session_id:
            self.server.request("thread/resume", dict(params, threadId=self.session_id),
                                self._resumed, self._load_failed)
        else:
            self.server.request("thread/start", params, self._started, self._load_failed)

    def _started(self, result: dict) -> None:
        self._loading = False
        self._loaded = self.server.generation
        thread = result.get("thread") or {}
        self.model = result.get("model") or self.model
        if thread.get("id") and thread["id"] != self.session_id:
            self.session_id = thread["id"]
            self.sessionChanged.emit(self.session_id)
        self.message.emit({"method": "vp6/threadLoaded", "params": result})
        self._go_on()

    def _resumed(self, result: dict) -> None:
        self._loading = False
        self._loaded = self.server.generation
        self.model = result.get("model") or self.model
        self.resumed.emit(result.get("thread") or {})
        self.message.emit({"method": "vp6/threadLoaded", "params": result})
        self._go_on()

    def _go_on(self) -> None:
        text, self._pending = self._pending, None
        if text is not None:
            self._start_turn(text)

    def _load_failed(self, message: str) -> None:
        self._loading = False
        self._pending = None
        self._set_busy(False)
        self.failed.emit(message)

    def _start_turn(self, text: str) -> None:
        approval, sandbox = mode_policies(self.mode)
        if sandbox["type"] == "workspaceWrite":
            sandbox = dict(sandbox, writableRoots=[os.path.abspath(self.folder)])
        self.turn_id = None
        self.server.request("turn/start", {
            "threadId": self.session_id, "cwd": self.folder, "approvalPolicy": approval,
            "sandboxPolicy": sandbox,
            "input": [{"type": "text", "text": text, "text_elements": []}]},
            self._turn_started, self._turn_failed)

    def _turn_started(self, result: dict) -> None:
        turn = result.get("turn") or {}
        if turn.get("id") and self.busy:
            self.turn_id = turn["id"]

    def _turn_failed(self, message: str) -> None:
        self._set_busy(False)
        self.failed.emit(message)

    # -- what the server says ---------------------------------------------------------------------
    def _notified(self, method: str, params: dict) -> None:
        thread = params.get("threadId") or (params.get("thread") or {}).get("id")
        if not self.session_id or thread != self.session_id:
            return
        if method == "turn/started":
            self.turn_id = (params.get("turn") or {}).get("id") or self.turn_id
        elif method == "item/started":
            item = params.get("item") or {}
            if item.get("type") == "fileChange":
                self._changes[item.get("id", "")] = [
                    c.get("path", "") for c in item.get("changes") or [] if isinstance(c, dict)]
        elif method == "turn/completed":
            self.turn_id = None
            self._changes.clear()
            self._set_busy(False)
        self.message.emit({"method": method, "params": params})

    def _asked(self, server_id, method: str, params: dict) -> None:
        if not self.session_id or params.get("threadId") != self.session_id:
            return
        request_id = str(server_id)
        reason = params.get("reason") or ""
        if method == "item/commandExecution/requestApproval":
            self._requests[request_id] = server_id
            command = params.get("command") or ""
            if not command and params.get("networkApprovalContext"):
                command = "network access"
            self.permissionRequested.emit(request_id, "Shell",
                                          {"command": command, "reason": reason})
        elif method == "item/fileChange/requestApproval":
            self._requests[request_id] = server_id
            files = self._changes.get(params.get("itemId", ""), [])
            shown = ", ".join(os.path.relpath(f, self.folder) if os.path.isabs(f) else f
                              for f in files)
            self.permissionRequested.emit(request_id, "Edit Files", {
                "description": shown or params.get("grantRoot") or reason or "files",
                "reason": reason})
        else:  # (questions the IDE can't show: the server goes on without)
            self.server.respond_error(server_id, f"VP6 can't answer {method}")

    def _server_stopped(self, message: str) -> None:
        was_busy = self.busy
        self._loaded = 0
        self._loading = False
        self._requests.clear()
        self.turn_id = None
        self._set_busy(False)
        if was_busy:
            self.failed.emit(message)

    def _set_busy(self, busy: bool) -> None:
        if busy != self.busy:
            self.busy = busy
            self.busyChanged.emit(busy)
