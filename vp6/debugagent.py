"""The debugger's side in the program: run from the IDE with Start, a program
connects to it (``VP6_DEBUG_PORT``) and lets it set breakpoints, pause it,
step through its code and evaluate expressions while it is paused.

``Agent`` traces the program's own code (the files in the project's folder,
``VP6_DEBUG_ROOT``) line by line with ``sys.settrace`` (the main thread
only); other code (VP6, Qt, the standard library) runs untraced. It stops at
a breakpoint, when stepping, when the IDE asks it to pause (in the program's
code, or between events when it is idle) and at an error an event handler
didn't handle (after its traceback). While it is stopped the program's
thread waits for the IDE's commands: evaluating an expression (or running a
statement) in a frame of the stack, then continuing or stepping.

The protocol is one JSON object a line over a localhost TCP connection.
From the IDE: ``start`` (the breakpoints, and ``step``: stop at the first
line of the program's procedures), ``breakpoints``, ``pause``, ``continue``,
``step`` (into), ``next`` (over), ``return`` (out), ``eval`` (``id``,
``expr``, ``frame``, ``exec``: statements allowed), ``apply`` (``id``,
``files``: path → new text; Edit and Continue, see ``hotpatch``). To the
IDE: ``paused`` (``reason``: breakpoint, step, pause or error; ``file``,
``line``, ``function``, ``stack``, ``error``), ``running`` and ``result``
(``id``, and ``value`` and ``type``, or ``error``; for ``apply``:
``changed``, ``added``, ``removed``, ``running``, ``errors`` and ``files``,
those applied).
"""

from __future__ import annotations

import json
import os
import queue
import socket
import sys
import threading

PORT_ENV = "VP6_DEBUG_PORT"
ROOT_ENV = "VP6_DEBUG_ROOT"
REPR_LIMIT = 1000  # (a value's repr is cut there)

_agent: "Agent | None" = None


def active() -> "Agent | None":
    """The program's debugger agent, when it runs under the IDE's debugger."""
    return _agent


def start_from_environment() -> "Agent | None":
    """Connect to the IDE's debugger when it started the program (its port in
    ``VP6_DEBUG_PORT``) and start tracing: called by the runner before the
    project's code runs. Waits for the IDE's breakpoints first."""
    global _agent
    port = os.environ.pop(PORT_ENV, "")  # (not for the programs it starts in turn)
    if not port or _agent is not None:
        return _agent
    try:
        connection = socket.create_connection(("127.0.0.1", int(port)), timeout=10)
    except (OSError, ValueError) as exc:
        print(f"VP6: can't reach the IDE's debugger ({exc}): running without it",
              file=sys.stderr)
        return None
    connection.settimeout(None)
    _agent = Agent(connection, os.environ.pop(ROOT_ENV, os.getcwd()))
    _agent.start()
    return _agent


def canonical(path: str) -> str:
    """A file's path as the debugger compares them (real, normalized case)."""
    return os.path.normcase(os.path.realpath(path))


def _short_repr(value) -> str:
    try:
        text = repr(value)
    except Exception as exc:  # noqa: BLE001 - a broken __repr__ is the program's
        text = f"<repr failed: {type(exc).__name__}: {exc}>"
    return text if len(text) <= REPR_LIMIT else text[:REPR_LIMIT] + "…"


