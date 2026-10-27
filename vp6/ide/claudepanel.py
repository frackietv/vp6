"""The IDE's Claude window (a panel at the bottom, with Immediate) and its
chats (windows in the MDI area, next to the designers and code windows).

The panel says whether Claude Code is logged in (Log In runs ``claude auth
login`` in the Terminal window; the login is Claude Code's own and lasts) and
lists the project folder's sessions: New, Open, Rename, Delete, Refresh. A
chat (``ClaudeChatWindow``) shows the conversation, asks before Claude uses a
tool, and takes the next message (Enter; Shift+Enter for a new line).
"""

from __future__ import annotations

import html
import json
import os

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import claude
from .claude import (PERMISSION_MODES, AuthStatus, ClaudeChat, SessionInfo, describe_time,
                     find_claude, list_sessions)
from .logic.chats import ClaudeMessages, login_hint, tool_summary  # noqa: F401
from .theme import ide_settings, theme_manager

INSTALL_URL = "https://docs.anthropic.com/en/docs/claude-code/setup"


class ClaudePanel(QWidget):
    """View > Claude Window. ``folder`` gives the project's folder (None: the
    home folder's sessions). (The Codex window is a subclass.)"""

    NAME = "Claude"
    PRODUCT = "Claude Code"
    COMMAND = "claude"
    COMMAND_KEY = claude.COMMAND_KEY
    INSTALL_URL = INSTALL_URL

    openSession = Signal(str)  # a session's id; "" for a new one
    loginRequested = Signal()  # Log In: run ``claude auth login`` where it can be answered

    def __init__(self, folder=None, parent=None):
        super().__init__(parent)
        self._folder = folder
        self.logged_in: bool | None = None  # (None: not known yet)
        self.sessions: list[SessionInfo] = []
        self._listed_folder: str | None = None
        self.auth = AuthStatus(self)
        self.auth.checked.connect(self._auth_checked)
        # After Log In: asked again every few seconds until logged in
        self._login_poll = QTimer(self)
        self._login_poll.setInterval(3000)
        self._login_poll.timeout.connect(self.check_login)
        self._login_polls = 0

        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.status.setOpenExternalLinks(True)
        self.status.setWordWrap(True)
        self.login_button = QPushButton("Log In")
        self.login_button.clicked.connect(self._login_clicked)
        self.locate_button = QPushButton("Locate…")
        self.locate_button.setToolTip(f"Choose the {self.COMMAND} command")
        self.locate_button.clicked.connect(lambda: self.locate_command())
        top = QHBoxLayout()
        top.setContentsMargins(6, 4, 6, 0)
        top.addWidget(self.status, 1)
        top.addWidget(self.locate_button)
        top.addWidget(self.login_button)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Session", "Changed"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemActivated.connect(lambda *_: self.open_selected())
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        self.buttons: dict[str, QToolButton] = {}
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for text, slot, tip in (
                ("New", self.new_session, f"Start a new session with {self.NAME}"),
                ("Open", self.open_selected, "Go on with the session selected"),
                ("Rename", self.rename_selected, "Name the session selected"),
                ("Delete", self.delete_selected, "Delete the session selected"),
                ("Refresh", self.refresh, "List the sessions and check the login again")):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(lambda *_, s=slot: s())
            row.addWidget(button)
            self.buttons[text] = button
        row.addStretch(1)
        self.where = QLabel()
        self.where.setEnabled(False)  # (dimmed)
        row.addWidget(self.where)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(top)
        layout.addLayout(row)
        layout.addWidget(self.tree, 1)
        self._update_buttons()

    def folder(self) -> str:
        folder = self._folder() if self._folder is not None else None
        return folder if folder and os.path.isdir(folder) else os.path.expanduser("~")

    # -- the login --------------------------------------------------------------------------------
    def find_command(self) -> str | None:
        return find_claude()

    def check_login(self) -> None:
        command = self.find_command()
        self.locate_button.setVisible(command is None)
        if command is None:
            self._login_poll.stop()
            self.logged_in = None
            self.status.setText(f"{self.PRODUCT} isn't installed: the {self.COMMAND} command "
                                f"wasn't found. <a href='{self.INSTALL_URL}'>Install it</a>, "
                                f"then Refresh, or locate it.")
            self.login_button.hide()
            return
        if self.logged_in is None:
            self.status.setText(f"{self.PRODUCT}: checking the login…")
        self._ask_login(command)

    def _ask_login(self, command: str) -> None:
        self.auth.check(command)

    def _auth_checked(self, logged_in: bool, text: str) -> None:
        self.logged_in = logged_in
        self.status.setText(html.escape(f"{self.PRODUCT}: {text}"))
        self.login_button.setText("Log Out" if logged_in else "Log In")
        self.login_button.show()
        self._login_polls += 1
        if logged_in or self._login_polls > 200:  # (10 minutes)
            self._login_poll.stop()

    def _login_clicked(self) -> None:
        if self.logged_in:
            self.log_out()
        else:
            self.log_in()

    def log_in(self) -> None:
        """Log In: the IDE runs ``claude auth login`` in the Terminal window
        (and then calls ``log_in_started``)."""
        self.loginRequested.emit()

    def log_in_started(self) -> None:
        """Check the login again every few seconds until it's done."""
        self._login_polls = 0
        self._login_poll.start()

    def log_out(self, confirm: bool = True) -> None:
        command = self.find_command()
        if command is None:
            return
        if confirm and QMessageBox.question(
                self, self.NAME, f"Log {self.PRODUCT} out? Every project and session uses "
                f"its login.") != QMessageBox.Yes:
            return
        self._log_out(command)

    def _log_out(self, command: str) -> None:
        claude.log_out(command)
        self.logged_in = None
        self.check_login()

    def locate_command(self, path: str | None = None) -> None:
        """Choose the claude (or codex) command (remembered)."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, f"Locate the {self.COMMAND} Command",
                                                  os.path.expanduser("~"))
        if path:
            ide_settings().setValue(self.COMMAND_KEY, path)
            self.refresh()

    # -- the sessions -----------------------------------------------------------------------------
    def refresh(self) -> None:
        """List the folder's sessions again (keeping the one selected) and check
        the login."""
        folder = self.folder()
        self._listed_folder = folder
        self.where.setText(os.path.basename(folder.rstrip(os.sep)) or folder)
        self.where.setToolTip(folder)
        self._list(folder)
        self.check_login()

    def _list(self, folder: str) -> None:
        self.show_sessions(list_sessions(folder))

    def show_sessions(self, sessions: list) -> None:
        """List these sessions (keeping the one selected)."""
        selected = self.selected()
        self.sessions = sessions
        self.tree.clear()
        for info in self.sessions:
            item = QTreeWidgetItem([info.title, describe_time(info.modified)])
            item.setData(0, Qt.UserRole, info.id)
            item.setToolTip(0, self._tip(info))
            self.tree.addTopLevelItem(item)
            if selected is not None and info.id == selected.id:
                self.tree.setCurrentItem(item)
        self._update_buttons()

    def _tip(self, info: SessionInfo) -> str:
        return f"{info.title}\n{info.messages} messages\n{info.id}"

    def refresh_if_moved(self) -> None:
        """Refresh if the project's folder isn't the one listed."""
        if self.folder() != self._listed_folder:
            self.refresh()

    def selected(self) -> SessionInfo | None:
        item = self.tree.currentItem()
        if item is None or not item.isSelected():
            return None
        session_id = item.data(0, Qt.UserRole)
        return next((s for s in self.sessions if s.id == session_id), None)

    def select(self, session_id: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == session_id:
                self.tree.setCurrentItem(item)
                return

    def new_session(self) -> None:
        self.openSession.emit("")

    def open_selected(self) -> None:
        info = self.selected()
        if info is not None:
            self.openSession.emit(info.id)

    def rename_selected(self, title: str | None = None) -> None:
        info = self.selected()
        if info is None:
            return
        if title is None:
            title, ok = QInputDialog.getText(self, "Rename Session", "Name:", text=info.title)
            if not ok:
                return
        self._rename(info, title)

    def _rename(self, info: SessionInfo, title: str) -> None:
        claude.rename_session(info.id, title)
        self.refresh()

    def delete_selected(self, confirm: bool = True) -> None:
        info = self.selected()
        if info is None:
            return
        if confirm and QMessageBox.question(
                self, "Delete Session", f"Delete the session “{info.title}”? Its "
                "transcript is deleted and it can't be resumed.") != QMessageBox.Yes:
            return
        self._delete(info)

    def _delete(self, info: SessionInfo) -> None:
        try:
            claude.delete_session(info)
        except OSError as exc:
            QMessageBox.warning(self, "Delete Session", f"Can't delete the session: {exc}")
        self.refresh()

    def _update_buttons(self) -> None:
        chosen = self.selected() is not None
        for name in ("Open", "Rename", "Delete"):
            self.buttons[name].setEnabled(chosen)

    def _context_menu(self) -> QMenu:
        menu = QMenu(self)
        for name in ("New", "Open", "Rename", "Delete", None, "Refresh"):
            if name is None:
                menu.addSeparator()
                continue
            button = self.buttons[name]
            action = menu.addAction(name, button.click)
            action.setEnabled(button.isEnabled())
        return menu

    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is not None:
            self.tree.setCurrentItem(item)
        menu = self._context_menu()
        menu.exec(self.tree.viewport().mapToGlobal(pos))
        menu.deleteLater()

    def end(self) -> None:
        """Stop checking the login (the IDE closing)."""
        self._login_poll.stop()
        self.auth.cancel()

    def showEvent(self, event):
        super().showEvent(event)
        if self._listed_folder is None:  # the first time it's shown
            self.refresh()
        else:
            self.refresh_if_moved()


# -- a chat ------------------------------------------------------------------------------------

class ChatWindow(QWidget):
    """A session with an assistant, in the MDI area: the conversation, a
    question about using a tool when it asks one, and the message box. A
    subclass makes the ``chat`` (``_make_chat``), shows what it says
    (``show_message``) and what was said before (``_show_session``)."""

    NAME = ""  # the assistant's name, as the conversation shows it
    PRODUCT = ""  # the program that does the work (logged in to)
    MODES: list[tuple[str, str]] = []  # (mode, what the IDE calls it)
    MODE_KEY = ""  # the setting: the mode of new chats
    COLORS = ("#e8a07a", "#b5532e")  # the assistant's name: dark, light

    titleChanged = Signal(str)
    sessionChanged = Signal(str)  # its session's id (a new one: once it's given)
    replied = Signal()  # a reply finished (the session list may have changed)
    loginRequested = Signal()
    sending = Signal()  # a message is about to go (the IDE saves its files)

    def __init__(self, folder: str, session=None, parent=None):
        super().__init__(parent)
        self.chat = self._make_chat(folder, session)
        self.chat.message.connect(self.show_message)
        self.chat.sessionChanged.connect(self.sessionChanged)
        self.chat.busyChanged.connect(self._busy_changed)
        self.chat.permissionRequested.connect(self._permission_requested)
        self.chat.failed.connect(self._failed)
        self.new_title = f"New {self.NAME} Session"
        self.title = session.title if session else self.new_title
        self._speaker: str | None = None  # who wrote the last block shown
        self._questions: list[tuple[str, str, dict]] = []  # waiting to be answered

        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link_clicked)
        self.view.document().setDocumentMargin(10)

        self.question = QFrame()
        self.question.setFrameShape(QFrame.StyledPanel)
        self.question_text = QLabel()
        self.question_text.setWordWrap(True)
        self.question_text.setTextFormat(Qt.RichText)
        self.allow_button = QPushButton("Allow")
        self.always_button = QPushButton("Always Allow")
        self.always_button.setToolTip("Allow this tool for the rest of the session")
        self.deny_button = QPushButton("Deny")
        self.allow_button.clicked.connect(lambda: self.answer(True))
        self.always_button.clicked.connect(lambda: self.answer(True, always=True))
        self.deny_button.clicked.connect(lambda: self.answer(False))
        question = QHBoxLayout(self.question)
        question.setContentsMargins(8, 4, 8, 4)
        question.addWidget(self.question_text, 1)
        for button in (self.allow_button, self.always_button, self.deny_button):
            question.addWidget(button)
        self.question.hide()

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(f"Ask {self.NAME}… (Enter sends, Shift+Enter starts a "
                                      f"new line)")
        self.input.setTabChangesFocus(True)
        self.input.setFixedHeight(72)
        self.input.installEventFilter(self)
        self.send_button = QPushButton("Send")
        self.send_button.setDefault(False)
        self.send_button.clicked.connect(self._send_clicked)
        self.mode = QComboBox()
        for mode, label in self.MODES:
            self.mode.addItem(label, mode)
        self.mode.setCurrentIndex(max(self.mode.findData(self.chat.mode), 0))
        self.mode.setToolTip(f"What {self.NAME} may do without asking")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.state = QLabel()
        self.state.setEnabled(False)  # (dimmed)

        entry = QHBoxLayout()
        entry.addWidget(self.input, 1)
        side = QVBoxLayout()
        side.addWidget(self.send_button)
        side.addStretch(1)
        entry.addLayout(side)
        bottom = QHBoxLayout()
        bottom.addWidget(self.mode)
        bottom.addWidget(self.state, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.question)
        layout.addLayout(entry)
        layout.addLayout(bottom)
        self.setFocusProxy(self.input)

        self.apply_theme()
        if session is not None:
            self._show_session(session)
        theme_manager().changed.connect(self.apply_theme)

    def _make_chat(self, folder: str, session):
        raise NotImplementedError

    def _show_session(self, session) -> None:
        """Show what was said before in a resumed session."""

    @property
    def session_id(self) -> str | None:
        return self.chat.session_id

    # -- sending ----------------------------------------------------------------------------------
    def send(self, text: str) -> bool:
        text = text.strip()
        if not text or self.chat.busy:
            return False
        if self.title == self.new_title:
            self.set_title(" ".join(text.split())[:60])
        self.sending.emit()
        self._show_text("user", text)
        return self.chat.send(text)

    def _send_clicked(self) -> None:
        if self.chat.busy:
            self.chat.stop()
            self.state.setText("Stopping…")
        elif self.send(self.input.toPlainText()):
            self.input.clear()

    def eventFilter(self, watched, event):
        if watched is self.input and event.type() == QEvent.KeyPress and \
                event.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                not event.modifiers() & Qt.ShiftModifier:
            if not self.chat.busy:
                self._send_clicked()
            return True
        return super().eventFilter(watched, event)

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        self.chat.set_mode(mode)
        ide_settings().setValue(self.MODE_KEY, mode)  # (new chats start in it too)

    def _busy_changed(self, busy: bool) -> None:
        self.send_button.setText("Stop" if busy else "Send")
        if busy:
            self.state.setText(f"{self.NAME} is working…")
        else:
            self.replied.emit()

    # -- showing messages (the view ``logic.chats`` shows them in) --------------------------------
    def show_message(self, data: dict) -> None:
        """Show one of the chat's messages (live, or from what was said before)."""
        self.messages.show_message(data)

    def show_text(self, who: str, text: str) -> None:
        self._show_text(who, text)

    def show_tool(self, name: str, summary: str) -> None:
        self._show_tool(name, summary)

    def show_tool_error(self, text: str) -> None:
        self._show_tool_error(text)

    def show_error(self, text: str) -> None:
        self._show_error(text)

    def set_state(self, text: str) -> None:
        self.state.setText(text)

    def state_text(self) -> str:
        return self.state.text()

    def _show_text(self, who: str, text: str) -> None:
        if who == "user":
            body = "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"
        else:
            from vp6help.markdown import to_html
            body = to_html(text)
        self._append(who, body)

    def _show_tool(self, name: str, summary: str) -> None:
        self._append("assistant", f"<p style='color:{self._dim}'>&#9656; "
                     f"<b>{html.escape(name)}</b> {html.escape(summary)}</p>")

    def _show_tool_error(self, text: str) -> None:
        first = (text.strip().splitlines() or [""])[0][:200]
        self._append("assistant", f"<p style='color:{self._error}'>&nbsp;&nbsp;"
                     f"&#8627; {html.escape(first)}</p>")

    def _show_error(self, text: str) -> None:
        body = html.escape(text).replace("\n", "<br>")
        hint = ""
        if login_hint(text):
            hint = f" <a href='vp6:login'>Log in to {html.escape(self.PRODUCT)}</a>"
        self._append("error", f"<p style='color:{self._error}'>{body}{hint}</p>")

    def _failed(self, text: str) -> None:
        self.state.setText("")
        self._show_error(text)

    def _append(self, who: str, body: str) -> None:
        if who != self._speaker and who in ("user", "assistant"):
            name = "You" if who == "user" else self.NAME
            color = self._you if who == "user" else self._assistant
            self.view.append(f"<p style='margin-top:10px'><b style='color:{color}'>{name}"
                             f"</b></p>")
        if who in ("user", "assistant"):
            self._speaker = who
        self.view.append(body)
        if "vp6math:" in body:  # (formulas in the answer: drawn)
            from vp6help import texdraw
            texdraw.install(self.view.document())
        self.view.moveCursor(QTextCursor.End)
        self.view.ensureCursorVisible()

    def _link_clicked(self, url) -> None:
        if url.toString() == "vp6:login":
            self.loginRequested.emit()
        else:
            QDesktopServices.openUrl(url)

    def transcript_text(self) -> str:
        return self.view.toPlainText()

    # -- questions about tools --------------------------------------------------------------------
    def _permission_requested(self, request_id: str, tool: str, tool_input: dict) -> None:
        self._questions.append((request_id, tool, tool_input))
        if len(self._questions) == 1:
            self._ask()

    def _ask(self) -> None:
        if not self._questions:
            self.question.hide()
            return
        _, tool, tool_input = self._questions[0]
        summary = tool_summary(tool, tool_input) or json.dumps(tool_input)[:160]
        self.question_text.setText(f"{self.NAME} wants to use <b>{html.escape(tool)}</b>: "
                                   f"<code>{html.escape(summary)}</code>")
        self.question.show()
        self.allow_button.setFocus()

    def answer(self, allow: bool, always: bool = False) -> None:
        """Answer the question shown (Allow, Always Allow, Deny)."""
        if not self._questions:
            return
        request_id, tool, tool_input = self._questions.pop(0)
        self.chat.answer(request_id, allow, tool_input, always=tool if always else None)
        if always:  # the others about the same tool too
            for question in [q for q in self._questions if q[1] == tool]:
                self._questions.remove(question)
                self.chat.answer(question[0], True, question[2])
        self._append("assistant", f"<p style='color:{self._dim}'>&nbsp;&nbsp;"
                     f"{'Allowed' if allow else 'Denied'}: {html.escape(tool)}</p>")
        self._ask()
        if not self._questions:
            self.input.setFocus()

    # -- the window -------------------------------------------------------------------------------
    def set_title(self, title: str) -> None:
        self.title = title
        self.titleChanged.emit(title)

    def apply_theme(self) -> None:
        dark = theme_manager().app_is_dark()
        self._dim = "#9a9a9a" if dark else "#707070"
        self._error = "#ff6b6b" if dark else "#c62828"
        self._you = "#6cb6ff" if dark else "#1f5fbf"
        self._assistant = self.COLORS[0] if dark else self.COLORS[1]

    def end(self) -> None:
        """End the chat (also when the window closes)."""
        self.chat.end()

    def closeEvent(self, event):
        self.end()
        super().closeEvent(event)


class ClaudeChatWindow(ChatWindow):
    """A session with Claude (``claude -p``, a ``ClaudeChat``)."""

    NAME = "Claude"
    PRODUCT = "Claude Code"
    MODES = PERMISSION_MODES
    MODE_KEY = claude.MODE_KEY

    def _make_chat(self, folder: str, session: SessionInfo | None):
        self.messages = ClaudeMessages(self)
        return ClaudeChat(folder, session.id if session else None, mode=claude.default_mode(),
                          parent=self)

    def _show_session(self, session: SessionInfo) -> None:
        self.messages.show_transcript(session.path)
