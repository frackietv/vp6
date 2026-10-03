"""Window frames painted around the form in the designer.

The designer can't embed a real title bar, so it paints one that looks like
the target platform's: macOS, Windows 11, GNOME or the classic VB6 look.
"Automatic" picks the one matching the OS the IDE runs on.

The frame reflects the form's BorderStyle, ControlBox, MinButton and
MaxButton the way the real window will. Title bars are drawn light or dark
as the real one will be (``FrameInfo.title_dark``: the form's scheme where
the OS lets a window have its own, else the OS appearance); the classic
frame follows the form's own color scheme.

macOS and Windows 11 windows have rounded corners at the bottom too. The
form's widget is square and lies over the frame, so ``paint_corners`` paints
those corners again over it (from the designer's overlay): the workspace,
the shadow and the outline, outside the rounded window.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen

AUTO, MACOS, WINDOWS, GNOME, CLASSIC = "auto", "macos", "windows", "gnome", "classic"
FRAME_STYLES = {
    AUTO: "Automatic (match this computer)",
    MACOS: "macOS",
    WINDOWS: "Windows 11",
    GNOME: "Linux (GNOME)",
    CLASSIC: "Classic (VB6)",
}


def resolve(style: str) -> str:
    if style in (MACOS, WINDOWS, GNOME, CLASSIC):
        return style
    if sys.platform == "darwin":
        return MACOS
    if sys.platform == "win32":
        return WINDOWS
    return GNOME


@dataclass
class FrameInfo:
    caption: str
    border_style: int = 2  # 0 None, 1 Fixed Single, 2 Sizable, 3 Fixed Dialog, 4/5 Tool
    control_box: bool = True
    min_button: bool = True
    max_button: bool = True
    title_dark: bool = False  # title bar appearance
    form_dark: bool = False  # the form's own scheme (classic frame, menu bar)
    menus: tuple[str, ...] = ()  # captions of the form's menu bar, if it has one

    @property
    def tool(self) -> bool:
        return self.border_style in (4, 5)

    @property
    def can_minimize(self) -> bool:
        return self.control_box and self.min_button and self.border_style in (1, 2)

    @property
    def can_maximize(self) -> bool:
        return self.control_box and self.max_button and self.border_style == 2


def metrics(style: str, info: FrameInfo) -> tuple[int, int]:
    """(title bar height, border width) for a resolved frame style."""
    if info.border_style == 0:
        return 0, 0
    title, tool_title, border = {
        MACOS: (28, 22, 1), WINDOWS: (32, 26, 1), GNOME: (38, 30, 1), CLASSIC: (22, 18, 4),
    }[style]
    return (tool_title if info.tool else title), border


MENU_HEIGHT = 22
_MENU_PADDING = 9


def menu_height(info: FrameInfo) -> int:
    """Height of the menu bar drawn between the title bar and the form."""
    return MENU_HEIGHT if info.menus else 0


def frame_rect(client: QRect, style: str, info: FrameInfo) -> QRect:
    title, border = metrics(style, info)
    title += menu_height(info)
    return QRect(client.left() - border, client.top() - border - title,
                 client.width() + 2 * border, client.height() + title + 2 * border)


def paint(p: QPainter, style: str, client: QRect, info: FrameInfo) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    # The painters see the menu bar as part of the window's inside
    inside = client.adjusted(0, -menu_height(info), 0, 0)
    if info.border_style == 0:
        _shadow(p, QRectF(inside), 0)
    else:
        {MACOS: _macos, WINDOWS: _windows, GNOME: _gnome, CLASSIC: _classic}[style](
            p, frame_rect(client, style, info), inside, info)
    if info.menus:
        _menu_bar(p, client, info)
    p.restore()


def _menu_font() -> QFont:
    font = QFont()
    font.setPixelSize(13)
    return font


def _menu_text(caption: str) -> str:
    return caption.replace("&&", "\0").replace("&", "").replace("\0", "&")


def menu_item_rects(client: QRect, info: FrameInfo) -> list[QRect]:
    """Where each menu bar caption is drawn (in info.menus order)."""
    metrics_ = QFontMetrics(_menu_font())
    rects, x = [], client.left() + 2
    top = client.top() - MENU_HEIGHT
    for caption in info.menus:
        width = metrics_.horizontalAdvance(_menu_text(caption)) + 2 * _MENU_PADDING
        rects.append(QRect(x, top, width, MENU_HEIGHT))
        x += width
    return rects


def _menu_bar(p: QPainter, client: QRect, info: FrameInfo) -> None:
    bar = QRect(client.left(), client.top() - MENU_HEIGHT, client.width(), MENU_HEIGHT)
    dark = info.form_dark
    p.setRenderHint(QPainter.Antialiasing, False)
    p.fillRect(bar, QColor("#2b2b2b" if dark else "#f3f3f3"))
    p.setPen(QColor("#3d3d3d" if dark else "#dcdcdc"))
    p.drawLine(bar.bottomLeft(), bar.bottomRight())
    p.setFont(_menu_font())
    p.setPen(QColor("#e8e8e8" if dark else "#1a1a1a"))
    p.save()
    p.setClipRect(bar)
    for caption, rect in zip(info.menus, menu_item_rects(client, info)):
        p.drawText(rect, Qt.AlignCenter, _menu_text(caption))
    p.restore()


# --- helpers ---------------------------------------------------------------------------

def _shadow(p: QPainter, rect: QRectF, radius: float, strength: int = 26) -> None:
    p.setPen(Qt.NoPen)
    for i in range(8, 0, -1):
        p.setBrush(QColor(0, 0, 0, max(strength // i, 2)))
        p.drawRoundedRect(rect.adjusted(-i, -i + 3, i, i + 3), radius + i, radius + i)


def _rounded(rect: QRectF, radius: float, bottom: float = 0) -> QPainterPath:
    """A window's outline: rounded at the top by ``radius``, at the bottom by
    ``bottom`` (0: square)."""
    path = QPainterPath()
    path.moveTo(rect.left(), rect.bottom() - bottom)
    path.lineTo(rect.left(), rect.top() + radius)
    path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
    path.lineTo(rect.right() - radius, rect.top())
    path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
    path.lineTo(rect.right(), rect.bottom() - bottom)
    if bottom:
        path.quadTo(rect.right(), rect.bottom(), rect.right() - bottom, rect.bottom())
        path.lineTo(rect.left() + bottom, rect.bottom())
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - bottom)
    path.closeSubpath()
    return path


# Rounded bottom corners (macOS, Windows 11), and how their outlines and shadows look
_BOTTOM_RADIUS = {MACOS: 10, WINDOWS: 8}
_SHADOW = {MACOS: 40, WINDOWS: 34, GNOME: 40}


def _outline_color(style: str, dark: bool) -> QColor:
    if style == WINDOWS:
        return QColor(255, 255, 255, 40) if dark else QColor(0, 0, 0, 60)
    return QColor(0, 0, 0, 160 if dark else 70)


def bottom_radius(style: str, info: FrameInfo) -> int:
    """The radius of the window's bottom corners (0: square)."""
    return 0 if info.border_style == 0 else _BOTTOM_RADIUS.get(style, 0)