class Agent:
    """The program's side of the debugger (the module's documentation)."""

    def __init__(self, connection: socket.socket, root: str):
        self._socket = connection
        self._file = connection.makefile("r", encoding="utf-8", newline="\n")
        self._send_lock = threading.Lock()
        self._root = canonical(root)
        self._skip = {canonical(os.path.dirname(os.path.abspath(__file__)))}  # (vp6 itself)
        self._user: dict[str, bool] = {}  # co_filename -> the program's own code?
        self._canonical: dict[str, str] = {}
        self.breakpoints: dict[str, set[int]] = {}
        self.commands: queue.Queue = queue.Queue()  # (for the program's thread, stopped)
        self.mode = "run"  # run, start, step, next or return
        self._target = None  # the frame of next and return
        self._pause = threading.Event()
        self.frames: list = []  # the stopped program's own frames, innermost first
        self._idle_namespace: dict | None = None
        self.stopped = False
        self._waker = None

    # -- the connection --------------------------------------------------------------------
    def send(self, message: dict) -> None:
        data = (json.dumps(message) + "\n").encode("utf-8")
        with self._send_lock:
            try:
                self._socket.sendall(data)
            except OSError:
                pass  # (the IDE has gone: the program goes on)

    def _read(self) -> dict | None:
        try:
            line = self._file.readline()
        except (OSError, ValueError):
            return None
        if not line:
            return None
        try:
            return json.loads(line)
        except ValueError:
            return {}

    def start(self) -> None:
        """Wait for the IDE's ``start`` (its breakpoints), then trace the
        program and keep reading its commands in a thread of its own."""
        message = self._read() or {}
        self._set_breakpoints(message.get("breakpoints", {}))
        if message.get("step"):
            self.mode = "start"  # (the first line of a procedure of the program's)
        self._make_waker()
        threading.Thread(target=self._reader, name="VP6 debugger", daemon=True).start()
        sys.settrace(self._trace_call)

    def _reader(self) -> None:
        while True:
            message = self._read()
            if message is None:  # the IDE has gone: no more stops
                self.breakpoints = {}
                self.mode = "run"
                self.commands.put({"cmd": "continue"})
                return
            command = message.get("cmd")
            if command == "breakpoints":
                self._set_breakpoints(message.get("breakpoints", {}))
            elif command == "pause":
                if not self.stopped:
                    self._pause.set()
                    self._wake()
            else:
                self.commands.put(message)

    def _set_breakpoints(self, breakpoints: dict) -> None:
        self.breakpoints = {canonical(path): set(lines) for path, lines in breakpoints.items()}

    # -- pausing while idle: an event for the program's thread ---------------------------------
    def _make_waker(self) -> None:
        """An object of the program's thread that a posted event reaches: a
        pause asked for while the program waits for events stops there."""
        try:
            from PySide6.QtCore import QEvent, QObject
        except ImportError:
            return
        agent = self

        class Waker(QObject):
            def event(self, event):
                if event.type() == QEvent.User:
                    if agent._pause.is_set() and not agent.stopped:
                        agent._pause.clear()
                        agent.stop(None, "pause")
                    return True
                return super().event(event)

        self._waker = Waker()

    def _wake(self) -> None:
        if self._waker is None:
            return
        from PySide6.QtCore import QCoreApplication, QEvent

        QCoreApplication.postEvent(self._waker, QEvent(QEvent.User))  # (thread-safe)

    # -- tracing -------------------------------------------------------------------------------
    def _path(self, filename: str) -> str:
        path = self._canonical.get(filename)
        if path is None:
            path = self._canonical[filename] = canonical(filename)
        return path

    def is_user_file(self, filename: str) -> bool:
        """Whether a code object's file is the program's own (in the project's
        folder, not VP6's or an installed package's)."""
        known = self._user.get(filename)
        if known is None:
            path = self._path(filename)
            # (absolute: some embedded code, such as Shiboken's, has a relative name)
            known = (os.path.isabs(filename) and os.path.isfile(path) and
                     path.startswith(self._root + os.sep) and
                     "site-packages" not in path and
                     not any(path.startswith(skip + os.sep) for skip in self._skip))
            self._user[filename] = known
        return known

    def _trace_call(self, frame, event, arg):
        if event != "call" or not self.is_user_file(frame.f_code.co_filename):
            return None  # (untraced: not the program's own)
        return self._trace_line

    def _trace_line(self, frame, event, arg):
        if event == "line":
            reason = self._stop_reason(frame)
            if reason:
                self.stop(frame, reason)
        elif event == "return" and frame is self._target:
            self.mode, self._target = "step", None  # (back in the caller: stop there)
        return self._trace_line

    def _stop_reason(self, frame) -> str | None:
        if self._pause.is_set():
            self._pause.clear()
            return "pause"
        lines = self.breakpoints.get(self._path(frame.f_code.co_filename))
        if lines and frame.f_lineno in lines:
            return "breakpoint"
        mode = self.mode
        if mode == "step" or (mode == "next" and frame is self._target) or \
                (mode == "start" and frame.f_code.co_name != "<module>"):
            return "step"
        return None

    # -- stopped -------------------------------------------------------------------------------
    def _user_frames(self, frame) -> list:
        frames = []
        while frame is not None:
            if self.is_user_file(frame.f_code.co_filename):
                frames.append(frame)
            frame = frame.f_back
        return frames

    def stop(self, frame, reason: str) -> None:
        """Stop the program here (frame None: between events) and do the IDE's
        commands until one goes on."""
        self.frames = self._user_frames(frame)
        self._interact([self._place(f, f.f_lineno) for f in self.frames], reason, None,
                       live=True)

    def post_mortem(self, exc: BaseException) -> bool:
        """Stop at the line of the program's own code where an unhandled error
        happened (its frames as they were), until the IDE goes on. False when
        it didn't (not in the program's code, or already stopped)."""
        tb, frame, line = exc.__traceback__, None, 0
        while tb is not None:
            if self.is_user_file(tb.tb_frame.f_code.co_filename):
                frame, line = tb.tb_frame, tb.tb_lineno
            tb = tb.tb_next
        if frame is None or self.stopped:
            return False
        self.frames = self._user_frames(frame)
        # (the error's line: the frame itself was left elsewhere)
        stack = [self._place(f, line if f is frame else f.f_lineno) for f in self.frames]
        self._interact(stack, "error", f"{type(exc).__name__}: {exc}", live=False)
        return True

    def _place(self, frame, line: int) -> dict:
        return {"file": self._path(frame.f_code.co_filename), "line": line,
                "function": frame.f_code.co_name}

    def _interact(self, stack: list, reason: str, error: str | None, live: bool) -> None:
        """Tell the IDE where the program stopped, then do its commands until one
        goes on (``live``: the frames still run, so Step Over and Step Out
        follow the innermost; after an error, every step is to the next line run)."""
        self.mode, self._target, self.stopped = "run", None, True
        self._idle_namespace = None
        top = stack[0] if stack else {"file": None, "line": None, "function": None}
        sys.stdout.flush()
        sys.stderr.flush()
        self.send({"event": "paused", "reason": reason, "error": error, "stack": stack, **top})
        try:
            while True:
                message = self.commands.get()
                command = message.get("cmd")
                if command == "eval":
                    self._evaluate(message)
                    continue
                if command == "apply":
                    self._apply(message)
                    continue
                if command in ("next", "return") and live and self.frames:
                    self.mode, self._target = command, self.frames[0]
                elif command in ("step", "next", "return"):
                    self.mode = "step"  # (between events, or after an error: the next line)
                if command in ("continue", "step", "next", "return"):
                    break
        finally:
            self.stopped = False
            self.frames = []
        self.send({"event": "running"})

    def _apply(self, message: dict) -> None:
        """Edit and Continue: the files' new text applied to their modules
        (``hotpatch``), while stopped. A file whose module isn't loaded yet
        needs nothing: it will be read when it is."""
        from . import hotpatch

        running = {frame.f_code for frame in self.frames}
        changed, added, removed, now_running, errors, done = [], [], [], [], [], []
        modules = {}
        for module in list(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            if filename and self.is_user_file(filename):
                modules[self._path(filename)] = module
        for path, text in message.get("files", {}).items():
            module = modules.get(canonical(path))
            if module is None or module.__name__ == "__main__":
                done.append(path)  # (nothing to do)
                continue
            report = hotpatch.apply(module, text, module.__file__, running)
            if report.error:
                errors.append(f"{os.path.basename(path)}: {report.error}")
                continue
            done.append(path)
            changed += report.changed
            added += report.added
            removed += report.removed
            now_running += report.running
        sys.stdout.flush()
        sys.stderr.flush()
        self.send({"event": "result", "id": message.get("id"), "changed": changed,
                   "added": added, "removed": removed, "running": now_running,
                   "errors": errors, "files": done})

    def _namespaces(self, index: int) -> tuple[dict, object]:
        if self.frames:
            frame = self.frames[min(max(index, 0), len(self.frames) - 1)]
            return frame.f_globals, frame.f_locals
        if self._idle_namespace is None:  # (between events: VP6's names and the forms)
            namespace = dict(vars(sys.modules.get("__main__", sys)))
            try:
                import vp6
                from vp6.form import Forms

                namespace.update({name: getattr(vp6, name) for name in vp6.__all__})
                for form in Forms:
                    namespace.setdefault(form.Name, form)
            except Exception:  # noqa: BLE001 - only what is there
                pass
            self._idle_namespace = namespace
        return self._idle_namespace, self._idle_namespace

    def _evaluate(self, message: dict) -> None:
        expression = message.get("expr", "")
        globals_, locals_ = self._namespaces(int(message.get("frame", 0)))
        result: dict
        try:
            try:
                code = compile(expression, "<immediate>", "eval", dont_inherit=True)
            except SyntaxError:
                if not message.get("exec"):
                    raise
                exec(compile(expression, "<immediate>", "exec", dont_inherit=True), globals_,
                     locals_)
                result = {"value": None}
            else:
                value = eval(code, globals_, locals_)
                result = {"value": _short_repr(value), "type": type(value).__name__}
        except Exception as exc:  # noqa: BLE001 - the expression's error, for the IDE
            result = {"error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.flush()
        sys.stderr.flush()
        self.send({"event": "result", "id": message.get("id"), **result})
