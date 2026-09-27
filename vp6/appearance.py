"""Light / dark color schemes for forms.

``Form.ColorScheme`` is one of:

* ``vpSchemeProjectDefault`` (0) - use the project's scheme (the default),
* ``vpSchemeSystem`` (1) - native look, follows the OS appearance live,
* ``vpSchemeLight`` (2) / ``vpSchemeDark`` (3) - forced light or dark,
* ``vpSchemeIDE`` (4) - follow the VP6 IDE's appearance: live in the
  designer; when run from the IDE, the IDE's appearance at launch (passed in
  the ``VP6_IDE_SCHEME`` environment variable); otherwise System.

Native styles (notably macOS) ignore widget palettes, so forced schemes use
Qt's Fusion style with a fixed light or dark palette on the form, its
controls and the message boxes shown over it.

The project scheme is set by the runner from the ``.vp6p`` file. When a
form runs on its own (``python Form1.py``) it is read from a ``.vp6p`` next
to the form's file, if there is one.
"""

from __future__ import annotations

import glob
import os
import sys

import shiboken6
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QStyle, QStyleFactory, QWidget

vpSchemeProjectDefault = 0
vpSchemeSystem = 1
vpSchemeLight = 2
vpSchemeDark = 3
vpSchemeIDE = 4

PROJECT_SCHEMES = {"system": vpSchemeSystem, "light": vpSchemeLight, "dark": vpSchemeDark,
                   "ide": vpSchemeIDE}
SCHEME_NAMES = {v: k for k, v in PROJECT_SCHEMES.items()}
IDE_SCHEME_ENV = "VP6_IDE_SCHEME"

# Set by the IDE (inside the IDE process): returns System, Light or Dark
ide_scheme_provider = None

# Set by the project runner; None = look for a .vp6p next to the form
project_scheme: int | None = None
_found_schemes: dict[str, int] = {}
_fusion = None  # see fusion_style
_fusion_address = None


def scheme_from_name(name: str | None) -> int:
    return PROJECT_SCHEMES.get((name or "system").lower(), vpSchemeSystem)


def ide_scheme() -> int:
    """What vpSchemeIDE currently means: System, Light or Dark."""
    if ide_scheme_provider is not None:
        return ide_scheme_provider()
    scheme = PROJECT_SCHEMES.get(os.environ.get(IDE_SCHEME_ENV, "").lower(), vpSchemeSystem)
    return scheme if scheme != vpSchemeIDE else vpSchemeSystem


def resolve(scheme: int) -> int:
    """Turn any scheme except Project Default into System, Light or Dark."""
    if scheme == vpSchemeIDE:
        scheme = ide_scheme()
    return scheme if scheme in (vpSchemeLight, vpSchemeDark) else vpSchemeSystem


def project_scheme_for(directory: str) -> int:
    """The project scheme for a form in ``directory``."""
    if project_scheme is not None:
        return project_scheme
    if directory not in _found_schemes:
        scheme = vpSchemeSystem
        from .project import Project

        for path in sorted(glob.glob(os.path.join(directory, "*.vp6p"))):
            try:
                scheme = scheme_from_name(Project.load(path).color_scheme)
                break
            except (OSError, ValueError):
                continue
        _found_schemes[directory] = scheme
    return _found_schemes[directory]


def _qt_scheme_is_dark() -> bool:
    from PySide6.QtCore import Qt

    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return QGuiApplication.palette().color(QPalette.Window).lightness() < 128


# The IDE can force the whole application light or dark. Qt then reports the
# forced scheme, so the real OS appearance is queried from the OS instead.
_override_active = False
_os_dark_before_override = False
_os_query_cache: tuple[float, bool] | None = None


def set_app_override(active: bool) -> None:
    """Called by the IDE before it forces (or stops forcing) the app scheme."""
    global _override_active, _os_dark_before_override, _os_query_cache
    if active and not _override_active:
        _os_dark_before_override = _qt_scheme_is_dark()
    _override_active = active
    _os_query_cache = None


def app_override_active() -> bool:
    return _override_active


def _query_os_dark() -> bool:
    global _os_query_cache
    import time

    now = time.monotonic()
    if _os_query_cache and now - _os_query_cache[0] < 2:
        return _os_query_cache[1]
    dark = _os_dark_before_override
    try:
        if sys.platform == "darwin":
            import subprocess

            result = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                    capture_output=True, text=True, timeout=1)
            dark = result.stdout.strip().lower() == "dark"
        elif sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                                 r"\CurrentVersion\Themes\Personalize")
            dark = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:  # noqa: BLE001 - fall back to the last known appearance
        pass
    _os_query_cache = (now, dark)
    return dark


def system_is_dark() -> bool:
    """Whether the operating system appearance is dark."""
    return _query_os_dark() if _override_active else _qt_scheme_is_dark()


