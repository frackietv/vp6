"""The IDE's Codex window and chats, with a stand-in for ``codex app-server``
(a script speaking its JSON-RPC, keeping threads and a login as it does)."""

import json
import os
import sys

import pytest
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6.ide import codex, codexpanel
from vp6.ide.codex import (CodexChat, CodexServer, describe_account, find_codex, list_params,
                           mode_policies, session_of)
from vp6.ide.codexpanel import CodexChatWindow, CodexPanel, command_line
from vp6.ide.mainwindow import MainWindow, create_project

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in is a script")

FAKE = r'''#!PYTHON
import json, os, sys, time, uuid

home = os.environ["CODEX_HOME"]
flag = os.path.join(home, "logged-in")
threads = os.path.join(home, "threads")
os.makedirs(threads, exist_ok=True)
if sys.argv[1:] != ["app-server"]:
    sys.exit(2)
waiting = []  # (read while waiting for an answer)

def out(data):
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()

def notify(method, params):
    out({"method": method, "params": params})

def log(data):
    with open(os.path.join(home, "requests.txt"), "a") as file:
        file.write(json.dumps(data) + "\n")

def path(thread_id):
    return os.path.join(threads, thread_id + ".json")

def load(thread_id):
    with open(path(thread_id)) as file:
        return json.load(file)

def save(thread):
    with open(path(thread["id"]), "w") as file:
        json.dump(thread, file)

def bare(thread):
    return dict(thread, turns=[])

def read():
    if waiting:
        return waiting.pop(0)
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    return json.loads(line)

def ask(method, params):
    """A request to the IDE: its answer."""
    request_id = "s-" + uuid.uuid4().hex[:6]
    out({"id": request_id, "method": method, "params": params})
    while True:
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        data = json.loads(line)
        if data.get("id") == request_id and "method" not in data:
            log({"answer": data.get("result")})
            return data.get("result") or {}
        waiting.append(data)

def item(thread, turn, items, data):
    notify("item/started", {"threadId": thread, "turnId": turn, "item": data})
    notify("item/completed", {"threadId": thread, "turnId": turn, "item": data})
    items.append(data)

def say(thread, turn, items, text):
    item(thread, turn, items, {"type": "agentMessage", "id": uuid.uuid4().hex, "text": text})

def turn(request_id, params):
    thread_id = params["threadId"]
    thread = load(thread_id)
    text = params["input"][0]["text"]
    turn_id = "turn-" + uuid.uuid4().hex[:6]
    out({"id": request_id, "result": {"turn": {"id": turn_id, "status": "inProgress",
                                               "items": []}}})
    notify("turn/started", {"threadId": thread_id, "turn": {"id": turn_id}})
    items = []
    item(thread_id, turn_id, items, {"type": "userMessage", "id": uuid.uuid4().hex,
                                     "content": [{"type": "text", "text": text}]})
    thread["preview"] = thread["preview"] or text
    status, error = "completed", None
    if text.startswith("run "):
        answer = ask("item/commandExecution/requestApproval", {
            "threadId": thread_id, "turnId": turn_id, "itemId": "c1", "command": text[4:],
            "reason": "outside the sandbox"})
        allowed = answer.get("decision") in ("accept", "acceptForSession")
        item(thread_id, turn_id, items, {
            "type": "commandExecution", "id": "c1", "command": "/bin/sh -lc " + text[4:],
            "commandActions": [{"type": "unknown", "command": text[4:]}],
            "status": "completed" if allowed else "declined", "exitCode": 0 if allowed else None,
            "aggregatedOutput": ""})
        say(thread_id, turn_id, items, "ran " + text[4:] if allowed else "not allowed")
    elif text.startswith(("edit ", "askedit ")):  # edit FILE|OLD|NEW
        name, old, new = text.split(" ", 1)[1].split("|")
        change = {"type": "fileChange", "id": "f1", "status": "inProgress", "changes": [
            {"path": os.path.abspath(name), "kind": {"type": "update", "move_path": None},
             "diff": ""}]}
        notify("item/started", {"threadId": thread_id, "turnId": turn_id, "item": change})
        allowed = True
        if text.startswith("askedit "):
            answer = ask("item/fileChange/requestApproval", {
                "threadId": thread_id, "turnId": turn_id, "itemId": "f1"})
            allowed = answer.get("decision") in ("accept", "acceptForSession")
        if allowed:
            with open(name) as file:
                content = file.read()
            with open(name + ".tmp", "w") as file:  # (written anew, then moved over it)
                file.write(content.replace(old, new))
            os.replace(name + ".tmp", name)
        change = dict(change, status="completed" if allowed else "declined")
        notify("item/completed", {"threadId": thread_id, "turnId": turn_id, "item": change})
        items.append(change)
        say(thread_id, turn_id, items, ("edited " if allowed else "left ") + name)
    elif text == "slow":
        while True:
            data = read()
            if data.get("method") == "turn/interrupt":
                log(data)
                out({"id": data["id"], "result": {}})
                break
            waiting.append(data)
        status = "interrupted"
    elif text == "fail":
        error = {"message": "Your access token could not be refreshed. Please log in again."}
        notify("error", {"threadId": thread_id, "turnId": turn_id, "error": error,
                         "willRetry": False})
        status = "failed"
    elif text == "crash":
        sys.stderr.write("fake codex crashed\n")
        sys.exit(3)
    else:
        say(thread_id, turn_id, items, "You said: **" + text + "**")
    thread["turns"].append({"id": turn_id, "items": items, "status": status})
    thread["updatedAt"] = time.time()
    save(thread)
    notify("turn/completed", {"threadId": thread_id, "turn": {
        "id": turn_id, "items": [], "status": status, "error": error, "durationMs": 1500}})

while True:
    data = read()
    method, params, request_id = data.get("method"), data.get("params") or {}, data.get("id")
    if request_id is None:
        continue  # (initialized)
    log(data)
    result = {}
    if method == "initialize":
        result = {"userAgent": "fake", "codexHome": home}
    elif method == "account/read":
        result = {"account": {"type": "chatgpt", "email": "ada@example.com",
                              "planType": "plus"} if os.path.exists(flag) else None,
                  "requiresOpenaiAuth": True}
    elif method == "account/login/start":
        out({"id": request_id, "result": {"type": "chatgpt", "loginId": "login-1",
                                          "authUrl": "https://auth.example/login"}})
        open(flag, "w").close()
        notify("account/login/completed", {"loginId": "login-1", "success": True,
                                           "error": None})
        continue
    elif method == "account/logout":
        if os.path.exists(flag):
            os.remove(flag)
    elif method == "thread/list":
        found = []
        for name in os.listdir(threads):
            thread = load(name[:-5])
            if thread["cwd"] == params.get("cwd") and thread["turns"]:
                found.append(bare(thread))
        found.sort(key=lambda t: t["updatedAt"], reverse=True)
        result = {"data": found, "nextCursor": None}
    elif method == "thread/start":
        thread_id = str(uuid.uuid4())
        thread = {"id": thread_id, "cwd": params["cwd"], "name": None, "preview": "",
                  "createdAt": time.time(), "updatedAt": time.time(), "turns": [],
                  "path": path(thread_id)}
        save(thread)
        notify("thread/started", {"thread": bare(thread)})
        result = {"thread": bare(thread), "model": "fake-model"}
    elif method == "thread/resume":
        if not os.path.exists(path(params["threadId"])):
            out({"id": request_id, "error": {"code": -32600, "message": "no such thread"}})
            continue
        result = {"thread": load(params["threadId"]), "model": "fake-model"}
    elif method == "thread/name/set":
        thread = load(params["threadId"])
        thread["name"] = params["name"]
        save(thread)
    elif method == "thread/delete":
        os.remove(path(params["threadId"]))
    elif method == "turn/start":
        turn(request_id, params)
        continue
    out({"id": request_id, "result": result})
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    path = tmp_path / "codex"
    path.write_text(FAKE.replace("PYTHON", sys.executable))
    path.chmod(0o755)
    monkeypatch.setenv("VP6_CODEX", str(path))
    return str(path)


@pytest.fixture
def opened(monkeypatch):
    """The login pages the IDE opened (none in the browser)."""
    urls = []
    monkeypatch.setattr(codexpanel, "open_url", urls.append)
    return urls


@pytest.fixture
def server(qapp):
    server = CodexServer()
    yield server
    server.end()
    server.deleteLater()


def _logged_in():
    open(os.path.join(codex.codex_home(), "logged-in"), "w").close()


def _requests(method=None):
    with open(os.path.join(codex.codex_home(), "requests.txt")) as file:
        found = [json.loads(line) for line in file]
    return [r for r in found if method is None or r.get("method") == method]


def _ask(server, method, params):
    """A request's result, waited for."""
    answers = []
    server.request(method, params, answers.append, lambda m: answers.append({"error": m}))
    wait_for(lambda: answers)
    return answers[0]


# -- the parts ----------------------------------------------------------------------------------

def test_finding_the_command(fake, tmp_path, monkeypatch):
    assert find_codex() == fake
    monkeypatch.setenv("VP6_CODEX", str(tmp_path / "missing"))
    assert find_codex() is None
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home"))
    assert codex.codex_home() == str(tmp_path / "home")


def test_describe_account():
    assert describe_account({"account": {"type": "chatgpt", "email": "ada@example.com",
                                         "planType": "pro"}}) == \
        (True, "Logged in as ada@example.com (ChatGPT pro)")
    assert describe_account({"account": {"type": "apiKey"}}) == \
        (True, "Logged in with an API key")
    assert describe_account({"account": None, "requiresOpenaiAuth": True}) == \
        (False, "Not logged in")
    assert describe_account({"account": None, "requiresOpenaiAuth": False})[0]


def test_sessions_and_modes(tmp_path):
    info = session_of({"id": "t1", "preview": "Make  a\nform", "name": None, "updatedAt": 5,
                       "cwd": "/x", "path": "/r.jsonl"})
    assert (info.id, info.title, info.modified, info.path) == ("t1", "Make a form", 5.0,
                                                               "/r.jsonl")
    assert session_of({"id": "t2", "preview": "x", "name": "Named"}).title == "Named"
    assert session_of({"id": "t3"}).title == "(untitled)"
    params = list_params(str(tmp_path), "next")
    assert params["cwd"] == str(tmp_path) and params["cursor"] == "next"
    assert "appServer" in params["sourceKinds"] and "subAgent" not in params["sourceKinds"]
    assert mode_policies("full") == ("never", {"type": "dangerFullAccess"})
    assert mode_policies("read-only")[1]["type"] == "readOnly"
    assert mode_policies("nonsense") == mode_policies("auto")
    assert codex.default_mode() == "auto"
    assert command_line({"command": "/bin/sh -lc 'ls'",
                         "commandActions": [{"type": "listFiles", "command": "ls"}]}) == "ls"
    assert command_line({"command": "make", "commandActions": []}) == "make"


# -- the server ---------------------------------------------------------------------------------

def test_the_server_starts_when_asked(qapp, fake, server):
    assert not server.running
    result = _ask(server, "account/read", {})  # (sent once it's initialized)
    assert result["account"] is None and server.running and server.ready
    assert [r["method"] for r in _requests()] == ["initialize", "account/read"]
    assert _requests("initialize")[0]["params"]["clientInfo"]["name"] == "vp6"
    process = server.process
    _ask(server, "account/read", {})
    assert server.process is process and server.generation == 1  # (kept running)
    assert "error" in _ask(server, "thread/resume", {"threadId": "missing"})
    server.end()
    assert not server.running


def test_without_codex(qapp, server):
    assert _ask(server, "account/read", {}) == \
        {"error": "Codex isn't installed (the codex command wasn't found)."}
    chat = CodexChat(server, "/tmp")
    failures = []
    chat.failed.connect(failures.append)
    assert not chat.send("hello")
    assert failures and "isn't installed" in failures[0] and not chat.busy


# -- a chat -------------------------------------------------------------------------------------

def test_a_chat(qapp, fake, server, tmp_path):
    chat = CodexChat(server, str(tmp_path))
    messages, sessions = [], []
    chat.message.connect(messages.append)
    chat.sessionChanged.connect(sessions.append)
    assert chat.send("hello") and chat.busy
    wait_for(lambda: not chat.busy)
    assert sessions and chat.session_id == sessions[0]
    methods = [m["method"] for m in messages]
    assert methods[0] == "vp6/threadLoaded" and methods[-1] == "turn/completed"
    assert "turn/started" in methods
    said = [m["params"]["item"]["text"] for m in messages if m["method"] == "item/completed"
            and m["params"]["item"]["type"] == "agentMessage"]
    assert said == ["You said: **hello**"]
    start = _requests("thread/start")[0]["params"]
    assert start["cwd"] == str(tmp_path) and start["approvalPolicy"] == "on-request"
    assert start["sandbox"] == "workspace-write"
    chat.set_mode("full")
    chat.send("again")  # (the same thread, in the new mode)
    wait_for(lambda: not chat.busy)
    assert len(_requests("thread/start")) == 1
    turns = _requests("turn/start")
    assert turns[0]["params"]["sandboxPolicy"]["writableRoots"] == [str(tmp_path)]
    assert turns[1]["params"]["approvalPolicy"] == "never"
    assert turns[1]["params"]["sandboxPolicy"] == {"type": "dangerFullAccess"}
    assert turns[1]["params"]["input"] == [{"type": "text", "text": "again",
                                            "text_elements": []}]
    chat.end()
    wait_for(lambda: _requests("thread/unsubscribe"))


def test_chats_take_their_own_threads(qapp, fake, server, tmp_path):
    one, two = CodexChat(server, str(tmp_path)), CodexChat(server, str(tmp_path))
    heard = {one: [], two: []}
    one.message.connect(heard[one].append)
    two.message.connect(heard[two].append)
    one.send("first")
    wait_for(lambda: not one.busy)
    two.send("second")
    wait_for(lambda: not two.busy)
    assert one.session_id != two.session_id
    for chat, text in ((one, "first"), (two, "second")):
        assert all(m["params"].get("threadId", chat.session_id) == chat.session_id
                   for m in heard[chat] if m["method"] != "thread/started")
        assert f"You said: **{text}**" in json.dumps(heard[chat])


def test_asking_before_running_a_command(qapp, fake, server, tmp_path):
    chat = CodexChat(server, str(tmp_path))
    questions = []
    chat.permissionRequested.connect(lambda *q: questions.append(q))
    chat.send("run ls")
    wait_for(lambda: questions)
    request_id, tool, details = questions[0]
    assert tool == "Shell" and details["command"] == "ls"
    chat.answer(request_id, True)
    wait_for(lambda: not chat.busy)
    chat.send("run rm x")
    wait_for(lambda: len(questions) == 2)
    chat.answer(questions[1][0], False)
    wait_for(lambda: not chat.busy)
    chat.send("run make")
    wait_for(lambda: len(questions) == 3)
    chat.answer(questions[2][0], True, always="Shell")
    wait_for(lambda: not chat.busy)
    assert [a["answer"]["decision"] for a in _requests() if "answer" in a] == \
        ["accept", "decline", "acceptForSession"]


def test_a_resumed_chat_and_a_restarted_server(qapp, fake, server, tmp_path):
    chat = CodexChat(server, str(tmp_path))
    chat.send("hello")
    wait_for(lambda: not chat.busy)
    resumed = []
    again = CodexChat(server, str(tmp_path), chat.session_id)
    again.resumed.connect(resumed.append)
    again.open()
    wait_for(lambda: resumed)
    assert [i["type"] for i in resumed[0]["turns"][0]["items"]] == ["userMessage",
                                                                     "agentMessage"]
    failures = []
    chat.failed.connect(failures.append)
    chat.send("crash")  # (the server ends while it works)
    wait_for(lambda: not chat.busy)
    assert failures == ["fake codex crashed"] and not chat.running and not server.running
    chat.send("after")  # the server starts again, the thread is resumed
    wait_for(lambda: not chat.busy)
    assert server.generation == 2
    assert _requests("thread/resume")[-1]["params"]["threadId"] == chat.session_id


def test_stop(qapp, fake, server, tmp_path):
    chat = CodexChat(server, str(tmp_path))
    messages = []
    chat.message.connect(messages.append)
    chat.send("slow")
    wait_for(lambda: chat.turn_id)
    chat.stop()
    wait_for(lambda: not chat.busy)
    assert _requests("turn/interrupt")[0]["params"]["turnId"] == \
        messages[-1]["params"]["turn"]["id"]
    assert messages[-1]["params"]["turn"]["status"] == "interrupted"


# -- the chat window ----------------------------------------------------------------------------

def test_the_chat_window(qapp, fake, server, tmp_path):
    window = CodexChatWindow(server, str(tmp_path))
    assert window.title == "New Codex Session" and window.mode.currentData() == "auto"
    assert [window.mode.itemData(i) for i in range(window.mode.count())] == \
        [m[0] for m in codex.MODES]
    window.input.setPlainText("Make a form")
    window.send_button.click()
    assert window.title == "Make a form" and window.send_button.text() == "Stop"
    wait_for(lambda: not window.chat.busy)
    text = window.transcript_text()
    assert "You\nMake a form" in text and "Codex\nYou said: Make a form" in text
    assert window.state.text() == "Done (1.5 s)"
    window.send("run ls")
    wait_for(lambda: window.question.isVisibleTo(window))
    assert "Codex wants to use <b>Shell</b>" in window.question_text.text()
    window.answer(False)
    wait_for(lambda: not window.chat.busy)
    text = window.transcript_text()
    assert "Denied: Shell" in text and "Declined" in text and "not allowed" in text
    (tmp_path / "notes.txt").write_text("one\n")
    window.send(f"askedit {tmp_path / 'notes.txt'}|one|two")
    wait_for(lambda: window.question.isVisibleTo(window))
    assert "Edit Files" in window.question_text.text()
    assert "notes.txt" in window.question_text.text()
    window.answer(True)
    wait_for(lambda: not window.chat.busy)
    assert (tmp_path / "notes.txt").read_text() == "two\n"
    assert "Edit notes.txt" in window.transcript_text()
    window.mode.setCurrentIndex(window.mode.findData("read-only"))
    assert codex.default_mode() == "read-only"  # (new chats start in it)
    window.send("fail")
    wait_for(lambda: not window.chat.busy)
    assert "Please log in again." in window.transcript_text()
    assert "vp6:login" in window.view.toHtml()
    window.close()
    window.deleteLater()


def test_a_resumed_session_shows_what_was_said(qapp, fake, server, tmp_path):
    chat = CodexChat(server, str(tmp_path))
    chat.send("hello")
    wait_for(lambda: not chat.busy)
    session = session_of({"id": chat.session_id, "preview": "hello"})
    window = CodexChatWindow(server, str(tmp_path), session)
    assert window.title == "hello"
    wait_for(lambda: "You said: hello" in window.transcript_text())
    assert window.transcript_text().index("You\nhello") < \
        window.transcript_text().index("You said")
    assert window.state.text().startswith("Resumed")
    window.send("more")  # (the thread resumed: no new one)
    wait_for(lambda: not window.chat.busy)
    assert len(_requests("thread/start")) == 1 and window.session_id == chat.session_id
    window.close()
    window.deleteLater()


# -- the panel ----------------------------------------------------------------------------------

def test_the_panel_without_codex(qapp, tmp_path):
    panel = CodexPanel(lambda: str(tmp_path))
    panel.refresh()
    assert "Codex isn't installed" in panel.status.text()
    assert "developers.openai.com" in panel.status.text()
    assert panel.locate_button.isVisibleTo(panel) and not panel.login_button.isVisibleTo(panel)
    panel.end()
    panel.deleteLater()


def test_the_panel(qapp, fake, tmp_path, opened):
    panel = CodexPanel(lambda: str(tmp_path))
    panel.refresh()
    wait_for(lambda: panel.logged_in is False)
    assert panel.status.text() == "Codex: Not logged in"
    assert panel.login_button.text() == "Log In"
    panel.login_button.click()  # (the browser opened at the login page)
    wait_for(lambda: panel.logged_in)
    assert opened == ["https://auth.example/login"]
    assert panel.status.text() == "Codex: Logged in as ada@example.com (ChatGPT plus)"
    assert panel.login_button.text() == "Log Out" and panel.login_id is None
    # Sessions: the folder's own, the latest first
    for text in ("first", "second"):
        chat = CodexChat(panel.server, str(tmp_path))
        chat.send(text)
        wait_for(lambda: not chat.busy)
    elsewhere = CodexChat(panel.server, str(tmp_path / ".."))
    elsewhere.send("not here")
    wait_for(lambda: not elsewhere.busy)
    panel.refresh()
    wait_for(lambda: len(panel.sessions) == 2)
    assert [s.title for s in panel.sessions] == ["second", "first"]
    assert not panel.buttons["Open"].isEnabled()
    panel.select(panel.sessions[1].id)
    assert panel.buttons["Open"].isEnabled()
    opens = []
    panel.openSession.connect(opens.append)
    panel.open_selected()
    panel.new_session()
    assert opens == [panel.sessions[1].id, ""]
    panel.rename_selected("The first")
    wait_for(lambda: panel.sessions and panel.sessions[1].title == "The first")
    panel.select(panel.sessions[0].id)
    panel.delete_selected(confirm=False)
    wait_for(lambda: [s.title for s in panel.sessions] == ["The first"])
    panel.log_out(confirm=False)
    wait_for(lambda: panel.logged_in is False)
    panel.end()
    assert not panel.server.running
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
    assert window.codex_dock.isHidden() and window.codex_dock.windowTitle() == "Codex"
    assert window.act_view_codex in window.view_menu.actions()
    assert not window.codex_panel.server.running  # (started when first needed)
    window.act_view_codex.trigger()
    assert not window.codex_dock.isHidden()
    assert window.codex_dock in window.tabifiedDockWidgets(window.immediate_dock)
    window.reset_layout()
    assert window.codex_dock.isHidden()


def test_sessions_open_in_the_mdi_area(window, fake, tmp_path):
    _logged_in()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    folder = window.project.directory
    window.show_codex()
    assert window.codex_panel.folder() == folder
    chat = window.open_codex_session()
    sub = window.mdi.activeSubWindow()
    assert sub.widget() is chat and sub.windowTitle() == "New Codex Session"
    assert chat.chat.server is window.codex_panel.server  # (one server for all)
    assert not window.claude_windows() and window.codex_windows() == [sub]
    chat.send("Make a form")
    wait_for(lambda: not chat.chat.busy)
    assert sub.windowTitle() == "Make a form"
    assert _requests("thread/start")[0]["params"]["cwd"] == folder
    wait_for(lambda: window.codex_panel.sessions)  # (listed once it replied)
    session_id = window.codex_panel.sessions[0].id
    assert session_id == chat.session_id
    window.view_code(next(iter(window.documents)))
    assert window.open_codex_session(session_id) is chat  # (the one open)
    assert window.mdi.activeSubWindow() is sub
    window.close_project()  # (its chats close)
    assert not window.codex_windows()


def test_log_in_from_a_chat(window, fake, opened):
    chat = window.open_codex_session()
    chat.send("fail")
    wait_for(lambda: not chat.chat.busy)
    chat._link_clicked(type("Url", (), {"toString": lambda self: "vp6:login"})())
    assert not window.codex_dock.isHidden()
    wait_for(lambda: window.codex_panel.logged_in)
    assert opened == ["https://auth.example/login"]


BUTTON = ("        self.Command1 = CommandButton(self, Caption='Go', Left=16, Top=16, Width=90, "
          "Height=30)\n")


def test_files_changed_by_codex_shown_at_once(window, fake, tmp_path):
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    path = window.project.abspath("Form1.py")
    designer = window.view_object(path)
    code = window.view_code(path)
    doc = window.documents[path]
    doc.replace_text(doc.text.replace("pass", "self.Caption = 'Mine'"))  # (not saved)
    chat = window.open_codex_session()
    chat.send(f"edit {path}|self.Height = 360|self.Height = 360\n" + BUTTON.rstrip())
    assert not doc.modified  # (saved before Codex got the message)
    wait_for(lambda: not chat.chat.busy)
    wait_for(lambda: "Command1" in designer.controls)  # the designer...
    assert "CommandButton(self, Caption='Go'" in code.editor.toPlainText()  # ...the code
    assert "self.Caption = 'Mine'" in doc.text and not doc.modified


def test_closing_the_ide_ends_the_server(qapp, fake):
    w = MainWindow()
    w.show()
    chat = w.open_codex_session()
    chat.send("hi")
    wait_for(lambda: not chat.chat.busy)
    process = w.codex_panel.server.process
    pid = process.processId()
    w.close()
    assert not w.codex_panel.server.running
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_screenshot(window, fake, tmp_path):
    window.resize(1000, 700)
    window.show_codex()
    chat = window.open_codex_session()
    chat.send("hello")
    wait_for(lambda: not chat.chat.busy)
    chat.send("run ls -la")
    wait_for(lambda: chat.question.isVisibleTo(chat))
    QTest.qWait(50)
    image = chat.grab().toImage()
    assert image.width() > 300 and image.height() > 200
    if os.environ.get("VP6_SCREENSHOTS"):
        image.save(os.path.join(os.environ["VP6_SCREENSHOTS"], "codex-chat.png"))
        window.grab().save(os.path.join(os.environ["VP6_SCREENSHOTS"], "codex-ide.png"))
    chat.answer(True)
    wait_for(lambda: not chat.chat.busy)
