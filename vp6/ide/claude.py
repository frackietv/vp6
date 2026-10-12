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

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .theme import ide_settings

CLAUDE_ENV = "VP6_CLAUDE"  # the claude command to run (before the setting and the PATH)
COMMAND_KEY = "claude/command"  # the setting: the claude command chosen in the IDE
MODE_KEY = "claude/mode"  # the setting: the permission mode of new chats
TITLES_KEY = "claude/titles"  # the setting's group: sessions' names given in the IDE

# Claude Code's permission modes: (mode, what the IDE calls it)
PERMISSION_MODES = [
    ("default", "Ask Before Using Tools"),
    ("acceptEdits", "Accept Edits"),
    ("plan", "Plan Only"),
    ("bypassPermissions", "Bypass Permissions"),
]

# Where installers put the command, for an IDE not started from a shell (its PATH short)
_PLACES = ["~/.claude/local/claude", "~/.local/bin/claude", "/opt/homebrew/bin/claude",
           "/usr/local/bin/claude", "~/.npm-global/bin/claude", "~/.bun/bin/claude"]


def find_claude() -> str | None:
    """The claude command: $VP6_CLAUDE, else the one chosen in the IDE, else the
    one on the PATH or in an installer's usual place. None if there's none."""
    chosen = os.environ.get(CLAUDE_ENV)
    if chosen is None:
        chosen = ide_settings().value(COMMAND_KEY, "") or None
    if chosen is not None:
        return chosen if _runnable(chosen) else None
    found = shutil.which("claude")
    if found:
        return found
    for place in _PLACES:
        path = os.path.expanduser(place)
        if _runnable(path):
            return path
    return None


def _runnable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def environment(command: str) -> QProcessEnvironment:
    """The IDE's environment, with the command's folder (and Homebrew's) on the
    PATH: an npm-installed claude runs under ``env node``."""
    env = QProcessEnvironment.systemEnvironment()
    parts = env.value("PATH", "").split(os.pathsep)
    for folder in (os.path.dirname(command), "/opt/homebrew/bin", "/usr/local/bin"):
        if folder and folder not in parts and os.path.isdir(folder):
            parts.append(folder)
    env.insert("PATH", os.pathsep.join(p for p in parts if p))
    return env


def config_dir() -> str:
    """Claude Code's folder: $CLAUDE_CONFIG_DIR, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def project_key(folder: str) -> str:
    """The name of a folder's transcripts folder: every character that isn't a
    letter or a digit becomes a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(folder))


def sessions_folder(folder: str) -> str:
    return os.path.join(config_dir(), "projects", project_key(folder))


# -- sessions ---------------------------------------------------------------------------------

@dataclass
class SessionInfo:
    id: str
    path: str  # its transcript
    title: str  # the name given in the IDE, Claude Code's, or the first thing asked
    modified: float  # (seconds since the epoch)
    messages: int  # the user's and Claude's (not tool results)


_cache: dict[str, tuple[float, int, SessionInfo]] = {}  # path: (mtime, size, info)


