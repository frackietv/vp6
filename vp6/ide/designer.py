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

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QGuiApplication, QPainter, QPalette, QPen,
                           QPixmap)
from PySide6.QtWidgets import QApplication, QMenu, QScrollArea, QVBoxLayout, QWidget

from .. import appearance, colors
from .._props import normalize
from ..controls import CONTROL_TYPES, Control
from ..form import Form
from ..formfile import ControlDef, FormDef
from . import chrome
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
    "VScrollBar": "VScroll", "Timer": "Timer",
}

_clipboard: list[ControlDef] = []


def snap(value: int) -> int:
    return int(round(value / GRID)) * GRID


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

    def _handle_at(self, pos: QPoint) -> tuple[str | None, str] | None:
        d = self.d
        if not d.selection:
            for key, rect in self._form_handles().items():
                if rect.adjusted(-2, -2, 2, 2).contains(pos):
                    return None, key
        elif len(d.selection) == 1 and d.controls[d.selection[0]].TypeName != "Timer":
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
        form_rect = d.form_canvas_rect()

        if d.tool is not None:
            if form_rect.contains(pos):
                self._drag = {"kind": "draw", "start": pos, "pos": pos, "moved": False,
                              "container": d.container_at(pos)}
            return

        handle = self._handle_at(pos)
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
                      "orig": {n: d.parent_rect(n) for n in d.selection}}

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
            primary = drag["orig"][drag["primary"]]
            if event.modifiers() & Qt.AltModifier:
                dx, dy = delta.x(), delta.y()
            else:
                dx = snap(primary.x() + delta.x()) - primary.x()
                dy = snap(primary.y() + delta.y()) - primary.y()
            for name, rect in drag["orig"].items():
                d.controls[name]._widget.move(rect.x() + dx, rect.y() + dy)
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
                             drag["start"])
        elif kind == "band" and drag["moved"]:
            band = QRect(drag["start"], event.position().toPoint()).normalized()
            names = [c.name for c in d.form_def.controls
                     if c.parent == drag["container"] and band.intersects(d.canvas_rect(c.name))]
            d.select((d.selection if drag["additive"] else []) + names)
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
        if name is not None:
            d.viewCodeRequested.emit(name, d.controls[name].DefaultEvent)
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
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            lambda *_: QTimer.singleShot(0, self.refresh_scheme))

    # -- color schemes -------------------------------------------------------------------------
    def set_project_scheme(self, scheme: int) -> None:
        self.project_scheme = scheme
        self.refresh_scheme()

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
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
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
            self.statusMessage.emit(f"{control_def.name}: {exc}")
            control = cls(parent, Name=control_def.name)
        self.controls[control_def.name] = control
        self._prepare_widget(control)
        control._widget.show()
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
            title_dark=appearance.system_is_dark(), form_dark=form._is_dark())

    def _layout_form(self) -> None:
        """Place the form below the frame's title bar (its height depends on
        the frame style and BorderStyle)."""
        title, border = chrome.metrics(self.frame_style(), self.frame_info())
        position = QPoint(MARGIN + border, MARGIN + border + title)
        if self.form_widget().pos() != position:
            self.form_widget().move(position)
            self.overlay.update()
        self.update_canvas_size()

    def _on_ide_theme_changed(self) -> None:
        self.refresh_scheme()  # also redraws the grid (it can be turned off)
        self._layout_form()

    def update_canvas_size(self) -> None:
        frame = self.canvas.form_frame_rect()
        size = QSize(frame.right() + MARGIN + HANDLE, frame.bottom() + MARGIN + HANDLE)
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
        form_widget = self.form_widget()
        widget = form_widget.childAt(form_widget.mapFrom(self.canvas, pos))
        while widget is not None and widget is not form_widget:
            control = getattr(widget, "_vp_control", None)  # set on each control's widget
            if control is not None and self.controls.get(control.Name) is control:
                return control.Name
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
        self.selection = seen
        self.overlay.update()
        self.selectionChanged.emit()

    def select_by_name(self, name: str) -> None:
        self.select([] if name == self.form_def.class_name else [name])

    def selected_objects(self) -> list:
        if not self.selection:
            return [self.form]
        return [self.controls[n] for n in self.selection]

    def object_name(self, obj) -> str:
        return self.form_def.class_name if obj is self.form else obj.Name

    def all_objects(self) -> list[tuple[str, str]]:
        return [(self.form_def.class_name, "Form")] + \
            [(c.name, c.type) for c in self.form_def.controls]

    def set_tool(self, tool: str | None) -> None:
        self.tool = tool
        self.overlay.setCursor(Qt.CrossCursor if tool else Qt.ArrowCursor)

    # -- committing changes --------------------------------------------------------------------------
    def _snapshot(self) -> FormDef:
        return copy.deepcopy(self.form_def)

    def _commit(self, before: FormDef) -> None:
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
        for name in names:
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
                       click_pos: QPoint | None = None) -> str:
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
        if "Width" in cls._specs:
            props.update(Width=width, Height=height)
        for text_prop in ("Caption", "Text"):
            if text_prop in cls._specs and cls._specs[text_prop].always:
                props[text_prop] = name
        if "TabIndex" in cls._specs:
            props["TabIndex"] = sum(1 for c in self.form_def.controls
                                    if "TabIndex" in CONTROL_TYPES[c.type]._specs)

        before = self._snapshot()
        control_def = ControlDef(type_name, name, container, props)
        self.form_def.controls.append(control_def)
        self._instantiate(control_def)
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
                result.add(control_def.name)
        return [c.name for c in self.form_def.controls if c.name in result]

    def delete_selection(self) -> None:
        if not self.selection:
            return
        before = self._snapshot()
        doomed = set(self._descendants(self.selection))
        self.form_def.controls = [c for c in self.form_def.controls if c.name not in doomed]
        for name in self.selection:  # deleting a container deletes its children
            widget = self.controls[name]._widget
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for name in doomed:
            control = self.controls.pop(name)
            if control in self.form._controls:
                self.form._controls.remove(control)
        self.select([])
        self._commit(before)

    # -- clipboard --------------------------------------------------------------------------------------
    def copy_selection(self) -> None:
        if not self.selection:
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
        taken = {c.name for c in self.form_def.controls}
        renamed: dict[str, str] = {}
        pasted_roots = []
        clipboard_names = {c.name for c in _clipboard}
        for original in _clipboard:
            control_def = copy.deepcopy(original)
            new_name = control_def.name
            if new_name in taken or not is_identifier(new_name):
                new_name = self.unique_name(NAME_PREFIX.get(control_def.type, control_def.type),
                                            taken)
            renamed[control_def.name] = new_name
            is_root = control_def.parent is None or control_def.parent not in clipboard_names
            if is_root:
                control_def.parent = target
                pasted_roots.append(new_name)
                if new_name != original.name:
                    control_def.props["Left"] = control_def.props.get("Left", 0) + GRID
                    control_def.props["Top"] = control_def.props.get("Top", 0) + GRID
            else:
                control_def.parent = renamed[control_def.parent]
            for text_prop in ("Caption", "Text"):
                if control_def.props.get(text_prop) == original.name:
                    control_def.props[text_prop] = new_name
            control_def.name = new_name
            taken.add(new_name)
            self.form_def.controls.append(control_def)
            self._instantiate(control_def)
        self.overlay.raise_()
        self.select(pasted_roots)
        self._commit(before)

    def select_all(self) -> None:
        self.select([c.name for c in self.form_def.controls if c.parent is None])

    # -- properties ----------------------------------------------------------------------------------------
    def set_property(self, prop: str, value) -> str | None:
        """Set a property on all selected objects. Returns an error message
        or None."""
        if prop == "Name":
            return self.rename(value)
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
                    props = self.form_def.control(obj.Name).props
                    props[prop] = stored
                    if prop in ("AutoSize", "Picture", "Caption") and obj._widget is not None:
                        # AutoSize may have changed the size
                        props.update(Width=obj._widget.width(), Height=obj._widget.height())
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
        old_name = self.selection[0] if self.selection else self.form_def.class_name
        if new_name == old_name:
            return None
        if new_name in self.controls or new_name == self.form_def.class_name:
            return f"The name '{new_name}' is already used"
        before = self._snapshot()
        if not self.selection:
            self.form_def.class_name = new_name
            self._rename_form_in_code(old_name, new_name)
            self.document.set_form_def(self.form_def)
            self._undo.append(before)
            self.designChanged.emit()
            self.selectionChanged.emit()
            return None
        from ..formfile import rename_control_references

        self.document.replace_text(
            rename_control_references(self.document.text, old_name, new_name))
        for control_def in self.form_def.controls:
            if control_def.name == old_name:
                control_def.name = new_name
            if control_def.parent == old_name:
                control_def.parent = new_name
        control = self.controls.pop(old_name)
        control.__dict__["_name"] = new_name
        self.controls[new_name] = control
        self.selection = [new_name]
        self._commit(before)
        self.selectionChanged.emit()
        return None

    def _rename_form_in_code(self, old: str, new: str) -> None:
        from ..formfile import rename_form_class

        self.document.replace_text(rename_form_class(self.document.text, old, new))
        self.formRenamed.emit(old, new)

    # -- Format menu -------------------------------------------------------------------------------------------
    def _selected_rects(self):
        return [(n, self.parent_rect(n)) for n in self.selection]

    def align(self, how: str) -> None:
        if len(self.selection) < 2:
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
        if not self.selection:
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
        for name, rect in self._selected_rects():
            if resize:
                if self.controls[name].TypeName == "Timer":
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
        target = self.selection[-1] if self.selection else "Form"
        event = self.controls[target].DefaultEvent if self.selection else Form.DefaultEvent

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
        menu.exec(global_pos)

    def _align_to_grid(self) -> None:
        for name, rect in self._selected_rects():
            rect.moveTopLeft(QPoint(snap(rect.x()), snap(rect.y())))
            self.controls[name]._widget.setGeometry(rect)
        self.commit_geometry(self.selection)
