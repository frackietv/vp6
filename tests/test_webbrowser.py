"""The WebBrowser (Qt WebEngine, Chromium): a real one, headless: navigating, links,
BeforeNavigate, NewWindow, errors, history, LoadHTML and RunScript, the events, the
focus; the designer's placeholder."""

import os

import pytest
from PySide6.QtCore import QDeadlineTimer, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from vp6 import Form, TextBox, WebBrowser
from vp6.controls import CONTROL_TYPES, EVENT_ARGS
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


def wait_until(condition, timeout=15000):
    deadline = QDeadlineTimer(timeout)
    while not condition():
        assert not deadline.hasExpired(), "timed out"
        QTest.qWait(20)


class Browser(Form):
    def InitializeComponent(self):
        self.events = []
        self.block = ""
        self.ignore_new_windows = False
        self.web = WebBrowser(self, Left=0, Top=0, Width=400, Height=300)
        self.txt = TextBox(self, Left=0, Top=310)

    def web_DocumentComplete(self, URL):
        self.events.append(("DocumentComplete", os.path.basename(URL)))

    def web_BeforeNavigate(self, URL):
        self.events.append(("BeforeNavigate", os.path.basename(URL)))
        return bool(self.block) and self.block in URL

    def web_NewWindow(self, URL):
        self.events.append(("NewWindow", os.path.basename(URL)))
        return self.ignore_new_windows

    def web_NavigateError(self, URL, Description):
        self.events.append(("NavigateError", Description))

    def web_TitleChange(self, Text):
        self.events.append(("TitleChange", Text))

    def web_StatusTextChange(self, Text):
        self.events.append(("StatusTextChange", Text))

    def web_GotFocus(self):
        self.events.append("GotFocus")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    folder = tmp_path_factory.mktemp("site")
    (folder / "a.html").write_text(
        "<title>A</title><a id='b' href='b.html'>B</a> "
        "<a id='new' target='_blank' href='c.html'>C</a>")
    (folder / "b.html").write_text("<title>B</title>")
    (folder / "c.html").write_text("<title>C</title>")
    return folder


@pytest.fixture(scope="module")
def browser(qapp, site):
    form = Browser()
    form.Show()
    yield form
    form.Unload()


def go(form, url):
    form.events.clear()
    form.web.Navigate(url)
    wait_until(lambda: any(e[0] in ("DocumentComplete", "NavigateError")
                           for e in form.events if isinstance(e, tuple)))


def test_navigating_and_links(browser, site):
    go(browser, str(site / "a.html"))
    assert ("BeforeNavigate", "a.html") in browser.events
    assert browser.events[-1] == ("DocumentComplete", "a.html") or \
        ("DocumentComplete", "a.html") in browser.events
    wait_until(lambda: browser.web.LocationName == "A")
    assert browser.web.LocationURL == QUrl.fromLocalFile(str(site / "a.html")).toString()
    browser.events.clear()
    browser.web.RunScript("document.getElementById('b').click()")  # a link clicked
    wait_until(lambda: ("DocumentComplete", "b.html") in browser.events)
    assert ("BeforeNavigate", "b.html") in browser.events
    assert not browser.web.Busy and browser.web.Progress == 100
    # (Chromium's Back skips a page left by a script's click, without the user: typed here)
    go(browser, str(site / "a.html"))
    go(browser, str(site / "b.html"))
    assert browser.web.CanGoBack
    browser.events.clear()
    browser.web.GoBack()
    wait_until(lambda: browser.web.LocationName == "A")
    assert browser.web.CanGoForward
    browser.web.GoForward()
    wait_until(lambda: browser.web.LocationName == "B")


def test_before_navigate_can_keep_it_here(browser, site):
    go(browser, str(site / "a.html"))
    browser.block = "b.html"
    browser.events.clear()
    browser.web.RunScript("document.getElementById('b').click()")
    wait_until(lambda: ("BeforeNavigate", "b.html") in browser.events)
    QTest.qWait(300)
    assert browser.web.LocationName == "A"  # it stayed
    browser.block = ""


def test_new_windows(browser, site):
    go(browser, str(site / "a.html"))
    browser.events.clear()
    browser.web.RunScript("document.getElementById('new').click()")  # target=_blank
    wait_until(lambda: ("NewWindow", "c.html") in browser.events)
    wait_until(lambda: browser.web.LocationName == "C")  # opened here
    go(browser, str(site / "a.html"))
    browser.ignore_new_windows = True
    browser.events.clear()
    browser.web.RunScript("document.getElementById('new').click()")
    wait_until(lambda: ("NewWindow", "c.html") in browser.events)
    QTest.qWait(300)
    assert browser.web.LocationName == "A"  # NewWindow returned True: ignored
    browser.ignore_new_windows = False


def test_errors(browser):
    go(browser, "https://nowhere.invalid/")
    assert browser.events[-1][0] == "NavigateError" and "NAME_NOT_RESOLVED" in \
        browser.events[-1][1]


def test_html_scripts_and_status_text(browser):
    browser.events.clear()
    browser.web.LoadHTML("<title>Mine</title><a href='https://example.com/x'>x</a>",
                         "https://example.com/")
    wait_until(lambda: ("TitleChange", "Mine") in browser.events)
    assert browser.web.LocationName == "Mine"
    results = []
    browser.web.RunScript("document.links.length", results.append)
    wait_until(lambda: results)
    assert results == [1]
    browser.web._widget.page().linkHovered.emit("https://example.com/x")  # the mouse on it
    assert browser.events[-1] == ("StatusTextChange", "https://example.com/x")


def test_focus(browser):
    browser.txt.SetFocus()
    browser.events.clear()
    browser.web.SetFocus()
    proxy = browser.web._widget.focusProxy()
    assert proxy is not None and proxy.property("_vp_watched")
    proxy.setFocus()
    QTest.qWait(50)
    assert "GotFocus" in browser.events


def test_in_the_designer_and_the_toolbox(qapp):
    class Designing(Form):
        _design_mode = True

        def InitializeComponent(self):
            self.web = WebBrowser(self, Name="web")

    form = Designing()
    assert isinstance(form.web._widget, QLabel) and form.web._view is None
    form._widget.close()
    cls = CONTROL_TYPES["WebBrowser"]
    assert "WebBrowser" in Toolbox().buttons and not icon("WebBrowser").isNull()
    assert {"BeforeNavigate", "NewWindow", "StatusTextChange"} <= set(cls.Events)
    assert "MousePointer" not in cls._specs and EVENT_ARGS["BeforeNavigate"] == "URL"
