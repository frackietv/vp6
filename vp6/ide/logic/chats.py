"""What a chat with Claude or Codex shows, without Qt: the messages of Claude
Code (``ClaudeMessages``) and the notifications of Codex's threads
(``CodexMessages``) read into what a chat window shows. The window is a
*view* with ``show_text(who, text)`` (who: "user" or "assistant"; the
assistant's text is Markdown), ``show_tool(name, summary)``,
``show_tool_error(text)``, ``show_error(text)`` and ``set_state(text)`` (the
line under the conversation); ``state_text()`` is what that line says now.
The IDE's chat windows are views.
"""

from __future__ import annotations

import os

from .claude import load_transcript, message_text
from .codex import user_text


def tool_summary(name: str, tool_input: dict) -> str:
    """One line about a tool's use: its command, file, pattern or address."""
    for key in ("command", "file_path", "notebook_path", "pattern", "url", "query",
                "description", "prompt"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            line = " ".join(value.split())
            return line if len(line) <= 160 else line[:157] + "…"
    return ""


def result_text(block: dict) -> str:
    """A tool result block's text."""
    content = block.get("content")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def login_hint(text: str) -> bool:
    """Whether an error is about the login (the view offers to log in)."""
    lowered = text.lower()
    return any(word in lowered for word in ("login", "log in", "api key", "authenticat"))


class ClaudeMessages:
    """Claude Code's stream-json messages (live, or a transcript's) shown in
    a view."""

    def __init__(self, view):
        self.view = view
        self.tools: dict[str, str] = {}  # tool use id: its name

    def show_transcript(self, path: str) -> None:
        """What was said before in a resumed session."""
        for message in load_transcript(path):
            self.show_message(message)
        self.view.set_state("Resumed: your next message goes on with this session")

    def show_message(self, data: dict) -> None:
        view = self.view
        kind = data.get("type")
        if kind == "system" and data.get("subtype") == "init":
            view.set_state(f"Model: {data.get('model', '?')}")
            return
        if kind == "result":
            self._show_result(data)
            return
        if kind not in ("user", "assistant"):
            return
        content = data.get("message", {}).get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = message_text({"message": {"content": [block]}})
                if text:
                    view.show_text(kind, text)
            elif block_type == "tool_use":
                name = block.get("name", "?")
                self.tools[block.get("id", "")] = name
                view.show_tool(name, tool_summary(name, block.get("input") or {}))
            elif block_type == "tool_result" and block.get("is_error"):
                view.show_tool_error(result_text(block))

    def _show_result(self, data: dict) -> None:
        parts = []
        cost = data.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            parts.append(f"${cost:.4f}")
        duration = data.get("duration_ms")
        if isinstance(duration, (int, float)):
            parts.append(f"{duration / 1000:.1f} s")
        self.view.set_state("Done" + (f" ({', '.join(parts)})" if parts else ""))
        if data.get("is_error") or data.get("subtype", "success") != "success":
            text = data.get("result") or data.get("subtype") or "error"
            self.view.show_error(str(text))


_CHANGE_KINDS = {"add": "Add", "delete": "Delete", "update": "Edit"}


def command_line(item: dict) -> str:
    """The command a commandExecution item runs (without the shell around it)."""
    actions = [a for a in item.get("commandActions") or [] if isinstance(a, dict)]
    if len(actions) == 1 and actions[0].get("command"):
        return actions[0]["command"]
    return item.get("command") or ""


class CodexMessages:
    """A Codex thread's notifications (live, or a resumed thread's turns)
    shown in a view; ``folder``: the chat's (file paths shown relative to
    it)."""

    def __init__(self, view, folder: str):
        self.view = view
        self.folder = folder
        self.failure = ""  # an error Codex gave up on, until its turn completes

    def show_thread(self, thread: dict) -> None:
        """What was said before in the resumed session."""
        for turn in thread.get("turns") or []:
            for item in turn.get("items") or []:
                if isinstance(item, dict):
                    self.item_started(item, history=True)
                    self.item_completed(item, history=True)
        self.view.set_state("Resumed: your next message goes on with this session")

    def show_message(self, data: dict) -> None:
        view = self.view
        method = data.get("method")
        params = data.get("params") or {}
        if method == "vp6/threadLoaded":
            if params.get("model") and "Resum" not in view.state_text():
                view.set_state(f"Model: {params['model']}")
        elif method == "item/started":
            self.item_started(params.get("item") or {})
        elif method == "item/completed":
            self.item_completed(params.get("item") or {})
        elif method == "error":
            message = (params.get("error") or {}).get("message") or "error"
            if params.get("willRetry"):
                view.set_state(f"Retrying: {message}")
            else:
                self.failure = message
        elif method == "turn/completed":
            self.turn_completed(params.get("turn") or {})

    def item_started(self, item: dict, history: bool = False) -> None:
        view = self.view
        kind = item.get("type")
        if kind == "commandExecution":
            view.show_tool("Shell", tool_summary("Shell", {"command": command_line(item)}))
        elif kind == "fileChange":
            for change in item.get("changes") or []:
                path = change.get("path", "")
                if os.path.isabs(path) and path.startswith(self.folder + os.sep):
                    path = os.path.relpath(path, self.folder)
                what = (change.get("kind") or {}).get("type", "update")
                view.show_tool(_CHANGE_KINDS.get(what, "Edit"), path)
        elif kind == "mcpToolCall":
            arguments = item.get("arguments")
            view.show_tool(f"{item.get('server', '?')}/{item.get('tool', '?')}",
                           tool_summary("", arguments if isinstance(arguments, dict) else {}))
        elif kind == "dynamicToolCall":
            arguments = item.get("arguments")
            view.show_tool(item.get("tool", "?"),
                           tool_summary("", arguments if isinstance(arguments, dict) else {}))
        elif kind == "webSearch":
            view.show_tool("Search", item.get("query") or "")
        elif kind == "imageView":
            view.show_tool("View", item.get("path") or "")

    def item_completed(self, item: dict, history: bool = False) -> None:
        view = self.view
        kind = item.get("type")
        status = item.get("status")
        if kind == "agentMessage":
            if (item.get("text") or "").strip():
                view.show_text("assistant", item["text"].strip())
        elif kind == "userMessage" and history:
            text = user_text(item)
            if text:
                view.show_text("user", text)
        elif kind == "commandExecution":
            code = item.get("exitCode")
            if status == "declined":
                view.show_tool_error("Declined")
            elif status == "failed" or code not in (None, 0):
                output = (item.get("aggregatedOutput") or "").strip()
                lines = output.splitlines()
                view.show_tool_error(lines[-1] if lines else f"exit code {code}")
        elif kind == "fileChange" and status in ("failed", "declined"):
            view.show_tool_error("Declined" if status == "declined" else "Not changed")
        elif kind == "mcpToolCall" and item.get("error"):
            view.show_tool_error(str((item["error"] or {}).get("message", "error")))

    def turn_completed(self, turn: dict) -> None:
        view = self.view
        status = turn.get("status")
        failure, self.failure = self.failure, ""
        if status == "interrupted":
            view.set_state("Stopped")
        elif status == "failed":
            view.set_state("")
            error = turn.get("error") or {}
            view.show_error(error.get("message") or failure or "Codex couldn't answer.")
        else:
            duration = turn.get("durationMs")
            view.set_state(f"Done ({duration / 1000:.1f} s)"
                           if isinstance(duration, (int, float)) else "Done")


def files_may_have_changed_claude(data: dict) -> bool:
    """Whether a Claude message means files may have changed (a tool's result,
    the end of an answer): the IDE looks at its files."""
    return data.get("type") in ("user", "result")


def files_may_have_changed_codex(data: dict) -> bool:
    params = data.get("params") or {}
    return data.get("method") == "turn/completed" or (
        data.get("method") == "item/completed" and (params.get("item") or {}).get("type") in
        ("commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"))