def corner_path(client: QRect, style: str, info: FrameInfo) -> QPainterPath:
    """The window's two bottom corners outside its rounded outline (empty
    when they are square)."""
    radius = bottom_radius(style, info)
    if not radius:
        return QPainterPath()
    frame = QRectF(frame_rect(client, style, info))
    strip = QPainterPath()
    strip.addRect(QRectF(frame.left(), frame.bottom() - radius, frame.width(), radius + 2))
    return strip.subtracted(_rounded(frame, 0, radius))


def paint_corners(p: QPainter, style: str, client: QRect, info: FrameInfo,
                  workspace: QColor) -> None:
    """Paint the window's rounded bottom corners over the (square) form: the
    workspace outside them, the window's shadow there, and its outline."""
    radius = bottom_radius(style, info)
    if not radius:
        return
    frame = QRectF(frame_rect(client, style, info))
    corners = corner_path(client, style, info)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setClipPath(corners)
    p.fillRect(frame.adjusted(-1, -1, 1, 1), workspace)
    _shadow(p, frame, radius, _SHADOW[style])
    # The outline again where it was painted over: in the corners, and over the form
    # (the canvas's outline beside them stays: drawn twice, it would look darker)
    covered = QPainterPath()
    covered.addRect(QRectF(client))
    p.setClipPath(corners.united(covered))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_outline_color(style, info.title_dark), 1))
    p.drawPath(_rounded(frame.adjusted(0.5, 0.5, 0.5, 0.5), radius, radius))
    p.restore()


