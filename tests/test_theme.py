import copy

import pytest
from PySide6.QtGui import QColor, QPalette

from vp6 import formfile
from vp6.ide import theme as theme_module
from vp6.ide.codeeditor import CodeEditor
from vp6.ide.documents import FormDocument
from vp6.ide.panels import ImmediateWindow
from vp6.ide.theme import (BUILTIN_THEMES, DARK, LIGHT, SYSTEM, ThemeManager, reset_theme_manager,
                            theme_manager)


def _luminance(color: str) -> float:
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    q = QColor(color)
    return 0.2126 * channel(q.red()) + 0.7152 * channel(q.green()) + 0.0722 * channel(q.blue())


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("name", [LIGHT, DARK])
def test_builtin_themes_are_readable(name):
    theme = BUILTIN_THEMES[name]
    for background in ("background", "current_line", "designer_region"):
        bg = theme.colors[background]
        assert contrast(theme.colors["foreground"], bg) >= 4.5, background
        for key, style in theme.syntax.items():
            assert contrast(style.color, bg) >= 3.0, (key, background)
    assert contrast(theme.colors["gutter_foreground"], theme.colors["gutter_background"]) >= 3


@pytest.fixture
def editor(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    return CodeEditor(FormDocument(str(path)))


def _base_and_text(widget):
    palette = widget.palette()
    return palette.color(QPalette.Base).name(), palette.color(QPalette.Text).name()


def test_editor_follows_selected_theme(editor):
    manager = theme_manager()
    manager.select(DARK)
    assert _base_and_text(editor) == ("#1e1e1e", "#d4d4d4")
    keyword = editor.doc.highlighter.formats["keyword"].foreground().color().name()
    assert keyword == BUILTIN_THEMES[DARK].syntax["keyword"].color
    manager.select(LIGHT)
    assert _base_and_text(editor) == ("#ffffff", "#000000")


def test_system_mode_follows_appearance(editor, monkeypatch):
    manager = theme_manager()
    manager.select(SYSTEM)
    monkeypatch.setattr(theme_module, "system_is_dark", lambda: True)
    manager._on_system_changed()
    assert _base_and_text(editor)[0] == "#1e1e1e"
    monkeypatch.setattr(theme_module, "system_is_dark", lambda: False)
    manager._on_system_changed()
    assert _base_and_text(editor)[0] == "#ffffff"


def test_customizations_persist_and_reset(qapp):
    manager = theme_manager()
    state = copy.deepcopy(manager.state)
    state.themes[DARK].syntax["keyword"].color = "#ff00ff"
    state.themes[DARK].syntax["keyword"].bold = True
    state.themes["Mine"] = copy.deepcopy(state.themes[LIGHT])
    state.themes["Mine"].name = "Mine"
    state.themes["Mine"].colors["background"] = "#fafaf0"
    state.selection, state.font_size = "Mine", 15
    manager.apply(state)

    reset_theme_manager()
    reloaded = ThemeManager()
    assert reloaded.state.themes[DARK].syntax["keyword"].color == "#ff00ff"
    assert reloaded.state.themes[DARK].syntax["keyword"].bold
    assert reloaded.current().name == "Mine"
    assert reloaded.current().colors["background"] == "#fafaf0"
    assert reloaded.font().pointSize() == 15

    state = copy.deepcopy(reloaded.state)
    state.themes[DARK] = copy.deepcopy(BUILTIN_THEMES[DARK])
    reloaded.apply(state)
    assert reloaded.state.themes[DARK] == BUILTIN_THEMES[DARK]


def test_immediate_window_recolors_existing_output(qapp):
    window = ImmediateWindow()
    theme_manager().select(LIGHT)
    window.append("boom\n", "err")
    theme_manager().select(DARK)
    fmt = window.output.document().begin().begin().fragment().charFormat()
    assert fmt.foreground().color().name() == BUILTIN_THEMES[DARK].colors["output_error"]
    assert _base_and_text(window.output)[0] == "#1e1e1e"


def test_options_dialog_new_theme(qapp, monkeypatch):
    from vp6.ide.options import OptionsDialog

    theme_manager().select(DARK)
    dialog = OptionsDialog()
    monkeypatch.setattr("vp6.ide.options.QInputDialog.getText",
                        lambda *a, **k: ("Midnight", True))
    dialog._new_theme()
    dialog._set_style_flag("comment", "bold", True)
    assert dialog.preview.palette().color(QPalette.Base).name() == "#1e1e1e"
    dialog.accept()
    manager = theme_manager()
    assert manager.state.selection == "Midnight"
    assert manager.current().syntax["comment"].bold
    assert manager.state.themes[DARK].syntax["comment"].bold is False
