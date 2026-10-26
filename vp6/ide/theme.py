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
import os

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from .. import appearance
from .logic import settings as shared_settings
from ..appearance import system_is_dark
from .logic.themes import (BUILTIN_THEMES, DARK, LIGHT, SYNTAX_ROLES, SYSTEM,  # noqa: F401
                           UI_ROLES, EditorSettings, TextStyle, Theme, read_settings, resolve,
                           write_settings)

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


shared_settings.use_by_default(ide_settings)  # (the shared logic's: Claude's, Codex's)


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
        return read_settings(self.settings_store)

    def apply(self, state: EditorSettings) -> None:
        """Save new settings and notify all editors."""
        self.state = copy.deepcopy(state)
        write_settings(state, self.settings_store)
        self.settings_store.sync()
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
        return resolve(state or self.state, system_is_dark())

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
