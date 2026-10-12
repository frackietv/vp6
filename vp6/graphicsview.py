"""The ``GraphicsView``: a canvas of shapes that are objects, which can be
moved, turned, scaled, selected, and dragged by the user.

    box = self.gvwPlan.Items.AddRect(20, 20, 120, 60, FillColor=vpYellow, Key="box")
    box.Rotation = 15
    box.Movable = True
    self.gvwPlan.Items.AddText("Kitchen", 30, 40)

* ``Items`` holds the shapes, in the order they were added (by Index from 1,
  or by ``Key``): ``AddRect``, ``AddEllipse``, ``AddLine``, ``AddPolygon``
  (a list of points), ``AddPath`` (SVG path data: ``"M 0 0 L 40 0 Q 60 20 40
  40 Z"``), ``AddText``, ``AddPicture`` (a picture file or Picture) and
  ``AddGroup`` (items that then move together). ``Remove`` and ``Clear``.
* Each item (a ``GraphicsItem``) has ``Left``/``Top`` (where it is),
  ``Rotation`` (degrees), ``Scale``, ``ZOrder`` (higher: on top),
  ``ForeColor`` and ``BorderWidth`` (its outline: ``None`` for none),
  ``FillColor`` (``None``: not filled), ``Visible``, ``Movable`` (the user can
  drag it), ``Selectable``, ``Selected``, ``Text`` (a text item), ``Tag``,
  ``Kind`` ("Rect", "Ellipse"...), ``Remove()``.
* The view: ``Zoom`` (1 = actual size), ``ZoomToFit()``, ``ScrollTo(X, Y)``,
  ``MouseMode`` (the left button: picks items, pans, or selects with a
  rubber band), ``SceneWidth``/``SceneHeight`` (0: as large as the items
  need), ``SelectedItems``, ``HitTest(X, Y)`` (the item under a point given
  by the mouse events), ``SceneX(X)``/``SceneY(Y)`` (such a point in the
  items' coordinates).
* Events: ``ItemClick(Item)``, ``ItemMoved(Item)`` (dragged by the user),
  ``SelectionChanged``, and the mouse events (in the view's pixels).
* ``Picture`` is the whole scene as a Picture (``SavePicture(gvw.Picture,
  "plan.png")``); ``PrintOut()`` prints it on the Printer.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QFrame, QGraphicsEllipseItem, QGraphicsItem,
                               QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView)

from . import colors
from ._props import P, enum_choices
from .controls import (_COMMON, _FONT, CONTROL_TYPES, EVENT_ARGS, Control, _add_mouse_members,
                       _add_validation, _geometry)
from .picture import picture_pixmap

EVENT_ARGS.update({"ItemMoved": "Item", "SelectionChanged": ""})
_ITEM_ROLE = 0  # (QGraphicsItem.data key: the GraphicsItem)
_PATH_TOKEN = re.compile(r"[A-Za-z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def svg_path(data: str) -> QPainterPath:
    """SVG path data as a QPainterPath: M, L, H, V, C, Q and Z, absolute
    (capitals) or relative (small letters)."""
    path = QPainterPath()
    tokens = _PATH_TOKEN.findall(str(data))
    command, i = "M", 0
    x = y = 0.0
    start = QPointF(0, 0)

    def numbers(count):
        nonlocal i
        try:
            values = [float(tokens[i + k]) for k in range(count)]
        except (IndexError, ValueError):
            raise ValueError(f"SVG path {data!r}: {command} needs {count} numbers") from None
        i += count
        return values

    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            if token not in "MmLlHhVvCcQqZz":
                raise ValueError(f"SVG path {data!r}: {token} isn't supported (M, L, H, V, "
                                 "C, Q and Z are)")
            command = token
            i += 1
            if command in "Zz":
                path.closeSubpath()
                x, y = start.x(), start.y()
            continue
        relative = command.islower()
        base = (x, y) if relative else (0.0, 0.0)
        kind = command.upper()
        if kind == "M":
            px, py = numbers(2)
            x, y = base[0] + px, base[1] + py
            path.moveTo(x, y)
            start = QPointF(x, y)
            command = "l" if relative else "L"  # (more pairs: lines)
        elif kind == "L":
            px, py = numbers(2)
            x, y = base[0] + px, base[1] + py
            path.lineTo(x, y)
        elif kind == "H":
            (px,) = numbers(1)
            x = base[0] + px
            path.lineTo(x, y)
        elif kind == "V":
            (py,) = numbers(1)
            y = base[1] + py
            path.lineTo(x, y)
        elif kind == "C":
            v = numbers(6)
            pts = [QPointF(base[0] + v[k], base[1] + v[k + 1]) for k in (0, 2, 4)]
            path.cubicTo(*pts)
            x, y = pts[2].x(), pts[2].y()
        elif kind == "Q":
            v = numbers(4)
            pts = [QPointF(base[0] + v[k], base[1] + v[k + 1]) for k in (0, 2)]
            path.quadTo(*pts)
            x, y = pts[1].x(), pts[1].y()
    return path


def _color(value) -> QColor:
    return colors.to_qcolor(value)


class GraphicsItem:
    """A shape on a GraphicsView (the module's documentation)."""

    def __init__(self, view: "GraphicsView", item: QGraphicsItem, kind: str, key: str = ""):
        self._view, self._item, self._kind, self._key = view, item, kind, key
        self._fore, self._fill, self._width = 0x000000, None, 1
        self.Tag = ""
        item.setData(_ITEM_ROLE, self)

    def __repr__(self):
        return f"<GraphicsItem {self._kind}{f' {self._key!r}' if self._key else ''}>"

    @property
    def Kind(self) -> str:
        """Rect, Ellipse, Line, Polygon, Path, Text, Picture or Group."""
        return self._kind

    @property
    def Key(self) -> str:
        return self._key

    @property
    def Index(self) -> int:
        """Its number in Items (from 1)."""
        return self._view._items._list.index(self) + 1

    # -- where it is ---------------------------------------------------------------------------
    @property
    def Left(self) -> float:
        return round(self._item.pos().x(), 6)

    @Left.setter
    def Left(self, value):
        self._item.setX(float(value))

    @property
    def Top(self) -> float:
        return round(self._item.pos().y(), 6)

    @Top.setter
    def Top(self, value):
        self._item.setY(float(value))

    def Move(self, Left, Top) -> None:
        self._item.setPos(float(Left), float(Top))

    @property
    def Width(self) -> float:
        """Its width (read-only: how much room it takes, before Rotation and Scale)."""
        return self._item.boundingRect().width()

    @property
    def Height(self) -> float:
        return self._item.boundingRect().height()

    @property
    def Rotation(self) -> float:
        """Degrees clockwise, around its own origin (its Left, Top)."""
        return self._item.rotation()

    @Rotation.setter
    def Rotation(self, value):
        self._item.setRotation(float(value))

    @property
    def Scale(self) -> float:
        return self._item.scale()

    @Scale.setter
    def Scale(self, value):
        self._item.setScale(float(value))

    @property
    def ZOrder(self) -> float:
        """Higher: drawn on top of the others."""
        return self._item.zValue()

    @ZOrder.setter
    def ZOrder(self, value):
        self._item.setZValue(float(value))

    # -- how it looks ---------------------------------------------------------------------------
    def _apply_pen(self) -> None:
        item = self._item
        if not hasattr(item, "setPen"):
            return
        if self._fore is None:
            item.setPen(QPen(Qt.NoPen))
        else:
            pen = QPen(_color(self._fore), self._width)
            pen.setCosmetic(self._width <= 1)
            item.setPen(pen)

    @property
    def ForeColor(self):
        """Its outline's (a text's: its letters') color; None: no outline."""
        return self._fore

    @ForeColor.setter
    def ForeColor(self, value):
        self._fore = None if value is None else colors.normalize(value)
        if isinstance(self._item, QGraphicsSimpleTextItem):
            self._item.setBrush(QBrush(_color(self._fore if self._fore is not None else 0)))
        else:
            self._apply_pen()

    @property
    def BorderWidth(self) -> float:
        return self._width

    @BorderWidth.setter
    def BorderWidth(self, value):
        self._width = float(value)
        self._apply_pen()

    @property
    def FillColor(self):
        """What fills it; None: not filled."""
        return self._fill

    @FillColor.setter
    def FillColor(self, value):
        self._fill = None if value is None else colors.normalize(value)
        if hasattr(self._item, "setBrush") and not isinstance(self._item,
                                                              QGraphicsSimpleTextItem):
            self._item.setBrush(QBrush(_color(self._fill)) if self._fill is not None
                                else QBrush(Qt.NoBrush))

    @property
    def Text(self) -> str:
        """A text item's text."""
        return self._item.text() if isinstance(self._item, QGraphicsSimpleTextItem) else ""

    @Text.setter
    def Text(self, value):
        if not isinstance(self._item, QGraphicsSimpleTextItem):
            raise AttributeError(f"A {self._kind} item has no Text")
        self._item.setText(str(value))

    @property
    def Visible(self) -> bool:
        return self._item.isVisible()

    @Visible.setter
    def Visible(self, value):
        self._item.setVisible(bool(value))

    @property
    def Movable(self) -> bool:
        """Whether the user can drag it (ItemMoved fires)."""
        return bool(self._item.flags() & QGraphicsItem.ItemIsMovable)

    @Movable.setter
    def Movable(self, value):
        self._item.setFlag(QGraphicsItem.ItemIsMovable, bool(value))

    @property
    def Selectable(self) -> bool:
        return bool(self._item.flags() & QGraphicsItem.ItemIsSelectable)

    @Selectable.setter
    def Selectable(self, value):
        self._item.setFlag(QGraphicsItem.ItemIsSelectable, bool(value))

    @property
    def Selected(self) -> bool:
        return self._item.isSelected()

    @Selected.setter
    def Selected(self, value):
        self._item.setSelected(bool(value))

    def Remove(self) -> None:
        """Take it off the view."""
        self._view._items.Remove(self)


class _Items:
    """GraphicsView.Items: its shapes, by Index (from 1) or Key."""

    def __init__(self, view: "GraphicsView"):
        self._view = view
        self._list: list[GraphicsItem] = []
        self._by_key: dict[str, GraphicsItem] = {}

    def __iter__(self):
        return iter(list(self._list))

    def __len__(self):
        return len(self._list)

    @property
    def Count(self) -> int:
        return len(self._list)

    def __call__(self, ref) -> GraphicsItem:
        if isinstance(ref, GraphicsItem):
            return ref
        if isinstance(ref, str):
            if ref not in self._by_key:
                raise KeyError(f"GraphicsView '{self._view.Name}' has no item {ref!r}")
            return self._by_key[ref]
        ref = int(ref)
        if not 1 <= ref <= len(self._list):
            raise IndexError(f"GraphicsView '{self._view.Name}' has no item {ref} "
                             f"(1 to {len(self._list)})")
        return self._list[ref - 1]

    Item = __getitem__ = __call__

    def _add(self, qitem: QGraphicsItem, kind: str, Key: str, ForeColor, FillColor,
             BorderWidth, extra=None) -> GraphicsItem:
        if Key and Key in self._by_key:
            raise ValueError(f"GraphicsView '{self._view.Name}': the key {Key!r} is not unique")
        item = GraphicsItem(self._view, qitem, kind, str(Key or ""))
        if extra is None:
            self._view._scene.addItem(qitem)
        item._width = float(BorderWidth)
        item.ForeColor = ForeColor
        if kind not in ("Text", "Picture", "Group", "Line"):
            item.FillColor = FillColor
        self._list.append(item)
        if Key:
            self._by_key[str(Key)] = item
        self._view._grow()
        return item

    def AddRect(self, X, Y, Width, Height, ForeColor=0, FillColor=None, BorderWidth=1,
                Key: str = "") -> GraphicsItem:
        """A rectangle; its Left and Top are X and Y (it turns around that corner)."""
        qitem = QGraphicsRectItem(0, 0, float(Width), float(Height))
        qitem.setPos(float(X), float(Y))
        return self._add(qitem, "Rect", Key, ForeColor, FillColor, BorderWidth)

    def AddEllipse(self, X, Y, Width, Height, ForeColor=0, FillColor=None, BorderWidth=1,
                   Key: str = "") -> GraphicsItem:
        """An ellipse in the rectangle X, Y, Width, Height."""
        qitem = QGraphicsEllipseItem(0, 0, float(Width), float(Height))
        qitem.setPos(float(X), float(Y))
        return self._add(qitem, "Ellipse", Key, ForeColor, FillColor, BorderWidth)

    def AddLine(self, X1, Y1, X2, Y2, ForeColor=0, BorderWidth=1,
                Key: str = "") -> GraphicsItem:
        """A line from X1, Y1 to X2, Y2 (its Left and Top are X1 and Y1)."""
        qitem = QGraphicsLineItem(0, 0, float(X2) - float(X1), float(Y2) - float(Y1))
        qitem.setPos(float(X1), float(Y1))
        return self._add(qitem, "Line", Key, ForeColor, None, BorderWidth)

    def AddPolygon(self, Points, ForeColor=0, FillColor=None, BorderWidth=1,
                   Key: str = "") -> GraphicsItem:
        """A polygon through Points ([(x, y), ...]), closed."""
        qitem = QGraphicsPolygonItem(QPolygonF([QPointF(float(x), float(y))
                                                for x, y in Points]))
        return self._add(qitem, "Polygon", Key, ForeColor, FillColor, BorderWidth)

    def AddPath(self, Path, ForeColor=0, FillColor=None, BorderWidth=1,
                Key: str = "") -> GraphicsItem:
        """A path: SVG path data ("M 10 10 L 50 10 Q 70 30 50 50 Z")."""
        path = Path if isinstance(Path, QPainterPath) else svg_path(Path)
        return self._add(QGraphicsPathItem(path), "Path", Key, ForeColor, FillColor,
                         BorderWidth)

    def AddText(self, Text, X=0, Y=0, ForeColor=0, FontSize=None, FontBold=False,
                Key: str = "") -> GraphicsItem:
        """Text whose top-left corner is at X, Y."""
        qitem = QGraphicsSimpleTextItem(str(Text))
        font = self._view._widget.font()
        if FontSize:
            font.setPointSizeF(float(FontSize))
        font.setBold(bool(FontBold))
        qitem.setFont(font)
        qitem.setPos(float(X), float(Y))
        return self._add(qitem, "Text", Key, ForeColor, None, 1)

    def AddPicture(self, Picture, X=0, Y=0, Key: str = "") -> GraphicsItem:
        """A picture (a file, relative to the form's folder, or a Picture)."""
        qitem = QGraphicsPixmapItem(picture_pixmap(self._view, Picture))
        qitem.setTransformationMode(Qt.SmoothTransformation)
        qitem.setPos(float(X), float(Y))
        return self._add(qitem, "Picture", Key, None, None, 1)

    def AddGroup(self, *Items, Key: str = "") -> GraphicsItem:
        """The items as one, which moves, turns and scales them together."""
        parts = [self(item) for item in Items]
        group = self._view._scene.createItemGroup([part._item for part in parts])
        return self._add(group, "Group", Key, None, None, 1, extra=True)

    def Remove(self, ref) -> None:
        item = self(ref)
        scene = self._view._scene
        if isinstance(item._item.parentItem(), QGraphicsItemGroup):
            item._item.parentItem().removeFromGroup(item._item)
        scene.removeItem(item._item)
        self._list.remove(item)
        self._by_key.pop(item._key, None)
        self._view._grow()

    def Clear(self) -> None:
        self._view._scene.clear()
        self._list.clear()
        self._by_key.clear()
        self._view._grow()


_MOUSE_MODES = (QGraphicsView.NoDrag, QGraphicsView.ScrollHandDrag,
                QGraphicsView.RubberBandDrag)


class GraphicsView(Control):
    """A canvas of shapes as objects (the module's documentation)."""

    TypeName = "GraphicsView"
    DefaultEvent = "ItemClick"
    DefaultSize = (321, 241)
    Events = ("ItemClick", "ItemMoved", "SelectionChanged", "Click", "DblClick", "GotFocus",
              "LostFocus", "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    EventArgs = {"ItemClick": "Item"}
    _qss_type = "QGraphicsView"
    Properties = (
        *_geometry(*DefaultSize),
        P("BackColor", "color", None, description="The canvas's color; unset = the default"),
        P("SceneWidth", "int", 0,
          description="The width of the area that scrolls; 0 = as wide as its items need"),
        P("SceneHeight", "int", 0,
          description="The height of the area that scrolls; 0 = as tall as its items need"),
        P("Zoom", "number", 1, description="How large the items are shown: 1 = actual size"),
        P("MouseMode", "enum", 0, enum_choices("Items", "Pan", "Select"),
          description="What dragging with the left button does: drags the movable items, "
                      "pans the view, or selects items with a rubber band"),
        P("Antialiasing", "bool", True, description="Smooth edges"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A border around it"),
        *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_items"] = _Items(self)
        self.__dict__["_press"] = None  # (the item pressed, and where the items were)
        scene = QGraphicsScene()
        view = QGraphicsView(scene, parent)
        scene.setParent(view)
        self.__dict__["_scene"] = scene
        view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        return view

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        self._scene.selectionChanged.connect(lambda: self._fire("SelectionChanged"))

    def _on_qt_event(self, watched, event):
        if watched is self._widget.viewport() and not self._design_mode:
            etype = event.type()
            if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                item = self.HitTest(event.position().x(), event.position().y())
                self.__dict__["_press"] = (item, {i: (i.Left, i.Top) for i in self._items._list})
            elif etype == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and \
                    self._press is not None:
                pressed, places = self._press
                self.__dict__["_press"] = None
                result = super()._on_qt_event(watched, event)
                moved = [i for i, place in places.items()
                         if i in self._items._list and (i.Left, i.Top) != place]
                for item in moved:
                    self._fire("ItemMoved", item)
                if moved:
                    self._grow()
                elif pressed is not None:
                    self._fire("ItemClick", pressed)
                return result
        return super()._on_qt_event(watched, event)

    # -- the items ------------------------------------------------------------------------------
    @property
    def Items(self) -> _Items:
        return self._items

    @property
    def SelectedItems(self) -> list[GraphicsItem]:
        return [item for item in self._items._list if item._item.isSelected()]

    def HitTest(self, X, Y) -> "GraphicsItem | None":
        """The item at a point in the view (as the mouse events give it), or None;
        an item in a group gives its group."""
        qitem = self._widget.itemAt(int(X), int(Y))
        while qitem is not None:
            item = qitem.data(_ITEM_ROLE)
            group = qitem.group()
            if group is not None:
                qitem = group
                continue
            if isinstance(item, GraphicsItem):
                return item
            qitem = qitem.parentItem()
        return None

    def SceneX(self, X, Y=0) -> float:
        """A point in the view (pixels) as the items' X."""
        return self._widget.mapToScene(int(X), int(Y)).x()

    def SceneY(self, Y, X=0) -> float:
        return self._widget.mapToScene(int(X), int(Y)).y()

    def _grow(self) -> None:
        """The scrolled area: SceneWidth x SceneHeight, or the items' extent (from 0, 0)."""
        bounds = self._scene.itemsBoundingRect()
        width = self._values.get("SceneWidth") or max(bounds.right(), 0)
        height = self._values.get("SceneHeight") or max(bounds.bottom(), 0)
        self._scene.setSceneRect(QRectF(0, 0, width, height))

    # -- the view -------------------------------------------------------------------------------
    def _apply_Zoom(self, v):
        zoom = max(0.01, float(v))
        transform = self._widget.transform()
        transform.reset()
        self._widget.setTransform(transform.scale(zoom, zoom))

    def _read_Zoom(self):
        return round(self._widget.transform().m11(), 6)

    def ZoomToFit(self) -> None:
        """Zoom so all the items fit."""
        bounds = self._scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        self._widget.fitInView(bounds.adjusted(-4, -4, 4, 4), Qt.KeepAspectRatio)
        self._values["Zoom"] = self._read_Zoom()

    def ScrollTo(self, X, Y) -> None:
        """Scroll so the point X, Y (the items' coordinates) is in the middle."""
        self._widget.centerOn(float(X), float(Y))

    def _apply_SceneWidth(self, v):
        self._grow()

    _apply_SceneHeight = _apply_SceneWidth

    def _apply_MouseMode(self, v):
        self._widget.setDragMode(_MOUSE_MODES[int(v) if 0 <= int(v) <= 2 else 0])

    def _apply_Antialiasing(self, v):
        self._widget.setRenderHint(QPainter.Antialiasing, bool(v))
        self._widget.setRenderHint(QPainter.TextAntialiasing, bool(v))

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken if v else QFrame.NoFrame)

    def _apply_BackColor(self, v):
        self._scene.setBackgroundBrush(QBrush(_color(v)) if v is not None else QBrush())

    # -- pictures, printing ------------------------------------------------------------------------
    def _render(self) -> QImage:
        rect = self._scene.sceneRect()
        image = QImage(max(1, int(rect.width())), max(1, int(rect.height())),
                       QImage.Format_ARGB32_Premultiplied)
        image.fill(_color(self._values["BackColor"]) if self._values.get("BackColor")
                   is not None else QColor(Qt.white))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        selected = self.SelectedItems
        for item in selected:  # (no selection outlines in the picture)
            item._item.setSelected(False)
        self._scene.render(painter, QRectF(image.rect()), rect)
        for item in selected:
            item._item.setSelected(True)
        painter.end()
        return image

    @property
    def Picture(self):
        """The whole scene, at actual size, as a Picture (read-only)."""
        from .picture import Picture

        return Picture(_image=self._render())

    def PrintOut(self) -> None:
        """Print the scene on the Printer (as large as fits on the page) and
        end the document."""
        from .printer import Printer

        picture = self.Picture
        width = Printer.ScaleX(picture.Width, 3)  # (pixels in the Printer's ScaleMode)
        height = Printer.ScaleY(picture.Height, 3)
        scale = min(1.0, Printer.ScaleWidth / max(width, 1e-9),
                    Printer.ScaleHeight / max(height, 1e-9))
        Printer.PaintPicture(picture, 0, 0, width * scale, height * scale)
        Printer.EndDoc()


_add_validation(GraphicsView)
_add_mouse_members(GraphicsView)
CONTROL_TYPES["GraphicsView"] = GraphicsView  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
