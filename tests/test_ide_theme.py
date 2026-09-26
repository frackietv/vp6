"""The IDE window (not just the editor) follows the light/dark theme."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from vp6 import appearance, formfile
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.mainwindow import MainWindow
from vp6.ide.theme import DARK, LIGHT, SYSTEM, theme_manager


def _ink_lightness(name: str, dark: bool) -> tuple[int, int]:
    """(darkest, lightest) lightness of the opaque pixels of an icon."""
    icons.set_dark(dark)
    image = icons.icon(name).pixmap(24, 24).toImage()
    values = [QColor(image.pixel(x, y)).lightness()
              for x in range(image.width()) for y in range(image.height())
              if QColor.fromRgba(image.pixel(x, y)).alpha() > 200]
    icons.set_dark(False)
    return min(values), max(values)


@pytest.mark.parametrize("name", ["Label", "Pointer", "Frame", "New", "Module"])
def test_dark_icons_have_light_ink(qapp, name):
    assert _ink_lightness(name, dark=False)[0] < 80  # dark outlines on light
    assert _ink_lightness(name, dark=True)[1] > 200  # light outlines on dark


def test_disabled_icons_stay_visible(qapp):
    icon = icons.icon("Stop")
    disabled = icon.pixmap(24, 24, icon.Mode.Disabled).toImage()
    alphas = [QColor.fromRgba(disabled.pixel(x, y)).alpha()
              for x in range(disabled.width()) for y in range(disabled.height())]
    assert 40 < max(alphas) < 150  # faded, not invisible


@pytest.fixture
def window(qapp):
    w = MainWindow()
    yield w
    w.close()


def app_window_color() -> str:
    return QApplication.palette().color(QPalette.Window).name()


def test_whole_ide_follows_explicit_theme(window):
    manager = theme_manager()
    run_icon_light = window.act_run.icon().cacheKey()
    manager.select(DARK)
    hints = QApplication.styleHints()
    # Either the platform switched the scheme, or the Fusion fallback did
    assert hints.colorScheme() == Qt.ColorScheme.Dark or app_window_color() == "#353535"
    assert appearance.app_override_active()
    assert icons.is_dark() and manager.app_is_dark()
    assert window.act_run.icon().cacheKey() != run_icon_light
    assert window.mdi.background().color().name() == "#1f1f21"
    manager.select(LIGHT)
    assert not manager.app_is_dark()
    assert window.mdi.background().color().name() == "#a3a8ae"
    manager.select(SYSTEM)  # back to the OS appearance, nothing forced
    assert not appearance.app_override_active()
    assert hints.colorScheme() != Qt.ColorScheme.Dark or appearance.system_is_dark()


def test_system_form_shows_os_appearance_when_ide_is_forced(window, tmp_path, monkeypatch):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    designer.create_control("CommandButton", None, None, None)
    monkeypatch.setattr(appearance, "_query_os_dark", lambda: False)  # OS is light
    theme_manager().select(DARK)  # ... but the IDE is forced dark
    designer.refresh_scheme()
    assert designer.form._render_scheme() == appearance.vpSchemeLight
    assert designer.form._widget.palette().color(QPalette.Button).name() == "#efefef"
    theme_manager().select(LIGHT)  # IDE matches the OS: native rendering again
    designer.refresh_scheme()
    assert designer.form._render_scheme() == appearance.vpSchemeSystem


# --- designer window frames ------------------------------------------------------------

from vp6.ide import chrome  # noqa: E402
from vp6.ide.designer import MARGIN  # noqa: E402


@pytest.mark.parametrize("platform, expected", [
    ("darwin", chrome.MACOS), ("win32", chrome.WINDOWS), ("linux", chrome.GNOME)])
def test_frame_style_matches_os(monkeypatch, platform, expected):
    monkeypatch.setattr(chrome.sys, "platform", platform)
    assert chrome.resolve(chrome.AUTO) == expected
    assert chrome.resolve(chrome.CLASSIC) == chrome.CLASSIC


def test_frame_metrics_follow_border_style():
    sizable = chrome.FrameInfo("F", border_style=2)
    tool = chrome.FrameInfo("F", border_style=4)
    borderless = chrome.FrameInfo("F", border_style=0)
    assert chrome.metrics(chrome.MACOS, sizable) == (28, 1)
    assert chrome.metrics(chrome.MACOS, tool)[0] < 28
    assert chrome.metrics(chrome.WINDOWS, borderless) == (0, 0)
    dialog = chrome.FrameInfo("F", border_style=3)
    assert not dialog.can_minimize and not dialog.can_maximize
    assert chrome.FrameInfo("F", border_style=2, min_button=False).can_maximize
    assert not chrome.FrameInfo("F", control_box=False).can_minimize


def _set_designer_options(**changes):
    import copy

    state = copy.deepcopy(theme_manager().state)
    for key, value in changes.items():
        setattr(state, key, value)
    theme_manager().apply(state)


@pytest.fixture
def form_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    return FormDesigner(FormDocument(str(path)), str(tmp_path))


def test_designer_places_form_below_the_frame(form_designer):
    d = form_designer
    _set_designer_options(frame_style=chrome.MACOS)
    assert d.form_widget().pos().y() == MARGIN + 1 + 28
    _set_designer_options(frame_style=chrome.WINDOWS)
    assert d.form_widget().pos().y() == MARGIN + 1 + 32
    d.select([])
    d.set_property("BorderStyle", 0)  # no title bar at all
    assert d.form_widget().pos().y() == MARGIN
    assert d.canvas.form_frame_rect() == d.form_canvas_rect()


@pytest.mark.parametrize("style", [chrome.MACOS, chrome.WINDOWS, chrome.GNOME, chrome.CLASSIC])
@pytest.mark.parametrize("border_style", range(6))
def test_every_frame_paints(form_designer, style, border_style):
    d = form_designer
    _set_designer_options(frame_style=style)
    d.select([])
    d.set_property("BorderStyle", border_style)
    image = d.canvas.grab().toImage()
    assert not image.isNull()


def test_grid_can_be_hidden(form_designer):
    d = form_designer
    assert not d.form._widget.palette().window().texture().isNull()
    _set_designer_options(show_grid=False)
    assert d.form._widget.palette().window().texture().isNull()
