"""The WebView: the platform's own web view (Qt WebView) with VB's WebBrowser names.
Offscreen Qt can't show native web views, so most tests give it a stand-in view; set
VP6_TEST_WEBVIEW=1 to also run a real one (in a process of its own, on the screen)."""

import os
import subprocess
import sys
import textwrap

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QWidget

from vp6 import Form, WebView
from vp6 import controls
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class _Status:
    def __init__(self, name):
        self.name = name


class _Info:
    def __init__(self, status, url, error=""):
        self._status, self._url, self._error = _Status(status), QUrl(url), error

    def status(self):
        return self._status

    def url(self):
        return self._url

    def errorString(self):
        return self._error


class FakeView:
    """Stands in for QWebView: loads instantly, keeps a history."""

    def __init__(self):
        self.loadingChanged, self.titleChanged, self.loadProgressChanged = (
            _Signal(), _Signal(), _Signal())
        self._url, self._title, self.history, self.index = QUrl(), "", [], -1
        self.calls, self.files_allowed = [], False

    def settings(self):
        view = self

        class Settings:
            def setAttribute(self, attribute, on):
                view.files_allowed = view.files_allowed or bool(on)

        return Settings()

    def _load(self, url, title):
        self.loadingChanged.emit(_Info("Started", url.toString()))
        self.loadProgressChanged.emit()
        if url.host() == "nowhere.invalid":
            self.loadingChanged.emit(_Info("Failed", url.toString(), "Host not found"))
            return
        self._url, self._title = url, title
        self.titleChanged.emit(title)
        self.loadingChanged.emit(_Info("Succeeded", url.toString()))

    def setUrl(self, url):
        self.history = self.history[:self.index + 1] + [url]
        self.index += 1
        self._load(url, url.fileName() or url.host())

    def loadHtml(self, html, base):
        self.calls.append(("loadHtml", html, base.toString()))
        self.history = self.history[:self.index + 1] + [QUrl("about:blank")]
        self.index += 1
        self._load(QUrl("about:blank"), "html")

    def goBack(self):
        self.index -= 1
        self._load(self.history[self.index], "back")

    def goForward(self):
        self.index += 1
        self._load(self.history[self.index], "forward")

    def reload(self):
        self.calls.append(("reload",))

    def stop(self):
        self.calls.append(("stop",))

    def runJavaScript(self, script, callback=None):
        self.calls.append(("js", script))
        if callback is not None:
            callback(42)

    def url(self):
        return self._url

    def title(self):
        return self._title

    def isLoading(self):
        return False

    def loadProgress(self):
        return 100

    def canGoBack(self):
        return self.index > 0

    def canGoForward(self):
        return self.index < len(self.history) - 1


@pytest.fixture
def fake(monkeypatch):
    views = []

    def make(parent):
        views.append(FakeView())
        return QWidget(parent), views[-1]

    monkeypatch.setattr(controls, "_new_web_view", make)
    return views


class Browser(Form):
    def InitializeComponent(self):
        self.events = []
        self.web = WebView(self, Left=0, Top=0, Width=300, Height=200, URL="start.html")

    def web_DocumentComplete(self, URL):
        self.events.append(("DocumentComplete", URL))

    def web_TitleChange(self, Text):
        self.events.append(("TitleChange", Text))

    def web_ProgressChange(self, Progress):
        self.events.append(("ProgressChange", Progress))

    def web_NavigateError(self, URL, Description):
        self.events.append(("NavigateError", URL, Description))


