"""Editor color themes and the IDE's light/dark appearance.

The selected theme is either a theme name or "System", which follows the
operating system's light/dark appearance (live) using the themes chosen for
each mode. Every theme, including the built-in ones, can be customized;
customizations are stored in QSettings and built-ins can be reset.

The IDE window itself follows the same choice: with "System" it uses the OS
appearance, with an explicit theme the whole application is forced light or
dark to match it (via Qt's color scheme request, or Fusion + palette on
platforms that can't switch).
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass, field

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from .. import appearance
from ..appearance import system_is_dark

SYSTEM = "System"
LIGHT = "Light"
DARK = "Dark"

# (key, label) - editor surface colors
UI_ROLES = [
    ("background", "Background"),
    ("foreground", "Text"),
    ("selection_background", "Selection background"),
    ("selection_foreground", "Selection text"),
    ("current_line", "Current line"),
    ("breakpoint", "Breakpoint line"),
    ("execution_point", "Execution point (paused)"),
    ("gutter_background", "Line numbers background"),
    ("gutter_foreground", "Line numbers"),
    ("designer_region", "Designer region background"),
    ("fold_marker", "Fold marker"),
    ("output_error", "Immediate: errors"),
    ("output_info", "Immediate: messages"),
    ("output_input", "Immediate: your input"),
]

# (key, label) - syntax styles (color + bold + italic)
SYNTAX_ROLES = [
    ("keyword", "Keywords"),
    ("builtin", "Python built-ins"),
    ("vp6", "VP6 names (MsgBox, vpYes…)"),
    ("self", "self"),
    ("string", "Strings"),
    ("comment", "Comments"),
    ("number", "Numbers"),
    ("defname", "Function / class names"),
    ("decorator", "Decorators"),
]


@dataclass
class TextStyle:
    color: str
    bold: bool = False
    italic: bool = False


@dataclass
class Theme:
    name: str
    dark: bool
    colors: dict[str, str]
    syntax: dict[str, TextStyle] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict, fallback: "Theme") -> "Theme":
        """Build a theme, filling missing roles from ``fallback``."""
        colors = dict(fallback.colors)
        colors.update({k: v for k, v in data.get("colors", {}).items() if k in colors})
        syntax = copy.deepcopy(fallback.syntax)
        for key, style in data.get("syntax", {}).items():
            if key in syntax and isinstance(style, dict):
                syntax[key] = TextStyle(style.get("color", syntax[key].color),
                                        bool(style.get("bold")), bool(style.get("italic")))
        return cls(data.get("name", fallback.name), bool(data.get("dark", fallback.dark)),
                   colors, syntax)


BUILTIN_THEMES: dict[str, Theme] = {
    LIGHT: Theme(LIGHT, False, {
        "background": "#ffffff", "foreground": "#000000",
        "selection_background": "#add6ff", "selection_foreground": "#000000",
        "current_line": "#fffbdd", "breakpoint": "#f7d4d1", "execution_point": "#fff19c",
        "gutter_background": "#f3f3f3",
        "gutter_foreground": "#6e7781", "designer_region": "#eef0f4",
        "fold_marker": "#808080", "output_error": "#c0392b", "output_info": "#7f8c8d",
        "output_input": "#1f5fbf",
    }, {
        "keyword": TextStyle("#0000ff"), "builtin": TextStyle("#795e26"),
        "vp6": TextStyle("#267f99"), "self": TextStyle("#808080", italic=True),
        "string": TextStyle("#a31515"), "comment": TextStyle("#008000", italic=True),
        "number": TextStyle("#098658"), "defname": TextStyle("#000000", bold=True),
        "decorator": TextStyle("#af00db"),
    }),
    DARK: Theme(DARK, True, {
        "background": "#1e1e1e", "foreground": "#d4d4d4",
        "selection_background": "#264f78", "selection_foreground": "#ffffff",
        "current_line": "#2a2d2e", "breakpoint": "#4b2424", "execution_point": "#4b4618",
        "gutter_background": "#1e1e1e",
        "gutter_foreground": "#858585", "designer_region": "#252a33",
        "fold_marker": "#c5c5c5", "output_error": "#f48771", "output_info": "#9d9d9d",
        "output_input": "#4fc1ff",
    }, {
        "keyword": TextStyle("#569cd6"), "builtin": TextStyle("#dcdcaa"),
        "vp6": TextStyle("#4ec9b0"), "self": TextStyle("#9cdcfe", italic=True),
        "string": TextStyle("#ce9178"), "comment": TextStyle("#6a9955", italic=True),
        "number": TextStyle("#b5cea8"), "defname": TextStyle("#dcdcaa", bold=True),
        "decorator": TextStyle("#c586c0"),
    }),
}


def ide_settings() -> QSettings:
    """The IDE's settings store. Uses QSettings' default format, so tests can
    redirect it to a temporary INI file (QSettings("org", "app") would always
    use the native store, e.g. the macOS plist). The VP6_SETTINGS_DIR
    environment variable keeps the settings in an INI file in that folder
    instead (for separate IDE instances, and tests that start the IDE)."""
    directory = os.environ.get("VP6_SETTINGS_DIR")
    if directory:
        return QSettings(os.path.join(directory, "VP6 IDE.ini"), QSettings.IniFormat)
    return QSettings(QSettings.defaultFormat(), QSettings.UserScope, "VP6", "VP6 IDE")


def default_code_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    if not QFontInfo(font).fixedPitch():
        for family in ("Menlo", "SF Mono", "Consolas", "DejaVu Sans Mono", "Courier New"):
            if family in QFontDatabase.families():
                font = QFont(family)
                break
        font.setStyleHint(QFont.Monospace)
    font.setPointSize(max(font.pointSize(), 12))
    return font


@dataclass
class EditorSettings:
    """Everything the Options dialog edits."""

    selection: str = SYSTEM
    system_light: str = LIGHT
    system_dark: str = DARK
    font_family: str = ""  # "" = default monospace font
    font_size: int = 0  # 0 = default size
    frame_style: str = "auto"  # designer window frame, see chrome.FRAME_STYLES
    show_grid: bool = True  # designer grid dots (snapping works either way)
    themes: dict[str, Theme] = field(default_factory=dict)


class ThemeManager(QObject):
    """Holds the themes and notifies editors when the effective one changes."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.settings_store = ide_settings()
        self.state = self._load()
        appearance.ide_scheme_provider = self.ide_scheme  # for forms set to "IDE"
        self._last_effective = self.current().name
        self._manages_app = False
        self._native_style: tuple[str, QPalette] | None = None  # saved for the fallback
        self._last_app_dark = self.app_is_dark()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_changed)

    # -- persistence ------------------------------------------------------------------------
    def _load(self) -> EditorSettings:
        s = self.settings_store
        themes = copy.deepcopy(BUILTIN_THEMES)
        try:
            custom = json.loads(s.value("editor/themes", "{}") or "{}")
        except (TypeError, ValueError):
            custom = {}
        for name, data in custom.items():
            fallback = themes.get(name) or themes[DARK if data.get("dark") else LIGHT]
            themes[name] = Theme.from_dict({**data, "name": name}, fallback)
        state = EditorSettings(
            selection=s.value("editor/theme", SYSTEM),
            system_light=s.value("editor/system_light", LIGHT),
            system_dark=s.value("editor/system_dark", DARK),
            font_family=s.value("editor/font_family", ""),
            font_size=int(s.value("editor/font_size", 0) or 0),
            frame_style=s.value("designer/frame_style", "auto"),
            show_grid=str(s.value("designer/show_grid", True)).lower() not in ("false", "0"),
            themes=themes,
        )
        if state.selection != SYSTEM and state.selection not in themes:
            state.selection = SYSTEM
        return state

    def apply(self, state: EditorSettings) -> None:
        """Save new settings and notify all editors."""
        self.state = copy.deepcopy(state)
        s = self.settings_store
        s.setValue("editor/theme", state.selection)
        s.setValue("editor/system_light", state.system_light)
        s.setValue("editor/system_dark", state.system_dark)
        s.setValue("editor/font_family", state.font_family)
        s.setValue("editor/font_size", state.font_size)
        s.setValue("designer/frame_style", state.frame_style)
        s.setValue("designer/show_grid", state.show_grid)
        # Store only themes that differ from the built-in defaults
        custom = {name: theme.to_dict() for name, theme in state.themes.items()
                  if BUILTIN_THEMES.get(name) != theme}
        s.setValue("editor/themes", json.dumps(custom))
        s.sync()
        self._last_effective = self.current().name
        if self._manages_app:
            self._apply_app_scheme()
        self._last_app_dark = self.app_is_dark()
        self.changed.emit()

    def select(self, selection: str) -> None:
        state = copy.deepcopy(self.state)
        state.selection = selection
        self.apply(state)

    # -- queries ------------------------------------------------------------------------------
    def resolve(self, state: EditorSettings | None = None) -> Theme:
        state = state or self.state
        name = state.selection
        if name == SYSTEM:
            name = state.system_dark if system_is_dark() else state.system_light
        return state.themes.get(name) or state.themes[DARK if system_is_dark() else LIGHT]

    def current(self) -> Theme:
        return self.resolve()

    def ide_scheme(self) -> int:
        """The IDE's appearance as a form color scheme: System while the IDE
        follows the OS, otherwise Light or Dark."""
        if self.state.selection == SYSTEM:
            return appearance.vpSchemeSystem
        return appearance.vpSchemeDark if self.current().dark else appearance.vpSchemeLight

    def app_is_dark(self) -> bool:
        """Whether the IDE window (menus, panels, icons) is dark."""
        if self.state.selection == SYSTEM:
            return system_is_dark()
        return self.current().dark

    # -- the application's color scheme ----------------------------------------------------------
    def manage_application(self) -> None:
        """Make the whole application follow the theme (called by the IDE)."""
        self._manages_app = True
        self._apply_app_scheme()
        self._last_app_dark = self.app_is_dark()

    def release_application(self) -> None:
        """Stop forcing a scheme and restore the native look."""
        if not self._manages_app:
            return
        self._manages_app = False
        appearance.set_app_override(False)
        QGuiApplication.styleHints().unsetColorScheme()
        self._restore_native_style()

    def _apply_app_scheme(self) -> None:
        app = QApplication.instance()
        hints = app.styleHints()
        if self.state.selection == SYSTEM:
            appearance.set_app_override(False)
            hints.unsetColorScheme()
            self._restore_native_style()
            return
        dark = self.current().dark
        wanted = Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light
        appearance.set_app_override(True)
        hints.setColorScheme(wanted)
        if hints.colorScheme() == wanted:
            self._restore_native_style()
            return
        # The platform can't switch schemes: emulate with Fusion + a palette
        if self._native_style is None:
            self._native_style = (app.style().name(), QPalette(app.palette()))
        app.setStyle("Fusion")
        app.setPalette(appearance.scheme_palette(dark))

    def _restore_native_style(self) -> None:
        if self._native_style is None:
            return
        name, palette = self._native_style
        self._native_style = None
        app = QApplication.instance()
        app.setStyle(name)
        app.setPalette(palette)

    def font(self, state: EditorSettings | None = None) -> QFont:
        state = state or self.state
        font = default_code_font()
        if state.font_family:
            font.setFamily(state.font_family)
        if state.font_size > 0:
            font.setPointSize(state.font_size)
        return font

    def _on_system_changed(self, *_):
        if self.state.selection != SYSTEM:
            return
        if self.current().name != self._last_effective or \
                self.app_is_dark() != self._last_app_dark:
            self._last_effective = self.current().name
            self._last_app_dark = self.app_is_dark()
            self.changed.emit()


_manager: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def reset_theme_manager() -> None:
    """Forget the singleton (used by tests with isolated settings)."""
    global _manager
    if _manager is not None:
        _manager.release_application()
        appearance.ide_scheme_provider = None
    _manager = None
