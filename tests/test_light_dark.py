"""Light and dark: Form.DarkMode, Screen.DarkMode and Form_ColorSchemeChanged;
the appearance watcher (the OS switching, also while the IDE forces its own
scheme; the IDE's scheme file); designers following it; programs run from
the IDE following the IDE's scheme live."""

import os
import subprocess
import sys
import textwrap

import pytest

import vp6
from conftest import wait_for
from vp6 import Form, Screen, appearance, vpSchemeDark, vpSchemeIDE, vpSchemeLight, \
    vpSchemeSystem
from vp6.controls import EVENT_ARGS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Themed(Form):
    def InitializeComponent(self):
        self.events = []

    def Form_ColorSchemeChanged(self, Dark):
        self.events.append(Dark)


@pytest.fixture
def os_dark(monkeypatch):
    """The OS appearance, as the tests set it."""
    state = {"dark": False}
    monkeypatch.setattr(appearance, "system_is_dark", lambda: state["dark"])
    watcher = appearance.watcher()
    monkeypatch.setattr(watcher, "dark", False)
    return state


def test_dark_mode_and_the_event(qapp, os_dark):
    form = Themed()
    form.ColorScheme = vpSchemeLight
    form.Show()
    assert not form.DarkMode and form.events == []  # (none while loading)
    form.ColorScheme = vpSchemeDark  # forced dark: the event, Dark True
    assert form.DarkMode and form.events == [True]
    form.ColorScheme = vpSchemeDark  # (not changed: no event)
    form.ColorScheme = vpSchemeSystem  # the OS's: light
    assert not form.DarkMode and form.events == [True, False]
    # The OS switching: System forms are told, forced ones aren't
    other = Themed()
    other.ColorScheme = vpSchemeLight
    other.Show()
    os_dark["dark"] = True
    appearance.watcher().check()
    assert form.DarkMode and form.events == [True, False, True] and other.events == []
    assert Screen.DarkMode is True
    appearance.watcher().check()  # (no change: nothing)
    assert form.events == [True, False, True]
    assert "ColorSchemeChanged" in Form.Events and EVENT_ARGS["ColorSchemeChanged"] == "Dark"
    form.Unload()
    other.Unload()


def test_the_watcher_polls_while_the_scheme_is_forced(qapp):
    watcher = appearance.watcher()
    try:
        appearance.set_app_override(True)  # (the IDE forcing Light or Dark)
        assert watcher._timer.isActive() and watcher._timer.interval() == appearance.OS_POLL_MS
    finally:
        appearance.set_app_override(False)
    assert not watcher._timer.isActive()


def test_the_ide_scheme_file(qapp, tmp_path, monkeypatch):
    path = str(tmp_path / "scheme.txt")
    monkeypatch.setenv(appearance.IDE_SCHEME_ENV, "light")
    assert appearance.ide_scheme() == vpSchemeLight  # (no file: the environment)
    appearance.write_ide_scheme_file(path, vpSchemeDark)
    monkeypatch.setenv(appearance.IDE_SCHEME_FILE_ENV, path)
    assert appearance.ide_scheme() == vpSchemeDark  # the file, as it is now
    appearance.write_ide_scheme_file(path, vpSchemeSystem)
    assert appearance.ide_scheme() == vpSchemeSystem
    assert open(path).read() == "system"


def test_designers_follow_the_watcher(qapp, tmp_path, monkeypatch):
    from vp6 import formfile
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument

    refreshed = []
    monkeypatch.setattr(FormDesigner, "refresh_scheme", lambda self: refreshed.append(self))
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    appearance.watcher().changed.emit()  # (e.g. the OS switched while the IDE is forced)
    wait_for(lambda: designer in refreshed)  # (and any other designer still about)
    assert designer in refreshed
    designer.close()


def test_the_ide_keeps_its_scheme_in_a_file(qapp, monkeypatch):
    from vp6.ide.mainwindow import MainWindow
    from vp6.ide.theme import theme_manager

    window = MainWindow()
    scheme = {"now": vpSchemeLight}
    monkeypatch.setattr(type(theme_manager()), "ide_scheme", lambda self: scheme["now"])
    path = window._write_ide_scheme()
    assert open(path).read() == "light"
    scheme["now"] = vpSchemeDark
    theme_manager().changed.emit()  # the IDE's theme changed: written again
    assert open(path).read() == "dark"
    window.close()
    assert not os.path.exists(path)  # (gone with the IDE)


