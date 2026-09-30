"""The form designer.

The form being designed is a real ``Form`` instance in design mode with real
controls on it, so what you see is exactly what runs. A transparent overlay
on top of everything handles the mouse: selecting, moving, resizing,
drawing new controls and rubber-band selection. Every change is written
back to the document's designer region.
"""

from __future__ import annotations

import copy
import keyword
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QGuiApplication, QPainter, QPalette, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QMenu, QMessageBox, QScrollArea, QVBoxLayout,
                               QWidget)

from .. import appearance, colors
from .._props import normalize
from ..controls import CONTROL_TYPES, Control
from ..form import Form
from ..formfile import ControlDef, FormDef, control_key, set_index_parameter
from . import chrome, menueditor
from .documents import FormDocument
from .theme import theme_manager

GRID = 8
MARGIN = 16
HANDLE = 7
DRAG_THRESHOLD = 3

NAME_PREFIX = {
    "PictureBox": "Picture", "Label": "Label", "TextBox": "Text", "Frame": "Frame",
    "CommandButton": "Command", "CheckBox": "Check", "OptionButton": "Option",
    "ComboBox": "Combo", "ListBox": "List", "HScrollBar": "HScroll",
    "VScrollBar": "VScroll", "Timer": "Timer", "Line": "Line", "Image": "Image",
    "TreeView": "TreeView", "Splitter": "Splitter", "DriveListBox": "Drive",
    "DirListBox": "Dir", "FileListBox": "File", "CodeBox": "Code", "FlexGrid": "Grid",
    "DockPanel": "Dock",
}

_clipboard: list[ControlDef] = []


def snap(value: int) -> int:
    return int(round(value / GRID)) * GRID


