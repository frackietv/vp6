"""The IDE's Codex window (a panel at the bottom, with Immediate) and its
chats (windows in the MDI area, next to the designers and code windows).

The panel and the chats share one ``codex app-server`` (``CodexServer``).
The panel says whether Codex is logged in (Log In opens ChatGPT's login in
the browser; the login is Codex's own and lasts) and lists the project
folder's sessions: New, Open, Rename, Delete, Refresh (as the Claude window,
which it is a kind of). A chat (``CodexChatWindow``) shows the conversation,
asks before Codex runs a command or changes files its mode doesn't allow,
and takes the next message.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from . import codex
from .claudepanel import ChatWindow, ClaudePanel, tool_summary
from .codex import (CodexChat, CodexServer, CodexSession, describe_account, find_codex,
                    list_params, session_of, user_text)

INSTALL_URL = "https://developers.openai.com/codex/cli"

_PAGES = 10  # (at most this many pages of 100 sessions listed)


def open_url(url: str) -> None:
    """Open the login page in the browser (the tests replace it)."""
    QDesktopServices.openUrl(QUrl(url))


class CodexPanel(ClaudePanel):
    """View > Codex Window. ``server``: the app-server it shares with the
    chats (its own if not given)."""

    NAME = "Codex"
    PRODUCT = "Codex"
    COMMAND = "codex"
    COMMAND_KEY = codex.COMMAND_KEY
    INSTALL_URL = INSTALL_URL

    def __init__(self, folder=None, server: CodexServer | None = None, parent=None):
        super().__init__(folder, parent)
        self.server = server if server is not None else CodexServer(parent=self)
        self.server.notification.connect(self._notified)
        self.login_id: str | None = None  # a login going on in the browser
        self.login_url = ""
        self._asking = False  # (account/read asked, not answered yet)
        self._listing = 0  # (the latest listing: older answers are dropped)

    def find_command(self) -> str | None:
        return find_codex()

    # -- the login --------------------------------------------------------------------------------
    def _ask_login(self, command: str) -> None:
        if self._asking:
            return
        self._asking = True
        self.server.request("account/read", {"refreshToken": False}, self._account_read,
                            self._account_failed)

    def _account_read(self, result: dict) -> None:
        self._asking = False
        if self.login_id is None:
            self._auth_checked(*describe_account(result))

    def _account_failed(self, message: str) -> None:
        self._asking = False
        self.logged_in = None
        self.status.setText(f"Codex: {message}")
        self.login_button.hide()

    def _login_clicked(self) -> None:
        if self.login_id is not None:
            self.cancel_login()
        else:
            super()._login_clicked()

    def log_in(self) -> None:
        """Log In: ChatGPT's login page in the browser; Codex notices when it's
        done (and keeps the login)."""
        if self.login_id is not None:
            if self.login_url:
                open_url(self.login_url)
            return
        self.server.request("account/login/start", {"type": "chatgpt"}, self._login_started,
                            self._account_failed)

    def _login_started(self, result: dict) -> None:
        self.login_id = result.get("loginId") or ""
        self.login_url = result.get("authUrl") or ""
        self.status.setText("Codex: log in in the browser (the login page has been opened)"
                            if self.login_url else "Codex: logging in…")
        self.login_button.setText("Cancel Login")
        self.login_button.show()
        if self.login_url:
            open_url(self.login_url)
        self.log_in_started()  # (and asked again now and then)

    def cancel_login(self) -> None:
        login_id, self.login_id = self.login_id, None
        if login_id:
            self.server.request("account/login/cancel", {"loginId": login_id})
        self._login_poll.stop()
        self.check_login()

    def _notified(self, method: str, params: dict) -> None:
        if method == "account/login/completed":
            self.login_id = None
            self._login_poll.stop()
            if not params.get("success") and params.get("error"):
                self.status.setText(f"Codex: the login failed: {params['error']}")
            self.check_login()
        elif method == "account/updated" and self.login_id is None:
            self.check_login()

    def _log_out(self, command: str) -> None:
        self.server.request("account/logout", {}, lambda _: self._logged_out(),
                            self._account_failed)

    def _logged_out(self) -> None:
        self.logged_in = None
        self.check_login()

    # -- the sessions -----------------------------------------------------------------------------
    def _list(self, folder: str) -> None:
        self._listing += 1
        self._page(folder, self._listing, [], None)

    def _page(self, folder: str, listing: int, found: list, cursor: str | None) -> None:
        def listed(result: dict):
            if listing != self._listing:
                return
            threads = [t for t in result.get("data") or [] if isinstance(t, dict)]
            sessions = found + [session_of(t) for t in threads]
            cursor = result.get("nextCursor")
            if cursor and len(sessions) < 100 * _PAGES:
                self._page(folder, listing, sessions, cursor)
            else:
                self.show_sessions(sorted(sessions, key=lambda s: s.modified, reverse=True))

        def failed(_message: str):
            if listing == self._listing:
                self.show_sessions([])
        self.server.request("thread/list", list_params(folder, cursor), listed, failed)

    def _tip(self, info: CodexSession) -> str:
        preview = info.preview if len(info.preview) <= 200 else info.preview[:197] + "…"
        return f"{info.title}\n{preview}\n{info.id}" if preview != info.title else \
            f"{info.title}\n{info.id}"

    def _rename(self, info: CodexSession, title: str) -> None:
        name = title.strip() or info.preview[:120]
        self.server.request("thread/name/set", {"threadId": info.id, "name": name},
                            lambda _: self.refresh(), self._failed("Rename Session"))

    def _delete(self, info: CodexSession) -> None:
        self.server.request("thread/delete", {"threadId": info.id}, lambda _: self.refresh(),
                            self._failed("Delete Session"))

    def _failed(self, title: str):
        def failed(message: str):
            QMessageBox.warning(self, title, f"Codex couldn't do it: {message}")
            self.refresh()
        return failed

    def end(self) -> None:
        """Stop checking the login and end the server (the IDE closing)."""
        super().end()
        self.server.end()


# -- a chat ------------------------------------------------------------------------------------

_CHANGE_KINDS = {"add": "Add", "delete": "Delete", "update": "Edit"}


def command_line(item: dict) -> str:
    """The command a commandExecution item runs (without the shell around it)."""
    actions = [a for a in item.get("commandActions") or [] if isinstance(a, dict)]
    if len(actions) == 1 and actions[0].get("command"):
        return actions[0]["command"]
    return item.get("command") or ""


class CodexChatWindow(ChatWindow):
    """A session with Codex (a ``CodexChat`` on the shared server)."""

    NAME = "Codex"
    PRODUCT = "Codex"
    MODES = [(mode, label) for mode, label, _approval, _sandbox in codex.MODES]
    MODE_KEY = codex.MODE_KEY
    COLORS = ("#7fd1b9", "#1a7f64")

    def __init__(self, server: CodexServer, folder: str, session: CodexSession | None = None,
                 parent=None):
        self._server = server
        self._failure = ""  # an error Codex gave up on, until its turn completes
        super().__init__(folder, session, parent)

    def _make_chat(self, folder: str, session: CodexSession | None):
        chat = CodexChat(self._server, folder, session.id if session else None,
                         mode=codex.default_mode(), parent=self)
        chat.resumed.connect(self._show_thread)
        return chat

    def _show_session(self, session: CodexSession) -> None:
        self.state.setText("Resuming the session…")
        self.chat.open()

    def _show_thread(self, thread: dict) -> None:
        """What was said before in the resumed session."""
        for turn in thread.get("turns") or []:
            for item in turn.get("items") or []:
                if isinstance(item, dict):
                    self._item_started(item, history=True)
                    self._item_completed(item, history=True)
        self.state.setText("Resumed: your next message goes on with this session")

    # -- showing messages -------------------------------------------------------------------------
    def show_message(self, data: dict) -> None:
        """Show one of the thread's notifications."""
        method = data.get("method")
        params = data.get("params") or {}
        if method == "vp6/threadLoaded":
            if params.get("model") and "Resum" not in self.state.text():
                self.state.setText(f"Model: {params['model']}")
        elif method == "item/started":
            self._item_started(params.get("item") or {})
        elif method == "item/completed":
            self._item_completed(params.get("item") or {})
        elif method == "error":
            message = (params.get("error") or {}).get("message") or "error"
            if params.get("willRetry"):
                self.state.setText(f"Retrying: {message}")
            else:
                self._failure = message
        elif method == "turn/completed":
            self._turn_completed(params.get("turn") or {})

    def _item_started(self, item: dict, history: bool = False) -> None:
        kind = item.get("type")
        if kind == "commandExecution":
            self._show_tool("Shell", tool_summary("Shell", {"command": command_line(item)}))
        elif kind == "fileChange":
            for change in item.get("changes") or []:
                path = change.get("path", "")
                if os.path.isabs(path) and path.startswith(self.chat.folder + os.sep):
                    path = os.path.relpath(path, self.chat.folder)
                what = (change.get("kind") or {}).get("type", "update")
                self._show_tool(_CHANGE_KINDS.get(what, "Edit"), path)
        elif kind == "mcpToolCall":
            arguments = item.get("arguments")
            self._show_tool(f"{item.get('server', '?')}/{item.get('tool', '?')}",
                            tool_summary("", arguments if isinstance(arguments, dict) else {}))
        elif kind == "dynamicToolCall":
            arguments = item.get("arguments")
            self._show_tool(item.get("tool", "?"),
                            tool_summary("", arguments if isinstance(arguments, dict) else {}))
        elif kind == "webSearch":
            self._show_tool("Search", item.get("query") or "")
        elif kind == "imageView":
            self._show_tool("View", item.get("path") or "")

    def _item_completed(self, item: dict, history: bool = False) -> None:
        kind = item.get("type")
        status = item.get("status")
        if kind == "agentMessage":
            if (item.get("text") or "").strip():
                self._show_text("assistant", item["text"].strip())
        elif kind == "userMessage" and history:
            text = user_text(item)
            if text:
                self._show_text("user", text)
        elif kind == "commandExecution":
            code = item.get("exitCode")
            if status == "declined":
                self._show_tool_error("Declined")
            elif status == "failed" or code not in (None, 0):
                output = (item.get("aggregatedOutput") or "").strip()
                lines = output.splitlines()
                self._show_tool_error(lines[-1] if lines else f"exit code {code}")
        elif kind == "fileChange" and status in ("failed", "declined"):
            self._show_tool_error("Declined" if status == "declined" else "Not changed")
        elif kind == "mcpToolCall" and item.get("error"):
            self._show_tool_error(str((item["error"] or {}).get("message", "error")))

    def _turn_completed(self, turn: dict) -> None:
        status = turn.get("status")
        failure, self._failure = self._failure, ""
        if status == "interrupted":
            self.state.setText("Stopped")
        elif status == "failed":
            self.state.setText("")
            error = turn.get("error") or {}
            self._show_error(error.get("message") or failure or "Codex couldn't answer.")
        else:
            duration = turn.get("durationMs")
            self.state.setText(f"Done ({duration / 1000:.1f} s)"
                               if isinstance(duration, (int, float)) else "Done")