def _top_rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(rect.left(), rect.bottom())
    path.lineTo(rect.left(), rect.top() + radius)
    path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
    path.lineTo(rect.right() - radius, rect.top())
    path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
    path.lineTo(rect.right(), rect.bottom())
    path.closeSubpath()
    return path


def _title_font(pixel_size: int, bold: bool) -> QFont:
    font = QFont()
    font.setPixelSize(pixel_size)
    font.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return font


def _draw_title(p, rect: QRect, text: str, font: QFont, color: QColor, align) -> None:
    p.setFont(font)
    p.setPen(color)
    p.drawText(rect, align | Qt.AlignVCenter,
               QFontMetrics(font).elidedText(text, Qt.ElideRight, max(rect.width(), 0)))


# --- macOS -------------------------------------------------------------------------------

_TRAFFIC = {"close": ("#ff5f57", "#e0443e"), "min": ("#febc2e", "#dea123"),
            "max": ("#28c840", "#1aab29")}


def _macos(p: QPainter, frame: QRect, client: QRect, info: FrameInfo) -> None:
    dark = info.title_dark
    radius = 10
    title = QRectF(frame.left(), frame.top(), frame.width(), client.top() - frame.top())
    _shadow(p, QRectF(frame), radius, _SHADOW[MACOS])
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#323234" if dark else "#ebebeb"))
    p.drawPath(_top_rounded(title, radius))
    p.fillRect(QRectF(frame.left(), client.top(), frame.width(), frame.bottom() - client.top() + 1),
               QColor("#323234" if dark else "#ebebeb"))
    p.setPen(QColor("#1c1c1e" if dark else "#d4d4d4"))
    p.drawLine(QPointF(frame.left(), client.top() - 0.5),
               QPointF(frame.right() + 1, client.top() - 0.5))
    # Outline (plus a faint inner highlight in dark mode, like macOS)
    outline = _rounded(QRectF(frame).adjusted(0.5, 0.5, 0.5, 0.5), radius, radius)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_outline_color(MACOS, dark), 1))
    p.drawPath(outline)
    if dark:
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(_top_rounded(QRectF(frame).adjusted(1.5, 1.5, -0.5, 0), radius - 1))

    # Traffic lights
    diameter = 10 if info.tool else 12
    center_y = title.center().y()
    x = frame.left() + (7 if info.tool else 9)
    buttons = [("close", info.control_box)] if info.tool else [
        ("close", info.control_box), ("min", info.can_minimize), ("max", info.can_maximize)]
    for name, enabled in buttons:
        if enabled:
            fill, edge = _TRAFFIC[name]
        else:
            fill, edge = ("#545456", "#48484a") if dark else ("#d9d9d9", "#c6c6c6")
        p.setBrush(QColor(fill))
        p.setPen(QPen(QColor(edge), 0.8))
        p.drawEllipse(QRectF(x, center_y - diameter / 2, diameter, diameter))
        x += diameter + 8
    # Centered on the window, clear of the buttons on both sides
    inset = int(x - frame.left())
    text_rect = QRect(frame.left() + inset, int(title.top()), frame.width() - 2 * inset,
                      int(title.height()))
    _draw_title(p, text_rect, info.caption, _title_font(11 if info.tool else 13, True),
                QColor("#dfdfdf" if dark else "#3b3b3b"), Qt.AlignHCenter)