def _distance(point: QPoint, a: QPoint, b: QPoint) -> float:
    """From a point to the segment a-b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((point.x() - a.x()) * dx +
                                                    (point.y() - a.y()) * dy) / length))
    x, y = a.x() + t * dx - point.x(), a.y() + t * dy - point.y()
    return (x * x + y * y) ** 0.5


def is_identifier(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


class DesignForm(Form):
    _design_mode = True

    def __init__(self, designer: "FormDesigner"):
        self.__dict__["_designer"] = designer
        super().__init__()

    def _base_dir(self) -> str:
        return self._designer.base_dir

    def _project_scheme(self) -> int:
        return self._designer.project_scheme

    def _render_scheme(self) -> int:
        # A System form normally renders natively, i.e. in the IDE's scheme.
        # When the IDE forces a scheme different from the OS appearance, force
        # the OS appearance on the form so it looks the way it will run.
        scheme = self._effective_scheme()
        if scheme == appearance.vpSchemeSystem and appearance.app_override_active():
            os_dark = appearance.system_is_dark()
            if os_dark != ide_is_dark():
                return appearance.vpSchemeDark if os_dark else appearance.vpSchemeLight
        return scheme

    def _control_widget_changed(self, control: Control) -> None:
        self._designer._prepare_widget(control)

    def _apply_colors(self, _=None):
        # Design time: the background shows the classic grid of dots. The
        # palette is the form's own scheme, independent of the IDE's.
        scheme = self._render_scheme()
        palette = QPalette(QApplication.palette()) if scheme == appearance.vpSchemeSystem \
            else appearance.scheme_palette(scheme == appearance.vpSchemeDark)
        back = self._values.get("BackColor")
        base = colors.to_qcolor(back) if back is not None else palette.color(QPalette.Window)
        if theme_manager().state.show_grid:
            tile = QPixmap(GRID, GRID)
            tile.fill(base)
            painter = QPainter(tile)
            painter.setPen(QColor(0, 0, 0, 110) if base.lightness() > 100
                           else QColor(255, 255, 255, 110))
            painter.drawPoint(0, 0)
            painter.end()
            palette.setBrush(QPalette.Window, QBrush(tile))
        else:
            palette.setColor(QPalette.Window, base)
        fore = self._values.get("ForeColor")
        if fore is not None:
            palette.setColor(QPalette.WindowText, colors.to_qcolor(fore))
        self._widget.setPalette(palette)
        self._widget.setAutoFillBackground(True)

    _apply_BackColor = _apply_ForeColor = _apply_colors


# The workspace around the form follows the IDE's light/dark appearance
WORKSPACE = {False: "#8c9096", True: "#262628"}


def ide_is_dark() -> bool:
    return theme_manager().app_is_dark()


class _Canvas(QWidget):
    """Workspace background with a painted window frame around the form."""

    def __init__(self, designer: "FormDesigner"):
        super().__init__()
        self.designer = designer

    def form_frame_rect(self) -> QRect:
        d = self.designer
        return chrome.frame_rect(d.form_canvas_rect(), d.frame_style(), d.frame_info())

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(WORKSPACE[ide_is_dark()]))
        d = self.designer
        if d.form is not None:
            chrome.paint(p, d.frame_style(), d.form_canvas_rect(), d.frame_info())


class _Overlay(QWidget):
    """Transparent layer above the form that implements all mouse handling."""

    def __init__(self, designer: "FormDesigner", parent: QWidget):
        super().__init__(parent)
        self.d = designer
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._drag = None  # dict describing the current drag operation

    # -- painting -------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        d = self.d
        selection = d.selection
        if not selection:
            for handle_rect in self._form_handles().values():
                self._draw_handle(p, handle_rect, filled=True)
        else:
            single = len(selection) == 1
            for name in selection:
                rect = d.canvas_rect(name)
                if rect is None:
                    continue
                primary = name == selection[-1]
                if d.is_line(name):  # a Line: handles at its two ends only
                    for handle_rect in self._line_handles(name).values():
                        self._draw_handle(p, handle_rect, filled=single or primary)
                    continue
                if not single:
                    self._draw_outline(p, rect.adjusted(-1, -1, 0, 0), Qt.DotLine)
                for handle_rect in self._handles(rect).values():
                    self._draw_handle(p, handle_rect, filled=single or primary)
        if self._drag and self._drag["kind"] in ("band", "draw") and self._drag.get("moved"):
            rect = QRect(self._drag["start"], self._drag["pos"]).normalized()
            p.fillRect(rect, QColor(0, 120, 215, 40))
            self._draw_outline(p, rect, Qt.DashLine)

    # Two-tone drawing stays visible on light and dark forms alike.
    @staticmethod
    def _draw_outline(p: QPainter, rect: QRect, style) -> None:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(Qt.white, 1))
        p.drawRect(rect)
        p.setPen(QPen(Qt.black, 1, style))
        p.drawRect(rect)

    @staticmethod
    def _draw_handle(p: QPainter, rect: QRect, filled: bool) -> None:
        p.fillRect(rect, QColor("#000080") if filled else Qt.white)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(Qt.white if filled else QColor("#000080"), 1))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    @staticmethod
    def _handles(rect: QRect) -> dict[str, QRect]:
        h = HANDLE
        xs = {"l": rect.left() - h // 2 - 1, "c": rect.center().x() - h // 2,
              "r": rect.right() - h // 2 + 1}
        ys = {"t": rect.top() - h // 2 - 1, "m": rect.center().y() - h // 2,
              "b": rect.bottom() - h // 2 + 1}
        handles = {}
        for key_y, y in ys.items():
            for key_x, x in xs.items():
                if key_x == "c" and key_y == "m":
                    continue
                handles[key_y + key_x] = QRect(x, y, h, h)
        return handles

    def _form_handles(self) -> dict[str, QRect]:
        rect = self.d.form_canvas_rect()
        h = HANDLE
        return {
            "mr": QRect(rect.right() + 1, rect.center().y() - h // 2, h, h),
            "bc": QRect(rect.center().x() - h // 2, rect.bottom() + 1, h, h),
            "br": QRect(rect.right() + 1, rect.bottom() + 1, h, h),
        }

    def _line_handles(self, name: str) -> dict[str, QRect]:
        h = HANDLE
        return {key: QRect(point.x() - h // 2, point.y() - h // 2, h, h)
                for key, point in zip(("p1", "p2"), self.d.line_points(name))}

    def _handle_at(self, pos: QPoint) -> tuple[str | None, str] | None:
        d = self.d
        if len(d.selection) == 1 and d.is_line(d.selection[0]):
            for key, handle_rect in self._line_handles(d.selection[0]).items():
                if handle_rect.adjusted(-2, -2, 2, 2).contains(pos):
                    return d.selection[0], key
            return None
        if not d.selection:
            for key, rect in self._form_handles().items():
                if rect.adjusted(-2, -2, 2, 2).contains(pos):
                    return None, key
        elif len(d.selection) == 1 and d.controls[d.selection[0]].TypeName != "Timer" and \
                d.canvas_rect(d.selection[0]) is not None:  # menus aren't on the canvas
            rect = d.canvas_rect(d.selection[0])
            for key, handle_rect in self._handles(rect).items():
                if handle_rect.adjusted(-2, -2, 2, 2).contains(pos):
                    return d.selection[0], key
        return None

    @staticmethod
    def _cursor_for(key: str):
        return {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "tc": Qt.SizeVerCursor, "bc": Qt.SizeVerCursor,
            "ml": Qt.SizeHorCursor, "mr": Qt.SizeHorCursor,
            # A Line's ends move in any direction
            "p1": Qt.SizeAllCursor, "p2": Qt.SizeAllCursor,
        }[key]

    # -- mouse -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        self.setFocus()
        d = self.d
        pos = event.position().toPoint()
        if event.button() == Qt.RightButton:
            name = d.control_at(pos)
            if name is not None and name not in d.selection:
                d.select([name])
            elif name is None and d.form_canvas_rect().contains(pos):
                d.select([])
            d.show_context_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.LeftButton:
            return
        menu = d.menu_at(pos)
        if menu is not None:  # the menu bar: show that menu, like VB's designer
            d.show_menu_popup(menu, self.mapToGlobal(d.menu_rect(menu).bottomLeft()))
            return
        form_rect = d.form_canvas_rect()

        if d.tool is not None:
            if form_rect.contains(pos):
                self._drag = {"kind": "draw", "start": pos, "pos": pos, "moved": False,
                              "container": d.container_at(pos)}
            return

        handle = self._handle_at(pos)
        if handle is not None and handle[1] in ("p1", "p2"):  # an end of a Line
            name, key = handle
            self._drag = {"kind": "endpoint", "name": name, "key": key, "start": pos,
                          "moved": False, "orig": d.line_point(name, key)}
            return
        if handle is not None:
            name, key = handle
            self._drag = {"kind": "resize" if name else "form_resize", "name": name,
                          "key": key, "start": pos, "moved": False,
                          "orig": d.parent_rect(name) if name else d.form_widget().geometry()}
            return

        additive = bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))
        name = d.control_at(pos)
        if name is not None and event.modifiers() & Qt.ControlModifier \
                and d.controls[name].IsContainer:
            # Ctrl+drag inside a container: rubber band over its children
            self._drag = {"kind": "band", "start": pos, "pos": pos, "moved": False,
                          "container": name, "additive": False}
            return
        if name is None:
            if form_rect.contains(pos):
                self._drag = {"kind": "band", "start": pos, "pos": pos, "moved": False,
                              "container": None, "additive": additive}
                if not additive:
                    d.select([])
            else:
                d.select([])
            return
        if additive:
            if name in d.selection:
                d.select([n for n in d.selection if n != name])
                return
            d.select(d.selection + [name])
        elif name not in d.selection:
            d.select([name])
        else:
            # Clicking an already selected control makes it the primary one
            d.select([n for n in d.selection if n != name] + [name])
        self._drag = {"kind": "move", "start": pos, "moved": False, "primary": name,
                      "orig": {n: d.parent_rect(n) for n in d.selection},
                      "anchor": d.snap_anchor(name)}

    def mouseMoveEvent(self, event):
        d = self.d
        pos = event.position().toPoint()
        drag = self._drag
        if drag is None:
            if d.tool is not None:
                self.setCursor(Qt.CrossCursor if d.form_canvas_rect().contains(pos)
                               else Qt.ArrowCursor)
                return
            handle = self._handle_at(pos)
            self.setCursor(self._cursor_for(handle[1]) if handle else Qt.ArrowCursor)
            return
        if not drag["moved"] and (pos - drag["start"]).manhattanLength() < DRAG_THRESHOLD:
            return
        drag["moved"] = True
        drag["pos"] = pos
        delta = pos - drag["start"]
        kind = drag["kind"]
        if kind == "move":
            anchor = drag["anchor"]  # the point that snaps to the grid
            if event.modifiers() & Qt.AltModifier:
                dx, dy = delta.x(), delta.y()
            else:
                dx = snap(anchor.x() + delta.x()) - anchor.x()
                dy = snap(anchor.y() + delta.y()) - anchor.y()
            for name, rect in drag["orig"].items():
                d.controls[name]._widget.move(rect.x() + dx, rect.y() + dy)
        elif kind == "endpoint":
            d.move_line_point(drag["name"], drag["key"], drag["orig"] + delta,
                              use_grid=not event.modifiers() & Qt.AltModifier)
        elif kind == "resize":
            d.controls[drag["name"]]._widget.setGeometry(
                self._resized(drag["orig"], drag["key"], delta,
                              not event.modifiers() & Qt.AltModifier))
        elif kind == "form_resize":
            orig = drag["orig"]
            width = orig.width() + (delta.x() if "r" in drag["key"] else 0)
            height = orig.height() + (delta.y() if drag["key"][0] == "b" else 0)
            d.form_widget().resize(max(width, 64), max(height, 32))
            d.update_canvas_size()
        self.update()

    @staticmethod
    def _resized(rect: QRect, key: str, delta: QPoint, use_grid: bool) -> QRect:
        left, top, right, bottom = rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1
        s = snap if use_grid else (lambda v: v)
        if key[1] == "l":
            left = min(s(left + delta.x()), right - 4)
        if key[1] == "r":
            right = max(s(right + delta.x()), left + 4)
        if key[0] == "t":
            top = min(s(top + delta.y()), bottom - 4)
        if key[0] == "b":
            bottom = max(s(bottom + delta.y()), top + 4)
        return QRect(left, top, right - left, bottom - top)

    def mouseReleaseEvent(self, event):
        drag, self._drag = self._drag, None
        if drag is None or event.button() != Qt.LeftButton:
            return
        d = self.d
        kind = drag["kind"]
        if kind == "draw":
            rect = QRect(drag["start"], event.position().toPoint()).normalized()
            d.create_control(d.tool, rect if drag["moved"] else None, drag["container"],
                             drag["start"], event.position().toPoint() if drag["moved"] else None)
        elif kind == "band" and drag["moved"]:
            band = QRect(drag["start"], event.position().toPoint()).normalized()
            names = [c.key for c in d.form_def.controls
                     if c.parent == drag["container"] and d.canvas_rect(c.key) is not None
                     and band.intersects(d.canvas_rect(c.key))]
            d.select((d.selection if drag["additive"] else []) + names)
        elif kind == "endpoint" and drag["moved"]:
            d.commit_geometry([drag["name"]])
        elif kind in ("move", "resize") and drag["moved"]:
            d.commit_geometry(list(drag["orig"]) if kind == "move" else [drag["name"]])
        elif kind == "form_resize" and drag["moved"]:
            d.commit_form_size()
        self.update()

    def mouseDoubleClickEvent(self, event):
        d = self.d
        if d.tool is not None:
            return
        pos = event.position().toPoint()
        name = d.control_at(pos)
        if name is not None:  # a Line has no events: just its form's code
            d.viewCodeRequested.emit(d.form_def.control(name).name,
                                     d.controls[name].DefaultEvent)
        elif d.form_canvas_rect().contains(pos):
            d.viewCodeRequested.emit("Form", Form.DefaultEvent)

    # -- keyboard ----------------------------------------------------------------------
    def keyPressEvent(self, event):
        d = self.d
        key = event.key()
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1),
                  Qt.Key_Down: (0, 1)}
        if key in arrows and d.selection:
            step = 1 if event.modifiers() & Qt.ControlModifier else GRID
            dx, dy = (v * step for v in arrows[key])
            d.nudge(dx, dy, resize=bool(event.modifiers() & Qt.ShiftModifier))
        elif key == Qt.Key_Escape:
            if d.tool is not None:
                d.toolConsumed.emit()
            elif d.selection:
                parent = d.form_def.control(d.selection[-1]).parent
                d.select([parent] if parent else [])
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            d.delete_selection()
        else:
            super().keyPressEvent(event)


class FormDesigner(QWidget):
    """Design surface for one FormDocument (the "Object" window in VB)."""

    selectionChanged = Signal()
    designChanged = Signal()
    viewCodeRequested = Signal(str, str)  # object name ("Form" for the form), event
    toolConsumed = Signal()
    formRenamed = Signal(str, str)
    statusMessage = Signal(str)

    def __init__(self, document: FormDocument, base_dir: str, parent=None,
                 project_scheme: int = appearance.vpSchemeSystem):
        super().__init__(parent)
        self.document = document
        self.base_dir = base_dir
        # The project's color scheme, used by forms set to "Project Default"
        self.project_scheme = project_scheme
        self.form: DesignForm | None = None
        self.controls: dict[str, Control] = {}
        self.form_def = FormDef(document.form_def.class_name)
        self.selection: list[str] = []  # empty = the form itself
        self.tool: str | None = None
        self._undo: list[FormDef] = []
        self._redo: list[FormDef] = []
        # Set by the IDE: whether another form of the project has this name
        self.form_name_taken: Callable[[str], bool] = lambda name: False

        self.canvas = _Canvas(self)
        self.overlay = _Overlay(self, self.canvas)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.viewport().installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

        self.load_def(document.form_def)
        document.designReloaded.connect(self._on_document_reloaded)
        theme_manager().changed.connect(self._on_ide_theme_changed)  # light/dark, frame
        # A bound method, not a lambda: disconnected when the designer is deleted
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_os_scheme_changed)

    # -- color schemes -------------------------------------------------------------------------
    def set_project_scheme(self, scheme: int) -> None:
        self.project_scheme = scheme
        self.refresh_scheme()

    def _on_os_scheme_changed(self, *_) -> None:
        QTimer.singleShot(0, self, self.refresh_scheme)  # cancelled if the designer is deleted

    def refresh_scheme(self) -> None:
        """Re-apply the form's scheme (project default or the OS appearance
        changed) and repaint the workspace."""
        if self.form is not None:
            self.form._apply_ColorScheme()
        self.canvas.update()

    def eventFilter(self, watched, event):
        # Size the canvas from the scroll area's viewport once *it* has been
        # resized. The designer's own resizeEvent comes before the layout
        # resizes the scroll area, so a single jump (maximize/restore) would
        # leave the canvas at the previous size.
        scroll = self.__dict__.get("scroll")  # gone while the designer is being destroyed
        if scroll is not None and watched is scroll.viewport() and \
                event.type() == QEvent.Resize:
            self.update_canvas_size()
        return super().eventFilter(watched, event)

    # -- building the live form ---------------------------------------------------------------
    def form_widget(self) -> QWidget:
        return self.form._widget

    def load_def(self, form_def: FormDef) -> None:
        """(Re)create the live form and controls from a FormDef."""
        self.form_def = copy.deepcopy(form_def)
        if self.form is not None:
            old = self.form._widget
            old.hide()
            old.setParent(None)
            old.deleteLater()
        self.controls = {}
        self.form = DesignForm(self)
        for prop, value in self.form_def.props.items():
            self._safe_set(self.form, prop, value)
        widget = self.form._widget
        widget.setParent(self.canvas)
        widget.show()
        self._layout_form()
        for control_def in self.form_def.controls:
            self._instantiate(control_def)
        self.overlay.raise_()
        self.update_canvas_size()
        self.selection = [n for n in self.selection if n in self.controls]
        self.selectionChanged.emit()
        self.canvas.update()

    def _instantiate(self, control_def: ControlDef) -> Control:
        cls = CONTROL_TYPES[control_def.type]
        parent = self.form if control_def.parent is None else self.controls[control_def.parent]
        valid = {k: v for k, v in control_def.props.items() if k in cls._specs}
        try:
            control = cls(parent, Name=control_def.name, **valid)
        except Exception as exc:  # noqa: BLE001 - keep the designer usable
            self.statusMessage.emit(f"{control_def.key}: {exc}")
            control = cls(parent, Name=control_def.name)
        control.__dict__["_index"] = control_def.index
        self.controls[control_def.key] = control
        self._prepare_widget(control)  # also shows it (menus have no widget)
        return control

    def _safe_set(self, obj, prop, value) -> None:
        try:
            setattr(obj, prop, value)
        except Exception as exc:  # noqa: BLE001
            self.statusMessage.emit(f"{prop}: {exc}")

    def _prepare_widget(self, control: Control) -> None:
        widget = control._widget
        if widget is None:
            return
        for w in [widget, *widget.findChildren(QWidget)]:
            w.setFocusPolicy(Qt.NoFocus)
        widget.show()
        self.overlay.raise_()

    # -- window frame ------------------------------------------------------------------------------
    def frame_style(self) -> str:
        """macos, windows, gnome or classic (Options > Form designer)."""
        return chrome.resolve(theme_manager().state.frame_style)

    def frame_info(self) -> chrome.FrameInfo:
        form = self.form
        return chrome.FrameInfo(
            caption=form.Caption, border_style=form.BorderStyle, control_box=form.ControlBox,
            min_button=form.MinButton, max_button=form.MaxButton,
            # The OS draws title bars in its own appearance at run time
            title_dark=appearance.system_is_dark(), form_dark=form._is_dark(),
            menus=tuple(self.form_def.control(key).props.get("Caption", "")
                        for key in self.menu_bar_keys()))

    def _layout_form(self) -> None:
        """Place the form below the frame's title bar (its height depends on
        the frame style and BorderStyle)."""
        info = self.frame_info()
        title, border = chrome.metrics(self.frame_style(), info)
        position = QPoint(MARGIN + border, MARGIN + border + title + chrome.menu_height(info))
        if self.form_widget().pos() != position:
            self.form_widget().move(position)
            self.overlay.update()
        self.update_canvas_size()

    def _on_ide_theme_changed(self) -> None:
        self.refresh_scheme()  # also redraws the grid (it can be turned off)
        self._layout_form()

    def preferred_size(self) -> QSize:
        """The size that shows the whole form: its window frame plus the margin
        and room for the selection handles around it."""
        frame = self.canvas.form_frame_rect()
        return QSize(frame.right() + MARGIN + HANDLE, frame.bottom() + MARGIN + HANDLE)

    def update_canvas_size(self) -> None:
        size = self.preferred_size()
        # The canvas paints the workspace, so it covers the whole visible area
        self.canvas.resize(size.expandedTo(self.scroll.viewport().size()))
        self.overlay.setGeometry(self.canvas.rect())
        self.canvas.update()

    def _on_document_reloaded(self) -> None:
        self.load_def(self.document.form_def)
        self.designChanged.emit()

    # -- geometry helpers -------------------------------------------------------------------------
    def form_canvas_rect(self) -> QRect:
        widget = self.form_widget()
        return QRect(widget.pos(), widget.size())

    def canvas_rect(self, name: str) -> QRect | None:
        control = self.controls.get(name)
        if control is None or control._widget is None:
            return None
        widget = control._widget
        return QRect(widget.mapTo(self.canvas, QPoint(0, 0)), widget.size())

    def parent_rect(self, name: str) -> QRect:
        return QRect(self.controls[name]._widget.geometry())

    def control_at(self, pos: QPoint) -> str | None:
        """The control drawn on top at a canvas position. Asks Qt which widget
        is there, so it follows the real stacking (ZIndex) and clipping by
        containers."""
        if not self.form_canvas_rect().contains(pos):
            return None
        line = self.line_at(pos)
        if line is not None:
            return line
        form_widget = self.form_widget()
        widget = form_widget.childAt(form_widget.mapFrom(self.canvas, pos))
        while widget is not None and widget is not form_widget:
            control = getattr(widget, "_vp_control", None)  # set on each control's widget
            if control is not None and self.controls.get(self.key_of(control)) is control:
                return self.key_of(control)
            widget = widget.parentWidget()
        return None

    def container_at(self, pos: QPoint) -> str | None:
        name = self.control_at(pos)
        while name is not None and not self.controls[name].IsContainer:
            name = self.form_def.control(name).parent
        return name

    def _container_widget(self, container: str | None) -> QWidget:
        return self.form_widget() if container is None else self.controls[container]._widget

    # -- selection -----------------------------------------------------------------------------------
    def select(self, names: list[str]) -> None:
        seen = []
        for name in names:
            if name in self.controls and name not in seen:
                seen.append(name)
        if len(seen) > 1:  # a menu (chosen in the Properties window) is selected alone
            seen = [n for n in seen if not self.is_menu(n)] or seen[-1:]
        self.selection = seen
        self.overlay.update()
        self.selectionChanged.emit()

    def select_by_name(self, name: str) -> None:
        self.select([] if name == self.form_def.class_name else [name])

    def selected_objects(self) -> list:
        if not self.selection:
            return [self.form]
        return [self.controls[n] for n in self.selection]

    @staticmethod
    def key_of(control: Control) -> str:
        """'Command1', or 'cmdDigit(3)' for an element of a control array."""
        return control_key(control._name, control._index)

    def object_name(self, obj) -> str:
        """What identifies an object in the Properties window's object list."""
        return self.form_def.class_name if obj is self.form else self.key_of(obj)

    def name_value(self, obj) -> str:
        """Its (Name): the same for all elements of a control array."""
        return self.form_def.class_name if obj is self.form else obj._name

    def supports_index(self, obj) -> bool:
        """Controls have an Index (control arrays); the form doesn't."""
        return obj is not self.form

    def all_objects(self) -> list[tuple[str, str]]:
        return [(self.form_def.class_name, "Form")] + \
            [(c.key, c.type) for c in self.form_def.controls]

    def set_tool(self, tool: str | None) -> None:
        self.tool = tool
        self.overlay.setCursor(Qt.CrossCursor if tool else Qt.ArrowCursor)

    # -- committing changes --------------------------------------------------------------------------
    def _snapshot(self) -> FormDef:
        return copy.deepcopy(self.form_def)

    def _sync_aligned(self) -> None:
        """Aligned PictureBoxes go where the form docks them (also after being
        dragged, or the form resized): store their geometry."""
        if self.form is None:
            return
        self.form._layout_aligned()
        for key, control in self.controls.items():
            control_def = self.form_def.control(key)
            if control_def is None or not control._values.get("Align"):
                continue
            geometry = control._widget.geometry()
            place = {"Left": geometry.x(), "Top": geometry.y(), "Width": geometry.width(),
                     "Height": geometry.height()}
            control_def.props.update(place)
            control._values.update(place)

    def _commit(self, before: FormDef) -> None:
        self._sync_aligned()
        if before == self.form_def:
            return
        self._undo.append(before)
        self._redo.clear()
        self.document.set_form_def(self.form_def)
        self._layout_form()  # BorderStyle may have changed the title bar
        self.overlay.update()
        self.canvas.update()
        self.designChanged.emit()

    def commit_geometry(self, names: list[str]) -> None:
        before = self._snapshot()
        for name in [n for n in names if not self.is_menu(n)]:
            if self.is_line(name):  # moved (or an end dragged): the new points
                control = self.controls[name]
                points = control._moved_points()
                self.form_def.control(name).props.update(points)
                control._values.update(points)
                control._update_geometry()
                continue
            geometry = self.controls[name]._widget.geometry()
            props = self.form_def.control(name).props
            props.update(Left=geometry.x(), Top=geometry.y())
            if self.controls[name].TypeName != "Timer":
                props.update(Width=geometry.width(), Height=geometry.height())
            self.controls[name]._values.update(
                {k: props[k] for k in ("Left", "Top", "Width", "Height") if k in props})
        self._commit(before)

    def commit_form_size(self) -> None:
        before = self._snapshot()
        size = self.form_widget().size()
        self.form._values.update(Width=size.width(), Height=size.height())
        self.form_def.props.update(Width=size.width(), Height=size.height())
        self._commit(before)

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())

    def _restore(self, form_def: FormDef) -> None:
        old_name = self.form_def.class_name
        self.load_def(form_def)
        if form_def.class_name != old_name:
            self._rename_form_in_code(old_name, form_def.class_name)
        self.document.set_form_def(self.form_def)
        self.designChanged.emit()

    # -- creating / deleting --------------------------------------------------------------------------
    def unique_name(self, prefix: str, taken: set[str] | None = None) -> str:
        taken = taken if taken is not None else {c.name for c in self.form_def.controls}
        taken = taken | {self.form_def.class_name}
        i = 1
        while f"{prefix}{i}" in taken:
            i += 1
        return f"{prefix}{i}"

    def create_control(self, type_name: str, rect: QRect | None, container: str | None,
                       click_pos: QPoint | None = None, end_pos: QPoint | None = None) -> str:
        cls = CONTROL_TYPES[type_name]
        name = self.unique_name(NAME_PREFIX.get(type_name, type_name))
        origin = self._container_widget(container).mapTo(self.canvas, QPoint(0, 0))
        width, height = cls.DefaultSize
        if rect is not None and rect.width() >= 4 and rect.height() >= 4:
            left, top = snap(rect.x() - origin.x()), snap(rect.y() - origin.y())
            right = snap(rect.right() + 1 - origin.x())
            bottom = snap(rect.bottom() + 1 - origin.y())
            width, height = max(right - left, GRID), max(bottom - top, GRID)
        else:
            point = (click_pos or QPoint(origin.x() + GRID, origin.y() + GRID)) - origin
            left, top = snap(point.x()), snap(point.y())
        if type_name == "Timer":
            width, height = cls.DefaultSize

        props = {"Left": left, "Top": top}
        if type_name == "Line":  # from where the mouse was pressed to where it was released
            if click_pos is not None and end_pos is not None:
                start, end = click_pos - origin, end_pos - origin
                props = {"X1": snap(start.x()), "Y1": snap(start.y()),
                         "X2": snap(end.x()), "Y2": snap(end.y())}
            else:
                middle = top + (height // 2 if rect is not None else 0)
                props = {"X1": left, "Y1": snap(middle), "X2": left + max(width, GRID),
                         "Y2": snap(middle)}
        elif "Width" in cls._specs:
            props.update(Width=width, Height=height)
        for text_prop in ("Caption", "Text"):
            if text_prop in cls._specs and cls._specs[text_prop].always:
                props[text_prop] = name
        before = self._snapshot()
        control_def = ControlDef(type_name, name, container, props)
        self.form_def.controls.append(control_def)
        self._instantiate(control_def)
        self._renumber_tab_order(last=[name])
        self.overlay.raise_()
        self.select([name])
        self._commit(before)
        self.toolConsumed.emit()
        return name

    def add_control_centered(self, type_name: str) -> None:
        """Toolbox double-click: add a default sized control in the middle."""
        cls = CONTROL_TYPES[type_name]
        form_rect = self.form_canvas_rect()
        w, h = cls.DefaultSize
        rect = QRect(form_rect.center().x() - w // 2, form_rect.center().y() - h // 2, w, h)
        self.create_control(type_name, rect, None)

    def _descendants(self, names: list[str]) -> list[str]:
        """names plus all controls nested in them, in definition order."""
        result = set(names)
        for control_def in self.form_def.controls:
            if control_def.parent in result:
                result.add(control_def.key)
        return [c.key for c in self.form_def.controls if c.key in result]

    def delete_selection(self) -> None:
        if not self.selection:
            return
        before = self._snapshot()
        doomed = set(self._descendants(self.selection))
        self.form_def.controls = [c for c in self.form_def.controls if c.key not in doomed]
        for name in self.selection:  # deleting a container deletes its children
            widget = self.controls[name]._widget
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for name in doomed:
            control = self.controls.pop(name)
            if control in self.form._controls:
                self.form._controls.remove(control)
        self._renumber_tab_order()
        self.select([])
        self._commit(before)

    # -- clipboard --------------------------------------------------------------------------------------
    def copy_selection(self) -> None:
        if not self.selection or self.menu_selected():  # menus: the Menu Editor
            return
        names = self._descendants(self.selection)
        roots = {n for n in names if self.form_def.control(n).parent not in names}
        _clipboard.clear()
        for name in names:
            control_def = copy.deepcopy(self.form_def.control(name))
            if name in roots:
                control_def.parent = None
            _clipboard.append(control_def)

    def cut_selection(self) -> None:
        self.copy_selection()
        self.delete_selection()

    def paste(self) -> None:
        if not _clipboard:
            return
        target = None
        if len(self.selection) == 1 and self.controls[self.selection[0]].IsContainer:
            target = self.selection[0]
        before = self._snapshot()
        renamed: dict[str, str] = {}  # clipboard key -> pasted key
        pasted_roots = []
        clipboard_keys = {c.key for c in _clipboard}
        for original in _clipboard:
            control_def = copy.deepcopy(original)
            control_def.name, control_def.index = self._paste_identity(original)
            renamed[original.key] = control_def.key
            is_root = control_def.parent is None or control_def.parent not in clipboard_keys
            if is_root:
                control_def.parent = target
                pasted_roots.append(control_def.key)
                if control_def.key != original.key:
                    moved = ("X1", "Y1", "X2", "Y2") if control_def.type == "Line" else \
                        ("Left", "Top")
                    for prop in moved:
                        control_def.props[prop] = control_def.props.get(prop, 0) + GRID
            else:
                control_def.parent = renamed[control_def.parent]
            if control_def.name != original.name:
                for text_prop in ("Caption", "Text"):
                    if control_def.props.get(text_prop) == original.name:
                        control_def.props[text_prop] = control_def.name
            self.form_def.controls.append(control_def)
            self._instantiate(control_def)
        self._renumber_tab_order(last=list(renamed.values()))
        self.overlay.raise_()
        self.select(pasted_roots)
        self._commit(before)

    def _renumber_tab_order(self, moved: str | None = None, last: list[str] = ()) -> None:
        """Keep the TabIndex values 0, 1, 2, ... without gaps or duplicates, like
        VB: after adding (``last``: new controls go to the end, in order),
        deleting, or setting one control's TabIndex (``moved``: it takes that
        place and the others make room)."""
        defs = [c for c in self.form_def.controls if "TabIndex" in CONTROL_TYPES[c.type]._specs]

        def current(control_def):
            return int(control_def.props.get("TabIndex", 0))

        order = sorted((c for c in defs if c.key != moved and c.key not in last), key=current)
        order += [c for key in last for c in defs if c.key == key]
        if moved is not None:
            moved_def = self.form_def.control(moved)
            order.insert(min(max(current(moved_def), 0), len(order)), moved_def)
        for index, control_def in enumerate(order):
            if current(control_def) != index:
                control_def.props["TabIndex"] = index
                self._safe_set(self.controls[control_def.key], "TabIndex", index)

    def select_all(self) -> None:
        self.select([c.key for c in self.form_def.controls
                     if c.parent is None and c.type != "Menu"])

    # -- properties ----------------------------------------------------------------------------------------
    def set_property(self, prop: str, value) -> str | None:
        """Set a property on all selected objects. Returns an error message
        or None."""
        if prop == "Name":
            return self.rename(value)
        if prop == "Index":
            return self.set_index(value)
        before = self._snapshot()
        try:
            for obj in self.selected_objects():
                if prop not in obj._specs:
                    continue
                spec = obj._specs[prop]
                setattr(obj, prop, value)
                stored = normalize(spec.kind, value)
                if obj is self.form:
                    self.form_def.props[prop] = stored
                else:
                    props = self.form_def.control(self.key_of(obj)).props
                    props[prop] = stored
                    if prop in ("AutoSize", "Picture", "Caption", "Stretch", "BorderStyle") \
                            and obj._widget is not None:
                        # AutoSize (or an Image without Stretch) may have changed the size
                        props.update(Width=obj._widget.width(), Height=obj._widget.height())
            if prop == "TabIndex":
                for obj in self.selected_objects():
                    if obj is not self.form and prop in obj._specs:
                        self._renumber_tab_order(moved=self.key_of(obj))
        except Exception as exc:  # noqa: BLE001 - report invalid values to the user
            self.load_def(before)
            return f"Invalid property value: {exc}"
        if prop in ("Width", "Height") and not self.selection:
            self.update_canvas_size()
        self._commit(before)
        return None

    def rename(self, new_name: str) -> str | None:
        new_name = str(new_name).strip()
        if len(self.selection) > 1:
            return "Can't rename multiple objects at once"
        if not is_identifier(new_name):
            return f"'{new_name}' is not a valid name"
        if not self.selection:
            return self._rename_form(new_name)
        key = self.selection[0]
        control_def = self.form_def.control(key)
        old_name = control_def.name
        if new_name == old_name:
            return None
        if new_name == self.form_def.class_name:
            return f"The name '{new_name}' is already used"
        others = self.form_def.elements(new_name)
        before = self._snapshot()
        if others:  # joining (or creating) a control array, like VB
            if others[0].type != control_def.type:
                return f"The name '{new_name}' is already used by a {others[0].type}"
            if others[0].index is None:
                if not self.ask_create_array(new_name):
                    return f"The name '{new_name}' is already used"
                self._make_array(new_name)
            index = control_def.index
            if index is None or any(o.index == index for o in self.form_def.elements(new_name)):
                index = self._next_index(new_name)
            self._rekey(key, new_name, index)
        else:
            alone = len(self.form_def.elements(old_name)) == 1
            if alone:  # its event handlers and references go with it
                from ..formfile import rename_control_references

                self.document.replace_text(
                    rename_control_references(self.document.text, old_name, new_name))
            self._rekey(key, new_name, control_def.index)
        self._commit(before)
        self.selectionChanged.emit()
        return None

    def _rename_form(self, new_name: str) -> str | None:
        old_name = self.form_def.class_name
        if new_name == old_name:
            return None
        if self.form_def.elements(new_name) or self.form_name_taken(new_name):
            return f"The name '{new_name}' is already used"
        before = self._snapshot()
        self.form_def.class_name = new_name
        self._rename_form_in_code(old_name, new_name)
        self.document.set_form_def(self.form_def)
        self._undo.append(before)
        self.designChanged.emit()
        self.selectionChanged.emit()
        return None

    # -- control arrays --------------------------------------------------------------------------------
    def ask_create_array(self, name: str) -> bool:
        """Whether to make a control array (VB's question; tests replace it)."""
        answer = QMessageBox.question(
            self, "VP6", f"You already have a control named '{name}'. "
                         "Do you want to create a control array?")
        return answer == QMessageBox.Yes

    def _next_index(self, name: str) -> int:
        return 1 + max((c.index for c in self.form_def.elements(name) if c.index is not None),
                       default=-1)

    def _rekey(self, key: str, name: str, index: int | None) -> None:
        """Give a control a new name and/or Index, updating everything that
        refers to it by its key (the live control, containers, selection)."""
        control_def = self.form_def.control(key)
        control_def.name, control_def.index = name, index
        new_key = control_def.key
        for other in self.form_def.controls:
            if other.parent == key:
                other.parent = new_key
        control = self.controls.pop(key)
        control.__dict__["_name"], control.__dict__["_index"] = name, index
        self.controls[new_key] = control
        self.selection = [new_key if k == key else k for k in self.selection]

    def _set_index_parameter(self, name: str, present: bool) -> None:
        """Add or remove Index in the name's event handlers, as VB does."""
        control_def = self.form_def.elements(name)[0]
        events = CONTROL_TYPES[control_def.type].Events
        self.document.replace_text(
            set_index_parameter(self.document.text, name, events, present))

    def _make_array(self, name: str) -> None:
        """Turn the control ``name`` into element 0 of a control array."""
        self._rekey(name, name, 0)
        self._set_index_parameter(name, True)

    def set_index(self, value) -> str | None:
        """The Index property: makes a control an element of a control array
        (any whole number 0 - 32767), changes its place in the array, or
        (empty) makes a lone element a plain control again."""
        if len(self.selection) != 1:
            return "Set the Index of one control at a time"
        key = self.selection[0]
        control_def = self.form_def.control(key)
        name = control_def.name
        if value in (None, ""):
            if control_def.index is None:
                return None
            if len(self.form_def.elements(name)) > 1:
                return (f"Other controls are named '{name}': rename or delete them before "
                        "removing this one's Index")
            before = self._snapshot()
            self._set_index_parameter(name, False)
            self._rekey(key, name, None)
        else:
            try:
                index = int(value)
            except (TypeError, ValueError):
                return f"Index must be a whole number, not '{value}'"
            if not 0 <= index <= 32767:
                return "Index must be from 0 to 32767"
            if index == control_def.index:
                return None
            if self.form_def.control(control_key(name, index)) is not None:
                return f"'{control_key(name, index)}' already exists"
            before = self._snapshot()
            if control_def.index is None:
                self._set_index_parameter(name, True)
            self._rekey(key, name, index)
        self._commit(before)
        self.selectionChanged.emit()
        return None

    def _paste_identity(self, original: ControlDef) -> tuple[str, int | None]:
        """(name, index) for a pasted copy. A copy of a control whose name is
        taken joins that name's control array (VB asks first when that makes
        a new array); otherwise it gets a new name."""
        name = original.name
        others = self.form_def.elements(name)
        if not others and is_identifier(name):
            return name, original.index
        if others and others[0].type == original.type and is_identifier(name):
            if others[0].index is not None or self.ask_create_array(name):
                if others[0].index is None:
                    self._make_array(name)
                return name, self._next_index(name)
        prefix = NAME_PREFIX.get(original.type, original.type)
        return self.unique_name(prefix), None

    def _rename_form_in_code(self, old: str, new: str) -> None:
        from ..formfile import rename_form_class

        self.document.replace_text(rename_form_class(self.document.text, old, new))
        self.formRenamed.emit(old, new)

    # -- Format menu -------------------------------------------------------------------------------------------
    def _selected_rects(self):
        return [(n, self.parent_rect(n)) for n in self.selection if not self.is_menu(n)]

    def align(self, how: str) -> None:
        if len(self.selection) < 2 or self.menu_selected():
            return
        ref = self.parent_rect(self.selection[-1])
        for name, rect in self._selected_rects()[:-1]:
            if how == "left":
                rect.moveLeft(ref.left())
            elif how == "right":
                rect.moveRight(ref.right())
            elif how == "center":
                rect.moveLeft(ref.center().x() - rect.width() // 2)
            elif how == "top":
                rect.moveTop(ref.top())
            elif how == "bottom":
                rect.moveBottom(ref.bottom())
            elif how == "middle":
                rect.moveTop(ref.center().y() - rect.height() // 2)
            elif how == "grid":
                rect.moveTopLeft(QPoint(snap(rect.x()), snap(rect.y())))
            self.controls[name]._widget.setGeometry(rect)
        self.commit_geometry(self.selection)

    def make_same_size(self, how: str) -> None:
        if len(self.selection) < 2:
            return
        ref = self.parent_rect(self.selection[-1])
        for name, rect in self._selected_rects()[:-1]:
            if how in ("width", "both"):
                rect.setWidth(ref.width())
            if how in ("height", "both"):
                rect.setHeight(ref.height())
            self.controls[name]._widget.setGeometry(rect)
        self.commit_geometry(self.selection)

    def center_in_form(self, horizontal: bool) -> None:
        if not self.selection or self.menu_selected():
            return
        rects = self._selected_rects()
        bounds = QRect(rects[0][1])
        for _, rect in rects[1:]:
            bounds = bounds.united(rect)
        parent = self.form_def.control(self.selection[0]).parent
        container = self._container_widget(parent).rect()
        dx = container.center().x() - bounds.center().x() if horizontal else 0
        dy = 0 if horizontal else container.center().y() - bounds.center().y()
        for name, rect in rects:
            self.controls[name]._widget.move(rect.x() + dx, rect.y() + dy)
        self.commit_geometry(self.selection)

    def nudge(self, dx: int, dy: int, resize: bool = False) -> None:
        if self.menu_selected():
            return
        for name, rect in self._selected_rects():
            if resize:
                if self.controls[name].TypeName in ("Timer", "Line"):
                    continue
                rect.setWidth(max(rect.width() + dx, 4))
                rect.setHeight(max(rect.height() + dy, 4))
            else:
                rect.translate(dx, dy)
            self.controls[name]._widget.setGeometry(rect)
        self.commit_geometry(self.selection)

    def z_order(self, front: bool) -> None:
        """Bring to Front / Send to Back: set ZIndex just above / below the
        other controls in the same container (the runtime ZOrder method)."""
        if not self.selection:
            return
        before = self._snapshot()
        for name in self.selection:
            control = self.controls[name]
            if not control._stackable():  # e.g. a Timer
                continue
            control.ZOrder(0 if front else 1)
            self.form_def.control(name).props["ZIndex"] = control.ZIndex
        self._commit(before)

    # -- context menu --------------------------------------------------------------------------------------------
    def show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        target = self.form_def.control(self.selection[-1]).name if self.selection else "Form"
        event = self.controls[self.selection[-1]].DefaultEvent if self.selection else \
            Form.DefaultEvent

        def add(text, slot, enabled=True):
            action = QAction(text, menu)
            action.setEnabled(enabled)
            action.triggered.connect(slot)
            menu.addAction(action)

        add("View Code", lambda: self.viewCodeRequested.emit(target, event))
        menu.addSeparator()
        add("Cut", self.cut_selection, bool(self.selection))
        add("Copy", self.copy_selection, bool(self.selection))
        add("Paste", self.paste, bool(_clipboard))
        add("Delete", self.delete_selection, bool(self.selection))
        menu.addSeparator()
        add("Bring to Front", lambda: self.z_order(True), bool(self.selection))
        add("Send to Back", lambda: self.z_order(False), bool(self.selection))
        menu.addSeparator()
        add("Align to Grid", lambda: self._align_to_grid(), bool(self.selection))
        menu.addSeparator()
        add("Menu Editor…", self.show_menu_editor)
        menu.exec(global_pos)

    # -- lines -------------------------------------------------------------------------------------------------
    def snap_anchor(self, key: str) -> QPoint:
        """The point of a control that snaps to the grid when it's moved: its
        top-left corner, or a Line's start."""
        if self.is_line(key):
            control = self.controls[key]
            return QPoint(control.X1, control.Y1)
        return self.parent_rect(key).topLeft()

    def is_line(self, key: str) -> bool:
        control_def = self.form_def.control(key)
        return control_def is not None and control_def.type == "Line"

    def line_points(self, key: str) -> tuple[QPoint, QPoint]:
        """A Line's two ends on the canvas."""
        return self.line_point(key, "p1"), self.line_point(key, "p2")

    def line_point(self, key: str, end: str) -> QPoint:
        """One end of a Line ("p1" or "p2") on the canvas."""
        control = self.controls[key]
        x, y = (control.X1, control.Y1) if end == "p1" else (control.X2, control.Y2)
        return control._widget.parentWidget().mapTo(self.canvas, QPoint(x, y))

    def move_line_point(self, key: str, end: str, canvas_pos: QPoint,
                        use_grid: bool = True) -> None:
        """Drag one end of a Line (committed with commit_geometry)."""
        control = self.controls[key]
        point = control._widget.parentWidget().mapFrom(self.canvas, canvas_pos)
        if use_grid:  # the grid of the line's container
            point = QPoint(snap(point.x()), snap(point.y()))
        names = ("X1", "Y1") if end == "p1" else ("X2", "Y2")
        for name, value in zip(names, (point.x(), point.y())):
            setattr(control, name, value)  # the widget follows
        self.overlay.update()

    def line_at(self, pos: QPoint) -> str | None:
        """The Line drawn near a canvas position (the top one), if any."""
        for control_def in reversed(self.form_def.controls):
            if control_def.type != "Line" or control_def.key not in self.controls:
                continue
            p1, p2 = self.line_points(control_def.key)
            width = self.controls[control_def.key].BorderWidth
            if _distance(pos, p1, p2) <= max(4, width / 2 + 2):
                return control_def.key
        return None

    # -- menus -------------------------------------------------------------------------------------------------
    def is_menu(self, key: str) -> bool:
        control_def = self.form_def.control(key)
        return control_def is not None and control_def.type == "Menu"

    def menu_selected(self) -> bool:
        return any(self.is_menu(key) for key in self.selection)

    def _menu_children(self, key: str | None) -> list[ControlDef]:
        return [c for c in self.form_def.controls if c.type == "Menu" and c.parent == key]

    def menu_bar_keys(self) -> list[str]:
        """The menus shown on the menu bar (visible top-level menus)."""
        return [c.key for c in self._menu_children(None) if c.props.get("Visible", True)]

    def menu_rect(self, key: str) -> QRect:
        """Where a menu bar menu is drawn on the canvas."""
        rects = chrome.menu_item_rects(self.form_canvas_rect(), self.frame_info())
        return rects[self.menu_bar_keys().index(key)]

    def menu_at(self, pos: QPoint) -> str | None:
        """The menu bar menu at a canvas position."""
        rects = chrome.menu_item_rects(self.form_canvas_rect(), self.frame_info())
        return next((key for key, rect in zip(self.menu_bar_keys(), rects)
                     if rect.contains(pos)), None)

    def menu_popup(self, key: str) -> QMenu | None:
        """The drop-down of a menu bar menu, as it will look; choosing an item
        opens its Click code. None if the menu has no items."""
        if not self._menu_children(key):
            return None
        popup = QMenu(self)
        self._fill_menu_popup(popup, key)
        return popup

    def _fill_menu_popup(self, popup: QMenu, key: str) -> None:
        for item in self._menu_children(key):
            props = item.props
            caption = props.get("Caption", "")
            if caption == "-":
                popup.addSeparator()
                continue
            text = caption + ("" if props.get("Visible", True) else "  (hidden)")
            if self._menu_children(item.key):
                self._fill_menu_popup(popup.addMenu(text), item.key)
                continue
            shortcut = props.get("Shortcut", "")
            action = popup.addAction(text + (f"\t{shortcut}" if shortcut else ""))
            action.setCheckable(bool(props.get("Checked")))
            action.setChecked(bool(props.get("Checked")))
            action.triggered.connect(
                lambda _=False, name=item.name: self.viewCodeRequested.emit(name, "Click"))

    def show_menu_popup(self, key: str, global_pos: QPoint) -> None:
        self.select([key])
        popup = self.menu_popup(key)
        if popup is None:  # a menu without items: its Click code
            self.viewCodeRequested.emit(self.form_def.control(key).name, "Click")
            return
        popup.exec(global_pos)
        popup.deleteLater()

    def menu_entries(self) -> list[menueditor.MenuEntry]:
        return menueditor.entries_from(self.form_def)

    def _names_besides_menus(self) -> set[str]:
        return {c.name for c in self.form_def.controls if c.type != "Menu"} | \
            {self.form_def.class_name}

    def show_menu_editor(self) -> None:
        """Tools > Menu Editor (Ctrl+E)."""
        dialog = menueditor.MenuEditorDialog(self.menu_entries(), self._names_besides_menus(),
                                             self)
        if dialog.exec():
            self.set_menus(dialog.result_entries())

    def set_menus(self, entries: list[menueditor.MenuEntry]) -> str | None:
        """Replace the form's menus (the Menu Editor's OK). Renamed menus take
        their event handlers along, and handlers get or lose Index when a menu
        becomes a control array or stops being one."""
        error = menueditor.validate(entries, self._names_besides_menus())
        if error:
            return error
        before = self._snapshot()
        old = {c.key: c for c in self.form_def.controls if c.type == "Menu"}
        old_names = {c.name for c in old.values()}
        new_defs = menueditor.menu_defs(entries)
        new_names = {c.name for c in new_defs}
        # Renames: every element of an old name went to one new, unused name
        targets: dict[str, set[str]] = {}
        for entry in entries:
            if entry.original in old:
                targets.setdefault(old[entry.original].name, set()).add(entry.name)
        renamed = {}
        for old_name, names in targets.items():
            new_name = next(iter(names))
            if len(names) == 1 and new_name != old_name and new_name not in old_names and \
                    old_name not in new_names:
                renamed[new_name] = old_name
                from ..formfile import rename_control_references

                self.document.replace_text(
                    rename_control_references(self.document.text, old_name, new_name))
        for name in new_names:
            was_array = any(c.index is not None for c in old.values()
                            if c.name == renamed.get(name, name))
            is_array = any(c.index is not None for c in new_defs if c.name == name)
            existed = renamed.get(name, name) in old_names
            if (existed and was_array != is_array) or (not existed and is_array):
                self.document.replace_text(set_index_parameter(
                    self.document.text, name, CONTROL_TYPES["Menu"].Events, is_array))
        self.form_def.controls = [c for c in self.form_def.controls
                                  if c.type != "Menu"] + new_defs
        self.selection = []
        self.load_def(self.form_def)
        self._commit(before)
        return None

    def _align_to_grid(self) -> None:
        for name, rect in self._selected_rects():
            rect.moveTopLeft(QPoint(snap(rect.x()), snap(rect.y())))
            self.controls[name]._widget.setGeometry(rect)
        self.commit_geometry(self.selection)
