"""Formulas drawn with Qt: ``vp6help.tex``'s layouts measured with a QFont and
painted with a QPainter, and formulas in a ``QTextDocument`` as inline objects
(one character each, the TeX source in its format) that follow the text's
font, size and colour, light or dark, at any resolution.

    install(document)              # pictures vp6help's HTML made of formulas become them
    insert_math(cursor, r"x^2")    # a formula at the cursor
    text_of(cursor)                # the selection's text, formulas as $…$ (TeX)

A formula that doesn't parse shows its source in red (its tooltip says why).
"""

from __future__ import annotations

from collections import OrderedDict
from urllib.parse import quote, unquote

from PySide6.QtCore import QMimeData, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QFontMetricsF,
                           QGuiApplication, QPainter, QPainterPath, QPen, QPyTextObject,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)

from . import tex

__all__ = ["MATH_OBJECT", "TEX_PROPERTY", "DISPLAY_PROPERTY", "SCHEME", "QtMetrics", "paint",
           "layout_of", "register", "install", "math_format", "insert_math", "is_math",
           "text_of", "has_math", "mime_data", "insert_text", "to_source", "image_url",
           "formula_text", "error_color"]

MATH_OBJECT = int(QTextFormat.UserObject) + 77
TEX_PROPERTY = int(QTextFormat.UserProperty) + 77
DISPLAY_PROPERTY = int(QTextFormat.UserProperty) + 78
SCHEME = "vp6math"  # (vp6help's HTML: <img src="vp6math:inline,x%5E2">)
OBJECT = "￼"
_ERROR_COLORS = ("#c62828", "#ff6b6b")  # (on a light background, on a dark one)


def image_url(tex_source: str, display: bool) -> str:
    """The address of a formula as a picture in HTML (``install`` turns it into one)."""
    return f"{SCHEME}:{'display' if display else 'inline'},{quote(tex_source, safe='')}"


def _dpi() -> float:
    screen = QGuiApplication.primaryScreen() if QGuiApplication.instance() else None
    return screen.logicalDotsPerInchY() if screen is not None else 96.0


class QtMetrics(tex.Metrics):
    """A QFont's sizes, for the layout (fonts in pixels, so drawing them on
    any device gives what was measured)."""

    def __init__(self, font: QFont):
        self.font = QFont(font)
        size = font.pixelSize()
        super().__init__(size if size > 0 else font.pointSizeF() * _dpi() / 72)
        self._fonts: dict = {}
        self._sizes: dict = {}
        metrics = QFontMetricsF(self.qfont("rm", 1.0))
        self._x_height = metrics.xHeight()
        plus = metrics.tightBoundingRect("+")
        self._axis = -(plus.top() + plus.bottom()) / 2 if plus.height() > 0 else 0.25 * self.em

    def qfont(self, font: str, scale: float) -> QFont:
        key = (font, round(scale, 3))
        qfont = self._fonts.get(key)
        if qfont is None:
            qfont = QFont(self.font)
            qfont.setPixelSize(max(1, round(self.em * scale)))
            qfont.setItalic(font in ("it", "bfit"))
            if font in ("bf", "bfit"):
                qfont.setWeight(QFont.Bold)
            qfont.setUnderline(False)
            qfont.setStrikeOut(False)
            if font == "tt":
                qfont.setFamilies([QFontDatabase.systemFont(QFontDatabase.FixedFont).family()])
            self._fonts[key] = qfont
        return qfont

    def measure(self, text: str, font: str, scale: float):
        key = (text, font, round(scale, 3))
        size = self._sizes.get(key)
        if size is None:
            metrics = QFontMetricsF(self.qfont(font, scale))
            width = metrics.horizontalAdvance(text)
            if not text.strip():
                size = (width, 0.0, 0.0, 0.0)
            else:
                ink = metrics.tightBoundingRect(text)
                italic = max(0.0, ink.right() - width) if font in ("it", "bfit") else 0.0
                size = (width, max(0.0, -ink.top()), max(0.0, ink.bottom()),
                        min(italic, 0.15 * self.em * scale))
            self._sizes[key] = size
        return size

    def x_height(self, scale: float = 1.0) -> float:
        return self._x_height * scale

    def axis_height(self, scale: float = 1.0) -> float:
        return self._axis * scale

    def rule_thickness(self, scale: float = 1.0) -> float:
        return max(0.8, 0.06 * self.em * scale)