# --- Windows 11 -----------------------------------------------------------------------------

def _windows(p: QPainter, frame: QRect, client: QRect, info: FrameInfo) -> None:
    dark = info.title_dark
    radius = 8
    title = QRectF(frame.left(), frame.top(), frame.width(), client.top() - frame.top())
    background = QColor("#202020" if dark else "#ffffff")
    ink = QColor("#ffffff" if dark else "#000000")
    _shadow(p, QRectF(frame), radius, _SHADOW[WINDOWS])
    p.setPen(Qt.NoPen)
    p.setBrush(background)
    p.drawPath(_top_rounded(title, radius))
    p.fillRect(QRectF(frame.left(), client.top(), frame.width(), frame.bottom() - client.top() + 1),
               background)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_outline_color(WINDOWS, dark), 1))
    p.drawPath(_rounded(QRectF(frame).adjusted(0.5, 0.5, 0.5, 0.5), radius, radius))

    # Caption buttons, right to left: close, maximize, minimize
    width = 36 if info.tool else 46
    right = frame.right() + 1
    glyph = 10 if not info.tool else 8
    cy = title.center().y()
    buttons = []
    if info.control_box:
        buttons.append(("close", True))
        if not info.tool and info.border_style in (1, 2) and (info.min_button or info.max_button):
            buttons += [("max", info.can_maximize), ("min", info.can_minimize)]
    for name, enabled in buttons:
        cx = right - width / 2
        color = QColor(ink)
        color.setAlpha(255 if enabled else 90)
        p.setPen(QPen(color, 1))
        g = glyph / 2
        if name == "close":
            p.drawLine(QPointF(cx - g, cy - g), QPointF(cx + g, cy + g))
            p.drawLine(QPointF(cx + g, cy - g), QPointF(cx - g, cy + g))
        elif name == "max":
            p.drawRoundedRect(QRectF(cx - g, cy - g, glyph, glyph), 1.5, 1.5)
        else:
            p.drawLine(QPointF(cx - g, cy + 0.5), QPointF(cx + g, cy + 0.5))
        right -= width

    # App icon and title, left aligned
    icon = QRectF(frame.left() + 12, cy - 8, 16, 16)
    p.setPen(QPen(QColor("#9aa4b0"), 1))
    p.setBrush(QColor("#3c3c3c") if dark else QColor("#f0f0f0"))
    p.drawRoundedRect(icon.adjusted(1, 2, -1, -2), 1.5, 1.5)
    p.fillRect(icon.adjusted(1.5, 2.5, -1.5, -10), QColor("#2b79d0"))
    text_rect = QRect(int(icon.right()) + 10, int(title.top()),
                      int(right - icon.right() - 16), int(title.height()))
    _draw_title(p, text_rect, info.caption, _title_font(11 if info.tool else 12, False), ink,
                Qt.AlignLeft)


# --- GNOME (Adwaita) --------------------------------------------------------------------------

def _gnome(p: QPainter, frame: QRect, client: QRect, info: FrameInfo) -> None:
    dark = info.title_dark
    radius = 12
    title = QRectF(frame.left(), frame.top(), frame.width(), client.top() - frame.top())
    _shadow(p, QRectF(frame), radius, _SHADOW[GNOME])
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#303030" if dark else "#ebebeb"))
    p.drawPath(_top_rounded(title, radius))
    p.fillRect(QRectF(frame.left(), client.top(), frame.width(), frame.bottom() - client.top() + 1),
               QColor("#303030" if dark else "#ebebeb"))
    p.setPen(QColor("#1e1e1e" if dark else "#d0d0d0"))
    p.drawLine(QPointF(frame.left(), client.top() - 0.5),
               QPointF(frame.right() + 1, client.top() - 0.5))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 150 if dark else 60), 1))
    p.drawPath(_top_rounded(QRectF(frame).adjusted(0.5, 0.5, 0.5, 1), radius))

    ink = QColor("#ffffff" if dark else "#2e2e2e")
    size = 22 if info.tool else 24
    cy = title.center().y()
    if info.control_box:
        center = QPointF(frame.right() - 8 - size / 2, cy)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#474747" if dark else "#dadada"))
        p.drawEllipse(center, size / 2, size / 2)
        p.setPen(QPen(ink, 1.4))
        g = 3.5
        p.drawLine(center + QPointF(-g, -g), center + QPointF(g, g))
        p.drawLine(center + QPointF(g, -g), center + QPointF(-g, g))
    margin = size + 20
    text_rect = QRect(int(frame.left() + margin), int(title.top()),
                      int(frame.width() - 2 * margin), int(title.height()))
    _draw_title(p, text_rect, info.caption, _title_font(12 if info.tool else 13, True), ink,
                Qt.AlignHCenter)


