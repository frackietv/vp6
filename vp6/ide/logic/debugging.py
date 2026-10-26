"""The debugger's IDE side, without Qt: the protocol spoken with the program's
debug agent (``vp6/debugagent.py``), and how a pause is described.

The IDE listens on a localhost port the program is told of
(``VP6_DEBUG_PORT``); once the program connects, ``DebugProtocol`` sends the
breakpoints first (``start``), then pauses, steps, continues, evaluates and
applies code changes, one JSON object a line (written with ``write``); what
the program sends (``feed``) is told by its ``paused(location)`` and
``resumed()`` events and the commands' callbacks. The IDE carries it over
a QTcpServer (``vp6.ide.debugger``).
"""

from __future__ import annotations

import json
import os

from .events import Event


def canonical(path: str) -> str:
    """A file's path as the debugger compares them (real, normalized case)."""
    return os.path.normcase(os.path.realpath(path))


def same_file(a: str, b: str) -> bool:
    return canonical(a) == canonical(b) if a and b else False


def describe(location: dict) -> str:
    """Where the program is paused, for the status bar."""
    if not location.get("file"):
        return "Paused between events"
    where = f"{os.path.basename(location['file'])}, line {location['line']}"
    return {"breakpoint": f"Breakpoint at {where}", "error": f"Error at {where}",
            "pause": f"Paused at {where}"}.get(location.get("reason"), f"Paused at {where}")


class DebugProtocol:
    """One run of the program under the debugger, as messages: see the
    module."""

    def __init__(self, write, breakpoints: dict[str, list[int]], step: bool = False):
        self._write = write  # (bytes to the program; nothing before it is connected)
        self._breakpoints = breakpoints
        self._step = step
        self._buffer = b""
        self._next_id = 0
        self._callbacks: dict[int, object] = {}
        self.connected = False
        self.location: dict | None = None  # where it is paused (None: running)
        self.frame = 0  # the frame of the stack expressions are evaluated in
        self.paused = Event()  # the agent's "paused" message: reason, file, line, stack, error
        self.resumed = Event()

    @property
    def is_paused(self) -> bool:
        return self.location is not None

    # -- the connection ----------------------------------------------------------------------
    def connect(self) -> None:
        """The program connected: send it the breakpoints (and whether to stop
        at its first line)."""
        self.connected = True
        self._send({"cmd": "start", "breakpoints": self._breakpoints, "step": self._step})

    def disconnect(self) -> None:
        """The program went (ended, or the connection closed)."""
        was_paused = self.is_paused
        self.connected = False
        self.location = None
        self._callbacks.clear()
        if was_paused:
            self.resumed.emit()

    def _send(self, message: dict) -> None:
        if self.connected:
            self._write((json.dumps(message) + "\n").encode("utf-8"))

    def feed(self, data: bytes) -> None:
        """What came from the program."""
        self._buffer += data
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                message = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(message, dict):
                self.dispatch(message)

    def dispatch(self, message: dict) -> None:
        event = message.get("event")
        if event == "paused":
            self.location = message
            self.frame = 0
            self.paused.emit(message)
        elif event == "running":
            self.location = None
            self.resumed.emit()
        elif event == "result":
            callback = self._callbacks.pop(message.get("id"), None)
            if callback is not None:
                callback(message)

    # -- commands ------------------------------------------------------------------------------
    def set_breakpoints(self, breakpoints: dict[str, list[int]]) -> None:
        self._breakpoints = breakpoints
        self._send({"cmd": "breakpoints", "breakpoints": breakpoints})

    def pause(self) -> None:
        if not self.is_paused:
            self._send({"cmd": "pause"})

    def resume(self, how: str = "continue") -> None:
        """continue, step (into), next (over) or return (out)."""
        if self.is_paused:
            self._send({"cmd": how})

    def apply_changes(self, files: dict[str, str], callback) -> None:
        """Edit and Continue: send the files' new text (path → text) to the
        paused program; ``callback`` gets what was changed (``changed``,
        ``added``, ``removed``, ``running``, ``errors``, ``files``)."""
        if not self.is_paused:
            callback({"errors": ["The program isn't paused"], "files": []})
            return
        self._next_id += 1
        self._callbacks[self._next_id] = callback
        self._send({"cmd": "apply", "id": self._next_id, "files": files})

    def evaluate(self, expression: str, callback, statements: bool = False) -> None:
        """Evaluate an expression (or, with ``statements``, run a statement) in
        the current frame while paused; ``callback`` gets the result (``value``
        and ``type``, or ``error``)."""
        if not self.is_paused:
            callback({"error": "The program isn't paused"})
            return
        self._next_id += 1
        self._callbacks[self._next_id] = callback
        self._send({"cmd": "eval", "id": self._next_id, "expr": expression,
                    "frame": self.frame, "exec": statements})
