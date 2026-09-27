"""The IDE's splash screen and the --no-splash option."""

import os

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import vp6
from conftest import wait_for
from vp6.ide import mainwindow, splash
from vp6.ide.mainwindow import MainWindow, create_project, parse_arguments
from vp6.ide.splash import SplashScreen


def test_parse_arguments(tmp_path):
    project = create_project(str(tmp_path), "Demo", "exe")
    assert parse_arguments(["vp6"]) == (None, True)
    assert parse_arguments(["vp6", "--no-splash"]) == (None, False)
    assert parse_arguments(["vp6", "--no-splash", project]) == (project, False)
    assert parse_arguments(["vp6", project, "--no-splash"]) == (project, False)
    assert parse_arguments(["vp6", "missing.vp6p"]) == (None, True)


def test_the_splash_screen(qapp):
    screen = SplashScreen(duration=300)
    assert screen.duration == 300 and SplashScreen().duration == splash.DURATION == 2000
    flags = screen.windowFlags()
    assert flags & Qt.FramelessWindowHint and flags & Qt.SplashScreen  # no frame: not movable
    assert screen.minimumSize() == screen.maximumSize()  # not resizable
    assert not screen.logo.pixmap().isNull()  # the logo...
    assert screen.version.text() == f"VP6 {vp6.__version__}"  # ...and the version under it
    assert screen.version.alignment() & Qt.AlignHCenter
    layout = screen.findChild(type(screen.logo)).parentWidget().layout()
    assert layout.indexOf(screen.logo) < layout.indexOf(screen.version)
    screen.start()
    assert screen.isVisible()
    assert not screen.close() and screen.isVisible()  # not closable...
    QTest.mouseClick(screen, Qt.LeftButton)  # ...by a click
    QTest.keyClick(screen, Qt.Key_Escape)  # ...or Esc
    assert screen.isVisible() and not screen.done
    wait_for(lambda: screen.done, timeout_ms=3000)  # it closes itself
    assert not screen.isVisible()
    screen.wait()  # (finished already: returns at once)


def test_main_shows_it_unless_no_splash(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("VP6_NO_OUTPUT_CAPTURE", "1")
    monkeypatch.setattr(splash, "DURATION", 150)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)  # (don't run the event loop)
    monkeypatch.setattr(MainWindow, "show_start_dialog", lambda self: None)
    shown = []
    real_start = SplashScreen.start
    monkeypatch.setattr(SplashScreen, "start", lambda self: (shown.append(self),
                                                              real_start(self)))
    project = create_project(str(tmp_path), "Demo", "exe")

    windows = []
    real_show = MainWindow.show
    monkeypatch.setattr(MainWindow, "show", lambda self: (windows.append(self),
                                                          real_show(self)))

    def run(*args):
        assert mainwindow.main(["vp6", *args]) == 0
        window = windows[-1]
        assert window.isVisible()
        return window

    window = run(project)
    assert len(shown) == 1 and shown[0].done  # the window came after the splash screen
    assert window.project is not None and os.path.samefile(window.project.path, project)
    window.close()
    window = run("--no-splash", project)
    assert len(shown) == 1  # no splash screen this time
    window.close()
