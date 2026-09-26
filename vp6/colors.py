"""VB6 style colors.

Like VB6, colors are integers in &H00BBGGRR& order, so ``RGB(255, 0, 0)``
equals ``vpRed`` equals ``0x0000FF``. Color properties also accept
``"#RRGGBB"`` strings and Qt color names for convenience.
"""

from PySide6.QtGui import QColor

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


def QBColor(index: int) -> int:
    """Return one of the 16 classic QuickBasic colors (0-15)."""
    return _QB_COLORS[index]


def to_qcolor(value) -> QColor | None:
    """Convert a VB color (int), '#RRGGBB' string or QColor to a QColor."""
    if value is None:
        return None
    if isinstance(value, QColor):
        return value
    if isinstance(value, str):
        color = QColor(value)
        if not color.isValid():
            raise ValueError(f"Invalid color: {value!r}")
        return color
    value = int(value)
    return QColor(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)


def from_qcolor(color: QColor) -> int:
    return RGB(color.red(), color.green(), color.blue())


def normalize(value) -> int | None:
    """Normalize any accepted color representation to a VB color int."""
    if value is None:
        return None
    return from_qcolor(to_qcolor(value))


__all__ = ["RGB", "QBColor", "vpBlack", "vpRed", "vpGreen", "vpYellow", "vpBlue",
           "vpMagenta", "vpCyan", "vpWhite"]
