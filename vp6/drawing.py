"""VB's graphics methods for forms and PictureBoxes: ``Line``, ``Circle``,
``PSet``, ``Print``, ``Cls``, ``Point``, ``TextWidth`` / ``TextHeight``, the
drawing properties (``DrawWidth``, ``DrawStyle``, ``FillStyle``,
``FillColor``, ``CurrentX`` / ``CurrentY``), ``AutoRedraw`` and the ``Paint``
event.

What is drawn outside a Paint handler goes on an image of the form's or
PictureBox's own (the "persistent graphics"), shown over its background and
picture and under its controls, until ``Cls``. With AutoRedraw False, Paint
fires whenever the surface is repainted, and what its handler draws goes
straight to the screen (drawn again at the next Paint). With AutoRedraw
True, Paint doesn't fire: everything is kept on the image.

A class using ``Drawing`` provides ``_drawing_surface()`` (the widget drawn
on), ``_drawing_origin()`` (where the drawing area starts in it: inside a
PictureBox's border), ``_values``, ``_fire`` and ``_design_mode``; its widget
calls ``_paint_drawing(widget)`` at the end of its ``paintEvent``.
"""

from __future__ import annotations

import math
from contextlib import contextmanager

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QFontMetricsF, QImage, QPainter, QPainterPath, QPalette, QPen

from . import colors
from ._props import P, enum_choices

# DrawStyle: 0 Solid ... 4 Dash-Dot-Dot, 5 Transparent, 6 Inside Solid
_DRAW_PENS = {0: Qt.SolidLine, 1: Qt.DashLine, 2: Qt.DotLine, 3: Qt.DashDotLine,
              4: Qt.DashDotDotLine, 6: Qt.SolidLine}
_TRANSPARENT, _INSIDE_SOLID = 5, 6

# ScaleMode: pixels per unit (x, y). VP6's pixel is 1/96 inch: a twip 1/15 of one;
# a character 120 x 240 twips, as in VB. 0 is User (ScaleLeft... set), 8 HiMetric
# (ScaleX / ScaleY only)
VP_USER, VP_PIXELS, VP_HIMETRIC = 0, 3, 8
_UNITS = {1: (1 / 15, 1 / 15), 2: (96 / 72, 96 / 72), 3: (1.0, 1.0), 4: (8.0, 16.0),
          5: (96.0, 96.0), 6: (96 / 25.4, 96 / 25.4), 7: (96 / 2.54, 96 / 2.54),
          8: (96 / 2540, 96 / 2540)}

DRAWING_PROPERTIES = (
    P("AutoRedraw", "bool", False,
      description="True: what the graphics methods draw is kept (no Paint event); False: "
                  "Paint fires whenever it needs drawing again"),
    P("DrawWidth", "int", 1, description="The width of the lines the graphics methods draw"),
    P("DrawStyle", "enum", 0, enum_choices(
        "Solid", "Dash", "Dot", "Dash-Dot", "Dash-Dot-Dot", "Transparent", "Inside Solid"),
      description="The lines the graphics methods draw"),
    P("FillStyle", "enum", 1, enum_choices(
        "Solid", "Transparent", "Horizontal Line", "Vertical Line", "Upward Diagonal",
        "Downward Diagonal", "Cross", "Diagonal Cross"),
      description="How Circle and Line with a box (B) fill what they draw"),
    P("FillColor", "color", None,
      description="The fill of Circle and Line boxes (FillStyle); unset = ForeColor"),
    P("ScaleMode", "enum", VP_PIXELS, enum_choices(
        "User", "Twips", "Points", "Pixels", "Characters", "Inches", "Millimeters",
        "Centimeters"),
      description="The units of the graphics methods, CurrentX / CurrentY, ScaleWidth / "
                  "ScaleHeight and its mouse events' X, Y (User: set by ScaleLeft, ScaleTop, "
                  "ScaleWidth, ScaleHeight or Scale)"),
)