def test_navigating(qapp, fake, tmp_path, monkeypatch):
    form = Browser()
    web, view = form.web, fake[0]
    assert view.files_allowed  # (a page from a file can open its files)
    assert view.history[0].scheme() == "https" and view.history[0].host() == "start.html"
    page = tmp_path / "page.html"
    page.write_text("<title>Mine</title>")
    web.Navigate(str(page))  # a file
    assert view.history[-1] == QUrl.fromLocalFile(str(page))
    assert ("DocumentComplete", QUrl.fromLocalFile(str(page)).toString()) in form.events
    assert ("ProgressChange", 100) in form.events and ("TitleChange", "page.html") in form.events
    monkeypatch.setattr(form, "_base_dir", lambda: str(tmp_path))
    web.Navigate("page.html")  # relative to the form's folder
    assert view.history[-1] == QUrl.fromLocalFile(str(page))
    web.Navigate("example.com")  # a domain
    assert web.LocationURL == "https://example.com" and web.LocationName == "example.com"
    assert web.URL == "https://example.com"
    web.Navigate("https://nowhere.invalid/x")
    assert form.events[-1] == ("NavigateError", "https://nowhere.invalid/x", "Host not found")
    assert web.CanGoBack and not web.CanGoForward
    web.GoBack()
    assert web.CanGoForward and web.LocationURL == "https://example.com"
    web.GoForward()
    web.Refresh()
    web.Stop()
    assert view.calls[-2:] == [("reload",), ("stop",)]
    assert not web.Busy and web.Progress == 100
    web.URL = "about:blank"  # setting URL goes there too
    assert view.history[-1] == QUrl("about:blank")


def test_html_and_scripts(qapp, fake):
    form = Browser()
    web, view = form.web, fake[0]
    web.LoadHTML("<b>hi</b>", "https://example.com/")
    assert view.calls[0] == ("loadHtml", "<b>hi</b>", "https://example.com/")
    results = []
    web.RunScript("1 + 41", results.append)
    web.RunScript("console.log('no result wanted')")
    assert results == [42] and view.calls[-1] == ("js", "console.log('no result wanted')")


def test_in_the_designer(qapp):
    class Designing(Form):
        _design_mode = True

        def InitializeComponent(self):
            self.web = WebView(self, Name="web", URL="https://example.com")

    form = Designing()
    assert isinstance(form.web._widget, QLabel) and form.web._view is None  # a placeholder
    assert form.web.URL == "https://example.com" and form.web.LocationURL == ""
    form.web.Navigate("x")  # (nothing to do there)
    form._widget.close()


def test_without_qt_webview(qapp, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_webview(name, *args, **kwargs):
        if name == "PySide6.QtWebView":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_webview)
    form = Form()
    with pytest.raises(RuntimeError, match="PySide6 6.11 or newer"):
        WebView(form, Name="web")


def test_toolbox_icon_and_events(qapp):
    cls = CONTROL_TYPES["WebView"]
    assert "WebView" in Toolbox().buttons and not icon("WebView").isNull()
    assert cls.DefaultEvent == "DocumentComplete" and "MousePointer" not in cls._specs
    assert EVENT_ARGS["NavigateError"] == "URL, Description"


@pytest.mark.skipif(not os.environ.get("VP6_TEST_WEBVIEW"),
                    reason="shows a real web view on the screen (set VP6_TEST_WEBVIEW=1)")
def test_a_real_web_view(tmp_path):
    script = tmp_path / "web.py"
    script.write_text(textwrap.dedent("""
        from PySide6.QtCore import QEventLoop, QTimer
        from vp6 import *

        class F(Form):
            def InitializeComponent(self):
                self.web = WebView(self, Width=300, Height=200)
                self.seen = []

            def web_DocumentComplete(self, URL):
                self.seen.append(URL)
                loop.quit()

        loop = QEventLoop()
        form = F()
        form.Show()
        form.web.LoadHTML("<title>Real</title><a href='x'>x</a><a href='y'>y</a>")
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        form.web.RunScript("document.links.length", lambda n: (print("links", n), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        print("done", form.seen)
    """))
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}  # (the screen)
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                            timeout=60, env=env)
    assert "links 2" in result.stdout and "done ['about:blank']" in result.stdout, \
        result.stderr