def _path(commands, x: float, y: float) -> QPainterPath:
    path = QPainterPath()
    for command in commands:
        op = command[0]
        if op == "M":
            path.moveTo(x + command[1], y + command[2])
        elif op == "L":
            path.lineTo(x + command[1], y + command[2])
        elif op == "C":
            path.cubicTo(x + command[1], y + command[2], x + command[3], y + command[4],
                         x + command[5], y + command[6])
        elif op == "Z":
            path.closeSubpath()
    return path


def error_color(color: QColor) -> QColor:
    """The colour of a formula that doesn't parse, readable by text of this colour."""
    return QColor(_ERROR_COLORS[color.lightness() > 128])


def paint(painter: QPainter, shape: tex.Layout, metrics: QtMetrics, x: float, y: float,
          color: QColor) -> None:
    """Draw a layout with its baseline's left end at (x, y), in a colour
    (what ``\\color`` doesn't change)."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    colors: dict = {}
    for item in shape.items:
        name = item.color
        if name is None:
            used = color
        elif name == tex.ERROR_COLOR:
            used = error_color(color)
        else:
            used = colors.get(name)
            if used is None:
                used = QColor(name)
                if not used.isValid():
                    used = color
                colors[name] = used
        if isinstance(item, tex.Text):
            painter.setFont(metrics.qfont(item.font, item.scale))
            painter.setPen(used)
            painter.drawText(QPointF(x + item.x, y + item.y), item.text)
        elif isinstance(item, tex.Rule):
            painter.fillRect(QRectF(x + item.x, y + item.y, item.width, item.height), used)
        else:
            path = _path(item.commands, x, y)
            if item.fill:
                painter.fillPath(path, used)
            else:
                pen = QPen(used, item.width)
                pen.setCapStyle(Qt.RoundCap if item.cap == "round" else Qt.FlatCap)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.strokePath(path, pen)
    painter.restore()


_layouts: OrderedDict = OrderedDict()  # (source, display, font) -> (layout, metrics)
_metrics: OrderedDict = OrderedDict()  # font -> QtMetrics


def layout_of(source: str, display: bool, font: QFont) -> tuple[tex.Layout, QtMetrics]:
    """A formula's layout in a font (kept: the same one is asked for at every paint)."""
    font_key = font.key()
    key = (source, display, font_key)
    found = _layouts.get(key)
    if found is not None:
        _layouts.move_to_end(key)
        return found
    metrics = _metrics.get(font_key)
    if metrics is None:
        metrics = _metrics[font_key] = QtMetrics(font)
        while len(_metrics) > 64:
            _metrics.popitem(last=False)
    found = _layouts[key] = (tex.render(source, metrics, display), metrics)
    while len(_layouts) > 2000:
        _layouts.popitem(last=False)
    return found


# --- formulas in a QTextDocument -----------------------------------------------------------------

def is_math(fmt: QTextFormat) -> bool:
    return fmt.objectType() == MATH_OBJECT


def _source(fmt: QTextFormat) -> tuple[str, bool]:
    return str(fmt.property(TEX_PROPERTY) or ""), bool(fmt.property(DISPLAY_PROPERTY))


def _padding(shape: tex.Layout, fmt: QTextCharFormat) -> tuple[float, float]:
    """Room above and below the formula so that Qt, which puts an object on
    the line by its vertical alignment, puts its baseline on the line's."""
    font = fmt.font()
    if fmt.verticalAlignment() == QTextCharFormat.AlignBaseline:
        return 0.0, max(0.0, QFontMetricsF(font).descent() - shape.descent)
    if fmt.verticalAlignment() == QTextCharFormat.AlignMiddle:
        half = QFontMetrics(font).xHeight() / 2  # (Qt centres the object half an x-height up)
        difference = shape.ascent - shape.descent - half
        return (0.0, difference) if difference >= 0 else (-difference, 0.0)
    return 0.0, 0.0