# --- Classic VB6 ------------------------------------------------------------------------------

_CLASSIC = {
    False: {"face": "#d4d0c8", "light": "#ffffff", "shadow": "#404040",
            "title": ("#0a246a", "#a6caf0"), "glyph": "#000000", "box": "#d4d0c8"},
    True: {"face": "#3a3a3c", "light": "#5c5c60", "shadow": "#111111",
           "title": ("#1b3564", "#3f6aa6"), "glyph": "#e8e8e8", "box": "#4a4a4d"},
}


def _classic(p: QPainter, frame: QRect, client: QRect, info: FrameInfo) -> None:
    p.setRenderHint(QPainter.Antialiasing, False)
    c = _CLASSIC[info.form_dark]
    face = QColor(c["face"])
    p.fillRect(frame, face)
    p.setPen(QColor(c["light"]))
    p.drawLine(frame.topLeft(), frame.topRight())
    p.drawLine(frame.topLeft(), frame.bottomLeft())
    p.setPen(QColor(c["shadow"]))
    p.drawLine(frame.bottomLeft(), frame.bottomRight())
    p.drawLine(frame.topRight(), frame.bottomRight())

    title = QRect(frame.left() + 3, frame.top() + 3, frame.width() - 6,
                  client.top() - frame.top() - 4)
    gradient = QLinearGradient(title.topLeft(), title.topRight())
    gradient.setColorAt(0, QColor(c["title"][0]))
    gradient.setColorAt(1, QColor(c["title"][1]))
    p.fillRect(title, gradient)

    box_h = min(14, title.height() - 4)
    box_w = box_h + 2
    x = title.right() - 2 - box_w
    y = title.top() + (title.height() - box_h) // 2
    buttons = []
    if info.control_box:
        buttons.append(("close", True))
        if not info.tool and info.border_style in (1, 2) and (info.min_button or info.max_button):
            buttons += [("max", info.can_maximize), ("min", info.can_minimize)]
    for name, enabled in buttons:
        rect = QRect(x, y, box_w, box_h)
        p.fillRect(rect, QColor(c["box"]))
        p.setPen(QColor(c["shadow"]))
        p.drawRect(rect.adjusted(0, 0, -1, -1))
        glyph = QColor(c["glyph"])
        if not enabled:
            glyph.setAlpha(90)
        p.setPen(QPen(glyph, 1.5 if name == "close" else 1))
        center = rect.center()
        if name == "close":
            p.drawLine(center.x() - 3, center.y() - 3, center.x() + 3, center.y() + 3)
            p.drawLine(center.x() + 3, center.y() - 3, center.x() - 3, center.y() + 3)
            x -= box_w + 2
        elif name == "max":
            p.drawRect(center.x() - 4, center.y() - 3, 8, 7)
            p.drawLine(center.x() - 4, center.y() - 2, center.x() + 4, center.y() - 2)
            x -= box_w
        else:
            p.drawLine(center.x() - 3, center.y() + 3, center.x() + 2, center.y() + 3)
    text_rect = QRect(title.left() + 6, title.top(), x - title.left() - 4, title.height())
    _draw_title(p, text_rect, info.caption, _title_font(11, True), QColor("#ffffff"),
                Qt.AlignLeft)
