"""VB6 style colors.

Like VB6, colors are integers in &H00BBGGRR& order, so ``RGB(255, 0, 0)``
equals ``vpRed`` equals ``0x0000FF``. Color properties also accept
``"#RRGGBB"`` strings and Qt color names for convenience.

``RGBA(red, green, blue, alpha)`` is a color you can partly see through, for
the graphics methods: its transparency (255 - alpha) is in the top byte, so
0 there (every RGB color) is opaque. Color properties keep just the color.

System colors, as VB's (``vpButtonFace``, ``vpGrayText``... ``&H800000nn&``),
are the application's palette's colors where they are used: a property set
to one keeps it, and follows the palette (light, dark) when it changes.
VP6 adds ``vpPlaceholderText``, ``vpLinkText`` and ``vpFormText`` (a form's
text, as a Label's). (An RGBA color with alpha 127 and those values would read
as a system color: use 126 or 128.)
"""

from PySide6.QtGui import QColor, QPalette

vpBlack = 0x000000
vpRed = 0x0000FF
vpGreen = 0x00FF00
vpYellow = 0x00FFFF
vpBlue = 0xFF0000
vpMagenta = 0xFF00FF
vpCyan = 0xFFFF00
vpWhite = 0xFFFFFF

_QB_COLORS = [
    0x000000, 0x800000, 0x008000, 0x808000, 0x000080, 0x800080, 0x008080, 0xC0C0C0,
    0x808080, 0xFF0000, 0x00FF00, 0xFFFF00, 0x0000FF, 0xFF00FF, 0x00FFFF, 0xFFFFFF,
]  # VB &H00BBGGRR& values


def RGB(red: int, green: int, blue: int) -> int:
    """Return a VB color value (BGR order) for the given components."""
    return (int(red) & 0xFF) | ((int(green) & 0xFF) << 8) | ((int(blue) & 0xFF) << 16)


def RGBA(red: int, green: int, blue: int, alpha: int = 255) -> int:
    """A color with an alpha, for the graphics methods: 255 opaque (as RGB),
    0 invisible, between them partly see-through."""
    return RGB(red, green, blue) | ((255 - (int(alpha) & 0xFF)) << 24)


def QBColor(index: int) -> int:
    """Return one of the 16 classic QuickBasic colors (0-15)."""
    return _QB_COLORS[index]


# System colors: their palette group and role, by their number (VB's 0-24, then VP6's)
_A, _I, _D = QPalette.Active, QPalette.Inactive, QPalette.Disabled
_SYSTEM = (
    (_A, QPalette.Button), (_A, QPalette.Dark), (_A, QPalette.Highlight),
    (_I, QPalette.Highlight), (_A, QPalette.Window), (_A, QPalette.Base), (_A, QPalette.Shadow),
    (_A, QPalette.WindowText), (_A, QPalette.Text), (_A, QPalette.HighlightedText),
    (_A, QPalette.Mid), (_I, QPalette.Mid), (_A, QPalette.Dark), (_A, QPalette.Highlight),
    (_A, QPalette.HighlightedText), (_A, QPalette.Button), (_A, QPalette.Dark),
    (_D, QPalette.Text), (_A, QPalette.ButtonText), (_I, QPalette.WindowText),
    (_A, QPalette.Light), (_A, QPalette.Shadow), (_A, QPalette.Midlight),
    (_A, QPalette.ToolTipText), (_A, QPalette.ToolTipBase), (_A, QPalette.PlaceholderText),
    (_A, QPalette.Link), (_A, QPalette.WindowText),
)
SYSTEM_BASE = 0x80000000


def is_system(value) -> bool:
    """Whether a color is a system color (vpButtonFace...)."""
    return isinstance(value, int) and not isinstance(value, bool) and \
        value & 0xFFFFFF00 == SYSTEM_BASE and value & 0xFF < len(_SYSTEM)


def current_palette() -> QPalette:
    """The palette system colors come from: App.ColorScheme's when the program
    chose one, else the application's (the system's look)."""
    from PySide6.QtWidgets import QApplication

    from . import appearance

    scheme = appearance.app_scheme
    if scheme is not None and scheme != appearance.vpSchemeSystem:
        return appearance.scheme_palette(appearance.is_dark(scheme))
    return QApplication.palette()


def system_color(value, palette: QPalette | None = None) -> QColor:
    """A system color as it is now in ``palette`` (else ``current_palette()``)."""
    palette = current_palette() if palette is None else palette
    group, role = _SYSTEM[value & 0xFF]
    return QColor(palette.color(group, role))


def to_qcolor(value, palette: QPalette | None = None) -> QColor | None:
    """Convert a VB color (int), '#RRGGBB' string or QColor to a QColor (a
    system color: as ``palette``, else the current palette, has it now)."""
    if value is None:
        return None
    if is_system(value):
        return system_color(value, palette)
    if isinstance(value, QColor):
        return value
    if isinstance(value, str):
        color = QColor(value)
        if not color.isValid():
            raise ValueError(f"Invalid color: {value!r}")
        return color
    value = int(value)
    return QColor(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF,
                  255 - ((value >> 24) & 0xFF))


def css(color: QColor) -> str:
    """A color for a style sheet (its alpha kept)."""
    if color.alpha() == 255:
        return color.name()
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def from_qcolor(color: QColor) -> int:
    return RGB(color.red(), color.green(), color.blue())


def normalize(value) -> int | None:
    """Normalize any accepted color representation to a VB color int (a system
    color stays one)."""
    if value is None:
        return None
    if is_system(value):
        return int(value)
    return from_qcolor(to_qcolor(value))


__all__ = ["RGB", "RGBA", "QBColor", "vpBlack", "vpRed", "vpGreen", "vpYellow", "vpBlue",
           "vpMagenta", "vpCyan", "vpWhite"]