class _MathObject(QPyTextObject):
    """Sizes and draws the formulas of a document (its layout's handler)."""

    def intrinsicSize(self, document, position, fmt):
        try:
            fmt = fmt.toCharFormat()
            source, display = _source(fmt)
            shape, _metrics = layout_of(source, display, fmt.font())
            top, bottom = _padding(shape, fmt)
            return QSizeF(shape.width, top + shape.ascent + shape.descent + bottom)
        except Exception:  # (never an exception out of Qt's layout)
            return QSizeF(0, 0)

    def drawObject(self, painter, rect, document, position, fmt):
        try:
            fmt = fmt.toCharFormat()
            source, display = _source(fmt)
            shape, metrics = layout_of(source, display, fmt.font())
            top, _bottom = _padding(shape, fmt)
            baseline = rect.top() + top + shape.ascent
            if fmt.verticalAlignment() == QTextCharFormat.AlignMiddle:
                # (Qt draws a centred object in the middle of the whole line: the
                # formula goes on the line's baseline, which has room for it)
                line = _line_at(document, position)
                if line is not None:
                    height = line.ascent() + line.descent() + (
                        max(0.0, line.leading()) if line.leadingIncluded() else 0.0)
                    baseline = rect.top() - (height - rect.height()) / 2 + line.ascent()
            paint(painter, shape, metrics, rect.left(), baseline, painter.pen().color())
        except Exception:
            pass


def _line_at(document: QTextDocument, position: int):
    block = document.findBlock(position)
    layout = block.layout() if block.isValid() else None
    if layout is None:
        return None
    line = layout.lineForTextPosition(position - block.position())
    return line if line.isValid() else None


def register(document: QTextDocument) -> None:
    """Make a document able to show formulas (its layout gets their handler)."""
    layout = document.documentLayout()
    if layout.handlerForObject(MATH_OBJECT) is None:
        layout.registerHandler(MATH_OBJECT, _MathObject(document))


def math_format(base: QTextCharFormat, source: str, display: bool = False) -> QTextCharFormat:
    """A formula's character format, from the text's where it goes."""
    fmt = QTextCharFormat(base)
    for prop in (QTextFormat.ImageName, QTextFormat.ImageWidth, QTextFormat.ImageHeight,
                 QTextFormat.ImageAltText, QTextFormat.ImageTitle):
        fmt.clearProperty(prop)
    fmt.setObjectType(MATH_OBJECT)
    fmt.setProperty(TEX_PROPERTY, source)
    fmt.setProperty(DISPLAY_PROPERTY, bool(display))
    shape, _metrics = layout_of(source, display, fmt.font())
    # Qt gives an object on the baseline only the font's descent below it: a
    # formula that goes deeper is centred instead (with room to put its baseline right)
    descent = QFontMetricsF(fmt.font()).descent()
    fmt.setVerticalAlignment(QTextCharFormat.AlignBaseline if shape.descent <= descent * 0.98
                             else QTextCharFormat.AlignMiddle)
    if shape.error:
        fmt.setToolTip(f"Not a formula: {shape.error}")
    else:
        fmt.clearProperty(QTextFormat.TextToolTip)
    return fmt


def _plain(fmt: QTextCharFormat) -> QTextCharFormat:
    """A format for text, from one that may be a formula's."""
    fmt = QTextCharFormat(fmt)
    if is_math(fmt):
        fmt.clearProperty(QTextFormat.ObjectType)
    for prop in (TEX_PROPERTY, DISPLAY_PROPERTY, QTextFormat.TextToolTip):
        fmt.clearProperty(prop)
    fmt.setVerticalAlignment(QTextCharFormat.AlignNormal)
    return fmt


def insert_math(cursor: QTextCursor, source: str, display: bool = False,
                base: QTextCharFormat | None = None) -> None:
    """Insert a formula at the cursor (replacing what is selected)."""
    register(cursor.document())
    if base is None:
        base = _plain(cursor.charFormat())
    cursor.insertText(OBJECT, math_format(base, source, display))