class Drawing:
    """The graphics methods and properties (a mixin for Form and PictureBox)."""

    # -- what the class provides ------------------------------------------------------------
    def _drawing_surface(self):
        raise NotImplementedError

    def _drawing_origin(self) -> QPoint:
        return QPoint(0, 0)

    # -- state ---------------------------------------------------------------------------------
    def _draw_state(self) -> dict:
        """The drawing state: the persistent image, the current point and the
        painter of a Paint in progress."""
        state = self.__dict__.get("_drawing_state")
        if state is None:
            # dash: where the last Line ended and how far its dash pattern had got
            state = {"image": None, "x": 0.0, "y": 0.0, "painter": None, "dash": None}
            self.__dict__["_drawing_state"] = state
        return state

    @property
    def CurrentX(self) -> float:
        """Where the next Print, or a Line from the current point, starts (in
        ScaleMode's units)."""
        left, _top, fx, _fy = self._scale_factors()
        return left + self._draw_state()["x"] / fx

    @CurrentX.setter
    def CurrentX(self, value):
        left, _top, fx, _fy = self._scale_factors()
        self._draw_state()["x"] = (float(value) - left) * fx

    @property
    def CurrentY(self) -> float:
        _left, top, _fx, fy = self._scale_factors()
        return top + self._draw_state()["y"] / fy

    @CurrentY.setter
    def CurrentY(self, value):
        _left, top, _fx, fy = self._scale_factors()
        self._draw_state()["y"] = (float(value) - top) * fy

    # -- ScaleMode: the units ------------------------------------------------------------------
    def _scale_factors(self) -> tuple[float, float, float, float]:
        """(ScaleLeft, ScaleTop, pixels per unit across, down)."""
        mode = int(self._values.get("ScaleMode", VP_PIXELS))
        user = self.__dict__.get("_user_scale")
        if mode == VP_USER and user is not None:
            left, top, width, height = user
            size = self._draw_area_size()
            return (left, top, size.width() / width if width else 1.0,
                    size.height() / height if height else 1.0)
        fx, fy = _UNITS.get(mode, (1.0, 1.0))
        return 0.0, 0.0, fx, fy

    def _to_px(self, x, y) -> tuple[float, float]:
        """A point in ScaleMode's units, in pixels of the drawing area."""
        left, top, fx, fy = self._scale_factors()
        return (float(x) - left) * fx, (float(y) - top) * fy

    def _to_px_size(self, width, height) -> tuple[float, float]:
        _left, _top, fx, fy = self._scale_factors()
        return float(width) * fx, float(height) * fy

    def _from_px(self, x, y) -> tuple[float, float]:
        left, top, fx, fy = self._scale_factors()
        return left + x / fx, top + y / fy

    def _scaled(self) -> bool:
        """Whether its units aren't pixels from the top left."""
        return int(self._values.get("ScaleMode", VP_PIXELS)) != VP_PIXELS

    def _mouse_xy(self, x, y):
        """A mouse event's X, Y (pixels of the widget) in ScaleMode's units, from
        the drawing area's top left (inside a PictureBox's border)."""
        origin = self._drawing_origin()
        x, y = x - origin.x(), y - origin.y()
        return self._from_px(x, y) if self._scaled() else (x, y)

    def _scale_rect(self) -> tuple[float, float, float, float]:
        left, top, fx, fy = self._scale_factors()
        size = self._draw_area_size()
        return left, top, size.width() / fx, size.height() / fy

    def _set_scale_part(self, index: int, value) -> None:
        """Setting ScaleLeft, ScaleTop, ScaleWidth or ScaleHeight: a User scale,
        the others as they are now."""
        scale = list(self._scale_rect())
        scale[index] = float(value)
        if index >= 2 and not scale[index]:
            raise ValueError("ScaleWidth and ScaleHeight can't be 0")
        self.__dict__["_user_scale"] = tuple(scale)
        self._values["ScaleMode"] = VP_USER

    @property
    def ScaleLeft(self) -> float:
        """The left edge's coordinate (User scales; else 0)."""
        return self._scale_rect()[0]

    @ScaleLeft.setter
    def ScaleLeft(self, value):
        self._set_scale_part(0, value)

    @property
    def ScaleTop(self) -> float:
        return self._scale_rect()[1]

    @ScaleTop.setter
    def ScaleTop(self, value):
        self._set_scale_part(1, value)

    @property
    def ScaleWidth(self) -> float:
        """The drawing area's width in ScaleMode's units (setting it: a User
        scale, e.g. 100 for percent; negative: right to left)."""
        return self._scale_rect()[2]

    @ScaleWidth.setter
    def ScaleWidth(self, value):
        self._set_scale_part(2, value)

    @property
    def ScaleHeight(self) -> float:
        return self._scale_rect()[3]

    @ScaleHeight.setter
    def ScaleHeight(self, value):
        self._set_scale_part(3, value)

    def Scale(self, X1=None, Y1=None, X2=None, Y2=None) -> None:
        """A User scale: X1, Y1 the top left corner, X2, Y2 the bottom right
        (``Scale(0, 100, 100, 0)``: 0 to 100, upwards). Without them: back to
        pixels."""
        if X1 is None:
            self.__dict__["_user_scale"] = None
            self._values["ScaleMode"] = VP_PIXELS
            return
        if X2 == X1 or Y2 == Y1:
            raise ValueError("Scale: the corners must differ")
        self.__dict__["_user_scale"] = (float(X1), float(Y1), float(X2) - float(X1),
                                        float(Y2) - float(Y1))
        self._values["ScaleMode"] = VP_USER

    def _apply_ScaleMode(self, v):
        if int(v) != VP_USER:
            self.__dict__["_user_scale"] = None
        elif self.__dict__.get("_user_scale") is None:  # User: the pixels it has, to begin
            size = self._draw_area_size()
            self.__dict__["_user_scale"] = (0.0, 0.0, float(size.width() or 1),
                                            float(size.height() or 1))

    def _units_per_pixel(self, mode: int, across: bool) -> float:
        if int(mode) == VP_USER:
            _left, _top, fx, fy = self._scale_factors() if \
                int(self._values.get("ScaleMode", VP_PIXELS)) == VP_USER else (0, 0, 1, 1)
            return fx if across else fy
        if int(mode) not in _UNITS:
            raise ValueError(f"Not a ScaleMode: {mode}")
        return _UNITS[int(mode)][0 if across else 1]

    def ScaleX(self, Width, FromScale=VP_HIMETRIC, ToScale=None) -> float:
        """A width in other units: from FromScale (default HiMetric, as in VB) to
        ToScale (default this one's ScaleMode); User means this one's scale."""
        to_scale = self._values.get("ScaleMode", VP_PIXELS) if ToScale is None else ToScale
        return float(Width) * self._units_per_pixel(FromScale, True) / \
            self._units_per_pixel(to_scale, True)

    def ScaleY(self, Height, FromScale=VP_HIMETRIC, ToScale=None) -> float:
        to_scale = self._values.get("ScaleMode", VP_PIXELS) if ToScale is None else ToScale
        return float(Height) * self._units_per_pixel(FromScale, False) / \
            self._units_per_pixel(to_scale, False)

    def _draw_area_size(self) -> QSize:
        surface = self._drawing_surface()
        origin = self._drawing_origin()
        return QSize(max(0, surface.width() - 2 * origin.x()),
                     max(0, surface.height() - 2 * origin.y()))

    def _draw_image(self) -> QImage:
        """The persistent image, at least as large as the drawing area (it
        grows with it, keeping what is on it, and never shrinks)."""
        state = self._draw_state()
        surface = self._drawing_surface()
        ratio = surface.devicePixelRatioF()
        size = self._draw_area_size()
        image = state["image"]
        if image is not None and image.devicePixelRatio() == ratio and \
                image.width() >= round(size.width() * ratio) and \
                image.height() >= round(size.height() * ratio):
            return image
        old = image
        width = max(size.width(), round(old.width() / old.devicePixelRatio()) if old else 0, 1)
        height = max(size.height(), round(old.height() / old.devicePixelRatio()) if old else 0, 1)
        image = QImage(round(width * ratio), round(height * ratio),
                       QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        if old is not None:
            painter = QPainter(image)
            painter.drawImage(0, 0, old)
            painter.end()
        state["image"] = image
        return image

    @contextmanager
    def _draw_painter(self, antialias=False):
        """A painter for a graphics method: the Paint's (AutoRedraw False, in
        a Paint handler), else the persistent image's."""
        state = self._draw_state()
        painter = state["painter"]
        if painter is not None:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, antialias)
            try:
                yield painter
            finally:
                painter.restore()
            return
        painter = QPainter(self._draw_image())
        painter.setRenderHint(QPainter.Antialiasing, antialias)
        try:
            yield painter
        finally:
            painter.end()
            self._drawing_surface().update()

    def _paint_drawing(self, widget) -> None:
        """The surface's paintEvent, after its background, picture and border:
        the persistent image, then (AutoRedraw False) the Paint event."""
        state = self._draw_state()
        image = state["image"]
        background = self._background_picture()
        paint = not self._design_mode and not self._values.get("AutoRedraw") and \
            state["painter"] is None
        if image is None and background is None and not (paint and self._handles_paint()):
            return
        painter = QPainter(widget)
        painter.translate(self._drawing_origin())
        painter.setClipRect(QRect(QPoint(0, 0), self._draw_area_size()))
        if background is not None:  # (a form's Picture: a PictureBox's label shows its own)
            painter.drawPixmap(0, 0, background)
        if image is not None:
            painter.drawImage(0, 0, image)
        if paint:
            state["painter"] = painter
            try:
                self._fire("Paint")
            finally:
                state["painter"] = None
        painter.end()

    def _handles_paint(self) -> bool:
        """Whether there is a Paint handler (else no painter is needed)."""
        return True

    def _background_picture(self):
        """A picture drawn under the drawing (a form's Picture), or None."""
        return None

    @property
    def Image(self):
        """A Picture of what it shows: its background, Picture and drawing
        (not its controls), e.g. to save with SavePicture or to use as another
        control's Picture."""
        from .picture import Picture

        size = self._draw_area_size()
        image = QImage(max(size.width(), 0), max(size.height(), 0),
                       QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        if not image.isNull():
            painter = QPainter(image)
            surface = self._drawing_surface()
            surface.render(painter, QPoint(0, 0), QRect(self._drawing_origin(), size),
                           surface.RenderFlag.DrawWindowBackground)
            painter.end()
        return Picture(_image=image)

    def PaintPicture(self, Picture, X1, Y1, Width1=None, Height1=None, X2=0, Y2=0,
                     Width2=None, Height2=None) -> None:
        """Draw a picture (a Picture, a file, or another control's Image) at X1,
        Y1, Width1 x Height1 (its own size when left out: scaled otherwise);
        X2, Y2, Width2, Height2 take just that part of it."""
        from .picture import picture_pixmap, to_picture

        if isinstance(Picture, str):  # a file, relative to the form's folder
            source = picture_pixmap(self, Picture).toImage()
        else:
            source = to_picture(Picture)._image
        if source.isNull():
            return
        width2 = source.width() - X2 if Width2 is None else Width2
        height2 = source.height() - Y2 if Height2 is None else Height2
        x1, y1 = self._to_px(X1, Y1)  # (where: in ScaleMode's units; the source: its pixels)
        width1 = width2 if Width1 is None else self._to_px_size(Width1, 0)[0]
        height1 = height2 if Height1 is None else self._to_px_size(0, Height1)[1]
        with self._draw_painter(antialias=True) as painter:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(QRectF(x1, y1, width1, height1), source,
                              QRectF(X2, Y2, width2, height2))

    # -- colors and pens -----------------------------------------------------------------
    def _draw_text_color(self):
        color = self._values.get("ForeColor")
        if color is not None:
            return colors.to_qcolor(color)
        return self._drawing_surface().palette().color(QPalette.WindowText)

    def _draw_color(self, Color):
        return self._draw_text_color() if Color is None else colors.to_qcolor(Color)

    def _draw_pen(self, color) -> QPen:
        style = int(self._values.get("DrawStyle", 0))
        width = max(1, int(self._values.get("DrawWidth", 1)))
        if style == _TRANSPARENT:
            return QPen(Qt.NoPen)
        pen = QPen(color, width)
        pen.setStyle(_DRAW_PENS.get(style, Qt.SolidLine))  # (VB: solid when wider than 1)
        # A one-pixel line doesn't cover its end point, as in VB; wider solid ones are
        # round (dashes keep their gaps)
        solid = pen.style() == Qt.SolidLine
        pen.setCapStyle(Qt.RoundCap if width > 1 and solid else Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        return pen

    def _draw_inset(self) -> float:
        """Inside Solid: boxes and circles drawn inside their bounds."""
        if int(self._values.get("DrawStyle", 0)) != _INSIDE_SOLID:
            return 0.0
        return max(1, int(self._values.get("DrawWidth", 1))) / 2

    def _draw_fill(self, painter: QPainter, path: QPainterPath) -> None:
        from .controls import _HATCHES, _hatch

        style = int(self._values.get("FillStyle", 1))
        fill = self._values.get("FillColor")
        color = colors.to_qcolor(fill) if fill is not None else self._draw_text_color()
        if style == 0:
            painter.fillPath(path, color)
        elif style in _HATCHES:  # (1: Transparent)
            _hatch(painter, path, style, color)

    def _point(self, X, Y, Step: bool) -> tuple[float, float]:
        """A method's point in pixels: X, Y in ScaleMode's units (Step: from the
        current point)."""
        if Step:
            state = self._draw_state()
            dx, dy = self._to_px_size(X, Y)
            return state["x"] + dx, state["y"] + dy
        return self._to_px(X, Y)

    # -- the graphics methods -----------------------------------------------------------------
    def PSet(self, X, Y, Color=None, Step: bool = False) -> None:
        """Draw a point (DrawWidth across) at X, Y (Step: relative to the
        current point; DrawStyle Transparent: none); the current point moves
        there."""
        state = self._draw_state()
        x, y = self._point(X, Y, Step)
        color = self._draw_color(Color)
        width = max(1, int(self._values.get("DrawWidth", 1)))
        with self._draw_painter(antialias=width > 1) as painter:
            if int(self._values.get("DrawStyle", 0)) == _TRANSPARENT:
                pass  # (it just moves the current point)
            elif width == 1:
                painter.fillRect(QRectF(math.floor(x), math.floor(y), 1, 1), color)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, y), width / 2, width / 2)
        state["x"], state["y"] = float(x), float(y)

    def Line(self, X1, Y1, X2=None, Y2=None, Color=None, Box: str = "",
             Step: bool = False) -> None:
        """Draw a line from X1, Y1 to X2, Y2 (VB's ``Line (X1, Y1)-(X2, Y2)``);
        with only X1, Y1, from the current point to there (``Line -(X, Y)``).
        Step: the second point is relative to the first. Box "B" draws a box
        with those corners, filled as FillStyle says; "BF" a box filled with
        the line's color. The current point moves to the second point."""
        state = self._draw_state()
        if X2 is None or Y2 is None:  # (from the current point)
            x1, y1 = state["x"], state["y"]
            x2, y2 = self._point(X1, Y1, Step)
        else:
            x1, y1 = self._to_px(X1, Y1)
            if Step:
                dx, dy = self._to_px_size(X2, Y2)
                x2, y2 = x1 + dx, y1 + dy
            else:
                x2, y2 = self._to_px(X2, Y2)
        color = self._draw_color(Color)
        box = str(Box or "").upper()
        if box not in ("", "B", "BF"):
            raise ValueError(f"Box is '', 'B' or 'BF', not {Box!r}")
        with self._draw_painter() as painter:
            if not box:
                pen = self._draw_pen(color)
                # A line going on from where the last one ended goes on with its dash
                # pattern, so lines drawn a bit at a time (e.g. following the mouse) are
                # dashed too, not each one starting a dash
                dash = state["dash"]
                travelled = dash[1] if dash is not None and dash[0] == (x1, y1) else 0.0
                if pen.style() not in (Qt.SolidLine, Qt.NoPen):  # (an offset makes any pen
                    pen.setDashOffset(travelled / pen.widthF())  # a dashed one: none there)
                painter.setPen(pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                state["dash"] = ((x2, y2), travelled + math.hypot(x2 - x1, y2 - y1))
            else:
                # The box covers both corners' pixels
                rect = QRectF(QPointF(min(x1, x2), min(y1, y2)),
                              QPointF(max(x1, x2) + 1, max(y1, y2) + 1))
                if box == "BF":
                    painter.fillRect(rect, color)
                else:
                    path = QPainterPath()
                    path.addRect(rect)
                    self._draw_fill(painter, path)
                    pen = self._draw_pen(color)
                    if pen.style() != Qt.NoPen:
                        width = pen.widthF()
                        inset = width / 2 if self._draw_inset() else 0.0
                        # (a pen's middle on the pixels' middles: inside the rect's edge)
                        edge = rect.adjusted(0.5, 0.5, -0.5, -0.5)
                        if width > 1 and inset:
                            edge = rect.adjusted(inset, inset, -inset, -inset)
                        pen.setCapStyle(Qt.SquareCap)
                        painter.setPen(pen)
                        painter.setBrush(Qt.NoBrush)
                        painter.drawRect(edge)
        state["x"], state["y"] = float(x2), float(y2)

    def Circle(self, X, Y, Radius, Color=None, Start=None, End=None, Aspect=1.0,
               Step: bool = False) -> None:
        """Draw a circle around X, Y (Step: relative to the current point).
        Aspect is the height to width ratio (an ellipse; Radius is the larger
        one). Start and End, in radians counterclockwise from 3 o'clock, draw
        an arc; a negative one also draws the radius to that end (both
        negative: a pie slice, filled as FillStyle says, like a whole circle).
        The current point moves to the center."""
        state = self._draw_state()
        x, y = self._point(X, Y, Step)
        Radius = abs(self._to_px_size(Radius, 0)[0])  # (in units across, as in VB)
        aspect = float(Aspect) if Aspect else 1.0
        rx, ry = (Radius, Radius * aspect) if aspect <= 1 else (Radius / aspect, Radius)
        inset = self._draw_inset()
        rx, ry = max(0.0, rx - inset), max(0.0, ry - inset)
        rect = QRectF(x - rx, y - ry, 2 * rx, 2 * ry)
        color = self._draw_color(Color)
        path = QPainterPath()
        closed = True
        if Start is None and End is None:
            path.addEllipse(rect)
        else:
            start = float(Start) if Start is not None else 0.0
            end = float(End) if End is not None else 2 * math.pi
            start_degrees = math.degrees(abs(start))
            span = math.degrees(abs(end)) - start_degrees
            if span <= 0:
                span += 360
            # (negative, -0.0 too: a radius to there)
            start_radius = math.copysign(1, start) < 0
            end_radius = math.copysign(1, end) < 0
            if start_radius:
                path.moveTo(x, y)
                path.arcTo(rect, start_degrees, span)
            else:
                path.arcMoveTo(rect, start_degrees)
                path.arcTo(rect, start_degrees, span)
            if end_radius:
                path.lineTo(x, y)
            closed = start_radius and end_radius
            if closed:
                path.closeSubpath()
        with self._draw_painter(antialias=True) as painter:
            if closed:
                self._draw_fill(painter, path)
            painter.setPen(self._draw_pen(color))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        state["x"], state["y"] = float(x), float(y)

    def Print(self, *values, sep: str = " ", end: str = "\n") -> None:
        """Write text at the current point, in the Font and ForeColor, like
        Python's print: values separated by ``sep``, then ``end`` (a new line:
        the next text starts at the left, one line lower). The current point
        moves to the end of the text."""
        state = self._draw_state()
        text = sep.join(str(value) for value in values) + end
        font = self._drawing_surface().font()
        metrics = QFontMetricsF(font)
        lines = text.split("\n")
        with self._draw_painter(antialias=True) as painter:
            painter.setFont(font)
            painter.setPen(self._draw_text_color())
            for number, line in enumerate(lines):
                if number:  # a new line
                    state["x"] = 0.0
                    state["y"] += metrics.lineSpacing()
                if line:
                    painter.drawText(QPointF(state["x"], state["y"] + metrics.ascent()), line)
                    state["x"] += metrics.horizontalAdvance(line)

    def Cls(self) -> None:
        """Clear what the graphics methods drew (not the Picture), and move the
        current point to 0, 0."""
        state = self._draw_state()
        state["image"] = state["dash"] = None
        state["x"] = state["y"] = 0.0
        if state["painter"] is None:  # (in a Paint: it is being drawn now)
            self._drawing_surface().update()

    def Point(self, X, Y) -> int:
        """The color at X, Y (what is drawn there, under any controls), or -1
        outside the drawing area."""
        size = self._draw_area_size()
        X, Y = self._to_px(X, Y)
        if not (0 <= X < size.width() and 0 <= Y < size.height()):
            return -1
        surface = self._drawing_surface()
        origin = self._drawing_origin()
        # (premultiplied: the macOS style draws frames through a Core Graphics context,
        # which it can't make for plain ARGB32, and says so on stderr)
        image = QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        # Just this one pixel, without the controls on it
        surface.render(painter, QPoint(0, 0),
                       QRect(origin.x() + int(X), origin.y() + int(Y), 1, 1),
                       surface.RenderFlag.DrawWindowBackground)
        painter.end()
        return colors.from_qcolor(image.pixelColor(0, 0))

    def TextWidth(self, Text) -> float:
        """How wide Print would write Text, in the Font (its longest line)."""
        metrics = QFontMetricsF(self._drawing_surface().font())
        width = max(metrics.horizontalAdvance(line) for line in str(Text).split("\n"))
        return width / abs(self._scale_factors()[2])

    def TextHeight(self, Text) -> float:
        """How tall Print would write Text: its lines' height, in the Font."""
        metrics = QFontMetricsF(self._drawing_surface().font())
        return metrics.lineSpacing() * (str(Text).count("\n") + 1) / \
            abs(self._scale_factors()[3])