def is_dark(scheme: int) -> bool:
    """Whether a resolved scheme (System/Light/Dark) renders dark right now."""
    return scheme == vpSchemeDark or (scheme == vpSchemeSystem and system_is_dark())


def fusion_style():
    """One shared Fusion style, a child of the application so it outlives
    every widget using it. Don't keep what this returns: call it again.

    PySide treats a style as belonging to the widgets it is set on, and when
    such a widget is destroyed (e.g. a Toolbar's buttons being rebuilt) it
    invalidates the style's Python wrapper, although the C++ style lives on
    and other widgets still use it. So the style is remembered by its C++
    address, and a fresh wrapper is found among the application's children
    when the old one was invalidated."""
    global _fusion, _fusion_address
    if _fusion is not None and shiboken6.isValid(_fusion):
        return _fusion
    app = QGuiApplication.instance()
    if _fusion_address is not None:
        for child in app.children():  # the same style: a new wrapper
            if isinstance(child, QStyle) and shiboken6.getCppPointer(child)[0] == \
                    _fusion_address:
                _fusion = child
                return _fusion
    _fusion = QStyleFactory.create("Fusion")
    _fusion.setParent(app)
    _fusion_address = shiboken6.getCppPointer(_fusion)[0]
    return _fusion


def _palette(colors: dict, disabled: dict) -> QPalette:
    palette = QPalette()
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role, color in disabled.items():
        palette.setColor(QPalette.Disabled, role, QColor(color))
    return palette


def scheme_palette(dark: bool) -> QPalette:
    """A complete palette for a forced light or dark scheme."""
    if dark:
        return _palette({
            QPalette.Window: "#353535", QPalette.WindowText: "#f0f0f0",
            QPalette.Base: "#252525", QPalette.AlternateBase: "#303030",
            QPalette.Text: "#f0f0f0", QPalette.Button: "#3c3c3c",
            QPalette.ButtonText: "#f0f0f0", QPalette.BrightText: "#ff5555",
            QPalette.Light: "#505050", QPalette.Midlight: "#454545", QPalette.Mid: "#2a2a2a",
            QPalette.Dark: "#1e1e1e", QPalette.Shadow: "#141414",
            QPalette.Highlight: "#2a82da", QPalette.HighlightedText: "#ffffff",
            QPalette.Link: "#5aa9f0", QPalette.LinkVisited: "#b48ef0",
            QPalette.ToolTipBase: "#454545", QPalette.ToolTipText: "#f0f0f0",
            QPalette.PlaceholderText: "#8a8a8a",
        }, {QPalette.WindowText: "#7f7f7f", QPalette.Text: "#7f7f7f",
            QPalette.ButtonText: "#7f7f7f", QPalette.Base: "#2d2d2d"})
    return _palette({
        QPalette.Window: "#efefef", QPalette.WindowText: "#000000",
        QPalette.Base: "#ffffff", QPalette.AlternateBase: "#f7f7f7",
        QPalette.Text: "#000000", QPalette.Button: "#efefef",
        QPalette.ButtonText: "#000000", QPalette.BrightText: "#ffffff",
        QPalette.Light: "#ffffff", QPalette.Midlight: "#cacaca", QPalette.Mid: "#b8b8b8",
        QPalette.Dark: "#9f9f9f", QPalette.Shadow: "#767676",
        QPalette.Highlight: "#308cc6", QPalette.HighlightedText: "#ffffff",
        QPalette.Link: "#0000ff", QPalette.LinkVisited: "#ff00ff",
        QPalette.ToolTipBase: "#ffffdc", QPalette.ToolTipText: "#000000",
        QPalette.PlaceholderText: "#7f7f7f",
    }, {QPalette.WindowText: "#bebebe", QPalette.Text: "#bebebe",
        QPalette.ButtonText: "#bebebe", QPalette.Base: "#efefef"})


def style_tree(widget: QWidget, style) -> None:
    """Apply ``style`` (None = the application style) to a widget and all its
    descendants; Qt doesn't propagate styles to children."""
    from PySide6.QtCore import Qt

    for w in [widget, *widget.findChildren(QWidget)]:
        if style is None:
            if w.testAttribute(Qt.WA_SetStyle):
                w.setStyle(None)
        else:
            w.setStyle(style)


def match_dialog(dialog: QWidget, parent: QWidget | None) -> None:
    """Give a message box the color scheme of the form it is shown over."""
    form = getattr(parent.window(), "_vp_form", None) if parent is not None else None
    if form is None:
        return
    scheme = form._effective_scheme()
    if scheme in (vpSchemeLight, vpSchemeDark):
        dialog.setPalette(scheme_palette(scheme == vpSchemeDark))
        style_tree(dialog, fusion_style())


__all__ = ["vpSchemeProjectDefault", "vpSchemeSystem", "vpSchemeLight", "vpSchemeDark",
           "vpSchemeIDE"]