def install(document: QTextDocument) -> int:
    """Turn the pictures vp6help's HTML made of formulas (``vp6math:``
    addresses) into formulas; how many."""
    targets = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            fmt = fragment.charFormat()
            if fmt.isImageFormat() and fmt.toImageFormat().name().startswith(SCHEME + ":"):
                targets.append((fragment.position(), fragment.length(),
                                fmt.toImageFormat().name()))
        block = block.next()
    if not targets:
        return 0
    register(document)
    undo = document.isUndoRedoEnabled()
    document.setUndoRedoEnabled(False)
    try:
        cursor = QTextCursor(document)
        for position, length, name in targets:
            kind, _, encoded = name[len(SCHEME) + 1:].partition(",")
            source = unquote(encoded)
            for k in range(length):
                cursor.setPosition(position + k)
                cursor.setPosition(position + k + 1, QTextCursor.KeepAnchor)
                cursor.setCharFormat(math_format(cursor.charFormat(), source, kind == "display"))
    finally:
        document.setUndoRedoEnabled(undo)
    return len(targets)


def formula_text(fmt: QTextFormat) -> str:
    """A formula's source as it is written in Markdown: ``$…$`` or ``$$…$$``."""
    source, display = _source(fmt)
    return f"$${source}$$" if display else f"${source.replace(chr(10), ' ')}$"


def text_of(cursor: QTextCursor) -> str:
    """The selected text, each formula as its source (``$…$``, ``$$…$$``)."""
    document = cursor.document()
    start, end = cursor.selectionStart(), cursor.selectionEnd()
    out: list[str] = []
    block = document.findBlock(start)
    first = True
    while block.isValid() and block.position() <= end:
        if not first:
            out.append("\n")
        first = False
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            begin = fragment.position()
            a, b = max(start, begin), min(end, begin + fragment.length())
            if a >= b:
                continue
            units = fragment.text().encode("utf-16-le")
            text = units[2 * (a - begin):2 * (b - begin)].decode("utf-16-le", "replace")
            if is_math(fragment.charFormat()):
                out.append(formula_text(fragment.charFormat()) * text.count(OBJECT))
            else:
                out.append(text.replace(" ", "\n").replace(" ", "\n"))
        block = block.next()
    return "".join(out)


def has_math(cursor: QTextCursor) -> bool:
    """Whether the selection holds a formula."""
    document = cursor.document()
    start, end = cursor.selectionStart(), cursor.selectionEnd()
    block = document.findBlock(start)
    while block.isValid() and block.position() <= end:
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if is_math(fragment.charFormat()) and fragment.position() < end and \
                    fragment.position() + fragment.length() > start:
                return True
        block = block.next()
    return False


def mime_data(cursor: QTextCursor) -> QMimeData | None:
    """What copying a selection with formulas puts on the clipboard: its text,
    the formulas as TeX (None: no formula, copy as usual)."""
    if not cursor.hasSelection() or not has_math(cursor):
        return None
    data = QMimeData()
    data.setText(text_of(cursor))
    return data


def insert_text(cursor: QTextCursor, text: str) -> None:
    """Insert text, its ``$…$`` formulas as formulas."""
    base = _plain(cursor.charFormat())
    spans = tex.math_spans(text)
    if spans:
        register(cursor.document())
    position = 0
    for span in spans:
        if span.start > position:
            cursor.insertText(text[position:span.start], base)
        cursor.insertText(OBJECT, math_format(base, span.tex, span.display))
        position = span.end
    if position < len(text):
        cursor.insertText(text[position:], base)


def to_source(document: QTextDocument) -> int:
    """Turn every formula back into its ``$…$`` text; how many."""
    targets = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if is_math(fragment.charFormat()):
                targets.append((fragment.position(), fragment.length(), fragment.charFormat()))
        block = block.next()
    cursor = QTextCursor(document)
    for position, length, fmt in reversed(targets):
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.KeepAnchor)
        cursor.insertText(formula_text(fmt) * length, _plain(fmt))
    return len(targets)