def test_a_program_follows_the_ide(tmp_path):
    # A program run from the IDE: its "IDE" form follows the scheme file live
    scheme_file = tmp_path / "scheme.txt"
    appearance.write_ide_scheme_file(str(scheme_file), vpSchemeLight)
    code = textwrap.dedent("""
        from PySide6.QtCore import QTimer
        from vp6 import End, Form, run, vpSchemeIDE

        class Main(Form):
            def InitializeComponent(self):
                self.ColorScheme = vpSchemeIDE

            def Form_Load(self):
                print("load", self.DarkMode, flush=True)

            def Form_ColorSchemeChanged(self, Dark):
                print("changed", Dark, self.DarkMode, flush=True)
                End()

        QTimer.singleShot(20000, End)
        run(Main)
    """)
    env = dict(os.environ, PYTHONPATH=ROOT, QT_QPA_PLATFORM="offscreen",
               VP6_IDE_SCHEME_FILE=str(scheme_file), VP6_NO_ERROR_DIALOG="1")
    env.pop(appearance.IDE_SCHEME_ENV, None)
    program = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        assert program.stdout.readline().strip() == "load False"
        appearance.write_ide_scheme_file(str(scheme_file), vpSchemeDark)  # the IDE turns dark
        assert program.stdout.readline().strip() == "changed True True"
    finally:
        program.kill()
        program.wait()


def test_exported():
    assert isinstance(Form.DarkMode, property) and vp6.vpSchemeIDE == vpSchemeIDE


def test_a_form_shown_in_another_looks_like_it(qapp, os_dark):
    host, page = Themed(), Themed()
    host.ColorScheme = vpSchemeLight
    host.Show()
    page.ShowIn(host)  # (its ColorScheme: the project's, System)
    assert not page.DarkMode and page.events == []
    host.ColorScheme = vpSchemeDark  # the window turns dark: so does the form in it
    assert page.DarkMode and host.events == [True] and page.events == [True]
    page.ShowIn(None)  # a window of its own again: the OS's (light), quietly
    assert not page.DarkMode and page.events == [True]
    page.Unload()
    host.Unload()


# --- title bars ----------------------------------------------------------------------------

def test_title_bars_follow_the_form_where_the_os_allows(qapp, os_dark, monkeypatch):
    calls = []
    monkeypatch.setattr(appearance, "set_title_bar",
                        lambda widget, dark: calls.append((widget, dark)) or True)
    form = Themed()
    form.ColorScheme = vpSchemeDark
    form.Show()
    assert calls[-1] == (form._widget, True)  # (shown: its window's)
    form.ColorScheme = vpSchemeLight
    assert calls[-1] == (form._widget, False)
    form.ColorScheme = vpSchemeSystem
    assert calls[-1] == (form._widget, None)  # the application's: the OS's, live
    try:
        appearance.set_app_override(True)  # (the IDE forcing its scheme on the app)
        os_dark["dark"] = True
        form._appearance_changed()
        assert calls[-1] == (form._widget, True)  # the OS's, told explicitly
    finally:
        appearance.set_app_override(False)
    form.Unload()


def test_no_title_bar_for_forms_that_are_no_windows(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(appearance, "set_title_bar",
                        lambda widget, dark: calls.append(widget) or True)
    host, inner = Themed(), Themed()
    inner.ColorScheme = vpSchemeDark
    host.Show()
    inner.ShowIn(host)
    inner._apply_title_bar()
    assert inner._widget not in calls  # (inside another form)
    created = Themed()  # (no native window yet: nothing to do before it is shown)
    created.ColorScheme = vpSchemeDark
    assert created._widget not in calls
    inner.Unload()
    host.Unload()
    created.Unload()


def test_set_title_bar_only_where_it_can(qapp):
    from PySide6.QtWidgets import QWidget

    assert not appearance.title_bars_follow_scheme()  # (the tests' offscreen platform)
    widget = QWidget()
    assert not appearance.set_title_bar(widget, True)
    widget.deleteLater()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS's NSAppearance")
def test_macos_title_bars_on_cocoa(tmp_path):
    """On the real platform (no window shown): a forced form's NSWindow gets its
    own appearance; a System one has none (the application's)."""
    script = tmp_path / "titlebar.py"
    script.write_text(textwrap.dedent("""
        import os
        os.environ["QT_QPA_PLATFORM"] = "cocoa"
        from vp6 import Form, appearance, vpSchemeDark, vpSchemeLight, vpSchemeSystem
        from vp6.app import ensure_app
        ensure_app()
        form = Form()
        form.ColorScheme = vpSchemeDark
        form._widget.winId()  # (its native window, not shown)
        form._apply_title_bar()
        print(appearance.macos_title_bar_appearance(form._widget))
        form.ColorScheme = vpSchemeLight
        print(appearance.macos_title_bar_appearance(form._widget))
        form.ColorScheme = vpSchemeSystem
        print(appearance.macos_title_bar_appearance(form._widget))
    """))
    env = dict(os.environ, PYTHONPATH=ROOT)
    env.pop("QT_QPA_PLATFORM", None)
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                            env=env, timeout=60)
    assert result.stdout.split() == ["NSAppearanceNameDarkAqua", "NSAppearanceNameAqua",
                                     "None"], result.stderr
