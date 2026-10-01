"""VB's Picture objects: ``LoadPicture``, ``SavePicture`` and the ``Picture``
class (VB's StdPicture), a picture in memory.

A Picture can be any picture property's value (a PictureBox's or Image's
``Picture``, a button's, a form's ``Icon`` or ``Picture``, ``MouseIcon``,
``DragIcon``, an ImageList's ListImage), as a file name can. It is also
drawn on with the graphics methods, like a PictureBox with AutoRedraw:
``Picture(64, 64)`` is a new, empty one; a form's or PictureBox's ``Image``
is a Picture of what it shows; ``Clipboard.GetData()`` and
``Clipboard.SetData`` exchange them with other programs.

``picture_pixmap(owner, value)`` is how controls turn a picture property's
value (a Picture, or a file relative to the form's folder) into a QPixmap.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from . import colors
from ._props import P, PropertyHost
from .drawing import DRAWING_PROPERTIES, Drawing

# Picture.Type (VB's vbPicType...)
PIC_TYPE_NONE, PIC_TYPE_BITMAP = 0, 1


class _PictureSurface:
    """What the graphics methods need of the surface they draw on, for a
    Picture: its size, font and colors (it has no widget)."""

    def __init__(self, picture: "Picture"):
        self._picture = picture

    def width(self) -> int:
        return self._picture._image.width()

    def height(self) -> int:
        return self._picture._image.height()

    def devicePixelRatioF(self) -> float:
        return 1.0

    def palette(self):
        app = QApplication.instance()
        return app.palette() if app is not None else None

    def font(self) -> QFont:
        values = self._picture._values
        font = QFont()
        if values.get("FontName"):
            font.setFamily(values["FontName"])
        if values.get("FontSize"):
            font.setPointSizeF(float(values["FontSize"]))
        font.setBold(bool(values.get("FontBold")))
        font.setItalic(bool(values.get("FontItalic")))
        font.setUnderline(bool(values.get("FontUnderline")))
        return font

    def update(self) -> None:
        pass


class Picture(Drawing, PropertyHost):
    """A picture in memory (VB's Picture object).

    ``Picture(Width, Height, BackColor=None)`` is a new one (transparent
    without a BackColor) to draw on with ``Line``, ``Circle``, ``PSet``,
    ``Print``, ``PaintPicture`` and the drawing properties; ``LoadPicture``
    reads one from a file. ``Width`` and ``Height`` are in pixels."""

    TypeName = "Picture"
    _design_mode = False
    Properties = (
        *(spec for spec in DRAWING_PROPERTIES if spec.name != "AutoRedraw"),
        P("ForeColor", "color", None, description="What the graphics methods draw with"),
        P("BackColor", "color", None, description="What Cls fills it with; unset: transparent"),
        P("FontName", "font", None), P("FontSize", "int", None),
        P("FontBold", "bool", False), P("FontItalic", "bool", False),
        P("FontUnderline", "bool", False),
    )

    def __init__(self, Width: int = 0, Height: int = 0, BackColor=None, _image=None):
        d = self.__dict__
        d["_values"] = {}
        d["_surface"] = _PictureSurface(self)
        if _image is None:
            _image = QImage(max(0, int(Width)), max(0, int(Height)),
                            QImage.Format_ARGB32_Premultiplied)
            _image.fill(Qt.transparent)
        elif _image.format() != QImage.Format_ARGB32_Premultiplied:
            _image = _image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        _image.setDevicePixelRatio(1.0)
        d["_image"] = _image
        self._init_values({"BackColor": BackColor})
        if BackColor is not None and not self._image.isNull():
            self._image.fill(colors.to_qcolor(BackColor))

    def __setattr__(self, name, value):
        if name in self._specs or isinstance(getattr(type(self), name, None), property):
            object.__setattr__(self, name, value)
        else:
            raise AttributeError(f"Picture has no property '{name}'")

    def __repr__(self):
        return f"<Picture {self.Width} x {self.Height}>"

    # -- what it is ----------------------------------------------------------------------------
    @property
    def Width(self) -> int:
        return self._image.width()

    @property
    def Height(self) -> int:
        return self._image.height()

    @property
    def Type(self) -> int:
        """vpPicTypeBitmap, or vpPicTypeNone for an empty picture (LoadPicture())."""
        return PIC_TYPE_NONE if self._image.isNull() else PIC_TYPE_BITMAP

    def _pixmap(self) -> QPixmap:
        return QPixmap.fromImage(self._image)

    def _fire(self, event, *args):
        return None  # (no events)

    # -- the graphics methods on it ---------------------------------------------------------
    def _drawing_surface(self):
        return self._surface

    def _draw_image(self) -> QImage:
        return self._image

    def _draw_area_size(self) -> QSize:
        return self._image.size()

    @property
    def Image(self) -> "Picture":
        """A copy of it (as a form's or PictureBox's Image is a Picture of it)."""
        return Picture(_image=self._image.copy())

    def Cls(self) -> None:
        """Fill it with its BackColor (transparent without one) and move the
        current point to 0, 0."""
        back = self._values.get("BackColor")
        self._image.fill(colors.to_qcolor(back) if back is not None else QColor(Qt.transparent))
        state = self._draw_state()
        state["x"] = state["y"] = 0.0
        state["dash"] = None

    def Point(self, X, Y) -> int:
        """The color at X, Y (-1 outside, or where it is transparent)."""
        if not (0 <= X < self.Width and 0 <= Y < self.Height):
            return -1
        color = self._image.pixelColor(QPoint(int(X), int(Y)))
        return -1 if color.alpha() == 0 else colors.from_qcolor(color)


def LoadPicture(FileName: str = "") -> Picture:
    """A Picture from an image file (PNG, JPEG, BMP, GIF, ICO, SVG...);
    ``LoadPicture()`` is an empty one (setting a Picture property to it clears
    it). A missing or unreadable file raises FileNotFoundError / ValueError."""
    if not FileName:
        return Picture()
    path = str(FileName)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    image = QImage(path)
    if image.isNull():
        raise ValueError(f"Not a picture this program can read: {path}")
    return Picture(_image=image)


def SavePicture(Picture, FileName: str) -> None:
    """Save a Picture (or a control's or form's Image) to a file, in the format
    its extension says (.png, .jpg, .bmp...; without one, BMP as in VB)."""
    path = str(FileName)
    image = to_picture(Picture)._image
    fmt = None if os.path.splitext(path)[1] else "BMP"
    if image.isNull() or not image.save(path, fmt):
        raise OSError(f"Couldn't save the picture as {path}")


def is_picture(value) -> bool:
    return isinstance(value, Picture)


def to_picture(value) -> Picture:
    """A Picture from a Picture, or a picture file's name."""
    if isinstance(value, Picture):
        return value
    if isinstance(value, (QPixmap, QImage)):
        return Picture(_image=value.toImage() if isinstance(value, QPixmap) else QImage(value))
    return LoadPicture(str(value or ""))


def picture_pixmap(owner, value) -> QPixmap:
    """A picture property's value as a QPixmap: a Picture's, or a file's
    (relative to the owner's form folder); empty when there is none or the file
    can't be read."""
    if isinstance(value, Picture):
        return value._pixmap()
    if not value:
        return QPixmap()
    path = str(value)
    if not os.path.isabs(path):
        base = owner._base_dir() if hasattr(owner, "_base_dir") else os.getcwd()
        path = os.path.join(base, path)
    return QPixmap(path)
