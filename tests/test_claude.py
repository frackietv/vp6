"""The IDE's Claude window and chats, with a stand-in for Claude Code (a script
speaking its stream-json and keeping transcripts as it does)."""

import json
import os
import sys
import time

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6.ide import claude
from vp6.ide.claude import (ClaudeChat, describe_time, find_claude, list_sessions,
                            parse_auth_status, project_key, sessions_folder)
from vp6.ide.claudepanel import ClaudeChatWindow, ClaudePanel, tool_summary
from vp6.ide.mainwindow import MainWindow, create_project

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in is a script")

FAKE = r'''#!PYTHON
import json, os, re, sys, uuid

config = os.environ["CLAUDE_CONFIG_DIR"]
flag = os.path.join(config, "logged-in")
args = sys.argv[1:]
if args[:1] == ["auth"]:
    if args[1] == "status":
        print(json.dumps({"loggedIn": os.path.exists(flag), "email": "ada@example.com",
                          "subscriptionType": "max"}))
        sys.exit(0 if os.path.exists(flag) else 1)
    if args[1] == "login":
        open(flag, "w").close()
        print("Login successful.")
    if args[1] == "logout" and os.path.exists(flag):
        os.remove(flag)
    sys.exit(0)
with open(os.path.join(config, "args.txt"), "a") as log:
    log.write(json.dumps(args) + "\n")
session = args[args.index("--resume") + 1] if "--resume" in args else str(uuid.uuid4())
folder = os.path.join(config, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.getcwd()))
os.makedirs(folder, exist_ok=True)
transcript = os.path.join(folder, session + ".jsonl")

def out(data):
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()

def keep(data):
    with open(transcript, "a") as file:
        file.write(json.dumps(dict(data, sessionId=session)) + "\n")

def say(text):
    message = {"type": "assistant", "session_id": session,
               "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
    keep(message)
    out(message)

out({"type": "system", "subtype": "init", "session_id": session, "model": "fake-model",
     "permissionMode": args[args.index("--permission-mode") + 1]})
for line in sys.stdin:
    data = json.loads(line)
    if data.get("type") != "user":
        continue
    text = data["message"]["content"][0]["text"]
    keep({"type": "user", "message": {"role": "user", "content": text}})
    if text.startswith("run "):
        out({"type": "control_request", "request_id": "r1", "request": {
            "subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": text[4:]}}})
        answer = json.loads(sys.stdin.readline())
        behavior = answer["response"]["response"]["behavior"]
        if behavior == "allow":
            out({"type": "assistant", "session_id": session, "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": answer["response"]["response"]["updatedInput"]}]}})
            say("ran " + text[4:])
        else:
            out({"type": "user", "session_id": session, "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                 "content": "Permission denied by the user"}]}})
            say("not allowed")
    elif text.startswith("edit "):  # edit FILE|OLD|NEW: as Claude's Edit tool does
        name, old, new = text[5:].split("|")
        with open(name) as file:
            content = file.read()
        tool = {"file_path": os.path.abspath(name), "old_string": old, "new_string": new}
        out({"type": "assistant", "session_id": session, "message": {"content": [
            {"type": "tool_use", "id": "t2", "name": "Edit", "input": tool}]}})
        with open(name + ".tmp", "w") as file:  # (written anew, then moved over it)
            file.write(content.replace(old, new))
        os.replace(name + ".tmp", name)
        out({"type": "user", "session_id": session, "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "edited"}]}})
        say("edited " + name)
    elif text == "slow":
        request = json.loads(sys.stdin.readline())
        say("interrupted" if request["request"]["subtype"] == "interrupt" else "?")
    elif text == "fail":
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": session,
             "result": "Invalid API key · Please run /login"})
        continue
    else:
        say("You said: **" + text + "**")
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "total_cost_usd": 0.0012, "duration_ms": 1500, "result": "done"})
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    path = tmp_path / "claude"
    path.write_text(FAKE.replace("PYTHON", sys.executable))
    path.chmod(0o755)
    monkeypatch.setenv("VP6_CLAUDE", str(path))
    return str(path)


def _logged_in():
    open(os.path.join(claude.config_dir(), "logged-in"), "w").close()


def _arguments():
    with open(os.path.join(claude.config_dir(), "args.txt")) as file:
        return [json.loads(line) for line in file]


def _transcript(folder, session_id, entries, modified=None):
    directory = sessions_folder(folder)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, session_id + ".jsonl")
    with open(path, "w") as file:
        for entry in entries:
            file.write(json.dumps(entry) + "\n")
    if modified is not None:
        os.utime(path, (modified, modified))
    return path


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _user(text, **more):
    return {"type": "user", "message": {"role": "user", "content": text}, **more}


def _assistant(text):
    return {"type": "assistant", "message": {"role": "assistant",
                                             "content": [{"type": "text", "text": text}]}}


# -- the sessions on disk -----------------------------------------------------------------------

def test_project_key_and_folder(tmp_path):
    assert project_key("/Users/ada/my project.v2") == "-Users-ada-my-project-v2"
    assert sessions_folder("/x/y") == os.path.join(claude.config_dir(), "projects", "-x-y")


def test_sessions_listed_with_their_titles(tmp_path):
    folder = str(tmp_path)
    _transcript(folder, "old", [
        _user("<command-name>/login</command-name>"),  # (Claude Code's own: not a title)
        _user("Caveat: the messages below were generated", isMeta=True),
        _user("Fix the   tab order\nof Form1"), _assistant("Done.")], modified=1000)
    _transcript(folder, "summed", [_user("first"), {"type": "summary", "summary": "Summed up"}],
                modified=2000)
    _transcript(folder, "named", [_user("a"), {"type": "custom-title", "customTitle": "Mine"}],
                modified=3000)
    _transcript(folder, "empty", [_user("<local-command-stdout>x</local-command-stdout>")])
    sessions = list_sessions(folder)
    assert [(s.id, s.title, s.messages) for s in sessions] == [
        ("named", "Mine", 1), ("summed", "Summed up", 1), ("old", "Fix the tab order of Form1", 2)]
    claude.rename_session("old", "Tab order")  # (the IDE's own name, before Claude Code's)
    assert list_sessions(folder)[-1].title == "Tab order"
    claude.rename_session("old", "")
    assert list_sessions(folder)[-1].title == "Fix the tab order of Form1"
    claude.delete_session(sessions[0])
    assert [s.id for s in list_sessions(folder)] == ["summed", "old"]
    assert list_sessions(str(tmp_path / "elsewhere")) == []


def test_transcript_messages(tmp_path):
    path = _transcript(str(tmp_path), "s", [
        {"type": "summary", "summary": "x"}, _user("hello"), _assistant("hi"),
        dict(_assistant("side"), isSidechain=True)])
    assert [m["type"] for m in claude.load_transcript(path)] == ["user", "assistant"]


def test_describe_time():
    now = time.mktime((2026, 10, 12, 18, 0, 0, 0, 0, -1))
    assert describe_time(now - 3600, now) == "17:00"
    assert describe_time(now - 86400 * 3, now) == "9 Oct 2026"


def test_auth_status():
    assert parse_auth_status(0, '{"loggedIn": true, "email": "a@b.c", "authMethod": '
                                '"claude.ai"}') == (True, "Logged in as a@b.c (claude.ai)")
    assert parse_auth_status(1, '{"loggedIn": false}') == (False, "Not logged in")
    assert parse_auth_status(0, "Logged in with an API key\n") == \
        (True, "Logged in with an API key")
    assert parse_auth_status(1, "error: unknown command") == (False, "Not logged in")


def test_finding_the_command(fake, tmp_path, monkeypatch):
    assert find_claude() == fake
    monkeypatch.setenv("VP6_CLAUDE", str(tmp_path / "missing"))
    assert find_claude() is None
    monkeypatch.delenv("VP6_CLAUDE")
    claude.ide_settings().setValue(claude.COMMAND_KEY, fake)  # (Locate…)
    assert find_claude() == fake


def test_tool_summary():
    assert tool_summary("Bash", {"command": "ls   -la", "description": "List"}) == "ls -la"
    assert tool_summary("Edit", {"file_path": "/a/b.py"}) == "/a/b.py"
    assert tool_summary("X", {}) == ""
    assert len(tool_summary("Bash", {"command": "x" * 500})) == 158


# -- a chat -------------------------------------------------------------------------------------

def test_a_chat_keeps_running_between_messages(qapp, fake, tmp_path):
    chat = ClaudeChat(str(tmp_path))
    messages, sessions = [], []
    chat.message.connect(messages.append)
    chat.sessionChanged.connect(sessions.append)
    assert chat.send("hello")
    assert chat.busy
    wait_for(lambda: not chat.busy)
    assert sessions and chat.session_id == sessions[0]
    assert [m["type"] for m in messages] == ["system", "assistant", "result"]
    process = chat.process
    assert chat.send("again")
    wait_for(lambda: not chat.busy)
    assert chat.process is process  # (the same Claude Code)
    assert "You said: **again**" in json.dumps(messages[-2])
    assert _arguments() == [["-p", "--input-format", "stream-json", "--output-format",
                             "stream-json", "--verbose", "--permission-prompt-tool", "stdio",
                             "--permission-mode", "default"]]
    chat.end()
    assert not chat.running
    # The next message resumes the session (in a new mode)
    chat.set_mode("acceptEdits")
    chat.send("third")
    wait_for(lambda: not chat.busy)
    assert _arguments()[-1][-3:] == ["acceptEdits", "--resume", sessions[0]]
    assert [s.messages for s in list_sessions(str(tmp_path))] == [6]
    chat.end()


def test_without_claude_code(qapp, tmp_path):
    chat = ClaudeChat(str(tmp_path))
    failures = []
    chat.failed.connect(failures.append)
    assert not chat.send("hello")
    assert "isn't installed" in failures[0]


def test_asking_before_using_a_tool(qapp, fake, tmp_path):
    window = ClaudeChatWindow(str(tmp_path))
    assert window.send("run ls")
    wait_for(lambda: window.question.isVisibleTo(window))
    assert "Bash" in window.question_text.text() and "ls" in window.question_text.text()
    window.answer(False)  # Deny
    wait_for(lambda: not window.chat.busy)
    text = window.transcript_text()
    assert "Denied: Bash" in text and "Permission denied by the user" in text
    assert "not allowed" in text
    window.send("run pwd")
    wait_for(lambda: window.question.isVisibleTo(window))
    window.answer(True, always=True)  # Always Allow
    wait_for(lambda: not window.chat.busy)
    assert "ran pwd" in window.transcript_text() and "▸ Bash pwd" in window.transcript_text()
    assert window.chat.allowed == {"Bash"}
    window.send("run date")  # (not asked again)
    wait_for(lambda: not window.chat.busy)
    assert not window.question.isVisibleTo(window) and "ran date" in window.transcript_text()
    window.end()
    window.deleteLater()


def test_the_chat_window(qapp, fake, tmp_path):
    window = ClaudeChatWindow(str(tmp_path))
    titles = []
    window.titleChanged.connect(titles.append)
    assert window.title == "New Claude Session"
    QTest.keyClicks(window.input, "Hello Claude")
    QTest.keyClick(window.input, Qt.Key_Return, Qt.ShiftModifier)  # (a new line)
    assert window.input.toPlainText() == "Hello Claude\n"
    QTest.keyClick(window.input, Qt.Key_Return)  # (sends)
    assert window.input.toPlainText() == "" and titles == ["Hello Claude"]
    assert window.send_button.text() == "Stop"
    wait_for(lambda: not window.chat.busy)
    assert window.send_button.text() == "Send"
    text = window.transcript_text()
    assert text.index("You") < text.index("Hello Claude") < text.index("Claude\n") \
        < text.index("You said: Hello Claude")  # (the Markdown made bold)
    assert "<b>Hello Claude</b>" in window.view.toHtml().replace(
        '<span style=" font-weight:700;">Hello Claude</span>', "<b>Hello Claude</b>")
    assert window.state.text() == "Done ($0.0012, 1.5 s)"
    window.send("fail")  # (an error, with a link to log in)
    wait_for(lambda: not window.chat.busy)
    assert "Invalid API key" in window.transcript_text()
    asked = []
    window.loginRequested.connect(lambda: asked.append(True))
    window._link_clicked(QUrl("vp6:login"))
    assert asked
    window.end()
    window.deleteLater()


def test_stop(qapp, fake, tmp_path):
    window = ClaudeChatWindow(str(tmp_path))
    window.send("slow")
    QTest.qWait(200)
    window.send_button.click()  # Stop: an interrupt request
    wait_for(lambda: not window.chat.busy)
    assert "interrupted" in window.transcript_text()
    window.end()
    window.deleteLater()


def test_a_resumed_session_shows_its_transcript(qapp, fake, tmp_path):
    folder = str(tmp_path)
    _transcript(folder, "abc", [_user("What is VP6?"), _assistant("A *VB6-like* IDE.")])
    session = list_sessions(folder)[0]
    window = ClaudeChatWindow(folder, session)
    assert window.title == "What is VP6?" and window.session_id == "abc"
    assert "A VB6-like IDE." in window.transcript_text()
    window.send("more")
    wait_for(lambda: not window.chat.busy)
    assert _arguments()[-1][-2:] == ["--resume", "abc"]
    window.end()
    window.deleteLater()


# -- the panel ----------------------------------------------------------------------------------

def test_the_panel_without_claude_code(qapp, tmp_path):
    panel = ClaudePanel(lambda: str(tmp_path))
    panel.refresh()
    assert "isn't installed" in panel.status.text()
    assert not panel.locate_button.isHidden() and panel.login_button.isHidden()
    panel.end()
    panel.deleteLater()


def test_the_panel(qapp, fake, tmp_path):
    folder = str(tmp_path)
    _transcript(folder, "one", [_user("First"), _assistant("a")], modified=1000)
    _transcript(folder, "two", [_user("Second"), _assistant("b")], modified=2000)
    panel = ClaudePanel(lambda: folder)
    panel.refresh()
    wait_for(lambda: panel.logged_in is not None)
    assert panel.logged_in is False and panel.login_button.text() == "Log In"
    assert panel.locate_button.isHidden()
    _logged_in()
    panel.refresh()
    wait_for(lambda: panel.logged_in)
    assert "Logged in as ada@example.com (max)" in panel.status.text()
    assert panel.login_button.text() == "Log Out"
    titles = [panel.tree.topLevelItem(i).text(0) for i in range(panel.tree.topLevelItemCount())]
    assert titles == ["Second", "First"]
    assert not panel.buttons["Open"].isEnabled()
    opened = []
    panel.openSession.connect(opened.append)
    panel.buttons["New"].click()
    panel.select("one")
    assert panel.buttons["Open"].isEnabled()
    panel.buttons["Open"].click()
    assert opened == ["", "one"]
    panel.rename_selected("Renamed")
    assert panel.selected().title == "Renamed"  # (still selected)
    menu = panel._context_menu()
    assert [a.text() for a in menu.actions() if a.text()] == \
        ["New", "Open", "Rename", "Delete", "Refresh"]
    menu.deleteLater()
    panel.delete_selected(confirm=False)
    assert [s.id for s in panel.sessions] == ["two"]
    panel.end()
    panel.deleteLater()


# -- in the IDE ---------------------------------------------------------------------------------

@pytest.fixture
def window(qapp):
    w = MainWindow()
    w.show()
    yield w
    w.close_project()
    w.close()


def test_hidden_by_default_next_to_the_immediate_window(window):
    assert window.claude_dock.isHidden() and window.claude_dock.windowTitle() == "Claude"
    assert window.act_view_claude in window.view_menu.actions()
    window.act_view_claude.trigger()
    assert not window.claude_dock.isHidden()
    assert window.claude_dock in window.tabifiedDockWidgets(window.immediate_dock)
    window.reset_layout()
    assert window.claude_dock.isHidden()


def test_sessions_open_in_the_mdi_area(window, fake, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = window.project.directory
    window.show_claude()
    assert window.claude_panel.folder() == folder
    chat = window.open_claude_session()
    sub = window.mdi.activeSubWindow()
    assert sub.widget() is chat and sub.windowTitle() == "New Claude Session"
    chat.send("Make a form")
    wait_for(lambda: not chat.chat.busy)
    assert sub.windowTitle() == "Make a form"
    assert chat.chat.process.workingDirectory() == folder
    wait_for(lambda: window.claude_panel.sessions)  # (listed once it replied)
    session_id = window.claude_panel.sessions[0].id
    assert session_id == chat.session_id
    window.view_code(next(iter(window.documents)))
    assert window.open_claude_session(session_id) is chat  # (the one open)
    assert window.mdi.activeSubWindow() is sub
    # Edit > Copy and Select All in the conversation
    chat.view.setFocus()
    window.act_select_all.trigger()
    window.act_copy.trigger()
    assert "Make a form" in QApplication.clipboard().text()
    pid = chat.chat.process.processId()
    window.close_project()  # (its chats close: Claude Code ends)
    assert not window.claude_windows() and not _alive(pid)


def test_closing_a_chat_window_ends_claude_code(window, fake):
    chat = window.open_claude_session()
    chat.send("hi")
    wait_for(lambda: not chat.chat.busy)
    pid = chat.chat.process.processId()
    window.mdi.activeSubWindow().close()
    assert not window.claude_windows() and not _alive(pid)


def test_log_in_from_the_ide(window, fake):
    window.show_claude()
    wait_for(lambda: window.claude_panel.logged_in is False)
    window.claude_panel.login_button.click()  # Log In: in the Terminal window
    assert not window.terminal_dock.isHidden()
    wait_for(lambda: "Login successful." in window.terminal.terminal._screen.text())
    wait_for(lambda: window.claude_panel.logged_in, 10000)  # (checked again until done)
    assert window.claude_panel.login_button.text() == "Log Out"
    assert not window.claude_panel._login_poll.isActive()


def test_screenshot(window, fake, tmp_path):
    window.resize(1000, 700)
    window.show_claude()
    chat = window.open_claude_session()
    chat.send("run ls")
    wait_for(lambda: chat.question.isVisibleTo(chat))
    QTest.qWait(50)
    image = chat.grab().toImage()
    assert image.width() > 300 and image.height() > 200
    chat.answer(True)
    wait_for(lambda: not chat.chat.busy)



# -- files Claude changes -----------------------------------------------------------------------

BUTTON = ("        self.Command1 = CommandButton(self, Caption='Go', Left=16, Top=16, Width=90, "
          "Height=30)\n")


def test_sessions_files_changed_by_claude_shown_at_once(window, fake, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    path = window.project.abspath("Form1.py")
    designer = window.view_object(path)
    code = window.view_code(path)
    doc = window.documents[path]
    code.editor.textCursor().insertText("")  # (the code window open, its cursor at the top)
    doc.replace_text(doc.text.replace("pass", "self.Caption = 'Mine'"))  # (not saved)
    assert doc.modified
    chat = window.open_claude_session()
    chat.send("edit Form1.py|self.Height = 360|self.Height = 360\n" + BUTTON.rstrip())
    assert not doc.modified  # (saved before Claude got the message)
    wait_for(lambda: not chat.chat.busy)
    wait_for(lambda: "Command1" in designer.controls)  # the designer...
    assert designer.controls["Command1"].Caption == "Go"
    assert "CommandButton(self, Caption='Go'" in code.editor.toPlainText()  # ...the code
    assert "self.Caption = 'Mine'" in doc.text and not doc.modified
    doc.text_document.undo()  # (Claude's change can be undone)
    wait_for(lambda: "Command1" not in designer.controls)
    doc.text_document.setModified(False)  # (closing the project would ask to save it)


def test_files_changed_by_another_program(window, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    path = window.project.abspath("Form1.py")
    designer = window.view_object(path)
    doc = window.documents[path]
    assert window.check_disk_changes() == []
    doc.save()  # (its own save isn't a change)
    assert window.check_disk_changes() == []
    with open(path, "w") as file:
        file.write(doc.text.replace("self.Height = 360\n", "self.Height = 360\n" + BUTTON))
    wait_for(lambda: "Command1" in designer.controls)  # (the watcher: no call needed)
    assert not doc.modified


def test_a_file_changed_here_and_on_disk(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    path = window.project.abspath("Module1.py")
    doc = window.documents[path]
    window._disk_check.timeout.disconnect(window.check_disk_changes)  # (called here only)
    doc.replace_text(doc.text + "\n# mine\n")
    answers = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: answers.pop(0) if answers else QMessageBox.No)
    with open(path, "a") as file:
        file.write("# theirs\n")
    os.utime(path, (1, 1))
    assert window.check_disk_changes() == []  # No: kept
    assert "# mine" in doc.text and doc.modified
    with open(path, "a") as file:
        file.write("# again\n")
    answers.append(QMessageBox.Yes)
    assert window.check_disk_changes() == [path]  # Yes: read again
    assert "# mine" not in doc.text and "# again" in doc.text and not doc.modified


def test_reloading_replaces_only_what_changed(qapp, tmp_path):
    from PySide6.QtGui import QTextCursor

    from vp6.ide.documents import Document

    path = tmp_path / "m.py"
    path.write_text("# 🙂 smile\na = 1\nb = 2\nc = 3\n")
    doc = Document(str(path))
    doc.set_breakpoint(4, True)
    cursor = QTextCursor(doc.text_document)
    cursor.setPosition(doc.text_document.findBlockByNumber(3).position() + 2)  # (in "c = 3")
    path.write_text("# 🙂 smile\na = 1\nb = 22\nb2 = 0\nc = 3\n")
    assert doc.changed_on_disk()
    assert doc.reload()
    assert doc.text == "# 🙂 smile\na = 1\nb = 22\nb2 = 0\nc = 3\n" and not doc.modified
    assert cursor.block().text() == "c = 3" and cursor.positionInBlock() == 2  # (kept)
    assert doc.breakpoint_lines() == [5]  # (it followed its line)
    assert not doc.changed_on_disk() and not doc.reload()  # (nothing more)
    doc.text_document.undo()
    assert doc.text == "# 🙂 smile\na = 1\nb = 2\nc = 3\n"
