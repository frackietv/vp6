"""Claude in the IDE, without Qt: finding Claude Code (the ``claude``
command), its sessions and their transcripts, its login's answer, and the
messages of a chat (``ClaudeProtocol``).

Claude Code keeps its own login (in the system's keychain or its config
folder), so one login lasts across projects, IDE sessions and restarts. It
keeps each conversation as a JSON-lines transcript in
``<config>/projects/<the folder, every other character a dash>/<id>.jsonl``;
the IDE lists those for the project's folder and resumes them.

A chat runs ``claude -p`` with JSON lines both ways (``stream-json``): the
user's messages go to its standard input, its messages come back one per
line, and so do its questions about using a tool (``--permission-prompt-tool
stdio``: a ``control_request`` answered with a ``control_response``). The IDE
runs the process (a QProcess, a VP6 Process); ``ClaudeProtocol`` reads and
writes what goes through it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass

from .events import Event
from .settings import settings

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
        chosen = settings().value(COMMAND_KEY, "") or None
    if chosen is not None:
        return chosen if runnable(chosen) else None
    found = shutil.which("claude")
    if found:
        return found
    for place in _PLACES:
        path = os.path.expanduser(place)
        if runnable(path):
            return path
    return None


def runnable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def search_path(command: str, path: str) -> str:
    """The PATH a command runs with: ``path`` (the IDE's), with the command's
    folder (and Homebrew's) added: an npm-installed claude runs under ``env
    node``."""
    parts = path.split(os.pathsep) if path else []
    for folder in (os.path.dirname(command), "/opt/homebrew/bin", "/usr/local/bin"):
        if folder and folder not in parts and os.path.isdir(folder):
            parts.append(folder)
    return os.pathsep.join(p for p in parts if p)


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
    return settings().value(f"{TITLES_KEY}/{session_id}", "") or ""


def rename_session(session_id: str, title: str) -> None:
    """Name a session (in the IDE's settings: the transcript is Claude Code's)."""
    store = settings()
    if title.strip():
        store.setValue(f"{TITLES_KEY}/{session_id}", title.strip())
    else:
        store.remove(f"{TITLES_KEY}/{session_id}")


def delete_session(info: SessionInfo) -> None:
    """Delete a session's transcript (and the folder of its subagents' ones)."""
    os.remove(info.path)
    folder = info.path[:-len(".jsonl")]
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    _cache.pop(info.path, None)
    settings().remove(f"{TITLES_KEY}/{info.id}")


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


def default_mode() -> str:
    mode = settings().value(MODE_KEY, "default")
    return mode if mode in dict(PERMISSION_MODES) else "default"


def shell_quote(path: str) -> str:
    """A path for a command line in the Terminal window's shell."""
    if sys.platform == "win32":
        return f'"{path}"'
    return "'" + path.replace("'", "'\\''") + "'"


# -- JSON lines -----------------------------------------------------------------------------

class JsonLines:
    """Reads JSON objects, one a line, from what comes in pieces."""

    def __init__(self):
        self._buffer = b""

    def feed(self, data: bytes) -> list[dict]:
        """The objects of the lines completed by ``data`` (lines that aren't
        a JSON object are left out)."""
        self._buffer += data
        *lines, self._buffer = self._buffer.split(b"\n")
        found = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                found.append(value)
        return found

    def clear(self) -> None:
        self._buffer = b""


def line(data: dict) -> bytes:
    """A message as a line to write."""
    return (json.dumps(data) + "\n").encode()


# -- a chat's messages ------------------------------------------------------------------------

class ClaudeProtocol:
    """What goes between the IDE and ``claude -p`` in a chat: the command's
    arguments, the user's messages, the answers to its questions and its
    interruption (written with ``write(bytes)``), and its messages read
    (``feed``), told by events:

    * ``message(data)``: each of Claude Code's messages (system, assistant,
      user, result);
    * ``sessionChanged(id)``: the session's id, once Claude Code gives it;
    * ``permissionRequested(request id, tool name, its input)``: a question
      about using a tool (tools always allowed in this chat are answered);
    * ``result()``: an answer is over (``busy`` is False again).
    """

    def __init__(self, write, session_id: str | None = None, mode: str = "default"):
        self._write = write
        self.session_id = session_id
        self.mode = mode
        self.allowed: set[str] = set()  # tools always allowed in this chat
        self.lines = JsonLines()
        self._requests = 0
        self.message = Event()
        self.sessionChanged = Event()
        self.permissionRequested = Event()
        self.result = Event()

    def arguments(self) -> list[str]:
        args = ["-p", "--input-format", "stream-json", "--output-format", "stream-json",
                "--verbose", "--permission-prompt-tool", "stdio", "--permission-mode",
                self.mode]
        if self.session_id:
            args += ["--resume", self.session_id]
        return args

    def send(self, text: str) -> None:
        """The user's message."""
        self._write(line({"type": "user", "session_id": self.session_id or "",
                          "parent_tool_use_id": None,
                          "message": {"role": "user",
                                      "content": [{"type": "text", "text": text}]}}))

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
        self._write(line({"type": "control_response", "response": {
            "subtype": "success", "request_id": request_id, "response": response}}))

    def interrupt(self) -> None:
        """Ask it to stop what it is doing."""
        self._requests += 1
        self._write(line({"type": "control_request", "request_id": f"vp6-{self._requests}",
                          "request": {"subtype": "interrupt"}}))

    def feed(self, data: bytes) -> None:
        """What came from its standard output."""
        for message in self.lines.feed(data):
            self.handle(message)

    def handle(self, data: dict) -> None:
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
            self.result.emit()
        self.message.emit(data)