def list_sessions(folder: str) -> list[SessionInfo]:
    """The folder's sessions, the latest first (none without a transcript with
    something asked in it)."""
    directory = sessions_folder(folder)
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    sessions = []
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(directory, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        cached = _cache.get(path)
        if cached and cached[:2] == (stat.st_mtime, stat.st_size):
            info = cached[2]
        else:
            info = _read_session(path, stat.st_mtime)
            _cache[path] = (stat.st_mtime, stat.st_size, info)
        if info.messages:
            given = session_title(info.id)
            sessions.append(SessionInfo(info.id, path, given or info.title, info.modified,
                                        info.messages))
    sessions.sort(key=lambda s: s.modified, reverse=True)
    return sessions


def _read_session(path: str, modified: float) -> SessionInfo:
    session_id = os.path.basename(path)[:-len(".jsonl")]
    first = summary = custom = ""
    count = 0
    for entry in _entries(path):
        kind = entry.get("type")
        if kind == "custom-title":
            custom = entry.get("customTitle") or custom
        elif kind == "summary":
            summary = entry.get("summary") or summary
        elif _is_message(entry):
            text = message_text(entry)
            if text or kind == "assistant":
                count += 1
            if kind == "user" and text and not first:
                first = text
    title = custom or summary or " ".join(first.split()) or "(untitled)"
    return SessionInfo(session_id, path, title[:120], modified, count)


def _entries(path: str):
    try:
        with open(path, encoding="utf-8", errors="replace") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    yield entry
    except OSError:
        return


def _is_message(entry: dict) -> bool:
    return entry.get("type") in ("user", "assistant") and isinstance(
        entry.get("message"), dict) and not entry.get("isMeta") and not entry.get("isSidechain")


# What Claude Code writes as the user's message for its own commands and notes
_NOT_ASKED = ("<command-", "<local-command", "Caveat:", "<system-reminder>",
              "[Request interrupted")


def message_text(entry: dict) -> str:
    """The text the user typed (or Claude wrote) in a message; "" for tool
    results and Claude Code's own notes."""
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return ""
    text = "\n".join(t for t in texts if t and not t.lstrip().startswith(_NOT_ASKED))
    return text.strip()


def load_transcript(path: str) -> list[dict]:
    """The messages of a session's transcript, to show (as Claude Code's
    stream-json messages: {"type": "user"/"assistant", "message": ...})."""
    return [entry for entry in _entries(path) if _is_message(entry)]


def session_title(session_id: str) -> str:
    return ide_settings().value(f"{TITLES_KEY}/{session_id}", "") or ""


def rename_session(session_id: str, title: str) -> None:
    """Name a session (in the IDE's settings: the transcript is Claude Code's)."""
    settings = ide_settings()
    if title.strip():
        settings.setValue(f"{TITLES_KEY}/{session_id}", title.strip())
    else:
        settings.remove(f"{TITLES_KEY}/{session_id}")


def delete_session(info: SessionInfo) -> None:
    """Delete a session's transcript (and the folder of its subagents' ones)."""
    os.remove(info.path)
    folder = info.path[:-len(".jsonl")]
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    _cache.pop(info.path, None)
    ide_settings().remove(f"{TITLES_KEY}/{info.id}")


def describe_time(seconds: float, now: float | None = None) -> str:
    """When a session was last changed: "14:05" today, else "12 Oct 2026"."""
    now = time.time() if now is None else now
    stamp, today = time.localtime(seconds), time.localtime(now)
    if stamp[:3] == today[:3]:
        return time.strftime("%H:%M", stamp)
    return time.strftime("%d %b %Y", stamp).lstrip("0")


# -- login ----------------------------------------------------------------------------------

def parse_auth_status(code: int, output: str) -> tuple[bool, str]:
    """(logged in, what to say) from ``claude auth status``'s exit code and output."""
    try:
        status = json.loads(output)
    except ValueError:
        status = None
    if isinstance(status, dict):
        if not status.get("loggedIn"):
            return False, "Not logged in"
        who = status.get("email") or status.get("orgName") or ""
        how = status.get("subscriptionType") or status.get("authMethod") or ""
        text = "Logged in" + (f" as {who}" if who else "") + (f" ({how})" if how else "")
        return True, text
    if code == 0:
        line = output.strip().splitlines()[0] if output.strip() else "Logged in"
        return True, line
    return False, "Not logged in"


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
    the next ones."""

    message = Signal(dict)  # each of Claude Code's messages (system, assistant, user, result)
    sessionChanged = Signal(str)  # the session's id, once Claude Code gives it
    busyChanged = Signal(bool)  # working on a message, or done
    permissionRequested = Signal(str, str, dict)  # request id, tool name, its input
    failed = Signal(str)  # it couldn't be started, or ended with an error

    def __init__(self, folder: str, session_id: str | None = None, command: str | None = None,
                 mode: str = "default", parent=None):
        super().__init__(parent)
        self.folder = folder
        self.session_id = session_id
        self.command = command
        self.mode = mode
        self.allowed: set[str] = set()  # tools always allowed in this chat
        self.process: QProcess | None = None
        self.busy = False
        self._buffer = b""
        self._errors = b""
        self._requests = 0
        self._stopping = False  # (stopped or ended: its end isn't a failure)
        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.setInterval(3000)
        self._stop_timer.timeout.connect(self._kill)

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def arguments(self) -> list[str]:
        args = ["-p", "--input-format", "stream-json", "--output-format", "stream-json",
                "--verbose", "--permission-prompt-tool", "stdio", "--permission-mode",
                self.mode]
        if self.session_id:
            args += ["--resume", self.session_id]
        return args

    def send(self, text: str) -> bool:
        """Send the user's message (starting Claude Code if it isn't running)."""
        if not self.running and not self._start():
            return False
        self._write({"type": "user", "session_id": self.session_id or "",
                     "parent_tool_use_id": None,
                     "message": {"role": "user", "content": [{"type": "text", "text": text}]}})
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
        if always:
            self.allowed.add(always)
        if allow:
            response = {"behavior": "allow", "updatedInput": tool_input or {}}
        else:
            response = {"behavior": "deny", "message": "The user didn't allow this."}
        self._write({"type": "control_response", "response": {
            "subtype": "success", "request_id": request_id, "response": response}})

    def stop(self) -> None:
        """Stop what Claude is doing (asked; ended if it doesn't within 3 s)."""
        if not self.running or not self.busy:
            return
        self._requests += 1
        self._stopping = True
        self._write({"type": "control_request", "request_id": f"vp6-{self._requests}",
                     "request": {"subtype": "interrupt"}})
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
        self._buffer = self._errors = b""
        self._stopping = False
        process.start(command, self.arguments())
        if not process.waitForStarted(10000):
            self.failed.emit(f"Claude Code couldn't be started: {process.errorString()}")
            self.process = None
            process.deleteLater()
            return False
        return True

    def _write(self, data: dict) -> None:
        if self.running:
            self.process.write((json.dumps(data) + "\n").encode())

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
            self._errors += bytes(self.process.readAllStandardError())

    def _handle(self, data: dict) -> None:
        kind = data.get("type")
        if kind == "control_request":
            request = data.get("request") or {}
            if request.get("subtype") == "can_use_tool":
                tool = request.get("tool_name", "")
                tool_input = request.get("input") or {}
                request_id = data.get("request_id", "")
                if tool in self.allowed:
                    self.answer(request_id, True, tool_input)
                else:
                    self.permissionRequested.emit(request_id, tool, tool_input)
            return
        if kind in ("control_response", "control_cancel_request", "keep_alive"):
            return
        session = data.get("session_id")
        if session and session != self.session_id:
            self.session_id = session
            self.sessionChanged.emit(session)
        if kind == "result":
            self._stop_timer.stop()
            self._stopping = False
            self._set_busy(False)
        self.message.emit(data)

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


def default_mode() -> str:
    mode = ide_settings().value(MODE_KEY, "default")
    return mode if mode in dict(PERMISSION_MODES) else "default"


def shell_quote(path: str) -> str:
    """A path for a command line in the Terminal window's shell."""
    if sys.platform == "win32":
        return f'"{path}"'
    return "'" + path.replace("'", "'\\''") + "'"
