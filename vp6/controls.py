"""VB6 style intrinsic controls built on Qt widgets.

Events are dispatched by name: a control named ``Command1`` on a form fires
``Command1_Click`` if the form defines it. Handlers may declare fewer
parameters than VB passes (``def Text1_KeyPress(self, KeyAscii)`` or just
``def Text1_KeyPress(self)``).
"""

from __future__ import annotations

import html
import keyword
import os
import re
import sys
import time

from PySide6.QtCore import (QByteArray, QDate, QEvent, QFileInfo, QItemSelectionModel, QLocale,
                            QMimeData, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTime,
                            QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QCursor, QDesktopServices,
                           QDrag, QFont, QFontDatabase, QIcon, QKeyEvent, QKeySequence, QPainter,
                           QPainterPath,
                           QPalette, QPen, QPixmap, QShortcut, QStandardItem, QStandardItemModel,
                           QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextDocumentFragment, QTextFormat)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QBoxLayout, QCheckBox, QColorDialog, QComboBox, QDialog,
    QFileDialog, QFontDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QRubberBand, QScrollArea, QScrollBar, QSizeGrip, QSlider, QStackedLayout, QStyle,
    QStyledItemDelegate, QStyleOptionTabWidgetFrame, QStyleOptionViewItem, QTableWidget,
    QTableWidgetItem, QTableWidgetSelectionRange, QTabWidget, QTextEdit, QToolBar, QToolButton,
    QTreeView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import colors
from ._props import P, PropertyHost, _make_property, enum_choices
from .app import call_handler

# Parameters passed to each event handler; used by the IDE to generate stubs.
EVENT_ARGS = {
    "Click": "", "DblClick": "", "Change": "", "Scroll": "", "Timer": "",
    "GotFocus": "", "LostFocus": "",
    "MouseDown": "Button, Shift, X, Y", "MouseUp": "Button, Shift, X, Y",
    "MouseMove": "Button, Shift, X, Y",
    "KeyDown": "KeyCode, Shift", "KeyUp": "KeyCode, Shift", "KeyPress": "KeyAscii",
    "Initialize": "", "Load": "", "QueryUnload": "UnloadMode", "Unload": "", "Activate": "",
    "Deactivate": "",
    "Resize": "", "Moved": "", "LinkClick": "URL",
    "NodeClick": "Node", "Expand": "Node", "Collapse": "Node", "NodeCheck": "Node",
    "UpClick": "", "DownClick": "", "PanelClick": "Panel", "PanelDblClick": "Panel",
    "BeforeClick": "", "ButtonClick": "Button",
    "ItemClick": "Item", "ColumnClick": "ColumnHeader", "ItemCheck": "Item",
    "SelChange": "", "Highlight": "Line, Text, State", "GutterClick": "Line",
    "ProtectedEdit": "Line",
    "EnterCell": "", "LeaveCell": "", "RowColChange": "", "BeforeEdit": "Row, Col",
    "ValidateEdit": "Row, Col, Text", "AfterEdit": "Row, Col", "CellButtonClick": "Row, Col",
    "DockChange": "", "Close": "", "Validate": "",
    "DragDrop": "Source, X, Y", "DragOver": "Source, X, Y, State",
    "OLEDragDrop": "Data, Effect, Button, Shift, X, Y",
    "OLEDragOver": "Data, Effect, Button, Shift, X, Y, State",
}

MOUSE_EVENTS = ("MouseDown", "MouseMove", "MouseUp")
KEY_EVENTS = ("KeyDown", "KeyPress", "KeyUp")
FOCUS_EVENTS = ("GotFocus", "LostFocus")

_QT_TO_VP_KEYS = {
    Qt.Key_Backspace: 8, Qt.Key_Tab: 9, Qt.Key_Return: 13, Qt.Key_Enter: 13,
    Qt.Key_Shift: 16, Qt.Key_Control: 17, Qt.Key_Meta: 17, Qt.Key_Alt: 18,
    Qt.Key_Pause: 19, Qt.Key_CapsLock: 20, Qt.Key_Escape: 27, Qt.Key_Space: 32,
    Qt.Key_PageUp: 33, Qt.Key_PageDown: 34, Qt.Key_End: 35, Qt.Key_Home: 36,
    Qt.Key_Left: 37, Qt.Key_Up: 38, Qt.Key_Right: 39, Qt.Key_Down: 40,
    Qt.Key_Insert: 45, Qt.Key_Delete: 46,
}
for _i in range(12):
    _QT_TO_VP_KEYS[Qt.Key_F1 + _i] = 112 + _i


def vp_key_code(key: int) -> int:
    if key in _QT_TO_VP_KEYS:
        return _QT_TO_VP_KEYS[key]
    if Qt.Key_0 <= key <= Qt.Key_9 or Qt.Key_A <= key <= Qt.Key_Z:
        return int(key)
    return int(key) & 0xFFFF


def vp_shift(modifiers) -> int:
    result = 0
    if modifiers & Qt.ShiftModifier:
        result |= 1
    if modifiers & (Qt.ControlModifier | Qt.MetaModifier):
        result |= 2
    if modifiers & Qt.AltModifier:
        result |= 4
    return result


def vp_buttons(buttons) -> int:
    result = 0
    if buttons & Qt.LeftButton:
        result |= 1
    if buttons & Qt.RightButton:
        result |= 2
    if buttons & Qt.MiddleButton:
        result |= 4
    return result


def strip_mnemonic(caption: str) -> str:
    """'&File' -> 'File', 'Save && Exit' -> 'Save & Exit'."""
    return caption.replace("&&", "\0").replace("&", "").replace("\0", "&")


def parse_mnemonic(caption: str) -> tuple[str, int]:
    """(the text shown, the index of its access key letter or -1): '&Name' ->
    ('Name', 0); '&&' is a literal & and a trailing & nothing."""
    text, index, i = [], -1, 0
    while i < len(caption):
        char = caption[i]
        if char == "&" and i + 1 < len(caption):
            if caption[i + 1] == "&":
                text.append("&")
            elif index < 0 and not caption[i + 1].isspace():
                index = len(text)
                text.append(caption[i + 1])
            else:
                text.append(caption[i + 1])
            i += 2
            continue
        if char != "&":
            text.append(char)
        i += 1
    return "".join(text), index


# The access key's modifiers: Alt (Windows, Linux); on macOS Control+Option, as
# Option+letter types accented letters there (Qt.META is the Control key on macOS)
ACCESS_KEY_MODIFIERS = (Qt.META | Qt.ALT) if sys.platform == "darwin" else Qt.ALT


def access_key_sequence(letter: str) -> QKeySequence | None:
    """The key sequence of a Label's access key letter (a letter or digit)."""
    letter = letter.upper()
    if not ("A" <= letter <= "Z" or "0" <= letter <= "9"):
        return None
    return QKeySequence(ACCESS_KEY_MODIFIERS | Qt.Key(ord(letter)))  # (Qt's key codes: ASCII)


def resolve_path(owner, path: str) -> str:
    if not path or os.path.isabs(path):
        return path
    base = owner._base_dir() if hasattr(owner, "_base_dir") else os.getcwd()
    return os.path.join(base, path)


# --- property groups ------------------------------------------------------------

def _geometry(width, height):
    return (P("Left", "int", 0, always=True,
              description="Distance from the container's left edge, in pixels"),
            P("Top", "int", 0, always=True,
              description="Distance from the container's top edge, in pixels"),
            P("Width", "int", width, always=True, description="Width in pixels"),
            P("Height", "int", height, always=True, description="Height in pixels"))


_FONT = (
    P("FontName", "font", None, description="Font family; unset = the container's font"),
    P("FontSize", "int", None, description="Font size in points; unset = the container's"),
    P("FontBold", "bool", False, description="Bold text"),
    P("FontItalic", "bool", False, description="Italic text"),
    P("FontUnderline", "bool", False, description="Underlined text"),
)
_COLORS = (P("BackColor", "color", None, description="Background color; unset = the default"),
           P("ForeColor", "color", None, description="Text color; unset = the default"))
_COMMON = (P("Enabled", "bool", True, description="Whether the control responds to the user"),
           P("Visible", "bool", True, description="Whether the control is shown at run time"),
           P("TabIndex", "int", 0, description="Position in the Tab key order"),
           P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
           P("Tag", "str", "", description="Free for your own use"),
           P("ZIndex", "int", 0,
             description="Stacking order among controls in the same container: higher "
                         "values are drawn on top. Equal values keep creation order "
                         "(later on top)."))
_ALIGNMENT = enum_choices("Left Justify", "Right Justify", "Center")
_QT_ALIGN = {0: Qt.AlignLeft, 1: Qt.AlignRight, 2: Qt.AlignHCenter}


# --- Validate: a control's value checked before the focus leaves it ------------------------------

# Focus events not to report (the focus going back after a Validate cancelled):
# (id(control), "GotFocus" / "LostFocus"); and the control whose Click a cancelled
# Validate holds back (the button clicked away to), until when
_VALIDATION: dict = {"skip": set(), "blocked": None}


def control_of_widget(widget) -> "Control | None":
    """The VP6 control a widget belongs to (it or a widget it is in), or None."""
    while widget is not None:
        control = getattr(widget, "_vp_control", None)
        if control is not None:
            return control
        widget = widget.parentWidget()
    return None


def outer_control(control: "Control | None") -> "Control | None":
    """A control on a user control's surface stands for the user control."""
    while control is not None:
        owner = getattr(control._form, "__dict__", {}).get("_owner")
        if owner is None:
            return control
        control = owner
    return None


class _EventBridge(QObject):
    """Forwards Qt events of a control's widget(s) to the control."""

    def __init__(self, control: "Control", parent: QObject):
        super().__init__(parent)
        self._control = control

    def eventFilter(self, watched, event):
        try:
            return bool(self._control._on_qt_event(watched, event))
        except RuntimeError:  # widget already deleted
            return False


class Control(PropertyHost):
    """Base class of all controls."""

    TypeName = "Control"
    DefaultEvent = "Click"
    Events: tuple[str, ...] = ()
    DefaultSize = (97, 33)
    IsContainer = False
    # Controls whose widget has no native click signal get Click/DblClick
    # synthesized from mouse events.
    _synthesize_click = False
    _qss_type = "QWidget"
    InToolbox = True  # Menu is designed with the Menu Editor instead

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.setdefault("_values", {})
        self.__dict__["_name"] = Name
        self.__dict__["_index"] = None  # set when it becomes an element of a ControlArray
        self.__dict__["_loaded_at_runtime"] = False  # created by ControlArray.Load
        self.__dict__["Parent"] = parent
        self._form = parent._owner_form()
        self._design_mode = getattr(self._form, "_design_mode", False)
        self._key_resend = False
        self._widget = None
        self._bridge = None
        self._build_widget()
        self._init_values(props)
        self._form._register_control(self)
        if self._stackable():
            self._restack()  # a new widget starts on top; put it where ZIndex says

    # -- identity ------------------------------------------------------------
    @property
    def Name(self) -> str:
        return self._name

    @property
    def Index(self) -> int | None:
        """The element's number in a control array; None for other controls."""
        return self._index

    @Index.setter
    def Index(self, value):
        raise AttributeError(f"{self.TypeName} '{self._name}': Index can only be set in the "
                             "designer (or by assigning to an element of a ControlArray)")

    @property
    def Container(self):
        """The form or container control (Frame, PictureBox, DockPanel) it is
        on. Setting it moves the control there at run time, as VB's ``Set
        Command1.Container = Frame1``: its Left and Top stay, now in the new
        container (option buttons join the new container's group)."""
        return self.Parent

    @Container.setter
    def Container(self, value):
        form = self._form
        if value is not form and not (isinstance(value, Control) and value.IsContainer and
                                      value._form is form):
            raise ValueError(f"{self.TypeName} '{self.Name}': the Container must be its form "
                             f"or a container control on it (a Frame, PictureBox or "
                             f"DockPanel), not {value!r}")
        if self._widget is None:
            raise TypeError(f"{self.TypeName} '{self.Name}' can't be moved to a container")
        inside = value
        while isinstance(inside, Control):
            if inside is self:
                raise ValueError(f"{self.TypeName} '{self.Name}' can't go into itself or into "
                                 f"a control on it")
            inside = inside.Parent
        if value is self.Parent:
            return
        widget = self._widget
        shown = not widget.isHidden()
        geometry = widget.geometry()
        self.__dict__["Parent"] = value
        widget.setParent(self._parent_widget())
        widget.setGeometry(geometry)  # (the same Left and Top, in the new container)
        if shown:
            widget.show()
        if self._stackable():
            self._restack()  # its place among the new container's controls
        if "Align" in self._specs and self._values.get("Align"):
            form._layout_aligned()  # (it was docked to the form, or is now)
        form._apply_tab_order()

    def __repr__(self):
        index = "" if self._index is None else f"({self._index})"
        return f"<{self.TypeName} {self._name or '?'}{index}>"

    def __setattr__(self, name, value):
        # VB error 438 "Object doesn't support this property or method" for
        # misspelled properties like Command1.Captoin = "x".
        if name[:1].isupper() and not hasattr(type(self), name) and name not in self.__dict__:
            raise AttributeError(
                f"{self.TypeName} '{self._name}' doesn't support property '{name}'")
        object.__setattr__(self, name, value)

    # -- widget management ---------------------------------------------------------
    def _owner_form(self):
        return self._form

    def _container_widget(self) -> QWidget:
        return self._widget

    def _fill_widget(self) -> QWidget:
        """The widget a form shown in this container (Form.ShowIn) follows."""
        return self._container_widget()

    def _fill_rect(self, designed: QSize) -> QRect:
        """Where a filling form goes; ``designed`` is the form's own size."""
        return self._container_widget().contentsRect()

    def _base_dir(self) -> str:
        return self._form._base_dir()

    def _parent_widget(self) -> QWidget:
        return self.Parent._container_widget()

    def _create_widget(self, parent: QWidget) -> QWidget | None:
        raise NotImplementedError

    def _build_widget(self) -> None:
        self._widget = self._create_widget(self._parent_widget())
        if self._widget is None:
            return
        self._widget._vp_control = self
        self._form._style_widget(self._widget)  # the form's light/dark scheme
        self._bridge = _EventBridge(self, self._widget)
        for target in self._event_targets():
            target.installEventFilter(self._bridge)
            target.setMouseTracking(True)
            if "DragDrop" in self.Events:
                target.setAcceptDrops(True)  # (drag events come to the filter)
        self._connect_signals()

    def _rebuild_widget(self) -> None:
        """Replace the Qt widget (e.g. TextBox switching to MultiLine) keeping
        all property values."""
        old = self._widget
        geometry = old.geometry() if old is not None else None
        text = self._read_Text() if hasattr(self, "_read_Text") else None
        self._build_widget()
        for spec in self.Properties:
            applier = getattr(self, "_apply_" + spec.name, None)
            if applier is not None and spec.name in self._values:
                applier(self._values[spec.name])
        if geometry is not None:
            self._widget.setGeometry(geometry)
        if text is not None:
            self._apply_Text(text)
        if old is not None:
            old.hide()
            old.setParent(None)
            old.deleteLater()
        if not self._design_mode and self._values.get("Visible", True):
            self._widget.show()
        if self._stackable() and self in self._form._controls:
            self._restack()  # the new widget starts on top
        notify = getattr(self._form, "_control_widget_changed", None)
        if notify:
            notify(self)

    def _event_targets(self) -> list[QWidget]:
        return [self._widget]

    def _connect_signals(self) -> None:
        pass

    def _place_after(self, other: "Control") -> None:
        """Where a control loaded into a control array goes; menus override it."""

    def _dispose(self) -> None:
        """Remove the control's Qt objects (an unloaded control array element)."""
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()
        if self._widget is not None:
            self._widget.hide()
            self._widget.setParent(None)
            self._widget.deleteLater()

    # -- event dispatch ----------------------------------------------------------------
    def _handler(self, event: str):
        if self._design_mode or not self._name:
            return None
        return getattr(self._form, f"{self._name}_{event}", None)

    def _fire(self, event: str, *args):
        if event == "Click" and _VALIDATION["blocked"] is not None:
            blocked, until = _VALIDATION["blocked"]
            if blocked is self:  # (clicked while a Validate kept the focus elsewhere)
                _VALIDATION["blocked"] = None
                if time.monotonic() < until:
                    return None
        handler = self._handler(event)
        if handler is None:
            return None
        if self._index is not None:  # control arrays: Command1_Click(self, Index)
            args = (self._index, *args)
        return call_handler(handler, *args)

    def _on_qt_event(self, watched: QWidget, event: QEvent) -> bool:
        if self._design_mode:
            return False
        etype = event.type()
        if etype in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave, QEvent.Drop) and \
                "DragDrop" in self.Events:
            pos = event.position().toPoint() if etype != QEvent.DragLeave else QPoint()
            if watched is not self._widget:
                pos = watched.mapTo(self._widget, pos)
            return handle_drag_event(self, event, pos)
        if etype == QEvent.MouseButtonPress and self._values.get("DragMode") == 1 and \
                event.button() == Qt.LeftButton:
            self.Drag(1)  # Automatic: pressing drags it (no MouseDown, no Click)
            return True
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove):
            pos = watched.mapTo(self._widget, event.position().toPoint()) \
                if watched is not self._widget else event.position().toPoint()
            shift = vp_shift(event.modifiers())
            if etype == QEvent.MouseButtonPress:
                self._fire("MouseDown", vp_buttons(event.button()), shift, pos.x(), pos.y())
            elif etype == QEvent.MouseButtonRelease:
                self._fire("MouseUp", vp_buttons(event.button()), shift, pos.x(), pos.y())
                if self._synthesize_click and self._widget.rect().contains(pos):
                    self._fire("Click")
            else:
                self._fire("MouseMove", vp_buttons(event.buttons()), shift, pos.x(), pos.y())
        elif etype == QEvent.MouseButtonDblClick:
            self._fire("DblClick")
        elif etype == QEvent.KeyPress:
            return self._on_key_press(watched, event)
        elif etype == QEvent.KeyRelease:
            shift = vp_shift(event.modifiers())
            if self._form._preview_key("KeyUp", vp_key_code(event.key()), shift):
                return True
            self._fire("KeyUp", vp_key_code(event.key()), shift)
        elif etype == QEvent.FocusIn:
            if not self._skip_focus_event("GotFocus"):
                self._fire("GotFocus")
        elif etype == QEvent.FocusOut:
            if not self._skip_focus_event("LostFocus") and not self._validation_cancels():
                self._fire("LostFocus")
        return False

    def _skip_focus_event(self, event: str) -> bool:
        key = (id(self), event)
        if key in _VALIDATION["skip"]:
            _VALIDATION["skip"].discard(key)
            return True
        return False

    def _validation_cancels(self) -> bool:
        """The focus is leaving for another control of the same window: if that
        one's CausesValidation is True, fire Validate; True from it keeps the
        focus here (as if it never left: no LostFocus, no GotFocus there, and
        no Click if it was a button being clicked)."""
        if self._handler("Validate") is None:
            return False
        new = QApplication.focusWidget()
        target = control_of_widget(new)
        if target is None or target is self or self._widget is None or \
                new.window() is not self._widget.window() or \
                not target._values.get("CausesValidation", True):
            return False
        if self._fire("Validate") is not True:
            return False
        skip = _VALIDATION["skip"]
        skip.update({(id(target), "GotFocus"), (id(target), "LostFocus"), (id(self), "GotFocus")})
        _VALIDATION["blocked"] = (target, time.monotonic() + 1.0)

        def back():
            if self._widget is not None:
                self._widget.setFocus()
            skip.difference_update({(id(target), "GotFocus"), (id(target), "LostFocus"),
                                    (id(self), "GotFocus")})

        QTimer.singleShot(0, back)
        return True

    def _on_key_press(self, watched: QWidget, event: QKeyEvent) -> bool:
        if self._key_resend:
            return False
        code, shift = vp_key_code(event.key()), vp_shift(event.modifiers())
        if self._form._preview_key("KeyDown", code, shift):
            return True
        self._fire("KeyDown", code, shift)
        text = event.text()
        if len(text) == 1:
            key_ascii = ord(text)
            if self._form.KeyPreview:
                result = self._form._fire("KeyPress", key_ascii)
                if isinstance(result, int) and not isinstance(result, bool):
                    key_ascii = result
            result = self._fire("KeyPress", key_ascii)
            if isinstance(result, int) and not isinstance(result, bool):
                key_ascii = result
            if key_ascii == 0:
                return True  # KeyAscii = 0 cancels the keystroke
            if key_ascii != ord(text):
                # Handler changed the character (e.g. to upper case): resend it.
                self._key_resend = True
                try:
                    QApplication.sendEvent(watched, QKeyEvent(
                        QEvent.KeyPress, event.key(), event.modifiers(), chr(key_ascii)))
                finally:
                    self._key_resend = False
                return True
        return self._form._handle_default_cancel(self, event)

    # -- common properties -----------------------------------------------------------
    def _read_Left(self):
        return self._widget.x() if self._widget else self._values.get("Left", 0)

    def _read_Top(self):
        return self._widget.y() if self._widget else self._values.get("Top", 0)

    def _read_Width(self):
        return self._widget.width() if self._widget else self._values.get("Width", 0)

    def _read_Height(self):
        return self._widget.height() if self._widget else self._values.get("Height", 0)

    def _apply_Left(self, v):
        if self._widget:
            self._widget.move(v, self._widget.y())

    def _apply_Top(self, v):
        if self._widget:
            self._widget.move(self._widget.x(), v)

    def _apply_Width(self, v):
        if self._widget:
            self._widget.resize(max(v, 1), self._widget.height())

    def _apply_Height(self, v):
        if self._widget:
            self._widget.resize(self._widget.width(), max(v, 1))

    def _apply_Enabled(self, v):
        if self._widget:
            self._widget.setEnabled(v)

    def _apply_Visible(self, v):
        if self._widget and not self._design_mode:
            self._widget.setVisible(v)

    def _apply_ToolTipText(self, v):
        if self._widget:
            self._widget.setToolTip(v)

    def _apply_font(self, _=None):
        if not self._widget:
            return
        # Only explicitly set attributes are resolved; the rest is inherited
        # from the container, so changing the form's font affects controls.
        font = QFont()
        values = self._values
        if values.get("FontName"):
            font.setFamily(values["FontName"])
        if values.get("FontSize"):
            font.setPointSize(values["FontSize"])
        if values.get("FontBold"):
            font.setBold(True)
        if values.get("FontItalic"):
            font.setItalic(True)
        if values.get("FontUnderline"):
            font.setUnderline(True)
        self._widget.setFont(font)

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font

    def _apply_colors(self, _=None):
        if not self._widget:
            return
        back, fore = self._values.get("BackColor"), self._values.get("ForeColor")
        rules = []
        if back is not None:
            rules.append(f"background-color: {colors.to_qcolor(back).name()};")
        if fore is not None:
            rules.append(f"color: {colors.to_qcolor(fore).name()};")
        self._widget.setStyleSheet(
            f"{self._qss_type} {{ {' '.join(rules)} }}" if rules else "")

    _apply_BackColor = _apply_ForeColor = _apply_colors

    # -- methods ---------------------------------------------------------------------
    def SetFocus(self) -> None:
        if self._widget:
            self._widget.setFocus()

    # -- the mouse pointer, dragging ----------------------------------------------------
    def _update_cursor(self, _=None) -> None:
        """MousePointer (and MouseIcon) on its widgets; vpDefault gives them
        their own pointers back (e.g. a TextBox's I-beam)."""
        if self._widget is None or self._design_mode:
            return
        cursor = pointer_cursor(self._values.get("MousePointer", 0),
                                resolve_path(self._form, self._values.get("MouseIcon", "")))
        saved = self.__dict__.setdefault("_saved_cursors", {})
        for widget in self._event_targets() or [self._widget]:
            if cursor is None:
                if widget in saved:
                    had_cursor, own = saved.pop(widget)
                    widget.setCursor(own) if had_cursor else widget.unsetCursor()
            else:
                if widget not in saved:
                    saved[widget] = (widget.testAttribute(Qt.WA_SetCursor), widget.cursor())
                widget.setCursor(cursor)

    _apply_MousePointer = _apply_MouseIcon = _update_cursor

    def _apply_DragMode(self, v):
        pass  # (looked at when the mouse is pressed)

    def Drag(self, Action: int = 1) -> None:
        """VB's Drag: vpBeginDrag (the default) starts dragging the control (call
        it in MouseDown); vpEndDrag drops it where it is; vpCancelDrag stops.
        DragOver and DragDrop fire on what it is dragged over and dropped on."""
        Action = int(Action)
        if Action == 0:
            if _DRAGGING["drag"] is not None:
                QDrag.cancel()
            return
        if Action == 2:
            target = _DRAGGING["target"]
            if _DRAGGING["drag"] is not None:
                _DRAGGING["target"] = None
                if target is not None:
                    target._fire("DragDrop", self, *_DRAGGING["pos"])
                QDrag.cancel()
            return
        if self._design_mode or self._widget is None or _DRAGGING["source"] is not None:
            return
        widget = self._widget
        drag = QDrag(widget)
        mime = QMimeData()
        mime.setData(_VP6_DRAG_MIME, QByteArray(str(id(self)).encode()))
        drag.setMimeData(mime)
        icon = QPixmap(resolve_path(self._form, self._values.get("DragIcon", "")))
        if not icon.isNull():
            drag.setPixmap(icon)
            drag.setHotSpot(QPoint(icon.width() // 2, icon.height() // 2))
        else:  # (an image of the control, see-through, held where it was grabbed)
            image = widget.grab()
            faded = QPixmap(image.size())
            faded.setDevicePixelRatio(image.devicePixelRatio())
            faded.fill(Qt.transparent)
            painter = QPainter(faded)
            painter.setOpacity(0.6)
            painter.drawPixmap(0, 0, image)
            painter.end()
            drag.setPixmap(faded)
            spot = widget.mapFromGlobal(QCursor.pos())
            drag.setHotSpot(spot if widget.rect().contains(spot) else QPoint(0, 0))
        _DRAGGING.update(source=self, drag=drag, target=None)
        try:
            drag.exec(Qt.MoveAction | Qt.CopyAction)
        finally:
            _DRAGGING.update(source=None, drag=None, target=None)

    def Move(self, Left, Top=None, Width=None, Height=None) -> None:
        self.Left = Left
        if Top is not None:
            self.Top = Top
        if Width is not None:
            self.Width = Width
        if Height is not None:
            self.Height = Height

    def Refresh(self) -> None:
        if self._widget:
            self._widget.update()

    def ZOrder(self, Position: int = 0) -> None:
        """0 brings the control to the front, 1 sends it to the back, by setting
        ZIndex just above or below the other controls in the same container."""
        if not self._stackable():
            return
        others = [c.ZIndex for c in self._siblings() if c is not self]
        if not others:
            return
        if Position == 0:
            if self.ZIndex <= max(others):
                self.ZIndex = max(others) + 1
        elif self.ZIndex >= min(others):
            self.ZIndex = min(others) - 1

    # -- stacking (ZIndex) ---------------------------------------------------------------
    def _stackable(self) -> bool:
        return self._widget is not None and "ZIndex" in self._specs

    def _siblings(self) -> list["Control"]:
        """Stackable controls in the same container, in creation order."""
        return [c for c in self._form._controls if c.Parent is self.Parent and c._stackable()]

    def _restack(self) -> None:
        """Order the container's children: higher ZIndex on top, equal values
        in creation order (later on top)."""
        siblings = self._siblings()
        order = sorted(range(len(siblings)),
                       key=lambda i: (siblings[i]._values.get("ZIndex", 0), i))
        for i in order:
            siblings[i]._widget.raise_()

    def _apply_ZIndex(self, v):
        # During construction the control isn't registered yet; __init__
        # restacks once it is.
        if self._stackable() and self in self._form._controls:
            self._restack()


def _container_palette(control: Control) -> None:
    """Containers use the palette for colors, so children don't inherit a
    style sheet."""
    widget = control._widget
    if not widget:
        return
    # Only the roles set here are explicit; everything else keeps following
    # the form (e.g. when its color scheme changes).
    palette = QPalette()
    back, fore = control._values.get("BackColor"), control._values.get("ForeColor")
    if back is not None:
        palette.setColor(QPalette.Window, colors.to_qcolor(back))
    if fore is not None:
        palette.setColor(QPalette.WindowText, colors.to_qcolor(fore))
    widget.setPalette(palette)
    widget.setAutoFillBackground(back is not None)


# --- Label -----------------------------------------------------------------------

_TEXT_FORMATS = {0: Qt.PlainText, 1: Qt.RichText, 2: Qt.MarkdownText}


class Label(Control):
    TypeName = "Label"
    DefaultSize = (97, 25)
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp", "LinkClick")
    _synthesize_click = True
    _qss_type = "QLabel"
    Properties = (
        # TextFormat before Caption: it decides how the Caption is shown
        P("TextFormat", "enum", 0, enum_choices("Plain", "Rich Text", "Markdown"),
          description="Plain: the Caption as it is. Rich Text: HTML (bold, headings, links, "
                      "colors). Markdown: bold, headings, lists and links written the "
                      "Markdown way"),
        P("Caption", "text", "", always=True,
          description="The text; in plain text an & before a letter underlines it, its "
                      "access key (&& shows a literal &)"),
        *_geometry(*DefaultSize),
        P("UseMnemonic", "bool", True,
          description="An & in the Caption marks an access key: Alt+the letter (on macOS "
                      "Control+Option+the letter) focuses the next control in the tab "
                      "order. False: the & is shown as it is"),
        P("Alignment", "enum", 0, _ALIGNMENT, description="Horizontal text alignment"),
        P("AutoSize", "bool", False, description="Resize to fit the text"),
        P("WordWrap", "bool", False, description="Wrap long text onto several lines"),
        P("BorderStyle", "enum", 0, enum_choices("None", "Fixed Single"),
          description="A thin border around the label"),
        P("BackStyle", "enum", 1, enum_choices("Transparent", "Opaque"),
          description="Opaque: the label fills its box (with BackColor, or its container's "
                      "color) and hides what is behind it; Transparent: what is behind it "
                      "(a picture, other controls) shows through, and BackColor is ignored"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        label = QLabel(parent)
        label.setTextFormat(Qt.PlainText)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setOpenExternalLinks(False)  # links go through LinkClick
        return label

    def _connect_signals(self):
        self._widget.linkActivated.connect(self._on_link)

    def _formatted(self) -> bool:
        return self._values.get("TextFormat", 0) in (1, 2)

    def _apply_TextFormat(self, v):
        self._widget.setTextFormat(_TEXT_FORMATS.get(v, Qt.PlainText))
        links = self._formatted() and not self._design_mode
        self._widget.setTextInteractionFlags(
            Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard if links
            else Qt.NoTextInteraction)
        if "Caption" in self._values:
            self._apply_Caption(self._values["Caption"])

    def _apply_Caption(self, v):
        key = None
        if self._formatted():
            self._widget.setText(v)
        elif not self._values.get("UseMnemonic", True):  # the & as it is
            self._widget.setTextFormat(Qt.PlainText)
            self._widget.setText(v)
        else:
            text, index = parse_mnemonic(v)
            if index < 0:
                self._widget.setTextFormat(Qt.PlainText)
                self._widget.setText(text)
            else:  # the access key letter underlined (drawn as rich text)
                self._widget.setTextFormat(Qt.RichText)
                self._widget.setText(
                    '<span style="white-space: pre-wrap">' + html.escape(text[:index]) +
                    f"<u>{html.escape(text[index])}</u>" + html.escape(text[index + 1:]) +
                    "</span>")
                key = access_key_sequence(text[index])
        self._set_access_key(key)
        if self._values.get("AutoSize"):
            self._widget.adjustSize()

    def _apply_UseMnemonic(self, v):
        if "Caption" in self._values:
            self._apply_Caption(self._values["Caption"])

    # -- the access key --------------------------------------------------------------------------
    @property
    def AccessKey(self) -> str:
        """The access key letter of the Caption ("" for none), read-only."""
        if self._formatted() or not self._values.get("UseMnemonic", True):
            return ""
        text, index = parse_mnemonic(self._values.get("Caption", ""))
        return text[index] if index >= 0 else ""

    def _set_access_key(self, sequence) -> None:
        old = self.__dict__.get("_shortcut")
        if old is not None:
            old.setEnabled(False)
            old.setParent(None)
            old.deleteLater()
        self.__dict__["_shortcut"] = None
        if sequence is None or self._design_mode:
            return
        shortcut = QShortcut(sequence, self._form._widget)
        shortcut.setContext(Qt.WindowShortcut)
        shortcut.activated.connect(self._on_access_key)
        self.__dict__["_shortcut"] = shortcut

    def _on_access_key(self) -> None:
        """The access key was pressed: focus the next control in the tab order
        that can take the focus (going round), as in VB."""
        if not (self._widget.isVisible() and self._widget.isEnabled()):
            return
        mine = self._values.get("TabIndex", 0)
        ordered = sorted((c for c in self._form._controls
                          if c is not self and "TabIndex" in c._specs and c._widget is not None),
                         key=lambda c: c._values.get("TabIndex", 0))
        after = [c for c in ordered if c._values.get("TabIndex", 0) > mine]
        before = [c for c in ordered if c._values.get("TabIndex", 0) <= mine]
        for control in after + before:
            widget = control._widget
            if widget.isVisible() and widget.isEnabled() and \
                    widget.focusPolicy() & Qt.TabFocus:
                control.SetFocus()
                return

    def _dispose(self) -> None:
        self._set_access_key(None)
        super()._dispose()

    def _on_link(self, url: str) -> None:
        """A link was clicked: LinkClick(URL), or without a handler, the
        default browser (or mail program) opens it."""
        if self._handler("LinkClick") is not None:
            self._fire("LinkClick", url)
        else:
            QDesktopServices.openUrl(QUrl(url))

    def _apply_Alignment(self, v):
        self._widget.setAlignment(_QT_ALIGN.get(v, Qt.AlignLeft) | Qt.AlignTop)

    def _apply_AutoSize(self, v):
        if v:
            self._widget.adjustSize()

    def _apply_WordWrap(self, v):
        self._widget.setWordWrap(v)

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.Box | QFrame.Plain if v else QFrame.NoFrame)

    def _apply_colors(self, _=None):
        """BackStyle decides the background: Opaque fills it (BackColor, or
        the container's color: the palette it inherits); Transparent leaves
        it unpainted, whatever BackColor says (as in VB)."""
        if not self._widget:
            return
        opaque = self._values.get("BackStyle", 1) == 1
        back = self._values.get("BackColor") if opaque else None
        fore = self._values.get("ForeColor")
        rules = []
        if back is not None:
            rules.append(f"background-color: {colors.to_qcolor(back).name()};")
        elif not opaque:
            rules.append("background: transparent;")
        if fore is not None:
            rules.append(f"color: {colors.to_qcolor(fore).name()};")
        self._widget.setStyleSheet(f"QLabel {{ {' '.join(rules)} }}" if rules else "")
        # (In a Frame the "container's color" is the frame's panel, which the
        # platform draws in its own shade, e.g. lighter on macOS: there an
        # opaque Label without a BackColor keeps that panel instead of the
        # palette's color)
        in_frame = isinstance(self._widget.parentWidget(), QGroupBox)
        self._widget.setAutoFillBackground(opaque and back is None and not in_frame)

    _apply_BackColor = _apply_ForeColor = _apply_BackStyle = _apply_colors


# --- TextBox ------------------------------------------------------------------------

class _TextEditing:
    """What TextBox and RichTextBox share for editors: lines and columns, the
    caret's place on screen, scrolling, undo and redo, AcceptsTab and
    SelChange. A line is a paragraph (it ends where Enter was pressed),
    counted from 0, as are columns; a single-line TextBox has one line."""

    def _editor(self):
        """The multi-line editor (QPlainTextEdit, QTextEdit); None for one line."""
        return None if isinstance(self._widget, QLineEdit) else self._widget

    def _connect_selection(self) -> None:
        self.__dict__["_selection"] = self._selection_range()
        self._widget.cursorPositionChanged.connect(self._on_selection)
        self._widget.selectionChanged.connect(self._on_selection)

    def _selection_range(self) -> tuple[int, int]:
        editor = self._editor()
        if editor is not None:
            cursor = editor.textCursor()
            return cursor.selectionStart(), cursor.selectionEnd()
        line = self._widget
        if line.hasSelectedText():
            return line.selectionStart(), line.selectionEnd()
        return line.cursorPosition(), line.cursorPosition()

    def _on_selection(self, *_):
        selection = self._selection_range()
        if selection != self._selection:
            self.__dict__["_selection"] = selection
            self._fire("SelChange")

    def _apply_AcceptsTab(self, v):
        editor = self._editor()
        if editor is not None:
            editor.setTabChangesFocus(not v)

    # -- lines and columns ------------------------------------------------------------------
    def _caret(self) -> int:
        editor = self._editor()
        return editor.textCursor().position() if editor is not None else \
            self._widget.cursorPosition()

    def _move_caret(self, position: int) -> None:
        editor = self._editor()
        if editor is not None:
            cursor = editor.textCursor()
            cursor.setPosition(position)
            editor.setTextCursor(cursor)
        else:
            self._widget.setCursorPosition(position)

    def _line_block(self, Line):
        """The paragraph of a line number (an IndexError if there is none)."""
        line, count = int(Line), self.LineCount
        if not 0 <= line < count:
            raise IndexError(f"{self.TypeName} '{self.Name}': no line {line} "
                             f"(LineCount is {count})")
        editor = self._editor()
        return editor.document().findBlockByNumber(line) if editor is not None else None

    @property
    def LineCount(self) -> int:
        """How many lines (paragraphs) the text has: 1 for no text."""
        editor = self._editor()
        return editor.document().blockCount() if editor is not None else 1

    def GetLine(self, Line: int) -> str:
        """The text of a line (from 0), without its line break."""
        block = self._line_block(Line)
        return block.text() if block is not None else self._widget.text()

    def GetLineFromChar(self, CharPos: int) -> int:
        """The line (paragraph, from 0) holding a character position."""
        editor = self._editor()
        if editor is None:
            return 0
        document = editor.document()
        block = document.findBlock(max(0, int(CharPos)))
        return block.blockNumber() if block.isValid() else document.blockCount() - 1

    def GetCharFromLine(self, Line: int) -> int:
        """Where a line starts (a character position, like SelStart)."""
        block = self._line_block(Line)
        return block.position() if block is not None else 0

    def GetColumnFromChar(self, CharPos: int) -> int:
        """A character position's column in its line (from 0)."""
        position = max(0, min(int(CharPos), len(self.Text)))
        return position - self.GetCharFromLine(self.GetLineFromChar(position))

    @property
    def CurrentLine(self) -> int:
        """The caret's line (from 0); setting it moves the caret there (keeping
        its column where the line is long enough), into view."""
        return self.GetLineFromChar(self._caret())

    @CurrentLine.setter
    def CurrentLine(self, value):
        start = self.GetCharFromLine(value)
        column = min(self.CurrentColumn, len(self.GetLine(value)))
        self._move_caret(start + column)

    @property
    def CurrentColumn(self) -> int:
        """The caret's column in its line (from 0); setting it moves the caret
        along the line (no further than its end)."""
        return self.GetColumnFromChar(self._caret())

    @CurrentColumn.setter
    def CurrentColumn(self, value):
        line = self.CurrentLine
        column = max(0, min(int(value), len(self.GetLine(line))))
        self._move_caret(self.GetCharFromLine(line) + column)

    # -- the screen -------------------------------------------------------------------------
    def _caret_rect(self) -> QRect:
        editor = self._editor()
        if editor is None:  # (its rectangle is wider than the caret, around it)
            rect = self._widget.cursorRect()
            return QRect(rect.center().x(), rect.top(), 1, rect.height())
        return editor.cursorRect().translated(editor.viewport().mapTo(editor, QPoint(0, 0)))

    @property
    def CaretLeft(self) -> int:
        """Where the caret is, in pixels from the control's left edge (e.g. to
        put a list of completions under it: Left + CaretLeft)."""
        return self._caret_rect().left()

    @property
    def CaretTop(self) -> int:
        """The top of the caret, in pixels from the control's top edge."""
        return self._caret_rect().top()

    @property
    def CaretHeight(self) -> int:
        """The caret's height in pixels (its line's): its bottom is
        CaretTop + CaretHeight."""
        return self._caret_rect().height()

    def GetCharFromPoint(self, X: int, Y: int) -> int:
        """The character position nearest a point (pixels in the control, as
        in MouseMove's X and Y)."""
        editor = self._editor()
        if editor is None:
            return self._widget.cursorPositionAt(QPoint(int(X), int(Y)))
        point = editor.viewport().mapFrom(editor, QPoint(int(X), int(Y)))
        return editor.cursorForPosition(point).position()

    @property
    def FirstVisibleLine(self) -> int:
        """The line at the top of the view; setting it scrolls that line to
        the top (as far as the text allows)."""
        editor = self._editor()
        if editor is None:
            return 0
        if isinstance(editor, QPlainTextEdit):
            return editor.firstVisibleBlock().blockNumber()
        margin = int(editor.document().documentMargin())
        return editor.cursorForPosition(QPoint(0, margin + 1)).blockNumber()

    @FirstVisibleLine.setter
    def FirstVisibleLine(self, value):
        editor = self._editor()
        if editor is None:
            return
        block = self._line_block(max(0, min(int(value), self.LineCount - 1)))
        bar = editor.verticalScrollBar()
        if isinstance(editor, QPlainTextEdit):  # (it scrolls by lines of text)
            lines, before = 0, editor.document().begin()
            while before.isValid() and before != block:
                lines += max(1, before.lineCount())
                before = before.next()
            bar.setValue(lines)
        else:  # (by pixels)
            top = editor.cursorRect(QTextCursor(block)).top()
            bar.setValue(bar.value() + top - int(editor.document().documentMargin()))

    @property
    def ScrollLeft(self) -> int:
        """How far the text is scrolled to the left, in pixels (a multi-line
        editor without wrapping); setting it scrolls."""
        editor = self._editor()
        return editor.horizontalScrollBar().value() if editor is not None else 0

    @ScrollLeft.setter
    def ScrollLeft(self, value):
        editor = self._editor()
        if editor is not None:
            editor.horizontalScrollBar().setValue(int(value))

    def ScrollToCaret(self) -> None:
        """Scroll so the caret is in view."""
        editor = self._editor()
        if editor is not None:
            editor.ensureCursorVisible()

    # -- undo -------------------------------------------------------------------------------
    def Undo(self) -> None:
        """Undo the last edit (typing, pasting, SelText...), like Ctrl+Z."""
        self._widget.undo()

    def Redo(self) -> None:
        """Redo what Undo undid."""
        self._widget.redo()

    @property
    def CanUndo(self) -> bool:
        editor = self._editor()
        return editor.document().isUndoAvailable() if editor is not None else \
            self._widget.isUndoAvailable()

    @property
    def CanRedo(self) -> bool:
        editor = self._editor()
        return editor.document().isRedoAvailable() if editor is not None else \
            self._widget.isRedoAvailable()

    def ClearUndo(self) -> None:
        """Forget the edits, so Undo can't go back past now (e.g. after loading)."""
        editor = self._editor()
        if editor is not None:
            editor.document().clearUndoRedoStacks()
            return
        line = self._widget
        position = line.cursorPosition()
        line.blockSignals(True)  # (setText clears the history; no Change)
        try:
            line.setText(line.text())
            line.setCursorPosition(position)
        finally:
            line.blockSignals(False)


_ACCEPTS_TAB = P("AcceptsTab", "bool", False,
                 description="Tab types a tab instead of moving to the next control "
                             "(multi-line)")


class TextBox(_TextEditing, Control):
    TypeName = "TextBox"
    DefaultEvent = "Change"
    DefaultSize = (121, 25)
    Events = ("Change", "SelChange", "Click", "DblClick", "GotFocus", "LostFocus",
              "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    Properties = (
        P("MultiLine", "bool", False, description="A multi-line editor instead of a single line"),
        P("Text", "text", "", always=True, description="The contents"),
        *_geometry(*DefaultSize),
        P("Alignment", "enum", 0, _ALIGNMENT,
          description="Horizontal text alignment (single-line only)"),
        P("PasswordChar", "str", "", description="Any character masks the input"),
        P("MaxLength", "int", 0, description="Maximum length; 0 = no limit (single-line)"),
        P("Locked", "bool", False, description="Read-only: the text can't be edited"),
        P("ScrollBars", "enum", 0, enum_choices("None", "Horizontal", "Vertical", "Both"),
          description="Scroll bars of a multi-line TextBox"),
        _ACCEPTS_TAB,
        *_COLORS, *_FONT, *_COMMON,
    )

    def __init__(self, parent, Name: str = "", **props):
        # Pick the right widget up front instead of rebuilding it.
        self.__dict__["_values"] = {"MultiLine": bool(props.get("MultiLine"))}
        super().__init__(parent, Name, **props)

    @property
    def _qss_type(self):
        return "QPlainTextEdit" if self._multiline else "QLineEdit"

    @property
    def _multiline(self) -> bool:
        return bool(self._values.get("MultiLine"))

    def _create_widget(self, parent):
        if self._multiline:
            widget = QPlainTextEdit(parent)
            widget.setTabChangesFocus(True)
            return widget
        return QLineEdit(parent)

    def _event_targets(self):
        if isinstance(self._widget, QPlainTextEdit):
            return [self._widget, self._widget.viewport()]
        return [self._widget]

    def _connect_signals(self):
        self._widget.textChanged.connect(lambda *_: self._fire("Change"))
        self._connect_selection()

    def _apply_MultiLine(self, v):
        if isinstance(self._widget, QPlainTextEdit) != bool(v):
            self._rebuild_widget()

    def _read_Text(self):
        if isinstance(self._widget, QPlainTextEdit):
            return self._widget.toPlainText()
        return self._widget.text()

    def _apply_Text(self, v):
        if isinstance(self._widget, QPlainTextEdit):
            if self._widget.toPlainText() != v:
                self._widget.setPlainText(v)
        elif self._widget.text() != v:
            self._widget.setText(v)

    def _apply_Alignment(self, v):
        if isinstance(self._widget, QLineEdit):
            self._widget.setAlignment(_QT_ALIGN.get(v, Qt.AlignLeft) | Qt.AlignVCenter)

    def _apply_PasswordChar(self, v):
        if isinstance(self._widget, QLineEdit):
            self._widget.setEchoMode(QLineEdit.Password if v else QLineEdit.Normal)

    def _apply_MaxLength(self, v):
        if isinstance(self._widget, QLineEdit):
            self._widget.setMaxLength(v if v > 0 else 32767)

    def _apply_Locked(self, v):
        self._widget.setReadOnly(v)

    def _apply_ScrollBars(self, v):
        if isinstance(self._widget, QPlainTextEdit):
            on, off = Qt.ScrollBarAsNeeded, Qt.ScrollBarAlwaysOff
            self._widget.setHorizontalScrollBarPolicy(on if v in (1, 3) else off)
            self._widget.setVerticalScrollBarPolicy(on if v in (2, 3) else off)
            self._widget.setLineWrapMode(
                QPlainTextEdit.NoWrap if v in (1, 3) else QPlainTextEdit.WidgetWidth)

    # Selection (runtime only)
    @property
    def SelStart(self) -> int:
        cursor = self._widget.textCursor() if self._multiline else None
        if cursor is not None:
            return cursor.selectionStart()
        return self._widget.selectionStart() if self._widget.hasSelectedText() \
            else self._widget.cursorPosition()

    @SelStart.setter
    def SelStart(self, value: int):
        if self._multiline:
            cursor = self._widget.textCursor()
            cursor.setPosition(int(value))
            self._widget.setTextCursor(cursor)
        else:
            self._widget.setCursorPosition(int(value))

    @property
    def SelLength(self) -> int:
        return len(self.SelText)

    @SelLength.setter
    def SelLength(self, value: int):
        start = self.SelStart
        if self._multiline:
            cursor = self._widget.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(start + int(value), cursor.MoveMode.KeepAnchor)
            self._widget.setTextCursor(cursor)
        else:
            self._widget.setSelection(start, int(value))

    @property
    def SelText(self) -> str:
        if self._multiline:
            return self._widget.textCursor().selectedText().replace(" ", "\n")
        return self._widget.selectedText()

    @SelText.setter
    def SelText(self, value: str):
        if self._multiline:
            self._widget.textCursor().insertText(str(value))
        else:
            self._widget.insert(str(value))


# --- RichTextBox ---------------------------------------------------------------------

_RTF_QT_ALIGN = {0: Qt.AlignLeft, 1: Qt.AlignRight, 2: Qt.AlignHCenter}


class _RichEdit(QTextEdit):
    """The RichTextBox's editor: pasted text keeps its formatting, but
    not pictures or tables from elsewhere (just their text)."""

    def insertFromMimeData(self, source):
        if not source.hasHtml():
            super().insertFromMimeData(source)
            return
        pasted = QTextDocument()
        pasted.setHtml(source.html())
        paragraphs = []  # each a list of (text, format) runs
        block = pasted.begin()
        while block.isValid():  # (a table's cells are paragraphs of their own)
            runs, it = [], block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                text = fragment.text().replace("\ufffc", "")  # (a picture's placeholder)
                if text and not fragment.charFormat().isImageFormat():
                    runs.append((text, fragment.charFormat()))
                it += 1
            paragraphs.append(runs)
            block = block.next()
        while paragraphs and not paragraphs[-1]:
            paragraphs.pop()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for number, runs in enumerate(paragraphs):
            if number:
                cursor.insertBlock()
            for text, fmt in runs:
                cursor.insertText(text, fmt)
        cursor.endEditBlock()
        self.setTextCursor(cursor)


class _EditorSelection:
    """SelStart, SelLength and SelText of RichTextBox and CodeBox (a
    QTextEdit or QPlainTextEdit)."""

    @property
    def SelStart(self) -> int:
        return self._widget.textCursor().selectionStart()

    @SelStart.setter
    def SelStart(self, value):
        cursor = self._widget.textCursor()
        cursor.setPosition(max(0, min(int(value), len(self.Text))))
        self._widget.setTextCursor(cursor)

    @property
    def SelLength(self) -> int:
        cursor = self._widget.textCursor()
        return cursor.selectionEnd() - cursor.selectionStart()

    @SelLength.setter
    def SelLength(self, value):
        start = self.SelStart
        cursor = self._widget.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(max(0, min(start + int(value), len(self.Text))),
                           QTextCursor.KeepAnchor)
        self._widget.setTextCursor(cursor)

    @property
    def SelText(self) -> str:
        return self._widget.textCursor().selectedText().replace("\u2029", "\n")

    @SelText.setter
    def SelText(self, value):
        """Replace the selection (or insert at the cursor), in the format of
        the Sel... properties."""
        self._widget.textCursor().insertText(str(value))


class RichTextBox(_EditorSelection, _TextEditing, Control):
    """Text with colors, fonts, bold, italic and underline, and aligned
    paragraphs, like VB's RichTextBox. Format the selection with its Sel...
    properties (SelBold, SelColor...; with nothing selected, what is typed
    next); add formatted text at the end with AppendText. VB's RTF is HTML
    here: TextHTML, SelHTML, and LoadFile/SaveFile with vpRtfHTML."""

    TypeName = "RichTextBox"
    DefaultEvent = "Change"
    DefaultSize = (201, 121)
    Events = ("Change", "SelChange", "Click", "DblClick", "GotFocus", "LostFocus",
              "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QTextEdit"
    Properties = (
        P("Text", "text", "", always=True, description="The contents, as plain text"),
        *_geometry(*DefaultSize),
        P("Locked", "bool", False, description="Read-only: the text can't be edited"),
        P("MaxLength", "int", 0, description="Maximum length; 0 = no limit"),
        P("ScrollBars", "enum", 2, enum_choices("None", "Horizontal", "Vertical", "Both"),
          description="Its scroll bars (shown when needed); with a horizontal one, lines "
                      "don't wrap"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A border around it"),
        _ACCEPTS_TAB,
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_trimming"] = False
        widget = _RichEdit(parent)
        widget.setTabChangesFocus(True)
        return widget

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        widget = self._widget
        widget.textChanged.connect(lambda: self._fire("Change"))
        widget.document().contentsChange.connect(self._limit_length)
        self._connect_selection()

    def _limit_length(self, position, removed, added):
        limit = self._values.get("MaxLength", 0)
        if not limit or not added or self._trimming:
            return
        excess = len(self._widget.toPlainText()) - limit
        if excess > 0:  # drop the end of what was just typed or pasted
            self.__dict__["_trimming"] = True
            try:
                cursor = QTextCursor(self._widget.document())
                end = position + added
                cursor.setPosition(end - min(excess, added))
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            finally:
                self.__dict__["_trimming"] = False

    # -- properties -------------------------------------------------------------------------
    def _read_Text(self):
        return self._widget.toPlainText()

    def _apply_Text(self, v):
        if self._widget.toPlainText() != v:
            self._widget.setPlainText(v)

    def _apply_Locked(self, v):
        self._widget.setReadOnly(v)
        self._widget.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard if v else
            Qt.TextEditorInteraction)

    def _apply_MaxLength(self, v):
        if v > 0 and len(self._widget.toPlainText()) > v:
            self.Text = self._widget.toPlainText()[:v]

    def _apply_ScrollBars(self, v):
        on, off = Qt.ScrollBarAsNeeded, Qt.ScrollBarAlwaysOff
        self._widget.setHorizontalScrollBarPolicy(on if v in (1, 3) else off)
        self._widget.setVerticalScrollBarPolicy(on if v in (2, 3) else off)
        self._widget.setLineWrapMode(QTextEdit.NoWrap if v in (1, 3) else QTextEdit.WidgetWidth)

    def _apply_BorderStyle(self, v):
        self._widget.setFrameShape(QFrame.StyledPanel if v else QFrame.NoFrame)

    @property
    def TextHTML(self) -> str:
        """The contents with their formatting, as HTML (VB's TextRTF)."""
        return self._widget.toHtml()

    @TextHTML.setter
    def TextHTML(self, value):
        self._widget.setHtml(str(value))

    @property
    def SelHTML(self) -> str:
        """The selection with its formatting, as HTML (VB's SelRTF)."""
        return QTextDocumentFragment(self._widget.textCursor()).toHtml()

    @SelHTML.setter
    def SelHTML(self, value):
        self._widget.textCursor().insertHtml(str(value))

    def _formats(self) -> list:
        """The character formats of the selection's pieces; with nothing
        selected, the format of what is typed next."""
        cursor = self._widget.textCursor()
        if not cursor.hasSelection():
            return [self._widget.currentCharFormat()]
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        probe = QTextCursor(self._widget.document())
        formats = []
        for position in range(start + 1, end + 1):  # (the format of the character before)
            probe.setPosition(position)
            if probe.block().position() == position and position > start + 1 and \
                    probe.block().length() > 1:
                continue  # (a paragraph break: not a character)
            formats.append(probe.charFormat())
        return formats or [self._widget.currentCharFormat()]

    def _font_of(self, fmt) -> QFont:
        return fmt.font().resolve(self._widget.document().defaultFont())

    def _sel_value(self, read):
        """One value for the selection, or None (VB's Null) when it is mixed."""
        values = [read(fmt) for fmt in self._formats()]
        first = values[0]
        return first if all(v == first for v in values) else None

    def _sel_merge(self, setup) -> None:
        fmt = QTextCharFormat()
        setup(fmt)
        self._widget.mergeCurrentCharFormat(fmt)

    @property
    def SelBold(self):
        """Whether the selection is bold (None if partly); set it to make it so."""
        return self._sel_value(lambda f: self._font_of(f).bold())

    @SelBold.setter
    def SelBold(self, value):
        self._sel_merge(lambda f: f.setFontWeight(QFont.Bold if value else QFont.Normal))

    @property
    def SelItalic(self):
        return self._sel_value(lambda f: self._font_of(f).italic())

    @SelItalic.setter
    def SelItalic(self, value):
        self._sel_merge(lambda f: f.setFontItalic(bool(value)))

    @property
    def SelUnderline(self):
        return self._sel_value(
            lambda f: f.fontUnderline() if f.hasProperty(QTextFormat.TextUnderlineStyle)
            else self._widget.document().defaultFont().underline())

    @SelUnderline.setter
    def SelUnderline(self, value):
        self._sel_merge(lambda f: f.setFontUnderline(bool(value)))

    @property
    def SelStrikeThru(self):
        return self._sel_value(lambda f: self._font_of(f).strikeOut())

    @SelStrikeThru.setter
    def SelStrikeThru(self, value):
        self._sel_merge(lambda f: f.setFontStrikeOut(bool(value)))

    @property
    def SelFontName(self):
        return self._sel_value(lambda f: self._font_of(f).family())

    @SelFontName.setter
    def SelFontName(self, value):
        self._sel_merge(lambda f: f.setFontFamilies([str(value)]))

    @property
    def SelFontSize(self):
        def size(fmt):
            points = self._font_of(fmt).pointSizeF()
            return int(points) if points == int(points) else points
        return self._sel_value(size)

    @SelFontSize.setter
    def SelFontSize(self, value):
        self._sel_merge(lambda f: f.setFontPointSize(float(value)))

    def _color_of(self, fmt):
        brush = fmt.foreground()
        if fmt.hasProperty(QTextFormat.ForegroundBrush) and brush.style() != Qt.NoBrush:
            return colors.from_qcolor(brush.color())
        return None

    @property
    def SelColor(self):
        """The selection's text color (vpRed, RGB(...)); the control's
        ForeColor where none was given. None if it is mixed."""
        values = [self._color_of(fmt) for fmt in self._formats()]
        if any(v != values[0] for v in values):
            return None
        if values[0] is not None:
            return values[0]
        fore = self._values.get("ForeColor")
        return fore if fore is not None else colors.from_qcolor(
            self._widget.palette().color(QPalette.Text))

    @SelColor.setter
    def SelColor(self, value):
        """A color, or None for the control's ForeColor."""
        self._sel_merge(lambda f: f.setForeground(
            QBrush() if value is None else QBrush(colors.to_qcolor(value))))

    def _blocks(self):
        cursor = self._widget.textCursor()
        document = self._widget.document()
        block = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        while block.isValid():
            yield block
            if block == last:
                break
            block = block.next()

    @property
    def SelAlignment(self):
        """The alignment of the selection's paragraphs (vpLeftJustify,
        vpRightJustify, vpCenter); None if they differ."""
        def alignment(block):
            align = block.blockFormat().alignment()
            if align & Qt.AlignRight:
                return 1
            return 2 if align & Qt.AlignHCenter else 0
        values = [alignment(b) for b in self._blocks()]
        return values[0] if all(v == values[0] for v in values) else None

    @SelAlignment.setter
    def SelAlignment(self, value):
        self._widget.setAlignment(_RTF_QT_ALIGN.get(int(value), Qt.AlignLeft) | Qt.AlignAbsolute)

    # -- methods ----------------------------------------------------------------------------
    def AppendText(self, Text, Color=None, Bold: bool = False, Italic: bool = False,
                   Underline: bool = False) -> None:
        """Add text at the end in its own format, without moving the cursor or
        the selection; the view follows the end if it was showing it (a log)."""
        widget = self._widget
        bar = widget.verticalScrollBar()
        following = bar.value() >= bar.maximum() - 2
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush() if Color is None else QBrush(colors.to_qcolor(Color)))
        fmt.setFontWeight(QFont.Bold if Bold else QFont.Normal)
        fmt.setFontItalic(bool(Italic))
        fmt.setFontUnderline(bool(Underline))
        cursor = QTextCursor(widget.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(str(Text), fmt)
        if following:
            bar.setValue(bar.maximum())

    def Find(self, String, Start: int | None = None, End: int | None = None,
             Options: int = 0) -> int:
        """Find text and select it; returns where it starts, or -1. It looks
        from Start (else just after the selection, so calling it again finds
        the next one) up to End. Options: vpRtfWholeWord, vpRtfMatchCase,
        vpRtfNoHighlight (don't select it), added together."""
        if Start is None:
            Start = self.SelStart + self.SelLength
        flags = QTextDocument.FindFlag(0)
        if Options & 2:
            flags |= QTextDocument.FindWholeWords
        if Options & 4:
            flags |= QTextDocument.FindCaseSensitively
        found = self._widget.document().find(str(String), int(Start), flags)
        if found.isNull() or (End is not None and found.selectionEnd() > int(End)):
            return -1
        if not Options & 8:
            self._widget.setTextCursor(found)
        return found.selectionStart()

    @staticmethod
    def _is_html(FileName, FileType) -> bool:
        if FileType is None:
            return os.path.splitext(str(FileName))[1].lower() in (".htm", ".html")
        return int(FileType) == 0

    def LoadFile(self, FileName, FileType: int | None = None) -> None:
        """Load a file: vpRtfHTML (formatted) or vpRtfText; without a FileType,
        .htm and .html files are HTML and others text."""
        with open(FileName, encoding="utf-8") as f:
            contents = f.read()
        if self._is_html(FileName, FileType):
            self._widget.setHtml(contents)
        else:
            self._widget.setPlainText(contents)

    def SaveFile(self, FileName, FileType: int | None = None) -> None:
        """Save the contents: vpRtfHTML (with the formatting) or vpRtfText;
        without a FileType, by the file's extension as in LoadFile."""
        contents = self.TextHTML if self._is_html(FileName, FileType) else self.Text
        with open(FileName, "w", encoding="utf-8") as f:
            f.write(contents)


# --- CodeBox ---------------------------------------------------------------------------

_PY_KEYWORDS = re.compile(r"\b(?:%s)\b" % "|".join(keyword.kwlist + ["match", "case"]))
_PY_NUMBER = re.compile(r"\b(?:0[xXoObB][0-9a-fA-F_]+|\d[\d_]*\.?\d*(?:[eE][+-]?\d+)?j?)\b")
_PY_DECORATOR = re.compile(r"^\s*@[\w.]+")
_PY_DEF = re.compile(r"\b(?:def|class)\s+(\w+)")
_PY_STRING = re.compile(r""""[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'""")
_PY_COLORS = {  # (on a light background, on a dark one)
    "keyword": ("#0000c0", "#569cd6"), "string": ("#a31515", "#ce9178"),
    "comment": ("#008000", "#6a9955"), "number": ("#098658", "#b5cea8"),
    "defname": ("#795e26", "#dcdcaa"), "decorator": ("#af00db", "#c586c0"),
}
_PY_IN_SINGLE, _PY_IN_DOUBLE = 1, 2  # inside ''' or """ at the line's end


class _CodeHighlighter(QSyntaxHighlighter):
    """Colors a CodeBox line by line: its Language's colors, then its
    Highlight event. A line's block state keeps both: the language's in the
    low two bits, the event's State above them."""

    def __init__(self, box: "CodeBox"):
        super().__init__(box._widget.document())
        self.box = box
        self.formats: dict[str, QTextCharFormat] = {}

    def set_dark(self, dark: bool) -> None:
        self.formats = {}
        for name, pair in _PY_COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(pair[dark]))
            if name == "comment":
                fmt.setFontItalic(True)
            self.formats[name] = fmt

    def highlightBlock(self, text: str) -> None:
        previous = max(self.previousBlockState(), 0)
        language = previous & 3
        if self.box._values.get("Language") == 1:
            language = self._python(text, language)
        else:
            language = 0
        state = self.box._highlight(self, self.currentBlock().blockNumber(), text,
                                    previous >> 2)
        self.setCurrentBlockState(state * 4 + language)

    def _python(self, text: str, state: int) -> int:
        formats = self.formats
        for pattern, name in ((_PY_KEYWORDS, "keyword"), (_PY_NUMBER, "number"),
                              (_PY_DECORATOR, "decorator")):
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), formats[name])
        for match in _PY_DEF.finditer(text):
            self.setFormat(match.start(1), len(match.group(1)), formats["defname"])
        index = 0
        if state:  # inside a triple-quoted string from an earlier line
            delimiter = "'''" if state == _PY_IN_SINGLE else '"""'
            end = text.find(delimiter)
            if end == -1:
                self.setFormat(0, len(text), formats["string"])
                return state
            self.setFormat(0, end + 3, formats["string"])
            index, state = end + 3, 0
        while index < len(text):
            char = text[index]
            if char == "#":
                self.setFormat(index, len(text) - index, formats["comment"])
                break
            if text.startswith(('"""', "'''"), index):
                delimiter = text[index:index + 3]
                end = text.find(delimiter, index + 3)
                if end == -1:
                    self.setFormat(index, len(text) - index, formats["string"])
                    return _PY_IN_SINGLE if delimiter == "'''" else _PY_IN_DOUBLE
                self.setFormat(index, end + 3 - index, formats["string"])
                index = end + 3
                continue
            if char in "\"'":
                match = _PY_STRING.match(text, index)
                if match:
                    self.setFormat(index, match.end() - index, formats["string"])
                    index = match.end()
                    continue
            index += 1
        return state


class _CodeGutter(QWidget):
    """The CodeBox's gutter: line numbers and markers, left of the text."""

    def __init__(self, edit: "_CodeEdit"):
        super().__init__(edit)
        self.edit = edit

    def paintEvent(self, event):
        self.edit.box._paint_gutter(self, event)

    def mousePressEvent(self, event):
        self.edit.box._gutter_clicked(event.position().toPoint())


class _CodeEdit(QPlainTextEdit):
    """The CodeBox's editor: its gutter, and the user's edits checked against
    the protected lines."""

    def __init__(self, box: "CodeBox", parent):
        super().__init__(parent)
        self.box = box
        self.gutter = _CodeGutter(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.box._place_gutter()

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        self.box._paint_shading(painter, event.rect())
        painter.end()
        super().paintEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.FontChange, QEvent.StyleChange):
            self.box._restyle()

    def keyPressEvent(self, event):
        if not self.box._key_press(event):
            super().keyPressEvent(event)

    def insertFromMimeData(self, source):  # pasting and dropping
        if self.box._may_edit():
            super().insertFromMimeData(source)
        else:
            self.box._reject_edit()

    def inputMethodEvent(self, event):
        if event.commitString() and not self.box._may_edit():
            self.box._reject_edit()
            return
        super().inputMethodEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        if not self.box._may_edit():  # (the menu's own Cut, Paste and Delete)
            for action in menu.actions():
                if action.objectName() in ("edit-cut", "edit-paste", "edit-delete"):
                    action.setEnabled(False)
        menu.exec(event.globalPos())
        menu.deleteLater()


class _LineMarkers:
    """CodeBox.LineMarker: ``Code1.LineMarker[5] = "●"`` shows a short text
    in line 5's gutter, ``Code1.LineMarker(5)`` reads it ("" = none). A marker
    stays with its line when lines are added or removed above it."""

    def __init__(self, box: "CodeBox"):
        self._box = box

    def _find(self, line: int):
        return next((entry for entry in self._box._markers
                     if entry[0].blockNumber() == line), None)

    def __call__(self, line):
        return self[line]

    def __getitem__(self, line) -> str:
        self._box._line_block(line)
        entry = self._find(int(line))
        return entry[1] if entry else ""

    def __setitem__(self, line, text):
        block = self._box._line_block(line)
        entry = self._find(int(line))
        if entry:
            self._box._markers.remove(entry)
        if text:
            cursor = QTextCursor(block)
            self._box._markers.append([cursor, str(text)])
        self._box._update_gutter()


class CodeBox(_EditorSelection, _TextEditing, Control):
    """A code editor: line numbers, the current line highlighted, syntax
    coloring (Language, and your own in the Highlight event), markers in the
    gutter (LineMarker, GutterClick), hidden (folded) lines and protected
    lines the user can't change (code can). Enter keeps the indentation, Tab
    and Shift+Tab indent; it has the TextBox's editing API."""

    TypeName = "CodeBox"
    DefaultEvent = "Change"
    DefaultSize = (321, 201)
    Events = ("Change", "SelChange", "Highlight", "GutterClick", "ProtectedEdit", "Click",
              "DblClick", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QPlainTextEdit"
    Properties = (
        P("Text", "text", "", always=True, description="The code"),
        *_geometry(*DefaultSize),
        P("Language", "enum", 0, enum_choices("None", "Python"),
          description="Built-in syntax coloring; add your own in the Highlight event"),
        P("LineNumbers", "bool", True, description="Line numbers in the gutter"),
        P("HighlightCurrentLine", "bool", True, description="Shade the caret's line"),
        P("CurrentLineColor", "color", None,
          description="The current line's shade; unset = a shade of the background"),
        P("ProtectedColor", "color", None,
          description="The background of protected lines; unset = a tint of the background"),
        P("TabWidth", "int", 4, description="Columns per indentation level (and tab stop)"),
        P("UseTabs", "bool", False, description="Indent with tab characters instead of spaces"),
        P("AutoIndent", "bool", True,
          description="Enter keeps the line's indentation (Python: one more after a colon)"),
        P("AcceptsTab", "bool", True,
          description="Tab and Shift+Tab indent instead of moving to another control"),
        P("WordWrap", "bool", False, description="Wrap long lines instead of scrolling"),
        P("Locked", "bool", False, description="Read-only: the code can't be edited"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_protected=[], _markers=[], _highlighting=None, _highlighter=None)
        widget = _CodeEdit(self, parent)
        self._widget = widget
        self.__dict__["_highlighter"] = _CodeHighlighter(self)
        self._highlighter.set_dark(self._dark())
        widget.blockCountChanged.connect(self._update_gutter)
        widget.updateRequest.connect(self._on_update_request)
        widget.cursorPositionChanged.connect(self._update_extra)
        return widget

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        self._widget.textChanged.connect(lambda: self._fire("Change"))
        self._connect_selection()

    # -- looks -------------------------------------------------------------------------------
    def _base_color(self) -> QColor:
        back = self._values.get("BackColor")
        return colors.to_qcolor(back) if back is not None else \
            self._widget.palette().color(QPalette.Base)

    def _dark(self) -> bool:
        return self._base_color().lightness() < 128

    def _restyle(self) -> None:
        """The colors or font changed: tab stops, gutter, coloring, shading."""
        widget = self._widget
        if widget is None or self._highlighter is None:
            return
        widget.setTabStopDistance(
            widget.fontMetrics().horizontalAdvance(" ") * max(1, self._values.get("TabWidth", 4)))
        dark = self._dark()
        if self._highlighter.formats.get("keyword") is None or \
                self._highlighter.formats["keyword"].foreground().color() != \
                QColor(_PY_COLORS["keyword"][dark]):
            self._highlighter.set_dark(dark)
            self._highlighter.rehighlight()
        self._update_gutter()
        self._update_extra()

    def _apply_font(self, _=None):
        super()._apply_font()
        if self._widget is not None and not self._values.get("FontName"):
            font = self._widget.font()  # code: a fixed-width font unless one is chosen
            font.setFamily(QFontDatabase.systemFont(QFontDatabase.FixedFont).family())
            self._widget.setFont(font)

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font

    def _apply_colors(self, _=None):
        super()._apply_colors()
        self._restyle()

    _apply_BackColor = _apply_ForeColor = _apply_colors

    def _apply_Language(self, v):
        self._highlighter.rehighlight()

    def _apply_LineNumbers(self, v):
        self._update_gutter()

    def _apply_HighlightCurrentLine(self, v):
        self._update_extra()

    _apply_CurrentLineColor = _apply_ProtectedColor = _apply_HighlightCurrentLine

    def _apply_TabWidth(self, v):
        self._restyle()

    def _apply_WordWrap(self, v):
        self._widget.setLineWrapMode(QPlainTextEdit.WidgetWidth if v else
                                     QPlainTextEdit.NoWrap)

    def _apply_Locked(self, v):
        self._widget.setReadOnly(v)

    def _read_Text(self):
        return self._widget.toPlainText()

    def _apply_Text(self, v):
        if self._widget.toPlainText() != v:
            self._widget.setPlainText(v)
            # (a new text: no protected, hidden or marked lines from the old one)
            self._protected.clear()
            self._markers.clear()
            self._update_gutter()
            self._update_extra()

    def _update_extra(self, *_) -> None:
        """Shade the current line (and the protected ones) again."""
        if self._widget is not None:
            self._widget.viewport().update()

    def _paint_shading(self, painter: QPainter, rect: QRect) -> None:
        """Under the text: the protected lines' tint and the current line's
        shade (painted first, so the text's own backgrounds stay on top)."""
        widget = self._widget
        dark = self._dark()
        protected = self._values.get("ProtectedColor")
        tint = colors.to_qcolor(protected) if protected is not None else (
            QColor(110, 140, 255, 45) if dark else QColor(60, 100, 220, 28))
        current = self._values.get("CurrentLineColor")
        shade = colors.to_qcolor(current) if current is not None else (
            QColor(255, 255, 255, 22) if dark else QColor(0, 0, 0, 16))
        show_current = self._values.get("HighlightCurrentLine", True)
        ranges = [(start.blockNumber(), end.blockNumber()) for start, end in self._protected]
        caret = widget.textCursor().blockNumber()
        block = widget.firstVisibleBlock()
        top = widget.blockBoundingGeometry(block).translated(widget.contentOffset()).top()
        while block.isValid() and top <= rect.bottom():
            height = widget.blockBoundingRect(block).height()
            if block.isVisible() and top + height >= rect.top():
                number = block.blockNumber()
                line = QRect(0, round(top), widget.viewport().width(), round(height))
                if any(first <= number <= last for first, last in ranges):
                    painter.fillRect(line, tint)
                if show_current and number == caret:
                    painter.fillRect(line, shade)
            top += height
            block = block.next()

    # -- the gutter ------------------------------------------------------------------------
    def _gutter_width(self) -> int:
        widget = self._widget
        marks = 14 if (self._values.get("LineNumbers", True) or self._markers or
                       self._has_hidden()) else 0
        if not self._values.get("LineNumbers", True):
            return marks
        digits = max(3, len(str(widget.blockCount())))
        return 6 + widget.fontMetrics().horizontalAdvance("9") * digits + marks

    def _has_hidden(self) -> bool:
        block = self._widget.document().begin()
        while block.isValid():
            if not block.isVisible():
                return True
            block = block.next()
        return False

    def _update_gutter(self, *_) -> None:
        widget = self._widget
        if widget is None:
            return
        widget.setViewportMargins(self._gutter_width(), 0, 0, 0)
        self._place_gutter()
        widget.gutter.update()

    def _place_gutter(self) -> None:
        widget = self._widget
        rect = widget.contentsRect()
        widget.gutter.setGeometry(QRect(rect.left(), rect.top(), self._gutter_width(),
                                        rect.height()))

    def _on_update_request(self, rect, dy):
        gutter = self._widget.gutter
        if dy:
            gutter.scroll(0, dy)
        else:
            gutter.update(0, rect.y(), gutter.width(), rect.height())

    def _paint_gutter(self, gutter: QWidget, event) -> None:
        widget = self._widget
        painter = QPainter(gutter)
        base, dark = self._base_color(), self._dark()
        painter.fillRect(event.rect(), base.lighter(115) if dark else base.darker(104))
        ink = QColor(widget.palette().color(QPalette.Text))
        ink.setAlpha(130)
        numbers = self._values.get("LineNumbers", True)
        markers = {cursor.blockNumber(): text for cursor, text in self._markers}
        block = widget.firstVisibleBlock()
        top = round(widget.blockBoundingGeometry(block).translated(widget.contentOffset()).top())
        height = widget.fontMetrics().height()
        width = gutter.width()
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(widget.blockBoundingRect(block).height())
            if block.isVisible() and bottom >= event.rect().top():
                number = block.blockNumber()
                if numbers:
                    painter.setPen(ink)
                    painter.drawText(0, top, width - 16, height, Qt.AlignRight, str(number + 1))
                marker = markers.get(number)
                folded = block.next().isValid() and not block.next().isVisible()
                if marker:
                    painter.setPen(widget.palette().color(QPalette.Text))
                    painter.drawText(width - 14, top, 14, height, Qt.AlignCenter, marker)
                elif folded:  # (hidden lines follow: a + box)
                    box = QRect(width - 12, top + (height - 9) // 2, 9, 9)
                    painter.setPen(ink)
                    painter.drawRect(box)
                    center = box.center()
                    painter.drawLine(center.x() - 2, center.y(), center.x() + 2, center.y())
                    painter.drawLine(center.x(), center.y() - 2, center.x(), center.y() + 2)
            block = block.next()
            top = bottom
        painter.end()

    def _gutter_clicked(self, point: QPoint) -> None:
        if not self._design_mode:
            self._fire("GutterClick", self._widget.cursorForPosition(
                QPoint(0, point.y())).blockNumber())

    @property
    def LineMarker(self) -> _LineMarkers:
        """A short text in a line's gutter (●, ▸...): ``LineMarker[5] = "●"``
        sets line 5's, ``LineMarker(5)`` reads it; "" removes it."""
        return _LineMarkers(self)

    # -- syntax coloring -------------------------------------------------------------------
    def _highlight(self, highlighter, line: int, text: str, state: int) -> int:
        if not self._name and not self._design_mode and not self.__dict__.get("_unnamed"):
            # (being made in InitializeComponent: named later, then colored again)
            self.__dict__["_unnamed"] = True
            QTimer.singleShot(0, self._widget, self._named)
        if self._handler("Highlight") is None:
            return 0
        self.__dict__["_highlighting"] = highlighter
        try:
            result = self._fire("Highlight", line, text, state)
        finally:
            self.__dict__["_highlighting"] = None
        return result if isinstance(result, int) and not isinstance(result, bool) and \
            result > 0 else 0

    def _named(self) -> None:
        """It has its name now: color the lines again for its Highlight event."""
        if self.__dict__.pop("_unnamed", False) and self._name:
            self._highlighter.rehighlight()

    def HighlightText(self, Start: int, Length: int, ForeColor=None, Bold=None, Italic=None,
                      BackColor=None, Underline=None) -> None:
        """In the Highlight event: format part of the line (Start is a
        column, from 0). Only what you give changes (e.g. the color, keeping
        the language's bold)."""
        highlighter = self._highlighting
        if highlighter is None:
            raise RuntimeError(f"CodeBox '{self.Name}': HighlightText works in the "
                               "Highlight event (Rehighlight() runs it again)")
        for column in range(max(0, int(Start)), max(0, int(Start) + int(Length))):
            fmt = QTextCharFormat(highlighter.format(column))
            if ForeColor is not None:
                fmt.setForeground(QBrush(colors.to_qcolor(ForeColor)))
            if BackColor is not None:
                fmt.setBackground(QBrush(colors.to_qcolor(BackColor)))
            if Bold is not None:
                fmt.setFontWeight(QFont.Bold if Bold else QFont.Normal)
            if Italic is not None:
                fmt.setFontItalic(bool(Italic))
            if Underline is not None:
                fmt.setFontUnderline(bool(Underline))
            highlighter.setFormat(column, 1, fmt)

    def Rehighlight(self) -> None:
        """Color every line again (e.g. when what Highlight colors changed)."""
        self._highlighter.rehighlight()

    # -- hidden lines -----------------------------------------------------------------------
    def _set_visible(self, first: int, last: int, visible: bool) -> None:
        document = self._widget.document()
        first_block, last_block = self._line_block(first), self._line_block(last)
        if last < first:
            raise ValueError(f"CodeBox '{self.Name}': lines {first} to {last}")
        block = first_block
        while block.isValid():
            block.setVisible(visible)
            if block == last_block:
                break
            block = block.next()
        document.markContentsDirty(first_block.position(), last_block.position() +
                                   last_block.length() - first_block.position())
        if not visible and first <= self.CurrentLine <= last:  # (the caret: out of them)
            self._move_caret(first_block.previous().position() if first > 0 else
                             last_block.next().position() if last_block.next().isValid()
                             else 0)
        self._update_gutter()
        self._widget.viewport().update()

    def HideLines(self, First: int, Last: int) -> None:
        """Hide lines First to Last (fold them); the line before shows a + in
        the gutter."""
        self._set_visible(int(First), int(Last), False)

    def ShowLines(self, First: int | None = None, Last: int | None = None) -> None:
        """Show hidden lines again: First to Last, or all."""
        first = 0 if First is None else int(First)
        last = self.LineCount - 1 if Last is None else int(Last)
        self._set_visible(first, last, True)

    def IsLineHidden(self, Line: int) -> bool:
        return not self._line_block(Line).isVisible()

    # -- protected lines ----------------------------------------------------------------------
    def ProtectLines(self, First: int, Last: int) -> None:
        """Protect lines First to Last: the user can't change them (code can,
        e.g. with SelText). They move with the text when lines are added or
        removed above them."""
        first_block, last_block = self._line_block(First), self._line_block(Last)
        if int(Last) < int(First):
            raise ValueError(f"CodeBox '{self.Name}': lines {First} to {Last}")
        start = QTextCursor(first_block)
        end = QTextCursor(last_block)
        end.movePosition(QTextCursor.EndOfBlock)
        end.setKeepPositionOnInsert(True)  # (Enter at its end: a new line outside)
        self._protected.append((start, end))
        self._update_extra()

    def UnprotectLines(self) -> None:
        """Let the user change every line again."""
        self._protected.clear()
        self._update_extra()

    def IsLineProtected(self, Line: int) -> bool:
        self._line_block(Line)
        return any(start.blockNumber() <= int(Line) <= end.blockNumber()
                   for start, end in self._protected)

    def _may_edit(self, key: int | None = None) -> bool:
        """Whether the user's edit at the selection leaves protected lines alone."""
        cursor = self._widget.textCursor()
        a, b = cursor.selectionStart(), cursor.selectionEnd()
        for start_cursor, end_cursor in self._protected:
            start, end = start_cursor.position(), end_cursor.position()
            if a == b:
                if key in (Qt.Key_Return, Qt.Key_Enter) and a in (start, end):
                    continue  # (a new line before or after them)
                low = a - 1 if key == Qt.Key_Backspace else a
                high = b + 1 if key == Qt.Key_Delete else b
            else:
                low, high = a, b
            if not (high < start or low > end):
                return False
        return True

    def _reject_edit(self) -> None:
        line = self.CurrentLine
        if self._handler("ProtectedEdit") is None:
            QApplication.beep()
        else:
            self._fire("ProtectedEdit", line)

    # -- keys -------------------------------------------------------------------------------
    def _indent_unit(self) -> str:
        return "\t" if self._values.get("UseTabs") else " " * max(1, self._values.get("TabWidth",
                                                                                      4))

    def _key_press(self, event) -> bool:
        """Protection, auto-indent and Tab indenting; True if it was handled."""
        if self._values.get("Locked"):
            return False
        key, modifiers = event.key(), event.modifiers()
        cut_or_paste = event.matches(QKeySequence.Cut) or event.matches(QKeySequence.Paste)
        modifies = bool(event.text()) or cut_or_paste or key in (
            Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Backtab)
        shortcut = bool(modifiers & (Qt.ControlModifier | Qt.MetaModifier)) and not cut_or_paste
        if modifies and not shortcut and not self._may_edit(key):
            self._reject_edit()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter) and not modifiers & Qt.ShiftModifier and \
                self._values.get("AutoIndent", True):
            self._new_line()
            return True
        if key == Qt.Key_Tab and not modifiers & ~Qt.KeypadModifier:
            self._indent(True)
            return True
        if key == Qt.Key_Backtab:
            self._indent(False)
            return True
        return False

    def _new_line(self) -> None:
        cursor = self._widget.textCursor()
        before = cursor.block().text()[:cursor.positionInBlock()]
        indent = before[:len(before) - len(before.lstrip())]
        stripped = before.strip()
        if self._values.get("Language") == 1:
            unit = self._indent_unit()
            if stripped.endswith(":"):
                indent += unit
            elif stripped.split(" ")[0] in ("return", "pass", "break", "continue", "raise") \
                    and indent.endswith(unit):
                indent = indent[:-len(unit)]
        cursor.insertText("\n" + indent)
        self._widget.ensureCursorVisible()

    def _indent(self, forward: bool) -> None:
        widget = self._widget
        cursor = widget.textCursor()
        unit = self._indent_unit()
        document = widget.document()
        first = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        if forward and first == last:  # no lines selected: to the next tab stop
            if unit == "\t":
                cursor.insertText("\t")
            else:
                column = cursor.positionInBlock()
                cursor.insertText(" " * (len(unit) - column % len(unit)))
            return
        if cursor.hasSelection() and last != first and \
                cursor.selectionEnd() == last.position():
            last = last.previous()  # (a selection ending at a line's start leaves it)
        cursor.beginEditBlock()
        block = first
        while block.isValid():
            edit = QTextCursor(block)
            if forward:
                edit.insertText(unit)
            else:
                text = block.text()
                spaces = len(text) - len(text.lstrip(" "))
                width = max(1, self._values.get("TabWidth", 4))
                remove = 1 if text.startswith("\t") else min(spaces, width)
                edit.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor, remove)
                edit.removeSelectedText()
            if block == last:
                break
            block = block.next()
        cursor.endEditBlock()


# --- CommandButton ------------------------------------------------------------------

_STYLE_DESCRIPTION = {
    "CommandButton": "Graphical: a button showing its Picture above the Caption",
    "CheckBox": "Graphical: a toggle button, pressed while Value is vpChecked, showing its "
                "Picture above the Caption",
    "OptionButton": "Graphical: a toggle button, pressed while Value is True (one of its "
                    "container's option buttons), showing its Picture above the Caption",
}


def _graphical_props(type_name: str) -> tuple:
    """Style and the pictures of a Graphical CommandButton, CheckBox or OptionButton."""
    return (
        P("Style", "enum", 0, enum_choices("Standard", "Graphical"),
          description=_STYLE_DESCRIPTION[type_name]),
        P("Picture", "file", "",
          description="A Graphical button's picture (relative to the form's folder)"),
        P("DownPicture", "file", "",
          description="A Graphical button's picture while it is pressed (or set); "
                      "empty = Picture"),
        P("DisabledPicture", "file", "",
          description="A Graphical button's picture while it is disabled; empty = Picture, "
                      "grayed"),
    )


class _Graphical:
    """Style = Graphical for CommandButton, CheckBox and OptionButton, as in VB:
    a button (a QToolButton) with its Picture above its Caption, DownPicture
    while pressed or set, DisabledPicture while disabled. A CheckBox or
    OptionButton becomes a toggle button, pressed while its Value is set
    (the option buttons of a container stay exclusive)."""

    _standard_qss = "QPushButton"
    _checkable = False  # (a toggle button: CheckBox, OptionButton)

    def __init__(self, parent, Name: str = "", **props):
        # Pick the right widget up front instead of rebuilding it.
        self.__dict__["_values"] = {"Style": int(props.get("Style") or 0)}
        super().__init__(parent, Name, **props)

    @property
    def _graphical(self) -> bool:
        return self._values.get("Style", 0) == 1

    @property
    def _qss_type(self):
        return "QToolButton" if self._graphical else self._standard_qss

    def _graphical_widget(self, parent) -> QToolButton:
        button = QToolButton(parent)
        button.setCheckable(self._checkable)
        button.setFocusPolicy(Qt.StrongFocus)
        for signal in (button.pressed, button.released, button.toggled):
            signal.connect(self._update_picture)
        return button

    def _apply_Style(self, v):
        if isinstance(self._widget, QToolButton) != (v == 1):
            self._before_rebuild()
            self.__dict__["_restyling"] = True  # the new widget gets the Value: no Click
            try:
                self._rebuild_widget()
            finally:
                self.__dict__["_restyling"] = False
        self._update_picture()

    def _fire(self, event: str, *args):
        if self.__dict__.get("_restyling"):
            return None
        return super()._fire(event, *args)

    def _before_rebuild(self) -> None:
        """Keep what the widget knows (e.g. a checked state) for the new one."""

    def _update_picture(self, *_) -> None:
        """Show the picture for the button's state (Graphical only)."""
        button = self._widget
        if not isinstance(button, QToolButton):
            return
        values = self._values
        name = "Picture"
        if not button.isEnabled() and values.get("DisabledPicture"):
            name = "DisabledPicture"
        elif (button.isDown() or button.isChecked()) and values.get("DownPicture"):
            name = "DownPicture"
        path = resolve_path(self, values.get(name, ""))
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            button.setIcon(QIcon())
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            return
        button.setIcon(QIcon(pixmap))
        button.setIconSize(pixmap.deviceIndependentSize().toSize())
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if button.text()
                                  else Qt.ToolButtonIconOnly)

    def _apply_Picture(self, v):
        self._update_picture()

    _apply_DownPicture = _apply_DisabledPicture = _apply_Picture

    def _apply_Caption(self, v):
        self._widget.setText(v)
        self._update_picture()  # (picture and text, or just the picture)

    def _apply_Enabled(self, v):
        super()._apply_Enabled(v)
        self._update_picture()

    def _apply_font(self, _=None):
        super()._apply_font()
        if isinstance(self._widget, QToolButton) and not self._values.get("FontSize"):
            # Some platforms (macOS) give tool buttons a smaller font: a Graphical
            # button's Caption is the size of an ordinary button's
            font = self._widget.font()
            font.setPointSizeF(QApplication.font("QPushButton").pointSizeF())
            self._widget.setFont(font)

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font


class CommandButton(_Graphical, Control):
    TypeName = "CommandButton"
    Events = ("Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    Properties = (
        P("Caption", "str", "", always=True, description="The text; & marks the access key"),
        *_geometry(*Control.DefaultSize),
        P("Default", "bool", False, description="Clicked when Enter is pressed on the form"),
        P("Cancel", "bool", False, description="Clicked when Esc is pressed on the form"),
        *_graphical_props("CommandButton"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        if self._graphical:
            return self._graphical_widget(parent)
        button = QPushButton(parent)
        button.setAutoDefault(False)
        return button

    def _connect_signals(self):
        self._widget.clicked.connect(lambda *_: self._fire("Click"))

    def _apply_Default(self, v):
        if isinstance(self._widget, QPushButton):  # (a Graphical one looks the same)
            self._widget.setDefault(v)

    @property
    def Value(self) -> bool:
        return False

    @Value.setter
    def Value(self, v):
        """Setting Value = True clicks the button (VB6 behavior)."""
        if v:
            self._widget.click()


# --- CheckBox / OptionButton ---------------------------------------------------------

class CheckBox(_Graphical, Control):
    TypeName = "CheckBox"
    Events = ("Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _standard_qss = "QCheckBox"
    _checkable = True
    Properties = (
        P("Caption", "str", "", always=True, description="The text; & marks the access key"),
        *_geometry(121, 25),
        P("Value", "enum", 0, enum_choices("Unchecked", "Checked", "Grayed"),
          description="vpUnchecked, vpChecked or vpGrayed; changing it fires Click"),
        *_graphical_props("CheckBox"),
        *_COLORS, *_FONT, *_COMMON,
    )
    DefaultSize = (121, 25)

    def _create_widget(self, parent):
        if self._graphical:
            return self._graphical_widget(parent)
        box = QCheckBox(parent)
        box.setTristate(False)
        return box

    def _connect_signals(self):
        if isinstance(self._widget, QToolButton):
            self._widget.toggled.connect(lambda *_: self._fire("Click"))
        else:
            self._widget.stateChanged.connect(lambda *_: self._fire("Click"))

    def _before_rebuild(self):
        self._values["Value"] = self._read_Value()

    def _read_Value(self):
        if isinstance(self._widget, QToolButton):
            return 1 if self._widget.isChecked() else 0
        state = self._widget.checkState()
        return {Qt.Unchecked: 0, Qt.Checked: 1}.get(state, 2)

    def _apply_Value(self, v):
        if isinstance(self._widget, QToolButton):  # (Grayed: not pressed)
            self._widget.setChecked(v == 1)
            return
        if v == 2:
            self._widget.setTristate(True)
        self._widget.setCheckState({0: Qt.Unchecked, 1: Qt.Checked}.get(v, Qt.PartiallyChecked))


class OptionButton(_Graphical, Control):
    TypeName = "OptionButton"
    Events = CheckBox.Events
    _standard_qss = "QRadioButton"
    _checkable = True
    DefaultSize = (121, 25)
    Properties = (
        P("Caption", "str", "", always=True, description="The text; & marks the access key"),
        *_geometry(121, 25),
        P("Value", "bool", False,
          description="Selected; option buttons in the same container are exclusive"),
        *_graphical_props("OptionButton"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        if self._graphical:
            button = self._graphical_widget(parent)
            button.setAutoExclusive(True)  # with the container's other option buttons
            return button
        return QRadioButton(parent)

    def _connect_signals(self):
        self._widget.toggled.connect(lambda checked: checked and self._fire("Click"))

    def _before_rebuild(self):
        self._values["Value"] = self._read_Value()

    def _read_Value(self):
        return self._widget.isChecked()

    def _apply_Value(self, v):
        self._widget.setChecked(v)


# --- Frame ------------------------------------------------------------------------------

class Frame(Control):
    TypeName = "Frame"
    DefaultSize = (185, 129)
    IsContainer = True
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        P("Caption", "str", "", always=True, description="The title shown on the frame"),
        *_geometry(*DefaultSize),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        return QGroupBox(parent)

    def _apply_Caption(self, v):
        self._widget.setTitle(v)

    def _apply_colors(self, _=None):
        _container_palette(self)

    _apply_BackColor = _apply_ForeColor = _apply_colors


# --- ListBox / ComboBox --------------------------------------------------------------------

class _PerItem:
    """A ListBox's or ComboBox's per-item property, like VB's ItemData:
    ``List1.ItemData(2)`` (or ``[2]``) reads item 2's, ``List1.ItemData[2] = 42``
    sets it (VB's ``List1.ItemData(2) = 42``). Indexes start at 0, like
    ListIndex; a value moves with its item (sorting, removing others)."""

    def __init__(self, control, name: str, read, write):
        self._control, self._name = control, name
        self._read, self._write = read, write

    def _check(self, index) -> int:
        index = int(index)
        if not 0 <= index < self._control.ListCount:
            raise IndexError(f"{self._control.TypeName} '{self._control.Name}': no item "
                             f"{index} for {self._name} (ListCount is "
                             f"{self._control.ListCount})")
        return index

    def __call__(self, index):
        return self[index]

    def __getitem__(self, index):
        return self._read(self._check(index))

    def __setitem__(self, index, value):
        self._write(self._check(index), value)

    def __len__(self):
        return self._control.ListCount


# The item roles of ListBox and ComboBox items (Qt's data roles)
_ITEM_DATA_ROLE = Qt.UserRole
_ITEM_IMAGE_ROLE = Qt.UserRole + 1
_NEW_ITEM_ROLE = Qt.UserRole + 2  # (AddItem: finding the item again after sorting)
_CHECKED_ROLE = Qt.UserRole + 3  # (a Checkbox ListBox: the state last seen, for ItemCheck)


class _ListMixin:
    """AddItem / RemoveItem / Clear / ListCount / ListIndex / List shared by
    ListBox and ComboBox, and their per-item ItemData, ItemImage, ItemBold,
    ItemItalic and ItemForeColor. The widget-specific part: ``_role(index,
    role)`` and ``_set_role(index, role, value)``."""

    _IMAGE_LIST_PROPS = ("ImageList",)

    # -- per-item properties ------------------------------------------------------------------
    @property
    def ItemData(self) -> _PerItem:
        """A value kept with each item (any value; VB's was a number), e.g. an
        id for the item's text: ``List1.ItemData[List1.ListIndex]``."""
        return _PerItem(self, "ItemData", lambda i: self._role(i, _ITEM_DATA_ROLE),
                        lambda i, v: self._set_role(i, _ITEM_DATA_ROLE, v))

    @property
    def ItemImage(self) -> _PerItem:
        """Each item's picture: a Key or Index in the control's ImageList, or
        without one a picture file. "" = none."""
        def write(index, value):
            value = "" if value is None else value
            icon = _picture_icon(self, value, strict=True)
            self._set_role(index, _ITEM_IMAGE_ROLE, value)
            self._set_role(index, Qt.DecorationRole, icon if not icon.isNull() else None)

        return _PerItem(self, "ItemImage",
                        lambda i: self._role(i, _ITEM_IMAGE_ROLE) or "", write)

    def _font_part(self, name: str, getter, setter) -> _PerItem:
        def read(index):
            font = self._role(index, Qt.FontRole)
            return bool(font is not None and getter(font))

        def write(index, value):
            font = self._role(index, Qt.FontRole)
            font = QFont(font) if font is not None else QFont(self._widget.font())
            setter(font, bool(value))
            self._set_role(index, Qt.FontRole, font)

        return _PerItem(self, name, read, write)

    @property
    def ItemBold(self) -> _PerItem:
        """Show an item in bold: ``List1.ItemBold[0] = True``."""
        return self._font_part("ItemBold", QFont.bold, QFont.setBold)

    @property
    def ItemItalic(self) -> _PerItem:
        return self._font_part("ItemItalic", QFont.italic, QFont.setItalic)

    @property
    def ItemForeColor(self) -> _PerItem:
        """An item's text color (vpRed, RGB(...)); None = the control's."""
        def read(index):
            brush = self._role(index, Qt.ForegroundRole)
            return colors.from_qcolor(brush.color()) if brush is not None else None

        def write(index, value):
            self._set_role(index, Qt.ForegroundRole,
                           None if value is None else QBrush(colors.to_qcolor(value)))

        return _PerItem(self, "ItemForeColor", read, write)

    def _image_list(self, prop: str = "ImageList"):
        return _UsesImageList._image_list(self, prop)

    def _apply_ImageList(self, v):
        self._refresh_images()

    def _refresh_images(self) -> None:
        """Show every item's ItemImage again (the ImageList or its pictures changed)."""
        images = self._image_list()
        if images is not None and all(images._size()):
            self._widget.setIconSize(QSize(*images._size()))
        for index in range(self.ListCount):
            icon = _picture_icon(self, self._role(index, _ITEM_IMAGE_ROLE) or "")
            self._set_role(index, Qt.DecorationRole, icon if not icon.isNull() else None)

    def AddItem(self, Item, Index: int | None = None) -> None:
        """Add an item, at the end or at Index (from 0); in a Sorted list, where
        the order puts it. NewIndex is then where it is."""
        index = self.ListCount if Index is None else int(Index)
        sorted_list = bool(self._values.get("Sorted"))
        self._insert(index, str(Item), mark=sorted_list)
        if sorted_list:  # sorted in: find it again by its mark
            self._sort()
            index = next(i for i in range(self.ListCount) if self._role(i, _NEW_ITEM_ROLE))
            self._set_role(index, _NEW_ITEM_ROLE, None)
        self.__dict__["_new_index"] = index

    def RemoveItem(self, Index: int) -> None:
        self._remove(int(Index))
        self.__dict__["_new_index"] = -1

    def Clear(self) -> None:
        self._widget.clear()
        self.__dict__["_new_index"] = -1

    @property
    def NewIndex(self) -> int:
        """The index of the item AddItem added last (where sorting put it);
        -1 after RemoveItem or Clear, and before any AddItem."""
        return self.__dict__.get("_new_index", -1)

    @property
    def ListCount(self) -> int:
        return len(self._items())

    def _read_List(self):
        return self._items()

    def _apply_List(self, items):
        self._widget.clear()
        for item in items:
            self._insert(self.ListCount, item)
        if self._values.get("Sorted"):
            self._sort()
        self.__dict__["_new_index"] = -1


_ITEM_IMAGE_LIST = P("ImageList", "str", "",
                     description="The name of an ImageList on the form: the items' ItemImage "
                                 "is then a picture's Key or Index in it")


class ListBox(_ListMixin, Control):
    TypeName = "ListBox"
    DefaultSize = (121, 97)
    Events = ("Click", "DblClick", "ItemCheck", "GotFocus", "LostFocus", "KeyDown", "KeyPress",
              "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QListWidget"
    Properties = (
        P("Style", "enum", 0, enum_choices("Standard", "Checkbox"),
          description="Checkbox: a check box in front of every item; an item is Selected "
                      "while it is checked, and ItemCheck fires when the user changes one"),
        *_geometry(*DefaultSize),
        P("List", "list", [], description="The items"),
        P("Sorted", "bool", False, description="Keep the items in alphabetical order"),
        P("MultiSelect", "enum", 0, enum_choices("None", "Simple", "Extended"),
          description="Whether several items can be selected"),
        _ITEM_IMAGE_LIST,
        *_COLORS, *_FONT, *_COMMON,
    )

    def _role(self, index, role):
        return self._widget.item(index).data(role)

    def _set_role(self, index, role, value):
        self._widget.item(index).setData(role, value)

    def _create_widget(self, parent):
        self.__dict__["_quiet"] = 0  # code changing check boxes: no ItemCheck
        return QListWidget(parent)

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        self._widget.currentRowChanged.connect(lambda *_: self._fire("Click"))
        self._widget.itemChanged.connect(self._on_item_changed)

    def _quietly(self) -> "_Quiet":
        return _Quiet(self)

    @property
    def _checkboxes(self) -> bool:
        return self._values.get("Style", 0) == 1

    def _items(self):
        return [self._widget.item(i).text() for i in range(self._widget.count())]

    def _insert(self, index, text, mark=False):
        item = QListWidgetItem(text)
        if mark:  # before inserting it: a sorted list puts it in its place at once
            item.setData(_NEW_ITEM_ROLE, True)
        self._widget.insertItem(index, item)
        if self._checkboxes:
            self._make_checkable(item, True)

    def _sort(self):
        self._widget.sortItems()

    def _remove(self, index):
        self._widget.takeItem(index)

    def _make_checkable(self, item, checkable: bool) -> None:
        with self._quietly():
            if checkable:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                state = item.checkState() if item.data(Qt.CheckStateRole) is not None \
                    else Qt.Unchecked
                item.setCheckState(state)
                item.setData(_CHECKED_ROLE, state == Qt.Checked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                item.setData(Qt.CheckStateRole, None)
                item.setData(_CHECKED_ROLE, None)

    def _apply_Style(self, v):
        for index in range(self._widget.count()):
            self._make_checkable(self._widget.item(index), v == 1)

    def _on_item_changed(self, item):
        # Any change of an item (its font, its data...) comes here: only a
        # check box the user changed is an ItemCheck
        if self._quiet or not self._checkboxes:
            return
        checked = item.checkState() == Qt.Checked
        if checked != bool(item.data(_CHECKED_ROLE)):
            with self._quietly():
                item.setData(_CHECKED_ROLE, checked)
            self._fire("ItemCheck", self._widget.row(item))

    def _apply_Sorted(self, v):
        self._widget.setSortingEnabled(v)
        if v:
            self._widget.sortItems()

    def _apply_MultiSelect(self, v):
        self._widget.setSelectionMode({
            0: QAbstractItemView.SingleSelection, 1: QAbstractItemView.MultiSelection,
            2: QAbstractItemView.ExtendedSelection}.get(v, QAbstractItemView.SingleSelection))

    @property
    def ListIndex(self) -> int:
        return self._widget.currentRow()

    @ListIndex.setter
    def ListIndex(self, value):
        self._widget.setCurrentRow(int(value))

    @property
    def Text(self) -> str:
        item = self._widget.currentItem()
        return item.text() if item else ""

    @property
    def Selected(self) -> _PerItem:
        """Whether an item is selected (in Checkbox style: checked):
        ``List1.Selected(2)`` reads it, ``List1.Selected[2] = True`` sets it
        (VB's ``List1.Selected(2) = True``; no ItemCheck)."""
        def read(index):
            item = self._widget.item(index)
            return item.checkState() == Qt.Checked if self._checkboxes else item.isSelected()

        def write(index, value):
            item = self._widget.item(index)
            if self._checkboxes:
                with self._quietly():
                    item.setCheckState(Qt.Checked if value else Qt.Unchecked)
                    item.setData(_CHECKED_ROLE, bool(value))
            else:
                item.setSelected(bool(value))

        return _PerItem(self, "Selected", read, write)

    @property
    def SelCount(self) -> int:
        """How many items are selected (in Checkbox style: checked)."""
        return sum(self.Selected(i) for i in range(self.ListCount))

    @property
    def TopIndex(self) -> int:
        """The index of the item at the top of the list (-1 if empty);
        setting it scrolls the list."""
        index = self._widget.indexAt(QPoint(1, 1))
        return index.row() if index.isValid() else (0 if self.ListCount else -1)

    @TopIndex.setter
    def TopIndex(self, value):
        item = self._widget.item(int(value))
        if item is not None:
            self._widget.scrollToItem(item, QAbstractItemView.PositionAtTop)


class _ComboWidget(QComboBox):
    """A QComboBox telling when its list is about to drop down (DropDown)."""

    aboutToDropDown = Signal()

    def showPopup(self):
        self.aboutToDropDown.emit()  # (the list can still be filled)
        super().showPopup()


class _SimpleCombo(QWidget):
    """A Simple Combo (ComboBox Style 1): a text box above a list that is always
    shown. It offers the part of QComboBox's interface ComboBox uses."""

    currentIndexChanged = Signal(int)
    editTextChanged = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.edit = QLineEdit(self)
        self.list = QListWidget(self)
        layout.addWidget(self.edit)
        layout.addWidget(self.list, 1)
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.edit.textChanged.connect(self.editTextChanged.emit)

    def _on_row_changed(self, row):
        if row >= 0:
            self.edit.setText(self.list.item(row).text())  # choosing an item: its text
        self.currentIndexChanged.emit(row)

    def count(self):
        return self.list.count()

    def itemText(self, index):
        return self.list.item(index).text()

    def insertItem(self, index, text):
        self.list.insertItem(index, text)

    def removeItem(self, index):
        self.list.takeItem(index)

    def clear(self):
        self.list.clear()

    def currentIndex(self):
        return self.list.currentRow()

    def setCurrentIndex(self, index):
        self.list.setCurrentRow(index)

    def currentText(self):
        return self.edit.text()

    def setEditText(self, text):
        self.edit.setText(text)

    def isEditable(self):
        return True

    def lineEdit(self):
        return self.edit

    def findText(self, text):
        return next((i for i in range(self.count()) if self.itemText(i) == text), -1)

    def itemData(self, index, role):
        return self.list.item(index).data(role)

    def setItemData(self, index, value, role):
        self.list.item(index).setData(role, value)

    def model(self):
        return self.list.model()

    def view(self):
        return self.list

    def setIconSize(self, size):
        self.list.setIconSize(size)


class ComboBox(_ListMixin, Control):
    TypeName = "ComboBox"
    DefaultSize = (121, 25)
    Events = ("Change", "Click", "DblClick", "DropDown", "GotFocus", "LostFocus", "KeyDown",
              "KeyPress", "KeyUp")
    Properties = (
        P("Style", "enum", 0,
          enum_choices("Dropdown Combo", "Simple Combo", "Dropdown List"),
          description="Dropdown Combo: editable text and a list that drops down; Simple "
                      "Combo: editable text above a list that is always shown (make it tall "
                      "enough); Dropdown List: choose an item only"),
        *_geometry(*DefaultSize),
        P("List", "list", [], description="The items"),
        P("Text", "str", "", always=True, description="The edit text or the selected item"),
        P("Sorted", "bool", False, description="Keep the items in alphabetical order"),
        _ITEM_IMAGE_LIST,
        *_COLORS, *_FONT, *_COMMON,
    )

    def __init__(self, parent, Name: str = "", **props):
        # Pick the right widget up front instead of rebuilding it.
        self.__dict__["_values"] = {"Style": int(props.get("Style") or 0)}
        super().__init__(parent, Name, **props)

    @property
    def _simple(self) -> bool:
        return self._values.get("Style", 0) == 1

    @property
    def _qss_type(self):
        return "QLineEdit" if self._simple else "QComboBox"

    def _create_widget(self, parent):
        if self._simple:
            return _SimpleCombo(parent)
        return _ComboWidget(parent)

    def _event_targets(self):
        if isinstance(self._widget, _SimpleCombo):
            return [self._widget, self._widget.edit, self._widget.list.viewport()]
        return [self._widget]

    def _role(self, index, role):
        return self._widget.itemData(index, role)

    def _set_role(self, index, role, value):
        self._widget.setItemData(index, value, role)

    def _connect_signals(self):
        self._widget.currentIndexChanged.connect(lambda *_: self._fire("Click"))
        self._widget.editTextChanged.connect(lambda *_: self._fire("Change"))
        if isinstance(self._widget, _ComboWidget):
            self._widget.aboutToDropDown.connect(lambda: self._fire("DropDown"))

    def _items(self):
        return [self._widget.itemText(i) for i in range(self._widget.count())]

    def _insert(self, index, text, mark=False):
        self._widget.insertItem(index, text)
        if mark:
            self._set_role(index, _NEW_ITEM_ROLE, True)

    def _sort(self):
        self._widget.model().sort(0)

    def _fire(self, event: str, *args):
        if self.__dict__.get("_restyling"):  # (a new widget being filled)
            return None
        return super()._fire(event, *args)

    def _remove(self, index):
        self._widget.removeItem(index)

    def _apply_Style(self, v):
        if isinstance(self._widget, _SimpleCombo) != (v == 1):
            # Simple Combo is another widget: keep the items, the text and the choice
            self._values["List"], self._values["Text"] = self._items(), self.Text
            index = self.ListIndex
            self.__dict__["_restyling"] = True  # no Click or Change for the refilling
            try:
                self._rebuild_widget()
                if index >= 0:
                    self.ListIndex = index
            finally:
                self.__dict__["_restyling"] = False
        if isinstance(self._widget, _ComboWidget):
            self._widget.setEditable(v != 2)
            if v != 2:
                self._widget.lineEdit().installEventFilter(self._bridge)

    def _apply_Sorted(self, v):
        if v:
            self._sort()

    def _read_Text(self):
        return self._widget.currentText()

    def _apply_Text(self, v):
        if self._widget.isEditable():
            self._widget.setEditText(v)
        else:
            index = self._widget.findText(v)
            if index >= 0:
                self._widget.setCurrentIndex(index)

    @property
    def ListIndex(self) -> int:
        return self._widget.currentIndex()

    @ListIndex.setter
    def ListIndex(self, value):
        self._widget.setCurrentIndex(int(value))

    @property
    def TopIndex(self) -> int:
        """The index of the item at the top of its list (as it drops down, or
        a Simple Combo's); setting it scrolls the list."""
        view = self._widget.view()
        index = view.indexAt(QPoint(1, 1))
        if index.isValid() and view.isVisible():
            return index.row()
        return self.__dict__.get("_top_index", 0 if self.ListCount else -1)

    @TopIndex.setter
    def TopIndex(self, value):
        value = int(value)
        self.__dict__["_top_index"] = value
        model = self._widget.model()
        if 0 <= value < model.rowCount():
            self._widget.view().scrollTo(model.index(value, 0),
                                         QAbstractItemView.PositionAtTop)


# --- DriveListBox, DirListBox and FileListBox ------------------------------------------------

def user_drives() -> list[tuple[str, str]]:
    """(root path, label) of the drives a DriveListBox lists: on Windows every
    drive letter; elsewhere / and the volumes users see (macOS /Volumes/...,
    Linux /media, /mnt, /run/media), not the system's own mounts."""
    from PySide6.QtCore import QStorageInfo

    drives = []
    for volume in QStorageInfo.mountedVolumes():
        if not volume.isValid():
            continue
        root = volume.rootPath()
        if sys.platform != "win32" and root != "/" and not root.startswith(
                ("/Volumes/", "/media/", "/mnt/", "/run/media/")):
            continue
        name = volume.displayName()
        if sys.platform == "win32":
            root = root.rstrip("/\\")[:2].lower() + "\\"  # c:\\
            label = root[:2] + (f" [{name}]" if name and name != volume.rootPath() else "")
        else:
            label = root + (f"  [{name}]" if name and name not in (root, "/") else "")
        if root not in [d[0] for d in drives]:
            drives.append((root, label))
    if not drives:
        drives.append((os.path.abspath(os.sep), os.path.abspath(os.sep)))
    return sorted(drives, key=lambda d: d[0].lower())


def _is_hidden_entry(path: str) -> bool:
    return os.path.basename(path).startswith(".") or QFileInfo(path).isHidden()


_FS_EVENTS = ("GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp")


class DriveListBox(Control):
    """A drop-down list of the drives, like VB's DriveListBox: Drive is the
    chosen one ("c:\\" on Windows, a volume's folder elsewhere); Change fires when
    it changes. Hand it to a DirListBox in Change: ``Dir1.Path = Drive1.Drive``."""

    TypeName = "DriveListBox"
    DefaultEvent = "Change"
    DefaultSize = (161, 25)
    Events = ("Change", *_FS_EVENTS)
    _qss_type = "QComboBox"
    Properties = (*_geometry(*DefaultSize), *_COLORS, *_FONT, *_COMMON)

    def _create_widget(self, parent):
        self.__dict__["_drives"] = []
        combo = QComboBox(parent)
        self.__dict__["_quiet"] = 1  # (filled while being made: no Change)
        self._widget = combo
        self.Refresh()
        start = self._base_dir() if self._design_mode else os.getcwd()
        combo.setCurrentIndex(self._drive_index(start))
        self.__dict__["_quiet"] = 0
        return combo

    def _connect_signals(self):
        self._widget.currentIndexChanged.connect(self._on_changed)

    def _on_changed(self, _index):
        if not self._quiet:
            self._fire("Change")

    def _drive_index(self, path: str) -> int:
        """The drive holding a path: the longest root it starts with."""
        path = os.path.normcase(os.path.abspath(path))
        best, best_length = 0, -1
        for index, (root, _label) in enumerate(self._drives):
            root_case = os.path.normcase(root)
            if path == root_case.rstrip(os.sep) or path.startswith(root_case.rstrip(os.sep) +
                                                                   os.sep) or root_case == os.sep:
                if len(root_case) > best_length:
                    best, best_length = index, len(root_case)
        return best

    def Refresh(self) -> None:
        """List the drives again (e.g. after one was plugged in)."""
        widget = self._widget
        current = self.Drive if widget is not None and widget.count() else None
        self.__dict__["_drives"] = user_drives()
        quiet = self._quiet
        self.__dict__["_quiet"] = 1
        widget.clear()
        for root, label in self._drives:
            widget.addItem(label, root)
        if current is not None:
            widget.setCurrentIndex(self._drive_index(current))
        self.__dict__["_quiet"] = quiet

    @property
    def Drive(self) -> str:
        index = self._widget.currentIndex()
        return self._drives[index][0] if 0 <= index < len(self._drives) else ""

    @Drive.setter
    def Drive(self, value):
        """Choose the drive holding this path (a drive, or any folder on it)."""
        value = str(value)
        if sys.platform == "win32" and len(value) >= 2 and value[1] == ":":
            value = value[:2] + "\\"
        if not os.path.exists(value):
            raise FileNotFoundError(f"DriveListBox '{self.Name}': no drive {value!r}")
        self._widget.setCurrentIndex(self._drive_index(value))

    @property
    def List(self) -> list[str]:
        return [label for _root, label in self._drives]

    @property
    def ListCount(self) -> int:
        return len(self._drives)

    @property
    def ListIndex(self) -> int:
        return self._widget.currentIndex()

    @ListIndex.setter
    def ListIndex(self, value):
        self._widget.setCurrentIndex(int(value))


class _DirList:
    """DirListBox.List: ``List(-1)`` is the folder shown (Path), ``List(-2)``
    its parent and so on up; ``List(0)`` ... ``List(ListCount - 1)`` its
    subfolders (full paths), as in VB."""

    def __init__(self, box: "DirListBox"):
        self._box = box

    def __call__(self, index: int) -> str:
        return self[index]

    def __getitem__(self, index: int) -> str:
        index = int(index)
        subfolders, ancestors = self._box._subfolders, self._box._ancestors
        if 0 <= index < len(subfolders):
            return subfolders[index]
        if -len(ancestors) <= index < 0:
            return ancestors[len(ancestors) + index]
        raise IndexError(f"DirListBox '{self._box.Name}': no List({index})")

    def __len__(self):
        return len(self._box._subfolders)

    def __iter__(self):
        return iter(list(self._box._subfolders))


class _DirTree(QTreeWidget):
    """The DirListBox's tree: indented folders without expand arrows."""

    def drawBranches(self, painter, rect, index):
        pass


class DirListBox(Control):
    """The folders, like VB's DirListBox: the folder shown (Path) with the
    folders above it, then its subfolders. Double-clicking a folder opens it
    (Path changes, Change fires); clicking one selects it (ListIndex, Click).
    Hand Path to a FileListBox in Change: ``File1.Path = Dir1.Path``."""

    TypeName = "DirListBox"
    DefaultEvent = "Change"
    DefaultSize = (161, 145)
    Events = ("Change", "Click", *_FS_EVENTS, "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QTreeWidget"
    Properties = (
        *_geometry(*DefaultSize),
        P("ShowHidden", "bool", False,
          description="Also list hidden folders (on macOS and Linux, those starting with .)"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_path="", _ancestors=[], _subfolders=[], _quiet=0)
        tree = _DirTree(parent)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(False)
        tree.setItemsExpandable(False)
        tree.setIndentation(14)
        self._widget = tree
        self._show(self._base_dir() if self._design_mode else os.getcwd())
        return tree

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        self._widget.itemDoubleClicked.connect(self._on_double_click)
        self._widget.currentItemChanged.connect(self._on_current_changed)

    def _show(self, path: str) -> None:
        """Fill the tree for a folder: its chain of ancestors, then its subfolders."""
        path = os.path.abspath(path)
        ancestors, folder = [], path
        while True:
            ancestors.insert(0, folder)
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
        try:
            names = sorted((n for n in os.listdir(path)
                            if os.path.isdir(os.path.join(path, n))), key=str.lower)
        except OSError:
            names = []
        subfolders = [os.path.join(path, n) for n in names
                      if self._values.get("ShowHidden") or
                      not _is_hidden_entry(os.path.join(path, n))]
        self.__dict__.update(_path=path, _ancestors=ancestors, _subfolders=subfolders)
        style = QApplication.style()
        open_icon, closed_icon = (style.standardIcon(QStyle.SP_DirOpenIcon),
                                  style.standardIcon(QStyle.SP_DirClosedIcon))
        tree = self._widget
        self.__dict__["_quiet"] += 1
        try:
            tree.clear()
            parent = None
            for folder in ancestors:  # each ancestor one level deeper
                item = QTreeWidgetItem([os.path.basename(folder) or folder])
                item.setIcon(0, open_icon)
                item.setData(0, Qt.UserRole, folder)
                if parent is None:
                    tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                parent = item
            current = parent
            for folder in subfolders:
                item = QTreeWidgetItem([os.path.basename(folder)])
                item.setIcon(0, closed_icon)
                item.setData(0, Qt.UserRole, folder)
                current.addChild(item)
            tree.expandAll()
            tree.setCurrentItem(current)
        finally:
            self.__dict__["_quiet"] -= 1

    def _on_double_click(self, item, _column):
        if not self._design_mode:
            self.Path = item.data(0, Qt.UserRole)

    def _on_current_changed(self, current, _previous):
        if not self._quiet and current is not None:
            self._fire("Click")

    @property
    def Path(self) -> str:
        return self._path

    @Path.setter
    def Path(self, value):
        """Show a folder (Change fires if it's another one)."""
        path = os.path.abspath(str(value))
        if not os.path.isdir(path):
            raise FileNotFoundError(f"DirListBox '{self.Name}': no folder {value!r}")
        changed = os.path.normcase(path) != os.path.normcase(self._path)
        self._show(path)
        if changed:
            self._fire("Change")

    @property
    def List(self) -> _DirList:
        return _DirList(self)

    @property
    def ListCount(self) -> int:
        """How many subfolders the folder shown has."""
        return len(self._subfolders)

    @property
    def ListIndex(self) -> int:
        """The selected folder: -1 for Path itself, -2 its parent..., 0... a
        subfolder."""
        item = self._widget.currentItem()
        folder = item.data(0, Qt.UserRole) if item is not None else self._path
        if folder in self._subfolders:
            return self._subfolders.index(folder)
        return self._ancestors.index(folder) - len(self._ancestors)

    @ListIndex.setter
    def ListIndex(self, value):
        folder = self.List[int(value)]
        item = next(i for i in _walk_tree(self._widget) if i.data(0, Qt.UserRole) == folder)
        self._widget.setCurrentItem(item)

    def Refresh(self) -> None:
        """Read the folder again (e.g. after a subfolder was made)."""
        self._show(self._path)

    def _apply_ShowHidden(self, v):
        if self._path:
            self._show(self._path)


def file_matches(name: str, pattern: str) -> bool:
    """Whether a file name matches a FileListBox Pattern: wildcards (* and ?),
    several separated by ; ("*.png;*.jpg"), not case-sensitive; *.* also
    matches names without an extension, as in VB."""
    import fnmatch

    name = name.lower()
    for part in (pattern or "*.*").split(";"):
        part = part.strip().lower()
        if not part:
            continue
        if part == "*.*":
            part = "*"
        if fnmatch.fnmatchcase(name, part):
            return True
    return False


class FileListBox(ListBox):
    """The files in a folder, like VB's FileListBox: those in Path whose names
    match Pattern ("*.*" = all; "*.png;*.jpg"). FileName is the selected one
    (a name; join it with Path). PathChange and PatternChange fire when those
    change; Click and DblClick as in a ListBox, whose selection, MultiSelect
    and per-item properties it has (its items come from the folder, so it has
    no AddItem, RemoveItem or Clear)."""

    TypeName = "FileListBox"
    DefaultEvent = "Click"
    DefaultSize = (161, 145)
    Events = ("Click", "DblClick", "PathChange", "PatternChange", *_FS_EVENTS, "MouseDown",
              "MouseMove", "MouseUp")
    Properties = (
        *_geometry(*DefaultSize),
        P("Pattern", "str", "*.*",
          description="Which files are listed: wildcards, several separated by ; "
                      "(*.txt;*.py); *.* lists all"),
        P("Hidden", "bool", False,
          description="Also list hidden files (on macOS and Linux, those starting with .)"),
        P("MultiSelect", "enum", 0, enum_choices("None", "Simple", "Extended"),
          description="Whether several files can be selected"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        widget = super()._create_widget(parent)
        self.__dict__["_path"] = os.path.abspath(self._base_dir() if self._design_mode
                                                 else os.getcwd())
        return widget

    def _fill(self) -> None:
        path = self._path
        hidden, pattern = self._values.get("Hidden"), self._values.get("Pattern", "*.*")
        try:
            names = sorted((n for n in os.listdir(path)
                            if os.path.isfile(os.path.join(path, n))), key=str.lower)
        except OSError:
            names = []
        widget = self._widget
        with self._quietly():
            widget.blockSignals(True)  # (no Click while refilling)
            try:
                widget.clear()
                for name in names:
                    if file_matches(name, pattern) and (
                            hidden or not _is_hidden_entry(os.path.join(path, name))):
                        self._insert(widget.count(), name)
            finally:
                widget.blockSignals(False)
        self.__dict__["_new_index"] = -1

    def _apply_Pattern(self, v):
        self._fill()
        if not self._loading_or_design():
            self._fire("PatternChange")

    def _apply_Hidden(self, v):
        self._fill()

    def _loading_or_design(self) -> bool:
        return self._design_mode or not self.__dict__.get("_ready")

    def __init__(self, parent, Name: str = "", **props):
        super().__init__(parent, Name, **props)
        self.__dict__["_ready"] = True  # (Pattern set by the designer: no PatternChange)

    @property
    def Path(self) -> str:
        return self._path

    @Path.setter
    def Path(self, value):
        """List the files of another folder (PathChange fires if it's another one)."""
        path = os.path.abspath(str(value))
        if not os.path.isdir(path):
            raise FileNotFoundError(f"FileListBox '{self.Name}': no folder {value!r}")
        changed = os.path.normcase(path) != os.path.normcase(self._path)
        self.__dict__["_path"] = path
        self._fill()
        if changed:
            self._fire("PathChange")

    @property
    def FileName(self) -> str:
        """The selected file's name ("" if none). Setting it to a folder sets
        Path, to a pattern (with * or ?) sets Pattern, to a folder and a
        pattern sets both, and to a file's name selects it."""
        return self.Text

    @FileName.setter
    def FileName(self, value):
        value = str(value)
        folder, name = os.path.split(value)
        if os.path.isdir(value):
            self.Path = value
            return
        if folder:
            self.Path = folder
        if any(c in name for c in "*?;"):
            self.Pattern = name
        elif name:
            items = self._items()
            match = next((i for i, n in enumerate(items) if n.lower() == name.lower()), None)
            if match is None:
                raise FileNotFoundError(f"FileListBox '{self.Name}': no file {name!r} listed")
            self.ListIndex = match

    @property
    def List(self) -> list[str]:
        """The file names listed."""
        return self._items()

    def Refresh(self) -> None:
        """Read the folder again (e.g. after a file was saved in it)."""
        selected = self.FileName
        self._fill()
        if selected in self._items():
            with self._quietly():
                self._widget.blockSignals(True)
                self._widget.setCurrentRow(self._items().index(selected))
                self._widget.blockSignals(False)

    def _no_items(self, *args, **kwargs):
        raise AttributeError(f"FileListBox '{self.Name}': its items are the files in Path "
                             "(set Path and Pattern instead)")

    AddItem = RemoveItem = Clear = _no_items


def _walk_tree(tree: QTreeWidget):
    """Every item of a QTreeWidget (by child(), not an iterator)."""
    def walk(item):
        yield item
        for i in range(item.childCount()):
            yield from walk(item.child(i))
    for i in range(tree.topLevelItemCount()):
        yield from walk(tree.topLevelItem(i))


# --- Timer ------------------------------------------------------------------------------------

class Timer(Control):
    """Invisible at run time; fires the Timer event every Interval ms."""

    TypeName = "Timer"
    DefaultEvent = "Timer"
    DefaultSize = (32, 32)
    Events = ("Timer",)
    Properties = (
        P("Left", "int", 0, always=True, description="Position in the designer only"),
        P("Top", "int", 0, always=True, description="Position in the designer only"),
        P("Interval", "int", 0, description="Milliseconds between Timer events (0 = off)"),
        P("Enabled", "bool", True, description="Whether the Timer event fires"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self._timer = None
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        if self._design_mode:
            return _timer_design_widget(parent)
        self._timer = QTimer()
        self._timer.timeout.connect(lambda: self._fire("Timer"))
        return None

    def _read_Width(self):
        return 32

    def _read_Height(self):
        return 32

    def _update_timer(self):
        if self._timer is None:
            return
        interval = self._values.get("Interval", 0)
        if self._values.get("Enabled", True) and interval > 0:
            self._timer.start(interval)
        else:
            self._timer.stop()

    def _apply_Interval(self, v):
        self._update_timer()

    def _apply_Enabled(self, v):
        self._update_timer()


def _timer_design_widget(parent: QWidget) -> QLabel:
    """The stopwatch icon the designer shows for a Timer."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.5))
    painter.setBrush(QColor("#fffbe6"))
    painter.drawEllipse(3, 5, 20, 20)
    painter.drawRect(11, 1, 4, 3)
    painter.drawLine(13, 15, 13, 8)
    painter.drawLine(13, 15, 18, 15)
    painter.end()
    label = QLabel(parent)
    label.setFixedSize(32, 32)
    label.setAlignment(Qt.AlignCenter)
    label.setFrameStyle(QFrame.Panel | QFrame.Raised)
    label.setPixmap(pixmap)
    return label


# --- Scroll bars ------------------------------------------------------------------------------

class _ScrollBar(Control):
    DefaultEvent = "Change"
    Events = ("Change", "Scroll", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp")
    _orientation = Qt.Horizontal
    _qss_type = "QScrollBar"

    def _create_widget(self, parent):
        return QScrollBar(self._orientation, parent)

    def _connect_signals(self):
        self._widget.valueChanged.connect(lambda *_: self._fire("Change"))
        self._widget.sliderMoved.connect(lambda *_: self._fire("Scroll"))

    def _apply_Min(self, v):
        self._widget.setMinimum(v)

    def _apply_Max(self, v):
        self._widget.setMaximum(v)

    def _read_Value(self):
        return self._widget.value()

    def _apply_Value(self, v):
        self._widget.setValue(v)

    def _apply_SmallChange(self, v):
        self._widget.setSingleStep(v)

    def _apply_LargeChange(self, v):
        self._widget.setPageStep(v)


def _scroll_props(width, height):
    return (
        *_geometry(width, height),
        P("Min", "int", 0, description="Smallest Value"),
        P("Max", "int", 32767, description="Largest Value"),
        P("Value", "int", 0, description="The current position; changing it fires Change"),
        P("SmallChange", "int", 1, description="Step for the arrow buttons"),
        P("LargeChange", "int", 1, description="Step for clicks on the track"),
        *_COMMON,
    )


class HScrollBar(_ScrollBar):
    TypeName = "HScrollBar"
    DefaultSize = (121, 17)
    Properties = _scroll_props(*DefaultSize)


class VScrollBar(_ScrollBar):
    TypeName = "VScrollBar"
    DefaultSize = (17, 121)
    _orientation = Qt.Vertical
    Properties = _scroll_props(*DefaultSize)


# --- ProgressBar, Slider and UpDown (VB's Windows Common Controls) -----------------------------

_ORIENTATION = enum_choices("Horizontal", "Vertical")
_QT_ORIENTATION = {0: Qt.Horizontal, 1: Qt.Vertical}


def _clamp(value, low, high) -> int:
    return max(low, min(high, int(value))) if low <= high else low


class ProgressBar(Control):
    """Shows how far an operation has got: a bar filled from Min to Max as
    Value grows. A Value outside Min..Max is kept at the nearer end."""

    TypeName = "ProgressBar"
    DefaultSize = (161, 25)
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QProgressBar"
    Properties = (
        *_geometry(*DefaultSize),
        P("Min", "int", 0, description="Value when the bar is empty"),
        P("Max", "int", 100, description="Value when the bar is full"),
        P("Value", "int", 0, description="How far along: from Min (empty) to Max (full)"),
        P("Orientation", "enum", 0, _ORIENTATION,
          description="Horizontal (filling to the right) or Vertical (filling upwards)"),
        P("Enabled", "bool", True, description="Whether the control responds to the user"),
        P("Visible", "bool", True, description="Whether the control is shown at run time"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
        P("ZIndex", "int", 0, description=_COMMON[-1].description),
    )

    def _create_widget(self, parent):
        widget = QProgressBar(parent)
        widget.setTextVisible(False)  # like VB's: just the bar
        widget.setFocusPolicy(Qt.NoFocus)
        return widget

    def _apply_Min(self, v):
        self._widget.setMinimum(int(v))
        self._apply_Value(self._values.get("Value", 0))

    def _apply_Max(self, v):
        self._widget.setMaximum(int(v))
        self._apply_Value(self._values.get("Value", 0))

    def _read_Value(self):
        return self._widget.value()

    def _apply_Value(self, v):
        value = _clamp(v, self._widget.minimum(), self._widget.maximum())
        self._values["Value"] = value
        self._widget.setValue(value)

    def _apply_Orientation(self, v):
        self._widget.setOrientation(_QT_ORIENTATION.get(v, Qt.Horizontal))


class Slider(Control):
    """A thumb dragged along a scale with tick marks, like VB's Slider.
    Scroll fires while the thumb is dragged, Change once the Value has
    changed (when the drag ends, or at once for keys, clicks and code)."""

    TypeName = "Slider"
    DefaultEvent = "Scroll"
    DefaultSize = (161, 41)
    Events = ("Scroll", "Change", "Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress",
              "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QSlider"
    Properties = (
        *_geometry(*DefaultSize),
        P("Min", "int", 0, description="Smallest Value"),
        P("Max", "int", 10, description="Largest Value"),
        P("Value", "int", 0, description="The thumb's position; changing it fires Change"),
        P("SmallChange", "int", 1, description="Step for the arrow keys"),
        P("LargeChange", "int", 5,
          description="Step for Page Up / Page Down and clicks beside the thumb"),
        P("Orientation", "enum", 0, _ORIENTATION, description="Horizontal or Vertical"),
        P("TickStyle", "enum", 0,
          enum_choices("Bottom/Right", "Top/Left", "Both", "No Ticks"),
          description="Where the tick marks are: below (right of) the scale, above (left of) "
                      "it, on both sides, or none"),
        P("TickFrequency", "int", 1, description="A tick mark every this many values"),
        *_COMMON,
    )
    _TICKS = {0: QSlider.TicksBelow, 1: QSlider.TicksAbove, 2: QSlider.TicksBothSides,
              3: QSlider.NoTicks}

    def _create_widget(self, parent):
        self.__dict__["_changed_while_dragging"] = False
        widget = QSlider(Qt.Horizontal, parent)
        widget.setTickPosition(QSlider.TicksBelow)
        return widget

    def _connect_signals(self):
        self._widget.valueChanged.connect(self._on_value_changed)
        self._widget.sliderReleased.connect(self._on_released)

    def _on_value_changed(self, _value):
        if self._widget.isSliderDown():  # being dragged: Change when it's let go
            self.__dict__["_changed_while_dragging"] = True
            self._fire("Scroll")
        else:
            self._fire("Change")

    def _on_released(self):
        if self._changed_while_dragging:
            self.__dict__["_changed_while_dragging"] = False
            self._fire("Change")

    def _apply_Min(self, v):
        self._widget.setMinimum(int(v))

    def _apply_Max(self, v):
        self._widget.setMaximum(int(v))

    def _read_Value(self):
        return self._widget.value()

    def _apply_Value(self, v):
        self._widget.setValue(int(v))

    def _apply_SmallChange(self, v):
        self._widget.setSingleStep(int(v))

    def _apply_LargeChange(self, v):
        self._widget.setPageStep(int(v))

    def _apply_Orientation(self, v):
        self._widget.setOrientation(_QT_ORIENTATION.get(v, Qt.Horizontal))

    def _apply_TickStyle(self, v):
        self._widget.setTickPosition(self._TICKS.get(v, QSlider.TicksBelow))

    def _apply_TickFrequency(self, v):
        self._widget.setTickInterval(max(0, int(v)))


class _UpDownWidget(QWidget):
    """Two arrow buttons, stacked (vertical) or side by side (horizontal)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.layout_ = QBoxLayout(QBoxLayout.TopToBottom, self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(0)
        self.up, self.down = QToolButton(self), QToolButton(self)
        for button in (self.up, self.down):
            button.setAutoRepeat(True)  # held down: steps on
            button.setFocusPolicy(Qt.NoFocus)
            button.setSizePolicy(button.sizePolicy().Policy.Expanding,
                                 button.sizePolicy().Policy.Expanding)
        self.set_vertical(True)

    def set_vertical(self, vertical: bool) -> None:
        for button in (self.up, self.down):
            self.layout_.removeWidget(button)
        if vertical:  # up above down
            self.layout_.setDirection(QBoxLayout.TopToBottom)
            self.up.setArrowType(Qt.UpArrow)
            self.down.setArrowType(Qt.DownArrow)
            self.layout_.addWidget(self.up)
            self.layout_.addWidget(self.down)
        else:  # down (left) beside up (right)
            self.layout_.setDirection(QBoxLayout.LeftToRight)
            self.up.setArrowType(Qt.RightArrow)
            self.down.setArrowType(Qt.LeftArrow)
            self.layout_.addWidget(self.down)
            self.layout_.addWidget(self.up)


class UpDown(Control):
    """A pair of arrow buttons that step a Value up or down, like VB's UpDown.
    With a BuddyControl and SyncBuddy, the buddy (e.g. a TextBox) shows the
    Value, and a number typed into it is where the next click starts."""

    TypeName = "UpDown"
    DefaultEvent = "Change"
    DefaultSize = (17, 33)
    Events = ("Change", "UpClick", "DownClick", "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QToolButton"
    Properties = (
        *_geometry(*DefaultSize),
        P("Min", "int", 0, description="Smallest Value"),
        P("Max", "int", 10, description="Largest Value"),
        P("Value", "int", 0,
          description="The current value, kept between Min and Max; changing it fires Change"),
        P("Increment", "int", 1, description="How much a click on an arrow changes Value"),
        P("Wrap", "bool", False,
          description="Past Max go on from Min (and below Min from Max) instead of stopping"),
        P("Orientation", "enum", 1, _ORIENTATION,
          description="Vertical (up and down arrows) or Horizontal (left and right arrows)"),
        P("BuddyControl", "str", "",
          description="The name of the control that shows the Value (e.g. a TextBox), on "
                      "the same form"),
        P("BuddyProperty", "str", "",
          description="The buddy's property that shows the Value; empty = its Text, or its "
                      "Caption"),
        P("SyncBuddy", "bool", False,
          description="Keep the buddy's property and the Value in step"),
        P("Enabled", "bool", True, description="Whether the control responds to the user"),
        P("Visible", "bool", True, description="Whether the control is shown at run time"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
        P("ZIndex", "int", 0, description=_COMMON[-1].description),
    )

    def _create_widget(self, parent):
        return _UpDownWidget(parent)

    def _event_targets(self):
        return [self._widget, self._widget.up, self._widget.down]

    def _connect_signals(self):
        self._widget.up.clicked.connect(lambda: self._step(+1))
        self._widget.down.clicked.connect(lambda: self._step(-1))

    # -- the buddy -------------------------------------------------------------------------
    @property
    def Buddy(self):
        """The BuddyControl, or None (no name, or no such control)."""
        name = self._values.get("BuddyControl", "")
        return getattr(self._form, name, None) if name else None

    def _buddy_property(self, buddy) -> str | None:
        name = self._values.get("BuddyProperty", "")
        if name:
            return name
        for candidate in ("Text", "Caption"):
            if candidate in getattr(buddy, "_specs", {}):
                return candidate
        return None

    def _sync_to_buddy(self) -> None:
        buddy = self.Buddy
        if not self._values.get("SyncBuddy") or buddy is None or self._design_mode:
            return
        prop = self._buddy_property(buddy)
        if prop is not None:
            setattr(buddy, prop, str(self.Value))

    def _value_from_buddy(self) -> None:
        """A number typed into the buddy is where a click starts from."""
        buddy = self.Buddy
        if not self._values.get("SyncBuddy") or buddy is None:
            return
        prop = self._buddy_property(buddy)
        try:
            typed = int(str(getattr(buddy, prop)).strip())
        except (TypeError, ValueError, AttributeError):
            return
        value = _clamp(typed, self.Min, self.Max)
        self._values["Value"] = self.__dict__["_shown_value"] = value  # (no Change: not yet)

    # -- stepping ----------------------------------------------------------------------------
    def _step(self, direction: int) -> None:
        if self._design_mode:
            return
        self._value_from_buddy()
        low, high = self.Min, self.Max
        value = self.Value + direction * self.Increment
        if self.Wrap and value > high:
            value = low
        elif self.Wrap and value < low:
            value = high
        self.Value = value
        self._sync_to_buddy()  # (also when the Value stays, e.g. a typed 99 over Max)
        self._fire("UpClick" if direction > 0 else "DownClick")

    def _apply_Value(self, v):
        value = _clamp(v, self._values.get("Min", 0), self._values.get("Max", 10))
        old = self.__dict__.get("_shown_value")
        self._values["Value"] = value
        self.__dict__["_shown_value"] = value
        if old is not None and old != value:
            self._sync_to_buddy()
            self._fire("Change")

    def _apply_Min(self, v):
        self._apply_Value(self._values.get("Value", 0))

    _apply_Max = _apply_Min

    def _apply_Orientation(self, v):
        self._widget.set_vertical(v != 0)


# --- PictureBox ---------------------------------------------------------------------------------

class _ScrollWatcher(QObject):
    """Keeps a scrolling PictureBox's content as large as its controls need:
    it watches the content (controls added or removed), the controls (moved,
    resized, shown, hidden) and the visible area (resized)."""

    _EVENTS = (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide)

    def __init__(self, picture: "PictureBox", content: QWidget):
        super().__init__(content)
        self._picture = picture
        self._pending = False

    def eventFilter(self, watched, event):
        etype = event.type()
        if etype == QEvent.ChildAdded and isinstance(event.child(), QWidget):
            event.child().installEventFilter(self)
            self._schedule()
        elif etype == QEvent.ChildRemoved or etype in self._EVENTS:
            self._schedule()
        return False

    def _schedule(self) -> None:
        if not self._pending:  # once per round of changes
            self._pending = True
            QTimer.singleShot(0, self, self._update)

    def _update(self) -> None:
        self._pending = False
        self._picture._update_scroll_size()


class _Docked:
    """For controls with an Align property (PictureBox, Splitter, StatusBar):
    docked, the form places and sizes them (Form._layout_aligned) whenever
    their Align, size, place or visibility changes; undocked, they are
    ordinary controls."""

    def _relayout(self) -> None:
        """Docked (or just undocked): let the form place its aligned panes."""
        if self in self._form._controls:
            self._form._layout_aligned()

    def _apply_Align(self, v):
        self._relayout()

    def _apply_Width(self, v):
        if self._values.get("Align") and self in self._form._controls:
            self._relayout()  # docked: the form resizes it, all panes at once
        else:
            super()._apply_Width(v)

    def _apply_Height(self, v):
        if self._values.get("Align") and self in self._form._controls:
            self._relayout()
        else:
            super()._apply_Height(v)

    def _apply_Left(self, v):
        super()._apply_Left(v)
        if self._values.get("Align"):
            self._relayout()  # an aligned pane stays where the form puts it

    def _apply_Top(self, v):
        super()._apply_Top(v)
        if self._values.get("Align"):
            self._relayout()

    def _apply_Visible(self, v):
        super()._apply_Visible(v)
        if self._values.get("Align"):
            self._relayout()  # a hidden pane gives its space to the others


class PictureBox(_Docked, Control):
    TypeName = "PictureBox"
    DefaultSize = (121, 97)
    IsContainer = True
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp", "Resize", "Scroll")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("Picture", "file", "", description="Image file (relative to the form's folder)"),
        P("Stretch", "bool", False, description="Scale the picture to fit the control"),
        P("AutoSize", "bool", False, description="Resize to fit the picture"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A sunken border around the picture"),
        P("Align", "enum", 0, enum_choices("None", "Top", "Bottom", "Left", "Right", "Fill"),
          description="Dock to that edge of the form and follow its size, keeping the height "
                      "(Top, Bottom) or width (Left, Right); Fill takes all the space the "
                      "others leave; only on the form itself"),
        P("ScrollBars", "enum", 0, enum_choices("None", "Horizontal", "Vertical", "Both"),
          description="Scroll bars that appear when the controls in it reach beyond its "
                      "edges (at run time); the picture stays in place"),
        *_COLORS, *_COMMON,
    )

    def _create_widget(self, parent):
        label = QLabel(parent)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.__dict__["_scroll_area"] = None  # with ScrollBars: see _apply_ScrollBars
        return label

    def _on_qt_event(self, watched, event):
        if event.type() == QEvent.Resize and watched is self._widget:
            if self._scroll_area is not None:
                self._scroll_area.setGeometry(self._widget.contentsRect())
            self._fire("Resize")  # e.g. a docked pane resized by its form or a Splitter
        return super()._on_qt_event(watched, event)

    # -- scrolling -------------------------------------------------------------------------
    def _container_widget(self) -> QWidget:
        area = self.__dict__.get("_scroll_area")
        return area.widget() if area is not None else self._widget

    def _fill_widget(self) -> QWidget:
        area = self._scroll_area
        return area.viewport() if area is not None else self._widget

    def _fill_rect(self, designed: QSize) -> QRect:
        """Scrolling: a form fills the visible area but keeps at least its own
        size, so a taller (or wider) one scrolls."""
        area = self._scroll_area
        if area is None:
            return self._widget.contentsRect()
        view = area.viewport().size()
        width = view.width() if self._values.get("ScrollBars") in (0, 2) else \
            max(view.width(), designed.width())
        height = view.height() if self._values.get("ScrollBars") in (0, 1) else \
            max(view.height(), designed.height())
        return QRect(0, 0, width, height)

    def _apply_ScrollBars(self, v):
        if self._design_mode:
            return  # the designer shows the controls where they are
        if v and self._scroll_area is None:
            self._start_scrolling()
        elif not v and self._scroll_area is not None:
            self._stop_scrolling()
        area = self._scroll_area
        if area is not None:
            area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarAsNeeded if v in (1, 3) else Qt.ScrollBarAlwaysOff)
            area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded if v in (2, 3) else Qt.ScrollBarAlwaysOff)
            self._update_scroll_size()

    def _start_scrolling(self) -> None:
        """Put the controls on a content widget in a scroll area over the
        picture; the content grows to hold them all."""
        label = self._widget
        area = QScrollArea(label)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidgetResizable(False)
        area.setAutoFillBackground(False)
        area.viewport().setAutoFillBackground(False)  # the PictureBox shows through
        content = QWidget()
        content.setAutoFillBackground(False)
        for child in label.children():
            if isinstance(child, QWidget) and child is not area and not child.isWindow():
                shown = not child.isHidden()
                child.setParent(content)
                if shown:
                    child.show()
        area.setWidget(content)
        watcher = _ScrollWatcher(self, content)
        content.installEventFilter(watcher)
        area.viewport().installEventFilter(watcher)
        for child in content.children():
            if isinstance(child, QWidget):
                child.installEventFilter(watcher)
        if self._bridge is not None:  # clicks on the empty area are the PictureBox's
            content.installEventFilter(self._bridge)  # it covers the whole visible area
            content.setMouseTracking(True)
        area.horizontalScrollBar().valueChanged.connect(self._on_scrolled)
        area.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        area.setGeometry(label.contentsRect())
        area.show()
        self.__dict__["_scroll_area"] = area

    def _stop_scrolling(self) -> None:
        area, label = self._scroll_area, self._widget
        content = area.takeWidget()
        for child in content.children():
            if isinstance(child, QWidget) and not child.isWindow():
                shown = not child.isHidden()
                child.setParent(label)
                if shown:
                    child.show()
        content.deleteLater()
        area.hide()
        area.deleteLater()
        self.__dict__["_scroll_area"] = None

    def _update_scroll_size(self) -> None:
        """The content is as large as the controls in it need (at least the
        visible area), so the scroll bars appear exactly when needed."""
        area = self._scroll_area
        if area is None:
            return
        content = area.widget()
        right = bottom = 0
        for child in content.children():
            if isinstance(child, QWidget) and not child.isHidden():
                right = max(right, child.geometry().right() + 1)
                bottom = max(bottom, child.geometry().bottom() + 1)
        full = area.contentsRect().size()  # the visible area without scroll bars
        if right <= full.width() and bottom <= full.height():
            content.resize(full)  # everything fits: no bars, in one step
            return
        view = area.viewport().size()
        content.resize(max(right, view.width()), max(bottom, view.height()))

    def _on_scrolled(self, *_):
        self._fire("Scroll")

    @property
    def ScrollLeft(self) -> int:
        """How far the contents are scrolled to the left (0 without ScrollBars)."""
        area = self._scroll_area
        return area.horizontalScrollBar().value() if area is not None else 0

    @ScrollLeft.setter
    def ScrollLeft(self, value):
        if self._scroll_area is not None:
            self._update_scroll_size()  # controls just added or moved count already
            self._scroll_area.horizontalScrollBar().setValue(int(value))

    @property
    def ScrollTop(self) -> int:
        """How far the contents are scrolled up (0 without ScrollBars)."""
        area = self._scroll_area
        return area.verticalScrollBar().value() if area is not None else 0

    @ScrollTop.setter
    def ScrollTop(self, value):
        if self._scroll_area is not None:
            self._update_scroll_size()
            self._scroll_area.verticalScrollBar().setValue(int(value))

    def _apply_Picture(self, v):
        path = resolve_path(self, v)
        pixmap = QPixmap(path) if path else QPixmap()
        self._widget.setPixmap(pixmap)
        if self._values.get("AutoSize") and not pixmap.isNull():
            self._widget.resize(pixmap.size())

    def _apply_Stretch(self, v):
        self._widget.setScaledContents(v)

    def _apply_AutoSize(self, v):
        if v and self._widget.pixmap() and not self._widget.pixmap().isNull():
            self._widget.resize(self._widget.pixmap().size())

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.Panel | QFrame.Sunken if v else QFrame.NoFrame)

    def _apply_colors(self, _=None):
        _container_palette(self)
        # Opaque like VB's PictureBox (the scheme's window color without a
        # BackColor), so e.g. a docked pane covers what is underneath
        if self._widget is not None:
            self._widget.setAutoFillBackground(True)

    _apply_BackColor = _apply_ForeColor = _apply_colors

    def Cls(self) -> None:
        self._widget.clear()


class Image(Control):
    """A lightweight picture: no container, no focus, no Tab stop, and a
    transparent background, like VB's Image. With Stretch = False it takes
    the size of its picture; with Stretch = True the picture fills it."""

    TypeName = "Image"
    DefaultSize = (97, 97)
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QLabel"
    Properties = (
        *_geometry(*DefaultSize),
        # Stretch and BorderStyle before Picture: loading the picture sizes the control
        P("Stretch", "bool", False,
          description="True: the picture is scaled to fill the control. False: the control "
                      "takes the size of the picture"),
        P("BorderStyle", "enum", 0, enum_choices("None", "Fixed Single"),
          description="A thin border around the image"),
        P("Picture", "file", "", description="Image file (relative to the form's folder)"),
        *(spec for spec in _COMMON if spec.name != "TabIndex"),
    )

    def _create_widget(self, parent):
        label = QLabel(parent)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setFocusPolicy(Qt.NoFocus)
        return label

    def _pixmap(self) -> QPixmap:
        pixmap = self._widget.pixmap()
        return pixmap if pixmap is not None else QPixmap()

    def _fit_to_picture(self) -> None:
        """Stretch = False: the control takes the picture's size (plus a border)."""
        pixmap = self._pixmap()
        if self._values.get("Stretch") or pixmap.isNull():
            return
        border = 2 * self._widget.frameWidth()
        self._widget.resize(pixmap.width() + border, pixmap.height() + border)

    def _apply_Picture(self, v):
        path = resolve_path(self, v)
        self._widget.setPixmap(QPixmap(path) if path else QPixmap())
        self._fit_to_picture()

    def _apply_Stretch(self, v):
        self._widget.setScaledContents(bool(v))
        self._fit_to_picture()

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.Box | QFrame.Plain if v else QFrame.NoFrame)
        self._fit_to_picture()

    def _apply_Enabled(self, v):
        pass  # a disabled Image isn't grayed, it just gets no events (see _on_qt_event)

    def _on_qt_event(self, watched, event):
        if not self._values.get("Enabled", True):
            return False
        return super()._on_qt_event(watched, event)


class _SplitterBar(QWidget):
    """The bar the user drags; see Splitter."""

    def __init__(self, splitter: "Splitter", parent: QWidget):
        super().__init__(parent)
        self._splitter = splitter
        self._drag = None  # (start position, the pane's size then) while dragging

    def paintEvent(self, event):
        splitter = self._splitter
        painter = QPainter(self)
        back = splitter._values.get("BackColor")
        # Unset: the button color (the Window color can be a pattern, e.g. the
        # designer's grid, whose color isn't the one you see)
        color = colors.to_qcolor(back) if back is not None else \
            self.palette().color(QPalette.Button)
        painter.fillRect(self.rect(), color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.palette().color(QPalette.WindowText))
        painter.setOpacity(0.35)
        center = self.rect().center()
        vertical = splitter._vertical()
        for i in (-6, 0, 6):  # a grip in the middle
            x, y = (center.x(), center.y() + i) if vertical else (center.x() + i, center.y())
            painter.drawEllipse(x - 1, y - 1, 3, 3)

    def mousePressEvent(self, event):
        splitter = self._splitter
        pane = splitter._pane()
        if event.button() != Qt.LeftButton or pane is None or splitter._design_mode or \
                not splitter._values.get("Enabled", True):
            return
        size = pane.Width if splitter._vertical() else pane.Height
        self._drag = (event.globalPosition().toPoint(), size, False)

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        start, size, _moved = self._drag
        delta = event.globalPosition().toPoint() - start
        self._splitter._resize_pane(size, delta.x() if self._splitter._vertical() else delta.y())
        self._drag = (start, size, True)

    def mouseReleaseEvent(self, event):
        if self._drag is not None and self._drag[2]:
            self._splitter._fire("Moved")
        self._drag = None


class Splitter(_Docked, Control):
    """A bar the user drags to resize a docked pane. It docks like an aligned
    PictureBox (Align, in creation order), right after the pane it resizes:
    the nearest earlier control docked to the same edge. Moved fires when
    the user lets go."""

    TypeName = "Splitter"
    DefaultEvent = "Moved"
    DefaultSize = (6, 97)
    Events = ("Moved",)
    Properties = (
        *_geometry(*DefaultSize),
        P("Align", "enum", 3, enum_choices("None", "Top", "Bottom", "Left", "Right"),
          description="The edge it docks to, next to the pane it resizes (docked to the "
                      "same edge before it)"),
        P("MinSize", "int", 30,
          description="The smallest size the pane, and the space left beside it, can get"),
        P("BackColor", "color", None,
          description="The bar's color; unset = a shade of the form's"),
        P("Enabled", "bool", True, description="Whether the user can drag it"),
        P("Visible", "bool", True, description="Whether the splitter is shown at run time"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def _create_widget(self, parent):
        return _SplitterBar(self, parent)

    def _event_targets(self):
        return []  # it handles the mouse itself

    def _vertical(self) -> bool:
        """A Left or Right splitter: a vertical bar that changes widths."""
        return self._values.get("Align", 3) in (3, 4)

    def _pane(self) -> "Control | None":
        """The control it resizes: the nearest earlier one docked to its edge."""
        align = self._values.get("Align", 0)
        pane = None
        for control in self._form._controls:
            if control is self:
                break
            if control.Parent is self.Parent and not isinstance(control, Splitter) and \
                    "Align" in control._specs and control._values.get("Align") == align and \
                    control._values.get("Visible", True):
                pane = control
        return pane if align else None

    def _resize_pane(self, size: int, delta: int) -> None:
        """Dragged by ``delta`` pixels from where the pane was ``size``."""
        pane = self._pane()
        if pane is None:
            return
        align = self._values.get("Align")
        grow = delta if align in (1, 3) else -delta  # Top/Left grow with the mouse
        minimum = max(0, self._values.get("MinSize", 30))
        left, top, right, bottom = self._form._free_area
        free = (right - left) if self._vertical() else (bottom - top)
        current = pane.Width if self._vertical() else pane.Height
        largest = max(minimum, current + free - minimum)  # leave MinSize beside it
        new = max(minimum, min(size + grow, largest))
        if self._vertical():
            pane.Width = new
        else:
            pane.Height = new

    def _apply_Align(self, v):
        if self._widget is not None:
            self._widget.setCursor(Qt.SplitHCursor if v in (3, 4) else Qt.SplitVCursor)
        if self in self._form._controls:
            self._form._layout_aligned()

    def _apply_BackColor(self, v):
        if self._widget is not None:
            self._widget.update()

    def _apply_Enabled(self, v):
        if self._widget is not None:
            self._widget.setCursor(Qt.ArrowCursor if not v else
                                   Qt.SplitHCursor if self._vertical() else Qt.SplitVCursor)


# --- DockPanel -------------------------------------------------------------------------

_DOCK_ALIGN = ((1, "1 - Top"), (2, "2 - Bottom"), (3, "3 - Left"), (4, "4 - Right"))
_DOCK_CAPTION = 22  # the caption bar's height
_DOCK_SIZER = 5  # the resizing edge of a docked panel
_DOCK_ZONE = 40  # how near an edge a dragged panel docks there


class _DockCaption(QWidget):
    """A DockPanel's caption bar: its Caption, a float button and a close
    button. Dragging it tears the panel off (floating) and docks it where it
    is dropped; double-clicking it floats or docks it."""

    def __init__(self, panel: "DockPanel", parent):
        super().__init__(parent)
        self.panel = panel
        self.setMouseTracking(True)
        self._press = None  # (global point, point in the bar) while the button is down
        self._pressed_button = None
        self._dragging = False

    def button_rects(self) -> dict:
        size = self.height() - 6
        right = self.width() - 4
        rects = {}
        if self.panel._values.get("Closable", True):
            rects["close"] = QRect(right - size, 3, size, size)
            right -= size + 2
        if self.panel._values.get("Floatable", True):
            rects["float"] = QRect(right - size, 3, size, size)
        return rects

    def _button_at(self, point):
        return next((name for name, rect in self.button_rects().items()
                     if rect.contains(point)), None)

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        window = palette.color(QPalette.Window)
        dark = window.lightness() < 128
        painter.fillRect(self.rect(), window.lighter(125) if dark else window.darker(112))
        ink = palette.color(QPalette.WindowText)
        painter.setPen(ink)
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        rects = self.button_rects()
        right = min((r.left() for r in rects.values()), default=self.width()) - 4
        painter.drawText(QRect(6, 0, max(right - 6, 0), self.height()),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(self.panel._values.get("Caption", ""),
                                                          Qt.ElideRight, max(right - 6, 0)))
        pen = QPen(ink, 1.2)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.Antialiasing)
        if "close" in rects:
            r = rects["close"].adjusted(4, 4, -4, -4)
            painter.drawLine(r.topLeft(), r.bottomRight())
            painter.drawLine(r.topRight(), r.bottomLeft())
        if "float" in rects:
            r = rects["float"].adjusted(4, 4, -4, -4)
            if self.panel._floating:  # (dock it: one box)
                painter.drawRect(r)
            else:  # (float it: two boxes)
                painter.drawRect(r.adjusted(3, 0, 0, -3))
                painter.drawRect(r.adjusted(0, 3, -3, 0))
        painter.end()

    def mousePressEvent(self, event):
        if self.panel._design_mode or event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        self._pressed_button = self._button_at(point)
        self._press = (event.globalPosition().toPoint(), point)
        self._dragging = False

    def mouseMoveEvent(self, event):
        if self._press is None or self._pressed_button is not None:
            return
        where = event.globalPosition().toPoint()
        if not self._dragging:
            if (where - self._press[0]).manhattanLength() < QApplication.startDragDistance():
                return
            self._dragging = self.panel._drag_start(where, self._press[1])
            if self._dragging:
                self.grabMouse()
        if self._dragging:
            self.panel._drag_move(where)

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        point = event.position().toPoint()
        if self._dragging:
            self.releaseMouse()
            self.panel._drag_end(event.globalPosition().toPoint())
        elif self._pressed_button is not None and self._button_at(point) == self._pressed_button:
            self.panel._caption_button(self._pressed_button)
        self._press, self._pressed_button, self._dragging = None, None, False

    def mouseDoubleClickEvent(self, event):
        if not self.panel._design_mode and self._button_at(event.position().toPoint()) is None:
            self.panel._toggle_floating()


class _DockSizer(QWidget):
    """The inner edge of a docked DockPanel: dragging it resizes the panel."""

    def __init__(self, panel: "DockPanel", parent):
        super().__init__(parent)
        self.panel = panel
        self._start = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.panel._design_mode:
            align = self.panel._values.get("Align", 3)
            size = self.panel._values.get("Height" if align in (1, 2) else "Width")
            self._start = (event.globalPosition().toPoint(), size)

    def mouseMoveEvent(self, event):
        if self._start is not None:
            point, size = self._start
            delta = event.globalPosition().toPoint() - point
            align = self.panel._values.get("Align", 3)
            change = {1: delta.y(), 2: -delta.y(), 3: delta.x(), 4: -delta.x()}[align]
            self.panel._resize_docked(size + change)

    def mouseReleaseEvent(self, event):
        self._start = None


class _DockFrame(QFrame):
    """A DockPanel: its caption bar, the area its controls are in, and (docked)
    the edge that resizes it."""

    def __init__(self, panel: "DockPanel", parent):
        super().__init__(parent)
        self.panel = panel
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)  # (opaque over whatever it is docked on)
        self.caption = _DockCaption(panel, self)
        self.content = QWidget(self)
        self.sizer = _DockSizer(panel, self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.panel._place_parts()


class _FloatWindow(QWidget):
    """The small window a floating DockPanel is in (the caption bar is its
    title bar; the corner grip resizes it)."""

    def __init__(self, panel: "DockPanel", parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.panel = panel
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.grip = QSizeGrip(self)
        self.grip.resize(14, 14)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.move(self.width() - self.grip.width(), self.height() - self.grip.height())
        self.grip.raise_()

    def closeEvent(self, event):  # (e.g. the window manager's close): as the X button
        if self.panel._closing or not self.panel._ask_close():
            event.accept() if self.panel._closing else event.ignore()
        else:
            event.ignore()
            self.panel.Visible = False


class DockPanel(_Docked, Control):
    """A tool window docked to an edge of its form (Align), like the IDE's
    panels: its caption bar has a float and a close button; dragging it tears
    the panel off into a window of its own (Floating) and drops it on another
    edge (or the same), double-clicking it floats or docks it, and its inner
    edge resizes it. Closing hides it (Close can cancel); Visible = True
    shows it again where it was. Put controls in it like in a Frame. The
    form's DockLayout saves and restores where all its panels are."""

    TypeName = "DockPanel"
    DefaultEvent = "DockChange"
    DefaultSize = (161, 201)
    IsContainer = True
    Events = ("DockChange", "Close", "Resize", "Click", "MouseDown", "MouseMove", "MouseUp")
    Properties = (
        *_geometry(*DefaultSize),
        P("Caption", "str", "", always=True, description="The title in its caption bar"),
        P("Align", "enum", 3, _DOCK_ALIGN,
          description="The edge of the form it docks to; its Width (Left, Right) or Height "
                      "(Top, Bottom) is its size there"),
        P("Floating", "bool", False,
          description="At run time: in a window of its own instead of docked"),
        P("Floatable", "bool", True,
          description="The user can float it and dock it to another edge (the float button, "
                      "dragging the caption bar)"),
        P("Closable", "bool", True, description="A close button in its caption bar"),
        P("Resizable", "bool", True, description="Its inner edge can be dragged to resize it"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_floating=False, _float_window=None, _float_rect=None,
                             _drag_offset=None, _band=None, _closing=False, _watching=None,
                             _was_visible=None)
        return _DockFrame(self, parent)

    def _container_widget(self) -> QWidget:
        return self._widget.content

    def _event_targets(self):
        return [self._widget, self._widget.content]

    def _on_qt_event(self, watched, event):
        if watched is self._widget and event.type() == QEvent.Resize:
            self._fire("Resize")
        return super()._on_qt_event(watched, event)

    def _place_parts(self) -> None:
        frame = self._widget
        rect = frame.contentsRect()
        docked = not self._floating and not self._design_mode and \
            self._values.get("Resizable", True)
        align = self._values.get("Align", 3)
        sizer = _DOCK_SIZER if docked else 0
        inner = QRect(rect)  # (the inner edge: the side facing the form's middle)
        if sizer:
            if align == 1:
                frame.sizer.setGeometry(rect.left(), rect.bottom() - sizer + 1, rect.width(),
                                        sizer)
                inner.setBottom(rect.bottom() - sizer)
                frame.sizer.setCursor(Qt.SizeVerCursor)
            elif align == 2:
                frame.sizer.setGeometry(rect.left(), rect.top(), rect.width(), sizer)
                inner.setTop(rect.top() + sizer)
                frame.sizer.setCursor(Qt.SizeVerCursor)
            elif align == 3:
                frame.sizer.setGeometry(rect.right() - sizer + 1, rect.top(), sizer,
                                        rect.height())
                inner.setRight(rect.right() - sizer)
                frame.sizer.setCursor(Qt.SizeHorCursor)
            else:
                frame.sizer.setGeometry(rect.left(), rect.top(), sizer, rect.height())
                inner.setLeft(rect.left() + sizer)
                frame.sizer.setCursor(Qt.SizeHorCursor)
        frame.sizer.setVisible(bool(sizer))
        frame.caption.setGeometry(inner.left(), inner.top(), inner.width(), _DOCK_CAPTION)
        frame.content.setGeometry(inner.left(), inner.top() + _DOCK_CAPTION, inner.width(),
                                  max(inner.height() - _DOCK_CAPTION, 0))
        frame.caption.update()

    def _apply_Caption(self, v):
        self._widget.caption.update()
        if self._float_window is not None:
            self._float_window.setWindowTitle(v)

    def _apply_Closable(self, v):
        self._widget.caption.update()

    _apply_Floatable = _apply_Closable

    def _apply_Resizable(self, v):
        self._place_parts()

    def _apply_Align(self, v):
        self._place_parts()
        if not self._floating:
            super()._apply_Align(v)

    # (floating: its size and place are the window's, not the form's)
    def _apply_Width(self, v):
        if not self._floating:
            super()._apply_Width(v)

    def _apply_Height(self, v):
        if not self._floating:
            super()._apply_Height(v)

    def _apply_Left(self, v):
        if not self._floating:
            super()._apply_Left(v)

    def _apply_Top(self, v):
        if not self._floating:
            super()._apply_Top(v)

    def _apply_Visible(self, v):
        self._watch_form()
        if self._floating:
            if not self._design_mode:
                self._float_window.setVisible(bool(v) and self._form._widget.isVisible())
        else:
            super()._apply_Visible(v)
        was = self._was_visible
        self.__dict__["_was_visible"] = bool(v)
        if was is not None and was != bool(v) and not self._design_mode:
            self._fire("DockChange")  # (closed, or shown again)

    def _apply_Floating(self, v):
        if self._design_mode:
            return
        if v and not self._floating:
            self._float()
        elif not v and self._floating:
            self._dock()

    # -- floating and docking ---------------------------------------------------------------
    def _watch_form(self) -> None:
        """Follow the form's showing and hiding (a floating panel's window too)."""
        if self._watching is None and not self._design_mode:
            self.__dict__["_watching"] = _DockWatcher(self)
            self._form._widget.installEventFilter(self._watching)

    def _float(self, rect: QRect | None = None) -> None:
        """Into a window of its own: ``rect`` (on the screen), else where it
        last floated, else beside where it is docked."""
        frame, form_widget = self._widget, self._form._widget
        if rect is None:
            rect = self._float_rect
        if rect is None:
            corner = frame.mapToGlobal(QPoint(0, 0)) if frame.isVisible() else \
                form_widget.mapToGlobal(QPoint(40, 40))
            rect = QRect(corner + QPoint(24, 24), frame.size().expandedTo(QSize(120, 80)))
        window = _FloatWindow(self, form_widget.window())
        window.setWindowTitle(self._values.get("Caption", ""))
        self.__dict__.update(_floating=True, _float_window=window)
        self._values["Floating"] = True
        frame.setParent(window)
        window.layout().addWidget(frame)
        frame.show()
        window.setGeometry(rect)
        self._place_parts()
        self._form._layout_aligned()  # (its edge's space goes to the others)
        self._watch_form()
        if self._values.get("Visible", True) and form_widget.isVisible():
            window.show()
        self._fire("DockChange")

    def _dock(self, align: int | None = None) -> None:
        """Back into the form, at an edge (``align``, else the one it had)."""
        frame = self._widget
        if align is not None:
            self._values["Align"] = int(align)
        if self._floating:
            window = self._float_window
            self.__dict__.update(_float_rect=window.geometry(), _floating=False,
                                 _float_window=None, _closing=True)
            frame.setParent(self._parent_widget())
            window.close()
            window.deleteLater()
            self.__dict__["_closing"] = False
            if self._values.get("Visible", True):
                frame.show()
            frame.raise_()
        self._values["Floating"] = False
        self._place_parts()
        self._form._layout_aligned()
        self._fire("DockChange")

    def Float(self) -> None:
        """Float it in a window of its own (where it last floated)."""
        self.Floating = True

    def Dock(self, Align: int | None = None) -> None:
        """Dock it: to an edge (vpAlignTop, vpAlignBottom, vpAlignLeft,
        vpAlignRight), else the one it had. Already docked elsewhere, it moves."""
        if self._floating:
            self._dock(Align)
        elif Align is not None and int(Align) != self._values.get("Align"):
            self.Align = int(Align)
            self._fire("DockChange")

    def _toggle_floating(self) -> None:
        if self._values.get("Floatable", True):
            self.Floating = not self._floating

    def _caption_button(self, name: str) -> None:
        if name == "close":
            if self._ask_close():
                self.Visible = False
        elif name == "float":
            self._toggle_floating()

    def _ask_close(self) -> bool:
        """Close fires: its handler returns True to keep the panel open."""
        return self._fire("Close") is not True

    def _resize_docked(self, size: int) -> None:
        area = self._parent_widget().rect()
        align = self._values.get("Align", 3)
        limit = (area.height() if align in (1, 2) else area.width()) - 40
        size = max(_DOCK_CAPTION + 20, min(int(size), max(limit, _DOCK_CAPTION + 20)))
        if align in (1, 2):
            self.Height = size
        else:
            self.Width = size

    # -- dragging the caption bar ------------------------------------------------------------
    def _drag_start(self, point: QPoint, offset: QPoint) -> bool:
        """The caption bar is being dragged (``point`` on the screen, ``offset``
        where it was grabbed in the bar): float the panel under the mouse."""
        if not self._values.get("Floatable", True):
            return False
        if not self._floating:
            size = self._widget.size().expandedTo(QSize(120, 80))
            self._float(QRect(point - offset, size))
        self.__dict__["_drag_offset"] = offset
        return True

    def _drop_edge(self, point: QPoint) -> int | None:
        """The edge of the form a panel dropped at ``point`` would dock to."""
        area = self._parent_widget()
        local = area.mapFromGlobal(point)
        rect = area.rect()
        if not rect.contains(local):
            return None
        distances = {3: local.x(), 4: rect.width() - local.x(), 1: local.y(),
                     2: rect.height() - local.y()}
        edge = min(distances, key=distances.get)
        return edge if distances[edge] < _DOCK_ZONE else None

    def _drop_rect(self, edge: int) -> QRect:
        area = self._parent_widget().rect()
        align_size = self._values.get("Height" if edge in (1, 2) else "Width")
        size = min(align_size, (area.height() if edge in (1, 2) else area.width()) // 2)
        return {1: QRect(0, 0, area.width(), size),
                2: QRect(0, area.height() - size, area.width(), size),
                3: QRect(0, 0, size, area.height()),
                4: QRect(area.width() - size, 0, size, area.height())}[edge]

    def _drag_move(self, point: QPoint) -> None:
        if self._float_window is not None and self._drag_offset is not None:
            self._float_window.move(point - self._drag_offset)
        edge = self._drop_edge(point)
        band = self._band
        if edge is None:
            if band is not None:
                band.hide()
            return
        if band is None:
            band = QRubberBand(QRubberBand.Rectangle, self._parent_widget())
            self.__dict__["_band"] = band
        band.setGeometry(self._drop_rect(edge))
        band.show()
        band.raise_()

    def _drag_end(self, point: QPoint) -> None:
        if self._band is not None:
            self._band.hide()
        edge = self._drop_edge(point)
        self.__dict__["_drag_offset"] = None
        if edge is not None:
            self._move_outermost()
            self._dock(edge)

    def _move_outermost(self) -> None:
        """First of the form's DockPanels: dropped on an edge, it goes next to
        the edge (inside the form's other docked panes, e.g. a Toolbar)."""
        controls = self._form._controls
        panels = [c for c in controls if isinstance(c, DockPanel) and c.Parent is self.Parent]
        if panels and panels[0] is not self:
            controls.remove(self)
            controls.insert(controls.index(panels[0]), self)

    # -- floating geometry --------------------------------------------------------------------
    def _float_geometry(self) -> QRect | None:
        if self._float_window is not None:
            return self._float_window.geometry()
        return self._float_rect

    @property
    def FloatLeft(self) -> int:
        """Where its window is (or was, last time it floated) on the screen."""
        rect = self._float_geometry()
        return rect.x() if rect is not None else 0

    @property
    def FloatTop(self) -> int:
        rect = self._float_geometry()
        return rect.y() if rect is not None else 0

    @property
    def FloatWidth(self) -> int:
        rect = self._float_geometry()
        return rect.width() if rect is not None else self._values.get("Width", 0)

    @property
    def FloatHeight(self) -> int:
        rect = self._float_geometry()
        return rect.height() if rect is not None else self._values.get("Height", 0)

    def FloatMove(self, Left: int, Top: int, Width: int | None = None,
                  Height: int | None = None) -> None:
        """Place its floating window (on the screen); docked, where it will float."""
        rect = QRect(int(Left), int(Top), int(Width if Width is not None else self.FloatWidth),
                     int(Height if Height is not None else self.FloatHeight))
        if self._float_window is not None:
            self._float_window.setGeometry(rect)
        else:
            self.__dict__["_float_rect"] = rect


class _DockWatcher(QObject):
    """Shows and hides a floating DockPanel's window with its form."""

    def __init__(self, panel: DockPanel):
        super().__init__(panel._form._widget)
        self.panel = panel

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Hide):
            panel = self.__dict__.get("panel")  # (gone while the form is torn down)
            window = panel.__dict__.get("_float_window") if panel is not None else None
            if window is not None:
                window.setVisible(event.type() == QEvent.Show and
                                  panel._values.get("Visible", True))
        return False


# --- Keyed collections (ListImages, Panels, Tabs) ------------------------------------------------

class _KeyedItem:
    """An item of a _KeyedCollection (a StatusBar's Panel, a TabStrip's Tab):
    its Index from 1 and a Key unique in the collection."""

    _collection: "_KeyedCollection"
    _key = ""

    def _changed(self):
        self._collection._changed()

    @property
    def Index(self) -> int:
        """Its position, from 1."""
        return self._collection._list.index(self) + 1

    @property
    def Key(self) -> str:
        return self._key

    @Key.setter
    def Key(self, value):
        value = str(value)
        by_key = self._collection._by_key
        if value and value != self._key and value in by_key:
            raise KeyError(f"Key '{value}' is not unique in the collection")
        by_key.pop(self._key, None)
        self._key = value
        if value:
            by_key[value] = self


class _KeyedCollection:
    """A control's collection of items (Panels, Tabs), in order: by Index
    (from 1) or Key, ``Count``, ``Remove``, ``Clear`` and iteration. The
    subclass adds ``Add``; ``changed`` updates the control."""

    _noun = "item"

    def __init__(self, owner, changed):
        self._owner = owner  # the control
        self._changed = changed
        self._list: list = []
        self._by_key: dict = {}

    def __len__(self):
        return len(self._list)

    def __iter__(self):
        return iter(list(self._list))

    @property
    def Count(self) -> int:
        return len(self._list)

    def _resolve(self, index):
        if isinstance(index, _KeyedItem):
            return index
        if isinstance(index, str):
            if index not in self._by_key:
                raise KeyError(f"No {self._noun} with the key '{index}'")
            return self._by_key[index]
        index = int(index)
        if not 1 <= index <= len(self._list):
            raise IndexError(f"No {self._noun} {index} (there are {len(self._list)})")
        return self._list[index - 1]

    def __call__(self, index):
        return self._resolve(index)

    Item = __call__

    def _insert(self, item, Index=None):
        """Add an item (at the end, or at Index from 1) without updating."""
        if item._key and item._key in self._by_key:
            raise KeyError(f"Key '{item._key}' is not unique in the collection")
        item._collection = self
        if Index is None:
            self._list.append(item)
        else:
            self._list.insert(max(0, int(Index) - 1), item)
        if item._key:
            self._by_key[item._key] = item
        return item

    def _reset(self) -> None:
        self._list.clear()
        self._by_key.clear()

    def Remove(self, index) -> None:
        item = self._resolve(index)
        self._list.remove(item)
        self._by_key.pop(item._key, None)
        self._changed()

    def Clear(self) -> None:
        self._reset()
        self._changed()


# --- ImageList ---------------------------------------------------------------------------------

def parse_list_image(line: str) -> dict:
    """A picture as the designer writes it (ImageList.ListImages): ``path|key``,
    the path relative to the form's folder, e.g. ``images/open.png|open``."""
    picture, _, key = str(line).partition("|")
    return {"Picture": picture.strip(), "Key": key.strip()}


def _image_ref(text: str):
    """An image reference from a designer line: digits are an Index (VB's keys
    can't be numbers), anything else a key."""
    text = str(text).strip()
    return int(text) if text.isdigit() else text


class ListImage(_KeyedItem):
    """One picture of an ImageList (``ImageList1.ListImages(1)`` or by Key)."""

    def __init__(self, images: "ImageList", key: str, picture: str):
        self._images = images
        self._key = key
        self._picture = str(picture)
        self.Tag = ""

    def __repr__(self):
        return f"<ListImage {self.Index} {self._key or self._picture!r}>"

    @property
    def Picture(self) -> str:
        """Its picture file (relative to the form's folder): also usable as an
        Image's or PictureBox's Picture."""
        return self._picture

    @Picture.setter
    def Picture(self, value):
        self._picture = str(value)
        self._changed()

    def _pixmap(self) -> QPixmap:
        """The picture, at the ImageList's size (ImageWidth, ImageHeight) in
        logical pixels: on a high-DPI screen it keeps that many more pixels,
        so a 32-pixel picture shown at 16 stays sharp."""
        path = resolve_path(self._images, self._picture)
        pixmap = QPixmap(path) if path else QPixmap()
        width, height = self._images._size()
        if pixmap.isNull() or (width, height) == (pixmap.width(), pixmap.height()):
            return pixmap
        app = QApplication.instance()
        ratio = app.devicePixelRatio() if app is not None else 1.0
        pixmap = pixmap.scaled(round(width * ratio), round(height * ratio),
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

    def _icon(self) -> QIcon:
        pixmap = self._pixmap()
        return QIcon(pixmap) if not pixmap.isNull() else QIcon()

    @property
    def Width(self) -> int:
        return self._images._size()[0]

    @property
    def Height(self) -> int:
        return self._images._size()[1]


class _ListImages(_KeyedCollection):
    """ImageList.ListImages: its pictures in order, by Index (from 1) or Key."""

    _noun = "picture"

    def Add(self, Index=None, Key: str = "", Picture: str = "") -> ListImage:
        """A new picture (a file, relative to the form's folder), at the end or
        at Index (from 1)."""
        image = self._insert(ListImage(self._owner, str(Key or ""), str(Picture)), Index)
        self._changed()
        return image


class ImageList(Control):
    """A collection of pictures for other controls, like VB's ImageList
    (Windows Common Controls): a TreeView's or TabStrip's ImageList names it,
    and their nodes' and tabs' Image is then a picture's Key or Index.
    Invisible at run time; the pictures are set in the designer (ListImages)
    or in code (ListImages.Add)."""

    TypeName = "ImageList"
    DefaultEvent = ""
    DefaultSize = (32, 32)
    Events = ()
    Properties = (
        P("Left", "int", 0, always=True, description="Position in the designer only"),
        P("Top", "int", 0, always=True, description="Position in the designer only"),
        P("ImageWidth", "int", 0,
          description="The pictures' width in pixels; 0 = the first picture's"),
        P("ImageHeight", "int", 0,
          description="The pictures' height in pixels; 0 = the first picture's"),
        P("ListImages", "images", [],
          description="The pictures, set in the designer: one per line, path|key, the path "
                      "relative to the form's folder"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__["_images"] = None
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        self.__dict__["_images"] = _ListImages(self, self._notify)
        if self._design_mode:
            return _imagelist_design_widget(parent)
        return None

    def _read_Width(self):
        return 32

    def _read_Height(self):
        return 32

    @property
    def ListImages(self) -> "_ListImages":
        return self._images

    @ListImages.setter
    def ListImages(self, lines):
        """In the designer (and InitializeComponent): the pictures as lines of
        text, see parse_list_image."""
        self._set_prop("ListImages", lines)

    def _apply_ListImages(self, lines):
        self._images._reset()
        for line in lines or []:
            spec = parse_list_image(line)
            if spec["Picture"]:
                self._images._insert(ListImage(self, spec["Key"], spec["Picture"]))
        self._notify()

    def _size(self) -> tuple[int, int]:
        """(ImageWidth, ImageHeight): as set, or the first picture's size."""
        width, height = self._values.get("ImageWidth", 0), self._values.get("ImageHeight", 0)
        if (not width or not height) and self._images is not None and len(self._images):
            first = self._images._list[0]
            path = resolve_path(self, first._picture)
            pixmap = QPixmap(path) if path else QPixmap()
            width, height = width or pixmap.width(), height or pixmap.height()
        return max(width, 0), max(height, 0)

    def _apply_ImageWidth(self, v):
        self._notify()

    _apply_ImageHeight = _apply_ImageWidth

    def _notify(self) -> None:
        """The pictures changed: the controls using this ImageList show them again."""
        if self._images is None or not self._name or self not in self._form._controls:
            return
        for control in self._form._controls:
            if any(control._values.get(prop) == self._name
                   for prop in getattr(control, "_IMAGE_LIST_PROPS", ())):
                control._refresh_images()


def _imagelist_design_widget(parent: QWidget) -> QLabel:
    """The icon the designer shows for an ImageList: a stack of pictures."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.2))
    for offset, color in ((0, "#9ec5fe"), (4, "#ffe08a"), (8, "#a3e4a8")):
        painter.setBrush(QColor(color))
        painter.drawRect(2 + offset, 10 - offset, 14, 12)
    painter.end()
    label = QLabel(parent)
    label.setFixedSize(32, 32)
    label.setAlignment(Qt.AlignCenter)
    label.setFrameStyle(QFrame.Panel | QFrame.Raised)
    label.setPixmap(pixmap)
    return label


class _UsesImageList:
    """For controls whose items show pictures (TreeView, TabStrip, Toolbar,
    ListView): their ImageList property (a ListView has two: Icons and
    SmallIcons) names an ImageList on the form, and an item's Image is then
    a picture's Key or Index in it (without one, a picture file)."""

    _IMAGE_LIST_PROPS = ("ImageList",)  # the properties naming ImageLists

    def _image_list(self, prop: str = "ImageList") -> "ImageList | None":
        name = self._values.get(prop, "")
        if not name:
            return None
        return next((c for c in self._form._controls
                     if isinstance(c, ImageList) and c._name == name), None)

    def _apply_ImageList(self, v):
        self._refresh_images()

    def _refresh_images(self) -> None:
        """Show every item's Image again (the ImageList or its pictures changed)."""


def _picture_icon(control, ref, strict: bool = False, prop: str = "ImageList") -> QIcon:
    """The icon of an item's Image: with the control's ImageList, the picture
    with that Key or Index (from 1); without one, a picture file (relative to
    the form's folder). ``strict``: an unknown Key or Index raises KeyError /
    IndexError (code setting an Image) instead of showing none. ``prop``: the
    property naming the ImageList (a ListView's Icons or SmallIcons)."""
    if ref is None or ref == "":
        return QIcon()
    images = control._image_list(prop)
    if images is not None:
        try:
            return images.ListImages(ref)._icon()
        except (KeyError, IndexError, ValueError):
            if strict:
                raise
            return QIcon()
    if isinstance(ref, int):
        if strict:
            raise ValueError(f"{control.TypeName} '{control.Name}': Image {ref} needs an "
                             "ImageList")
        return QIcon()
    path = resolve_path(control, str(ref))
    return QIcon(QPixmap(path)) if path else QIcon()


# --- StatusBar ---------------------------------------------------------------------------------

_SBR_STYLES = ("text", "caps", "num", "ins", "scrl", "time", "date")  # Panel.Style, by value
_SBR_AUTOSIZE = ("none", "spring", "contents")  # Panel.AutoSize
_SBR_ALIGNMENT = ("left", "center", "right")  # Panel.Alignment
_SBR_KEY_TEXTS = {1: "CAPS", 2: "NUM", 3: "INS", 4: "SCRL"}
_QT_PANEL_ALIGN = {0: Qt.AlignLeft, 1: Qt.AlignHCenter, 2: Qt.AlignRight}


def parse_panel(line: str) -> dict:
    """A panel as the designer writes it (StatusBar.Panels): ``Text|Key|options``,
    the options being words: a number (the Width), an AutoSize (spring,
    contents), a Style (caps, num, ins, scrl, time, date) and an Alignment
    (center, right). E.g. ``Ready|status|spring`` or ``|clock|time 80 right``."""
    text, _, rest = str(line).partition("|")
    key, _, options = rest.partition("|")
    panel = {"Text": text.strip(), "Key": key.strip()}
    for word in options.lower().split():
        if word.isdigit():
            panel["Width"] = int(word)
        elif word in _SBR_AUTOSIZE:
            panel["AutoSize"] = _SBR_AUTOSIZE.index(word)
        elif word in _SBR_STYLES:
            panel["Style"] = _SBR_STYLES.index(word)
        elif word in _SBR_ALIGNMENT:
            panel["Alignment"] = _SBR_ALIGNMENT.index(word)
    return panel


def _lock_key_on(style: int) -> bool:
    """Whether Caps Lock, Num Lock, Insert or Scroll Lock is on: read from the
    system on Windows (all four) and macOS (Caps Lock); off elsewhere."""
    import sys
    try:
        if sys.platform == "win32":
            import ctypes
            code = {1: 0x14, 2: 0x90, 3: 0x2D, 4: 0x91}[style]
            return bool(ctypes.windll.user32.GetKeyState(code) & 1)
        if sys.platform == "darwin" and style == 1:
            import ctypes
            import ctypes.util
            quartz = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
            quartz.CGEventSourceFlagsState.restype = ctypes.c_uint64
            quartz.CGEventSourceFlagsState.argtypes = [ctypes.c_int32]
            return bool(quartz.CGEventSourceFlagsState(0) & 0x10000)  # combined; AlphaShift
    except (OSError, AttributeError, KeyError, TypeError):
        pass
    return False


class Panel(_KeyedItem):
    """One panel of a StatusBar (``StatusBar1.Panels(1)`` or by Key). Setting
    a property updates the bar at once."""

    def __init__(self, bar: "StatusBar", key: str = "", text: str = "", style: int = 0):
        self._bar = bar
        self._key = key
        self._text = text
        self._style = int(style)
        self._width = 96
        self._auto_size = 0
        self._alignment = 0
        self._tooltip = ""
        self._visible = True
        self._enabled = True
        self.Tag = ""
        self._label = None  # its QLabel while it's shown

    def __repr__(self):
        return f"<Panel {self.Index} {self._key or self._text!r}>"

    @property
    def Text(self) -> str:
        """Its text (panels showing the time, the date or a lock key show that
        instead, but keep this)."""
        return self._text

    @Text.setter
    def Text(self, value):
        self._text = str(value)
        self._changed()

    @property
    def Style(self) -> int:
        return self._style

    @Style.setter
    def Style(self, value):
        self._style = int(value)
        self._changed()

    @property
    def Width(self) -> int:
        """Its width in pixels; the smallest one for a Spring or Contents panel."""
        return self._width

    @Width.setter
    def Width(self, value):
        self._width = max(0, int(value))
        self._changed()

    MinWidth = Width

    @property
    def AutoSize(self) -> int:
        return self._auto_size

    @AutoSize.setter
    def AutoSize(self, value):
        self._auto_size = int(value)
        self._changed()

    @property
    def Alignment(self) -> int:
        return self._alignment

    @Alignment.setter
    def Alignment(self, value):
        self._alignment = int(value)
        self._changed()

    @property
    def ToolTipText(self) -> str:
        return self._tooltip

    @ToolTipText.setter
    def ToolTipText(self, value):
        self._tooltip = str(value)
        self._changed()

    @property
    def Visible(self) -> bool:
        return self._visible

    @Visible.setter
    def Visible(self, value):
        self._visible = bool(value)
        self._changed()

    @property
    def Enabled(self) -> bool:
        return self._enabled

    @Enabled.setter
    def Enabled(self, value):
        self._enabled = bool(value)
        self._changed()

    @property
    def Left(self) -> int:
        """Where it starts in the bar, in pixels (read-only)."""
        return self._label.x() if self._label is not None else 0

    def _shown_text(self) -> str:
        """What the panel shows: its Text, or the time, the date or a key."""
        if self._style == 5:
            return QLocale().toString(QTime.currentTime(), QLocale.ShortFormat)
        if self._style == 6:
            return QLocale().toString(QDate.currentDate(), QLocale.ShortFormat)
        return _SBR_KEY_TEXTS.get(self._style, self._text)


class _Panels(_KeyedCollection):
    """StatusBar.Panels: its panels in order, by Index (from 1) or Key."""

    _noun = "panel"

    def Add(self, Index=None, Key: str = "", Text: str = "", Style: int = 0) -> Panel:
        """A new panel, at the end or at Index (from 1)."""
        panel = self._insert(Panel(self._owner, str(Key or ""), str(Text), Style), Index)
        self._changed()
        return panel


class StatusBar(_Docked, Control):
    """A bar of panels at the bottom of a form, like VB's StatusBar (Windows
    Common Controls). Each panel shows a text, or the time, the date or the
    state of a lock key; Spring panels share the space left. It docks like an
    aligned PictureBox (Bottom by default). Style = Simple shows SimpleText
    across the whole bar instead of the panels."""

    TypeName = "StatusBar"
    DefaultEvent = "PanelClick"
    DefaultSize = (400, 25)
    Events = ("PanelClick", "PanelDblClick", "Click", "DblClick", "MouseDown", "MouseMove",
              "MouseUp")
    _synthesize_click = True
    _qss_type = "QFrame"
    Properties = (
        *_geometry(*DefaultSize),
        P("Align", "enum", 2, enum_choices("None", "Top", "Bottom"),
          description="The edge it docks to (Bottom), like an aligned PictureBox; None: "
                      "where you put it"),
        P("Style", "enum", 0, enum_choices("Normal", "Simple"),
          description="Normal: the panels; Simple: SimpleText across the whole bar"),
        P("SimpleText", "str", "", description="The text shown when Style is Simple"),
        P("Panels", "panels", ["|panel1|spring"],
          description="The panels, set in the designer: one per line, Text|Key|options, "
                      "the options being words: a width in pixels, spring or contents "
                      "(AutoSize), caps, num, ins, scrl, time or date (Style), center or "
                      "right (Alignment). E.g. Ready|status|spring"),
        *_COLORS, *_FONT,
        P("Enabled", "bool", True, description="Whether the control responds to the user"),
        P("Visible", "bool", True, description="Whether the control is shown at run time"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def _create_widget(self, parent):
        self.__dict__["_panels"] = _Panels(self, self._update_panels)
        self.__dict__["_panel_labels"] = []
        widget = QFrame(parent)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(2)
        self.__dict__["_simple_label"] = QLabel(widget)
        layout.addWidget(self._simple_label, 1)
        self._simple_label.hide()
        # The time, the date and the lock keys are shown as they change
        timer = QTimer(widget)
        timer.setInterval(250)
        timer.timeout.connect(self._refresh_live_panels)
        self.__dict__["_timer"] = timer
        return widget

    # -- the collection ----------------------------------------------------------------------
    @property
    def Panels(self) -> _Panels:
        return self._panels

    @Panels.setter
    def Panels(self, lines):
        """In the designer (and InitializeComponent): the panels as lines of
        text, see parse_panel."""
        self._set_prop("Panels", lines)

    def _apply_Panels(self, lines):
        self._panels._reset()
        for line in lines or []:
            spec = parse_panel(line)
            panel = Panel(self, spec["Key"], spec["Text"], spec.get("Style", 0))
            panel._width = spec.get("Width", panel._width)
            panel._auto_size = spec.get("AutoSize", 0)
            panel._alignment = spec.get("Alignment", 0)
            self._panels._insert(panel)
        self._update_panels()

    # -- showing the panels ------------------------------------------------------------------
    def _update_panels(self) -> None:
        """Rebuild the bar's labels from the panels (or show SimpleText)."""
        widget = self._widget
        if widget is None:
            return
        layout = widget.layout()
        while layout.count():  # start again: the labels, and a stretch if there was one
            item = layout.takeAt(0)
            label = item.widget()
            if label is not None and label is not self._simple_label:
                label.hide()
                label.deleteLater()
        self._panel_labels.clear()
        simple = self._values.get("Style", 0) == 1
        layout.addWidget(self._simple_label, 1)
        self._simple_label.setVisible(simple)
        self._simple_label.setText(self._values.get("SimpleText", ""))
        live = False
        for panel in self._panels._list:
            panel._label = None
            if simple or not panel._visible:
                continue
            label = QLabel(panel._shown_text(), widget)
            label.setFrameShape(QFrame.StyledPanel)
            label.setFrameShadow(QFrame.Sunken)
            label.setAlignment(_QT_PANEL_ALIGN.get(panel._alignment, Qt.AlignLeft) |
                               Qt.AlignVCenter)
            label.setToolTip(panel._tooltip)
            label.setEnabled(panel._enabled and self._values.get("Enabled", True) and
                             (panel._style not in _SBR_KEY_TEXTS or _lock_key_on(panel._style)))
            label._vp_panel = panel
            if panel._auto_size == 1:  # Spring: shares the space left
                label.setMinimumWidth(panel._width)
                layout.addWidget(label, 1)
            elif panel._auto_size == 2:  # Contents: as wide as its text (at least Width)
                label.setMinimumWidth(max(panel._width, label.sizeHint().width()))
                layout.addWidget(label, 0)
            else:
                label.setFixedWidth(panel._width)
                layout.addWidget(label, 0)
            # The bar gets the mouse, and finds the panel by position (_panel_at)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            label.show()
            panel._label = label
            self._panel_labels.append(label)
            live = live or panel._style != 0
        if not simple and not any(label._vp_panel._auto_size == 1
                                  for label in self._panel_labels):
            layout.addStretch(1)  # no Spring panel: the panels on the left
        if live and not self._design_mode:
            self._timer.start()
        else:
            self._timer.stop()

    def _refresh_live_panels(self) -> None:
        for panel in self._panels._list:
            if panel._label is not None and panel._style != 0:
                panel._label.setText(panel._shown_text())
                if panel._style in _SBR_KEY_TEXTS:
                    panel._label.setEnabled(panel._enabled and _lock_key_on(panel._style))

    def _apply_Style(self, v):
        self._update_panels()

    def _apply_SimpleText(self, v):
        self._simple_label.setText(v)

    def _apply_Enabled(self, v):
        super()._apply_Enabled(v)
        self._update_panels()

    # -- events --------------------------------------------------------------------------------
    def _panel_at(self, pos) -> Panel | None:
        """The panel at a position in the bar, or None (between panels)."""
        for label in self._panel_labels:
            if label.geometry().contains(pos):
                return label._vp_panel
        return None

    def _on_qt_event(self, watched, event):
        etype = event.type()
        if not self._design_mode and etype in (QEvent.MouseButtonRelease,
                                               QEvent.MouseButtonDblClick):
            pos = event.position().toPoint()
            panel = self._panel_at(pos)
            if panel is not None and etype == QEvent.MouseButtonDblClick:
                self._fire("PanelDblClick", panel)
            elif panel is not None and self._widget.rect().contains(pos):
                self._fire("PanelClick", panel)
        return super()._on_qt_event(watched, event)


# --- TabStrip ----------------------------------------------------------------------------------

def parse_tab(line: str) -> dict:
    """A tab as the designer writes it (TabStrip.Tabs):
    ``Caption|Key|ToolTipText|Image``, e.g. ``&General|general|Name and size``;
    the Image is a Key or Index in the TabStrip's ImageList."""
    caption, _, rest = str(line).partition("|")
    key, _, rest = rest.partition("|")
    tip, _, image = rest.partition("|")
    return {"Caption": caption.strip(), "Key": key.strip(), "ToolTipText": tip.strip(),
            "Image": _image_ref(image) if image.strip() else ""}


class Tab(_KeyedItem):
    """One tab of a TabStrip (``TabStrip1.Tabs(1)`` or by Key)."""

    def __init__(self, strip: "TabStrip", key: str = "", caption: str = ""):
        self._strip = strip
        self._key = key
        self._caption = caption
        self._tooltip = ""
        self._image = ""
        self.Tag = ""

    def __repr__(self):
        return f"<Tab {self.Index} {self._key or self._caption!r}>"

    @property
    def Image(self):
        """The picture before the Caption: a Key or Index in the TabStrip's
        ImageList (without one, a picture file)."""
        return self._image

    @Image.setter
    def Image(self, value):
        value = "" if value is None else value
        _picture_icon(self._strip, value, strict=True)  # (an unknown Key raises here)
        self._image = value
        self._changed()

    @property
    def Caption(self) -> str:
        return self._caption

    @Caption.setter
    def Caption(self, value):
        self._caption = str(value)
        self._changed()

    @property
    def ToolTipText(self) -> str:
        return self._tooltip

    @ToolTipText.setter
    def ToolTipText(self, value):
        self._tooltip = str(value)
        self._changed()

    @property
    def Selected(self) -> bool:
        return self._strip.SelectedItem is self

    @Selected.setter
    def Selected(self, value):
        if value:
            self._strip.SelectedItem = self


class _Tabs(_KeyedCollection):
    """TabStrip.Tabs: its tabs in order, by Index (from 1) or Key."""

    _noun = "tab"

    def Add(self, Index=None, Key: str = "", Caption: str = "") -> Tab:
        """A new tab, at the end or at Index (from 1)."""
        tab = self._insert(Tab(self._owner, str(Key or ""), str(Caption)), Index)
        self._changed()
        return tab


class _TabWidget(QTabWidget):
    """A QTabWidget that can say where its pages go before it's shown (Qt
    lays them out only once it is visible)."""

    def contents_rect(self) -> QRect:
        """The pages' area, in the widget's coordinates: what Qt's own layout
        computes, from the style."""
        option = QStyleOptionTabWidgetFrame()
        self.initStyleOption(option)
        return self.style().subElementRect(QStyle.SE_TabWidgetTabContents, option, self)


class TabStrip(_UsesImageList, Control):
    """A row of tabs, like VB's TabStrip (Windows Common Controls). It isn't
    a container: put a Frame (or PictureBox) for each tab over its client
    area (ClientLeft, ClientTop, ClientWidth, ClientHeight) and show the one
    of the SelectedItem in Click. Returning True from BeforeClick keeps the
    current tab."""

    TypeName = "TabStrip"
    DefaultSize = (257, 177)
    Events = ("Click", "BeforeClick", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QTabWidget"
    Properties = (
        *_geometry(*DefaultSize),
        P("Tabs", "tabs", ["Tab1|tab1"],
          description="The tabs, set in the designer: one per line, "
                      "Caption|Key|ToolTipText|Image (an & in the Caption underlines its "
                      "access key; the Image is a Key or Index in the ImageList)"),
        P("Placement", "enum", 0, enum_choices("Top", "Bottom", "Left", "Right"),
          description="Which side the tabs are on"),
        P("ImageList", "str", "",
          description="The name of an ImageList on the form: the tabs' Image is then a "
                      "picture's Key or Index in it"),
        *_FONT, *_COMMON,
    )
    _QT_PLACEMENT = {0: QTabWidget.North, 1: QTabWidget.South, 2: QTabWidget.West,
                     3: QTabWidget.East}

    def _create_widget(self, parent):
        self.__dict__["_tabs"] = _Tabs(self, self._update_tabs)
        self.__dict__["_quiet"] = 0  # tabs being rebuilt: no Click
        self.__dict__["_current_tab"] = None  # the selected Tab (kept when tabs move)
        widget = _TabWidget(parent)
        widget.setUsesScrollButtons(True)
        return widget

    def _event_targets(self):
        return [self._widget, self._widget.tabBar()]

    def _connect_signals(self):
        self._widget.currentChanged.connect(self._on_current_changed)

    # -- the collection ----------------------------------------------------------------------
    @property
    def Tabs(self) -> _Tabs:
        return self._tabs

    @Tabs.setter
    def Tabs(self, lines):
        """In the designer (and InitializeComponent): the tabs as lines of
        text, see parse_tab."""
        self._set_prop("Tabs", lines)

    def _apply_Tabs(self, lines):
        self._tabs._reset()
        for line in lines or []:
            spec = parse_tab(line)
            tab = Tab(self, spec["Key"], spec["Caption"])
            tab._tooltip = spec["ToolTipText"]
            tab._image = spec["Image"]
            self._tabs._insert(tab)
        self._update_tabs()

    def _update_tabs(self) -> None:
        """Show the collection's tabs, keeping the selected one if it's still
        there (else the first)."""
        widget = self._widget
        selected = self._current_tab
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            while widget.count() > len(self._tabs):
                page = widget.widget(widget.count() - 1)
                widget.removeTab(widget.count() - 1)
                page.deleteLater()
            while widget.count() < len(self._tabs):
                widget.addTab(QWidget(), "")
            for index, tab in enumerate(self._tabs._list):
                widget.setTabText(index, tab._caption)
                widget.setTabToolTip(index, tab._tooltip)
                widget.setTabIcon(index, _picture_icon(self, tab._image))
            if selected in self._tabs._list:
                widget.setCurrentIndex(self._tabs._list.index(selected))
        finally:
            self.__dict__["_quiet"] = self._quiet - 1
        self.__dict__["_current_tab"] = self.SelectedItem

    # -- the selected tab --------------------------------------------------------------------
    @property
    def SelectedItem(self) -> "Tab | None":
        index = self._widget.currentIndex()
        return self._tabs._list[index] if 0 <= index < len(self._tabs) else None

    @SelectedItem.setter
    def SelectedItem(self, tab):
        """Select a tab (a Tab, its Index or its Key): Click fires, as in VB."""
        self._widget.setCurrentIndex(self._tabs._resolve(tab).Index - 1)

    def _on_current_changed(self, _index):
        if not self._quiet:
            self.__dict__["_current_tab"] = self.SelectedItem
            self._fire("Click")

    def _on_qt_event(self, watched, event):
        # BeforeClick: the user clicks another tab; True keeps the current one
        if not self._design_mode and watched is self._widget.tabBar() and \
                event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            index = watched.tabAt(event.position().toPoint())
            if index >= 0 and index != self._widget.currentIndex():
                if self._fire("BeforeClick") is True:
                    return True
        return super()._on_qt_event(watched, event)

    # -- the client area ---------------------------------------------------------------------
    def _client_rect(self) -> QRect:
        """The area inside the tabs' frame, in the container's coordinates
        (also before the form is shown, e.g. in Form_Load)."""
        return self._widget.contents_rect().translated(self._widget.pos())

    @property
    def ClientLeft(self) -> int:
        """Where the area inside the tabs starts (for the tabs' Frames), read-only."""
        return self._client_rect().x()

    @property
    def ClientTop(self) -> int:
        return self._client_rect().y()

    @property
    def ClientWidth(self) -> int:
        return self._client_rect().width()

    @property
    def ClientHeight(self) -> int:
        return self._client_rect().height()

    def _apply_Placement(self, v):
        self._widget.setTabPosition(self._QT_PLACEMENT.get(v, QTabWidget.North))

    def _refresh_images(self) -> None:
        if self._widget is not None:
            self._update_tabs()


# --- Toolbar -----------------------------------------------------------------------------------

_TBR_STYLE_WORDS = {"check": 1, "group": 2, "separator": 3}


def parse_button(line: str) -> dict:
    """A button as the designer writes it (Toolbar.Buttons):
    ``Caption|Key|Image|ToolTipText|options``, the Image a Key or Index in the
    Toolbar's ImageList and the options words: check or group (the Style),
    pressed, disabled, hidden. A line of just ``-`` is a separator. E.g.
    ``Open|open|open|Open a file`` or ``|bold|bold|Bold|check``."""
    line = str(line).strip()
    if line == "-":
        line = "||||separator"
    caption, key, image, tip, options = ([part.strip() for part in line.split("|", 4)] +
                                         [""] * 5)[:5]
    words = options.lower().split()
    style = next((_TBR_STYLE_WORDS[w] for w in words if w in _TBR_STYLE_WORDS), 0)
    return {"Caption": caption, "Key": key, "Image": _image_ref(image) if image else "",
            "ToolTipText": tip, "Style": style, "Value": 1 if "pressed" in words else 0,
            "Enabled": "disabled" not in words, "Visible": "hidden" not in words}


class Button(_KeyedItem):
    """One button of a Toolbar (``Toolbar1.Buttons(1)`` or by Key). Setting a
    property updates the toolbar at once."""

    def __init__(self, bar: "Toolbar", key: str = "", caption: str = "", style: int = 0,
                 image=""):
        self._bar = bar
        self._key = key
        self._caption = caption
        self._style = int(style)
        self._image = image
        self._value = 0
        self._tooltip = ""
        self._enabled = True
        self._visible = True
        self.Tag = ""
        self._action = None  # its QAction while it's shown

    def __repr__(self):
        return f"<Button {self.Index} {self._key or self._caption!r}>"

    @property
    def Caption(self) -> str:
        return self._caption

    @Caption.setter
    def Caption(self, value):
        self._caption = str(value)
        self._changed()

    @property
    def Image(self):
        """Its picture: a Key or Index in the Toolbar's ImageList (without one,
        a picture file)."""
        return self._image

    @Image.setter
    def Image(self, value):
        value = "" if value is None else value
        _picture_icon(self._bar, value, strict=True)  # (an unknown Key raises here)
        self._image = value
        self._changed()

    @property
    def Style(self) -> int:
        """vpTbrDefault, vpTbrCheck, vpTbrButtonGroup or vpTbrSeparator."""
        return self._style

    @Style.setter
    def Style(self, value):
        self._style = int(value)
        self._changed()

    @property
    def Value(self) -> int:
        """vpTbrPressed (1) or vpTbrUnpressed (0): a Check or ButtonGroup button's
        state. Pressing a ButtonGroup button releases the others of its group."""
        return self._value

    @Value.setter
    def Value(self, value):
        self._value = 1 if value else 0
        if self._value and self._style == 2:
            for other in self._bar._group_of(self):
                if other is not self:
                    other._value = 0
        self._changed()

    @property
    def ToolTipText(self) -> str:
        return self._tooltip

    @ToolTipText.setter
    def ToolTipText(self, value):
        self._tooltip = str(value)
        self._changed()

    @property
    def Enabled(self) -> bool:
        return self._enabled

    @Enabled.setter
    def Enabled(self, value):
        self._enabled = bool(value)
        self._changed()

    @property
    def Visible(self) -> bool:
        return self._visible

    @Visible.setter
    def Visible(self, value):
        self._visible = bool(value)
        self._changed()

    def _geometry(self) -> QRect:
        """Where its button is, in the Toolbar's container (read-only)."""
        widget = self._bar._widget.widgetForAction(self._action) if self._action else None
        if widget is None:
            return QRect()
        self._bar._widget.layout().activate()  # (just added buttons aren't placed yet)
        return widget.geometry().translated(self._bar._widget.pos())

    @property
    def Left(self) -> int:
        return self._geometry().x()

    @property
    def Top(self) -> int:
        return self._geometry().y()

    @property
    def Width(self) -> int:
        return self._geometry().width()

    @property
    def Height(self) -> int:
        return self._geometry().height()


class _Buttons(_KeyedCollection):
    """Toolbar.Buttons: its buttons in order, by Index (from 1) or Key."""

    _noun = "button"

    def Add(self, Index=None, Key: str = "", Caption: str = "", Style: int = 0,
            Image="") -> Button:
        """A new button, at the end or at Index (from 1)."""
        button = Button(self._owner, str(Key or ""), str(Caption), Style)
        if Image not in (None, ""):
            _picture_icon(self._owner, Image, strict=True)
            button._image = Image
        self._insert(button, Index)
        self._changed()
        return button


class Toolbar(_Docked, _UsesImageList, Control):
    """A row of buttons along the top of a form, like VB's Toolbar (Windows
    Common Controls): pictures from an ImageList, captions, check buttons,
    groups of buttons of which one is pressed, and separators. It docks like
    an aligned PictureBox (Top by default), as tall as its buttons need.
    ButtonClick gets the Button."""

    TypeName = "Toolbar"
    DefaultEvent = "ButtonClick"
    DefaultSize = (400, 40)
    Events = ("ButtonClick", "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QToolBar"
    Properties = (
        *_geometry(*DefaultSize),
        P("Align", "enum", 1, enum_choices("None", "Top", "Bottom", "Left", "Right"),
          description="The edge it docks to (Top), like an aligned PictureBox; Left and "
                      "Right make a vertical toolbar; None: where you put it"),
        P("Buttons", "buttons", ["Button1|button1"],
          description="The buttons, set in the designer: one per line, "
                      "Caption|Key|Image|ToolTipText|options (check, group, pressed, "
                      "disabled, hidden); - alone is a separator"),
        P("ImageList", "str", "",
          description="The name of an ImageList on the form: the buttons' Image is then a "
                      "picture's Key or Index in it"),
        P("TextAlignment", "enum", 0, enum_choices("Bottom", "Right"),
          description="Where a button's Caption is: under its picture, or beside it"),
        *_FONT,
        P("Enabled", "bool", True, description="Whether the control responds to the user"),
        P("Visible", "bool", True, description="Whether the control is shown at run time"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def _create_widget(self, parent):
        self.__dict__["_buttons"] = _Buttons(self, self._update_buttons)
        self.__dict__["_groups"] = []  # the QActionGroups of the ButtonGroup runs
        widget = QToolBar(parent)
        widget.setMovable(False)
        widget.setFloatable(False)
        return widget

    # -- the collection ----------------------------------------------------------------------
    @property
    def Buttons(self) -> _Buttons:
        return self._buttons

    @Buttons.setter
    def Buttons(self, lines):
        """In the designer (and InitializeComponent): the buttons as lines of
        text, see parse_button."""
        self._set_prop("Buttons", lines)

    def _apply_Buttons(self, lines):
        self._buttons._reset()
        for line in lines or []:
            spec = parse_button(line)
            button = Button(self, spec["Key"], spec["Caption"], spec["Style"], spec["Image"])
            button._tooltip = spec["ToolTipText"]
            button._value = spec["Value"]
            button._enabled = spec["Enabled"]
            button._visible = spec["Visible"]
            self._buttons._insert(button)
        self._update_buttons()

    def _group_of(self, button: Button) -> list[Button]:
        """The run of adjacent ButtonGroup buttons ``button`` is in."""
        runs, run = [], []
        for other in self._buttons._list:
            if other._style == 2:
                run.append(other)
            elif run:
                runs.append(run)
                run = []
        runs.append(run)
        return next((r for r in runs if button in r), [button])

    # -- showing the buttons -----------------------------------------------------------------
    def _update_buttons(self) -> None:
        """Rebuild the toolbar from the buttons."""
        widget = self._widget
        if widget is None:
            return
        widget.clear()
        for group in self._groups:
            group.deleteLater()
        self._groups.clear()
        images = self._image_list()
        if images is not None and all(images._size()):
            widget.setIconSize(QSize(*images._size()))
        vertical = self._values.get("Align", 1) in (3, 4)
        widget.setOrientation(Qt.Vertical if vertical else Qt.Horizontal)
        widget.setToolButtonStyle(Qt.ToolButtonTextBesideIcon
                                  if self._values.get("TextAlignment", 0) == 1
                                  else Qt.ToolButtonTextUnderIcon)
        group = None
        for button in self._buttons._list:
            button._action = None
            if button._style != 2:
                group = None
            if not button._visible:
                continue
            if button._style == 3:
                button._action = widget.addSeparator()
                continue
            action = widget.addAction(_picture_icon(self, button._image), button._caption)
            action.setToolTip(button._tooltip or button._caption)
            action.setEnabled(button._enabled)
            if button._style in (1, 2):
                action.setCheckable(True)
                action.setChecked(bool(button._value))
            if button._style == 2:
                if group is None:
                    group = QActionGroup(widget)
                    group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
                    self._groups.append(group)
                group.addAction(action)
            action.triggered.connect(lambda checked=False, b=button: self._on_triggered(b))
            button._action = action
            tool = widget.widgetForAction(action)
            if tool is not None:
                tool.setFocusPolicy(Qt.NoFocus)
        self._fit()

    def _fit(self) -> None:
        """Docked: as tall (Top, Bottom) or as wide (Left, Right) as the buttons need."""
        align = self._values.get("Align", 1)
        if not align:
            return
        hint = self._widget.sizeHint()
        if align in (1, 2):
            self._values["Height"] = hint.height()
        else:
            self._values["Width"] = hint.width()
        self._relayout()

    def _on_triggered(self, button: Button) -> None:
        action = button._action
        if button._style == 2 and not action.isChecked():
            action.setChecked(True)  # a pressed group button stays pressed, as in VB
        if button._style in (1, 2):
            for other in self._group_of(button) if button._style == 2 else [button]:
                other._value = 1 if other._action is not None and \
                    other._action.isChecked() else 0
        self._fire("ButtonClick", button)

    def _refresh_images(self) -> None:
        self._update_buttons()

    def _apply_Align(self, v):
        self._update_buttons()  # (its orientation, and its size)

    def _apply_TextAlignment(self, v):
        self._update_buttons()

    def _apply_font(self, _=None):
        super()._apply_font()
        if self._widget is not None and "_buttons" in self.__dict__:
            self._fit()

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font


# --- ListView ----------------------------------------------------------------------------------

_LVW_ALIGNMENT = ("left", "right", "center")  # ColumnHeader.Alignment, by value
_QT_COLUMN_ALIGN = {0: Qt.AlignLeft, 1: Qt.AlignRight, 2: Qt.AlignHCenter}


def parse_column(line: str) -> dict:
    """A column as the designer writes it (ListView.ColumnHeaders):
    ``Text|Key|Width|alignment``, the alignment left, right or center, e.g.
    ``Size|size|80|right``."""
    text, key, width, align = ([part.strip() for part in str(line).split("|", 3)] +
                               [""] * 4)[:4]
    return {"Text": text, "Key": key, "Width": int(width) if width.isdigit() else 100,
            "Alignment": _LVW_ALIGNMENT.index(align.lower())
            if align.lower() in _LVW_ALIGNMENT else 0}


def parse_list_item(line: str) -> dict:
    """An item as the designer writes it (ListView.ListItems):
    ``Text|Key|Icon|SmallIcon|SubItem 1|SubItem 2...``, the icons Keys or
    Indexes in the Icons and SmallIcons ImageLists, e.g.
    ``Earth|earth|planet|planet|12756 km|1 moon``."""
    parts = [part.strip() for part in str(line).split("|")]
    text, key, icon, small = (parts + [""] * 4)[:4]
    return {"Text": text, "Key": key, "Icon": _image_ref(icon) if icon else "",
            "SmallIcon": _image_ref(small) if small else "", "SubItems": parts[4:]}


class ColumnHeader(_KeyedItem):
    """One column of a ListView's Report view (``ListView1.ColumnHeaders(1)`` or
    by Key): the first shows the items' Text, the others their SubItems."""

    def __init__(self, view: "ListView", key: str = "", text: str = "", width: int = 100,
                 alignment: int = 0):
        self._view = view
        self._key = key
        self._text = text
        self._width = int(width)
        self._alignment = int(alignment)
        self.Tag = ""

    def __repr__(self):
        return f"<ColumnHeader {self.Index} {self._key or self._text!r}>"

    @property
    def Text(self) -> str:
        return self._text

    @Text.setter
    def Text(self, value):
        self._text = str(value)
        self._changed()

    @property
    def Width(self) -> int:
        """Its width in pixels (the user can drag it too)."""
        if self._view._columns_shown():
            return self._view._tree.columnWidth(self.Index - 1)
        return self._width

    @Width.setter
    def Width(self, value):
        self._width = max(0, int(value))
        self._changed()

    @property
    def Alignment(self) -> int:
        """vpLvwColumnLeft, vpLvwColumnRight or vpLvwColumnCenter (the first
        column is always left-aligned, as in VB)."""
        return self._alignment

    @Alignment.setter
    def Alignment(self, value):
        self._alignment = int(value)
        self._changed()

    @property
    def SubItemIndex(self) -> int:
        """Which SubItem it shows: 0 for the first column (the Text)."""
        return self.Index - 1


class _ColumnHeaders(_KeyedCollection):
    """ListView.ColumnHeaders: its columns in order, by Index (from 1) or Key."""

    _noun = "column"

    def Add(self, Index=None, Key: str = "", Text: str = "", Width: int = 100,
            Alignment: int = 0) -> ColumnHeader:
        """A new column, at the end or at Index (from 1)."""
        column = self._insert(ColumnHeader(self._owner, str(Key or ""), str(Text), Width,
                                           Alignment), Index)
        self._changed()
        return column


class _SubItems:
    """A ListItem's SubItems, its texts in the Report view's other columns:
    ``item.SubItems(1)`` (or ``[1]``) reads one, ``item.SubItems[1] = "x"``
    sets one (VB's ``Item.SubItems(1) = "x"``)."""

    def __init__(self, item: "ListItem"):
        self._item = item

    def __call__(self, index: int) -> str:
        return self[index]

    def __getitem__(self, index: int) -> str:
        cell = self._item._cell(int(index))
        return cell.text() if cell is not None else ""

    def __setitem__(self, index: int, value) -> None:
        index = int(index)
        if index < 1:
            raise IndexError("SubItems start at 1 (0 is the item's Text)")
        self._item._set_cell(index, str(value))

    def __len__(self):
        return max(self._item._view._model.columnCount() - 1, 0)


class ListItem:
    """One item of a ListView (``ListView1.ListItems(1)`` or by Key): its Text,
    pictures (Icon for the Icon view, SmallIcon for the others) and, in the
    Report view, its SubItems."""

    def __init__(self, view: "ListView", cell: QStandardItem, key: str):
        self._view = view
        self._cell0 = cell  # its first column; the row is where it is
        self._key = key
        self._icon = ""
        self._small_icon = ""
        self._check = Qt.Unchecked
        self.Tag = ""
        cell.setData(self, Qt.UserRole)

    def __repr__(self):
        return f"<ListItem {self.Index} {self._key or self.Text!r}>"

    def _row(self) -> int:
        return self._cell0.row()

    def _cell(self, column: int):
        return self._view._model.item(self._row(), column)

    def _set_cell(self, column: int, text: str) -> None:
        model = self._view._model
        if column >= model.columnCount():
            model.setColumnCount(column + 1)
        cell = model.item(self._row(), column)
        if cell is None:
            cell = QStandardItem()
            cell.setEditable(False)
            cell.setTextAlignment(self._view._column_alignment(column))
            model.setItem(self._row(), column, cell)
        cell.setText(text)
        self._view._keep_sorted()

    @property
    def Index(self) -> int:
        """Its position in the list, from 1 (sorting changes it, as in VB)."""
        return self._row() + 1

    @property
    def Key(self) -> str:
        return self._key

    @Key.setter
    def Key(self, value):
        value = str(value)
        by_key = self._view._items._by_key
        if value and value != self._key and value in by_key:
            raise KeyError(f"Key '{value}' is not unique in the collection")
        by_key.pop(self._key, None)
        self._key = value
        if value:
            by_key[value] = self

    @property
    def Text(self) -> str:
        return self._cell0.text()

    @Text.setter
    def Text(self, value):
        with self._view._quietly():
            self._cell0.setText(str(value))
        self._view._keep_sorted()

    @property
    def SubItems(self) -> _SubItems:
        return _SubItems(self)

    @property
    def Icon(self):
        """Its picture in the Icon view: a Key or Index in the Icons ImageList."""
        return self._icon

    @Icon.setter
    def Icon(self, value):
        value = "" if value is None else value
        _picture_icon(self._view, value, strict=True, prop="Icons")
        self._icon = value
        self._view._show_icon(self)

    @property
    def SmallIcon(self):
        """Its picture in the other views: a Key or Index in the SmallIcons
        ImageList."""
        return self._small_icon

    @SmallIcon.setter
    def SmallIcon(self, value):
        value = "" if value is None else value
        _picture_icon(self._view, value, strict=True, prop="SmallIcons")
        self._small_icon = value
        self._view._show_icon(self)

    @property
    def ToolTipText(self) -> str:
        return self._cell0.toolTip()

    @ToolTipText.setter
    def ToolTipText(self, value):
        self._cell0.setToolTip(str(value))

    @property
    def Selected(self) -> bool:
        return self._view._selection().isSelected(self._cell0.index())

    @Selected.setter
    def Selected(self, value):
        flags = QItemSelectionModel.Select if value else QItemSelectionModel.Deselect
        with self._view._quietly():
            if value and not self._view._values.get("MultiSelect"):
                self._view._selection().clear()
            self._view._selection().select(
                self._cell0.index(), flags | QItemSelectionModel.Rows)

    @property
    def Checked(self) -> bool:
        """Its check box (with the ListView's Checkboxes)."""
        return self._cell0.checkState() == Qt.Checked

    @Checked.setter
    def Checked(self, value):
        with self._view._quietly():
            self._check = Qt.Checked if value else Qt.Unchecked
            if self._view._values.get("Checkboxes"):
                self._cell0.setCheckState(self._check)

    def EnsureVisible(self) -> None:
        """Scroll so the item can be seen."""
        self._view._current_view().scrollTo(self._cell0.index())


class _ListItems:
    """ListView.ListItems: its items in the order shown, by Index (from 1) or
    Key."""

    def __init__(self, view: "ListView"):
        self._view = view
        self._by_key: dict[str, ListItem] = {}

    def _list(self) -> list[ListItem]:
        model = self._view._model
        return [model.item(row, 0).data(Qt.UserRole) for row in range(model.rowCount())]

    def __len__(self):
        return self._view._model.rowCount()

    def __iter__(self):
        return iter(self._list())

    def __contains__(self, key) -> bool:
        return key in self._by_key

    @property
    def Count(self) -> int:
        return len(self)

    def _resolve(self, index) -> ListItem:
        if isinstance(index, ListItem):
            return index
        if isinstance(index, str):
            if index not in self._by_key:
                raise KeyError(f"No item with the key '{index}'")
            return self._by_key[index]
        index = int(index)
        if not 1 <= index <= len(self):
            raise IndexError(f"No item {index} (there are {len(self)})")
        return self._view._model.item(index - 1, 0).data(Qt.UserRole)

    def __call__(self, index) -> ListItem:
        return self._resolve(index)

    Item = __call__

    def Add(self, Index=None, Key: str = "", Text: str = "", Icon="",
            SmallIcon="") -> ListItem:
        """A new item, at the end or at Index (from 1); in a Sorted ListView,
        where the order puts it."""
        Key = str(Key or "")
        if Key and Key in self._by_key:
            raise KeyError(f"Key '{Key}' is not unique in the collection")
        view = self._view
        cell = QStandardItem(str(Text))
        cell.setEditable(False)
        item = ListItem(view, cell, Key)
        with view._quietly():
            row = view._model.rowCount() if Index is None else \
                max(0, min(int(Index) - 1, view._model.rowCount()))
            view._model.insertRow(row, [cell])
            if view._values.get("Checkboxes"):
                cell.setCheckable(True)
                cell.setCheckState(Qt.Unchecked)
        if Key:
            self._by_key[Key] = item
        if Icon not in (None, ""):
            item.Icon = Icon
        if SmallIcon not in (None, ""):
            item.SmallIcon = SmallIcon
        view._keep_sorted()
        return item

    def Remove(self, index) -> None:
        item = self._resolve(index)
        self._by_key.pop(item._key, None)
        with self._view._quietly():
            self._view._model.removeRow(item._row())

    def Clear(self) -> None:
        self._by_key.clear()
        with self._view._quietly():
            self._view._model.removeRows(0, self._view._model.rowCount())


class ListView(_UsesImageList, Control):
    """A list of items shown as large icons, small icons, a list, or a report
    with columns, like VB's ListView (Windows Common Controls). Fill it in
    the designer (ListItems, ColumnHeaders) or in code (ListItems.Add,
    ColumnHeaders.Add). ItemClick gets the ListItem, ColumnClick the
    ColumnHeader (sort by it with SortKey and Sorted)."""

    TypeName = "ListView"
    DefaultEvent = "ItemClick"
    DefaultSize = (257, 177)
    Events = ("ItemClick", "ColumnClick", "ItemCheck", "Click", "DblClick", "GotFocus",
              "LostFocus", "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QAbstractItemView"
    _IMAGE_LIST_PROPS = ("Icons", "SmallIcons")
    Properties = (
        *_geometry(*DefaultSize),
        P("View", "enum", 0, enum_choices("Icon", "SmallIcon", "List", "Report"),
          description="How the items are shown: large icons, small icons, a list, or a "
                      "report with a column per ColumnHeader"),
        P("ColumnHeaders", "columns", [],
          description="The Report view's columns, set in the designer: one per line, "
                      "Text|Key|Width|alignment (left, right or center); the first shows the "
                      "items' Text, the others their SubItems"),
        P("ListItems", "listitems", [],
          description="The items, set in the designer: one per line, "
                      "Text|Key|Icon|SmallIcon|SubItem 1|SubItem 2..."),
        P("Icons", "str", "",
          description="The name of the ImageList with the items' Icons (the Icon view)"),
        P("SmallIcons", "str", "",
          description="The name of the ImageList with the items' SmallIcons (the other "
                      "views)"),
        P("Sorted", "bool", False, description="Keep the items sorted by the SortKey column"),
        P("SortKey", "int", 0,
          description="The column to sort by: 0 = the items' Text, 1 = the first SubItem..."),
        P("SortOrder", "enum", 0, enum_choices("Ascending", "Descending"),
          description="A to Z, or Z to A"),
        P("MultiSelect", "bool", False,
          description="Several items can be selected (Ctrl/Cmd- and Shift-click)"),
        P("Checkboxes", "bool", False, description="A check box in front of every item"),
        P("HideColumnHeaders", "bool", False,
          description="Hide the Report view's column titles"),
        *_COLORS, *_FONT, *_COMMON,
    )
    _QT_VIEWS = {  # View -> (QListView mode, flow): Report is the QTreeView
        0: (QListView.IconMode, QListView.LeftToRight),
        1: (QListView.ListMode, QListView.LeftToRight),
        2: (QListView.ListMode, QListView.TopToBottom),
    }

    def _create_widget(self, parent):
        self.__dict__["_quiet"] = 0
        self.__dict__["_columns"] = _ColumnHeaders(self, self._update_columns)
        model = QStandardItemModel()
        self.__dict__["_model"] = model
        self.__dict__["_items"] = _ListItems(self)
        widget = QWidget(parent)
        stack = QStackedLayout(widget)
        stack.setContentsMargins(0, 0, 0, 0)
        icons = QListView()
        icons.setModel(model)
        icons.setResizeMode(QListView.Adjust)
        icons.setWrapping(True)
        icons.setUniformItemSizes(False)
        icons.setEditTriggers(QAbstractItemView.NoEditTriggers)
        report = QTreeView()
        report.setModel(model)
        report.setSelectionModel(icons.selectionModel())  # one selection for every view
        report.setRootIsDecorated(False)
        report.setItemsExpandable(False)
        report.setUniformRowHeights(True)
        report.setEditTriggers(QAbstractItemView.NoEditTriggers)
        report.setSelectionBehavior(QAbstractItemView.SelectRows)
        report.header().setSectionsClickable(True)
        report.header().setStretchLastSection(False)
        stack.addWidget(icons)
        stack.addWidget(report)
        self.__dict__["_icons"], self.__dict__["_tree"] = icons, report
        self.__dict__["_stack"] = stack
        return widget

    def _event_targets(self):
        return [self._icons, self._icons.viewport(), self._tree, self._tree.viewport()]

    def _connect_signals(self):
        for view in (self._icons, self._tree):
            view.clicked.connect(self._on_clicked)
        self._tree.header().sectionClicked.connect(self._on_header_clicked)
        self._model.itemChanged.connect(self._on_item_changed)

    def _quietly(self) -> _Quiet:
        return _Quiet(self)

    # -- the collections -----------------------------------------------------------------------
    @property
    def ListItems(self) -> _ListItems:
        return self._items

    @ListItems.setter
    def ListItems(self, lines):
        """In the designer (and InitializeComponent): the items as lines of
        text, see parse_list_item."""
        self._set_prop("ListItems", lines)

    @property
    def ColumnHeaders(self) -> _ColumnHeaders:
        return self._columns

    @ColumnHeaders.setter
    def ColumnHeaders(self, lines):
        """In the designer: the columns as lines of text, see parse_column."""
        self._set_prop("ColumnHeaders", lines)

    def _apply_ListItems(self, lines):
        self._items.Clear()
        for line in lines or []:
            spec = parse_list_item(line)
            item = self._items.Add(Key=spec["Key"], Text=spec["Text"])
            item._icon, item._small_icon = spec["Icon"], spec["SmallIcon"]
            for number, text in enumerate(spec["SubItems"], 1):
                item.SubItems[number] = text
        self._refresh_images()  # (the ImageLists may come later)

    def _apply_ColumnHeaders(self, lines):
        self._columns._reset()
        for line in lines or []:
            spec = parse_column(line)
            self._columns._insert(ColumnHeader(self, spec["Key"], spec["Text"], spec["Width"],
                                               spec["Alignment"]))
        self._update_columns()

    def _columns_shown(self) -> bool:
        return len(self._columns) > 0

    def _column_alignment(self, number: int):
        """A column's cells' alignment (the first column is always left)."""
        column = self._columns._list[number] if 0 < number < len(self._columns) else None
        align = _QT_COLUMN_ALIGN.get(column._alignment, Qt.AlignLeft) if column else Qt.AlignLeft
        return align | Qt.AlignVCenter

    def _update_columns(self) -> None:
        model, tree = self._model, self._tree
        count = max(len(self._columns), 1, model.columnCount())
        model.setColumnCount(count)
        model.setHorizontalHeaderLabels(
            [c._text for c in self._columns._list] +
            [""] * (count - len(self._columns)))
        for number, column in enumerate(self._columns._list):
            tree.setColumnWidth(number, column._width)
            align = self._column_alignment(number)
            model.setHeaderData(number, Qt.Horizontal, int(align), Qt.TextAlignmentRole)
            for row in range(model.rowCount()):
                cell = model.item(row, number)
                if cell is not None:
                    cell.setTextAlignment(align)
        for number in range(model.columnCount()):  # only the ColumnHeaders' columns show
            tree.setColumnHidden(number, self._columns_shown() and
                                 number >= len(self._columns))
        self._apply_HideColumnHeaders(self._values.get("HideColumnHeaders", False))

    # -- views ---------------------------------------------------------------------------------
    def _current_view(self):
        return self._tree if self._values.get("View", 0) == 3 else self._icons

    def _selection(self) -> QItemSelectionModel:
        return self._icons.selectionModel()

    def _apply_View(self, v):
        if v == 3:
            self._stack.setCurrentWidget(self._tree)
        else:
            mode, flow = self._QT_VIEWS.get(v, self._QT_VIEWS[0])
            self._icons.setViewMode(mode)
            self._icons.setFlow(flow)
            self._icons.setWrapping(True)
            self._icons.setResizeMode(QListView.Adjust)
            self._icons.setSpacing(8 if v == 0 else 2)
            self._stack.setCurrentWidget(self._icons)
        self._refresh_images()  # Icons in the Icon view, SmallIcons in the others

    def _show_icon(self, item: ListItem) -> None:
        large = self._values.get("View", 0) == 0
        ref, prop = (item._icon, "Icons") if large else (item._small_icon, "SmallIcons")
        with self._quietly():
            item._cell0.setIcon(_picture_icon(self, ref, prop=prop))

    def _refresh_images(self) -> None:
        large = self._image_list("Icons") if self._values.get("View", 0) == 0 else \
            self._image_list("SmallIcons")
        if large is not None and all(large._size()):
            self._icons.setIconSize(QSize(*large._size()))
            self._tree.setIconSize(QSize(*large._size()))
        for item in self._items:
            self._show_icon(item)

    def _apply_Icons(self, v):
        self._refresh_images()

    _apply_SmallIcons = _apply_Icons

    # -- sorting -------------------------------------------------------------------------------
    def _keep_sorted(self) -> None:
        if self._values.get("Sorted"):
            order = Qt.DescendingOrder if self._values.get("SortOrder") == 1 else \
                Qt.AscendingOrder
            column = max(0, int(self._values.get("SortKey", 0)))
            if column < self._model.columnCount():
                with self._quietly():
                    self._model.sort(column, order)

    def _apply_Sorted(self, v):
        self._keep_sorted()

    _apply_SortKey = _apply_SortOrder = _apply_Sorted

    # -- other properties -----------------------------------------------------------------------
    def _apply_MultiSelect(self, v):
        mode = QAbstractItemView.ExtendedSelection if v else QAbstractItemView.SingleSelection
        self._icons.setSelectionMode(mode)
        self._tree.setSelectionMode(mode)

    def _apply_Checkboxes(self, v):
        with self._quietly():
            for item in self._items:
                item._cell0.setCheckable(bool(v))
                if v:
                    item._cell0.setCheckState(item._check)
                else:
                    item._cell0.setData(None, Qt.CheckStateRole)

    def _apply_HideColumnHeaders(self, v):
        self._tree.setHeaderHidden(bool(v) or not self._columns_shown())

    def _apply_font(self, _=None):
        super()._apply_font()
        if self._widget is not None:
            for view in (self._icons, self._tree):
                view.setFont(self._widget.font())

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font

    def _apply_colors(self, _=None):
        super()._apply_colors()
        if self._widget is not None:
            sheet = self._widget.styleSheet()
            for view in (self._icons, self._tree):
                view.setStyleSheet(sheet)

    _apply_BackColor = _apply_ForeColor = _apply_colors

    # -- the selected item, and finding items -------------------------------------------------
    @property
    def SelectedItem(self) -> "ListItem | None":
        index = self._selection().currentIndex()
        if not index.isValid() or not self._selection().isSelected(index.siblingAtColumn(0)):
            return None
        return self._model.item(index.row(), 0).data(Qt.UserRole)

    @SelectedItem.setter
    def SelectedItem(self, item):
        with self._quietly():
            if item is None:
                self._selection().clear()
                return
            item = self._items._resolve(item)
            self._selection().setCurrentIndex(
                item._cell0.index(), QItemSelectionModel.ClearAndSelect |
                QItemSelectionModel.Rows)

    def HitTest(self, X: int, Y: int) -> "ListItem | None":
        """The item at a position (as the mouse events give it), or None."""
        view = self._current_view()
        point = view.viewport().mapFrom(self._widget, QPoint(int(X), int(Y)))
        index = view.indexAt(point)
        return self._model.item(index.row(), 0).data(Qt.UserRole) if index.isValid() else None

    # -- events --------------------------------------------------------------------------------
    def _on_clicked(self, index):
        if not self._quiet and index.isValid():
            self._fire("ItemClick", self._model.item(index.row(), 0).data(Qt.UserRole))

    def _on_header_clicked(self, section):
        if not self._quiet and 0 <= section < len(self._columns):
            self._fire("ColumnClick", self._columns._list[section])

    def _on_item_changed(self, cell):
        if self._quiet or cell.column() != 0:
            return
        item = cell.data(Qt.UserRole)
        if item is None or not cell.isCheckable():
            return
        state = cell.checkState()
        if state != item._check:
            item._check = state
            self._fire("ItemCheck", item)


# Controls in toolbox order.
_PEN_STYLES = {1: Qt.SolidLine, 2: Qt.DashLine, 3: Qt.DotLine, 4: Qt.DashDotLine,
               5: Qt.DashDotDotLine, 6: Qt.SolidLine}


class _LineWidget(QWidget):
    """Covers the line's bounding box and paints the line; clicks go through
    to whatever is underneath (a VB Line has no events)."""

    def __init__(self, line: "Line", parent: QWidget):
        super().__init__(parent)
        self._line = line
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        line = self._line
        style = line._values.get("BorderStyle", 1)
        if style == 0:  # Transparent
            return
        color = line._values.get("BorderColor")
        pen = QPen(colors.to_qcolor(color) if color is not None
                   else self.palette().color(QPalette.WindowText))  # follows the scheme
        pen.setWidth(max(1, line._values.get("BorderWidth", 1)))
        pen.setStyle(_PEN_STYLES.get(style, Qt.SolidLine))
        pen.setCapStyle(Qt.FlatCap if style == 1 and pen.width() == 1 else Qt.RoundCap)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, line.X1 != line.X2 and line.Y1 != line.Y2)
        painter.setPen(pen)
        origin = self.pos()
        painter.drawLine(line.X1 - origin.x(), line.Y1 - origin.y(),
                         line.X2 - origin.x(), line.Y2 - origin.y())


class Line(Control):
    """A straight line from (X1, Y1) to (X2, Y2), in its container's
    coordinates. It has no events and never takes the focus; clicks go to
    what is underneath."""

    TypeName = "Line"
    DefaultEvent = ""
    Events: tuple[str, ...] = ()
    DefaultSize = (100, 0)  # a new line: 100 pixels to the right
    Properties = (
        P("X1", "int", 0, always=True, description="Horizontal position of the start"),
        P("Y1", "int", 0, always=True, description="Vertical position of the start"),
        P("X2", "int", 100, always=True, description="Horizontal position of the end"),
        P("Y2", "int", 0, always=True, description="Vertical position of the end"),
        P("BorderColor", "color", None,
          description="The line's color; unset = the text color of the color scheme"),
        P("BorderStyle", "enum", 1, enum_choices(
            "Transparent", "Solid", "Dash", "Dot", "Dash-Dot", "Dash-Dot-Dot", "Inside Solid"),
          description="How the line is drawn; Transparent hides it"),
        P("BorderWidth", "int", 1, description="Thickness in pixels"),
        P("Visible", "bool", True, description="Whether the line is shown at run time"),
        P("Tag", "str", "", description="Free for your own use"),
        next(spec for spec in _COMMON if spec.name == "ZIndex"),
    )

    def _create_widget(self, parent):
        return _LineWidget(self, parent)

    def _event_targets(self):
        return []  # no events

    def _padding(self) -> int:
        return max(1, self._values.get("BorderWidth", 1)) // 2 + 2

    def _update_geometry(self, _=None) -> None:
        """The widget covers the line plus room for its width."""
        if self._widget is None or not all(k in self._values for k in ("X1", "Y1", "X2", "Y2")):
            return
        x1, y1, x2, y2 = (self._values[k] for k in ("X1", "Y1", "X2", "Y2"))
        pad = self._padding()
        self._widget.setGeometry(min(x1, x2) - pad, min(y1, y2) - pad,
                                 abs(x2 - x1) + 2 * pad + 1, abs(y2 - y1) + 2 * pad + 1)
        self._widget.update()

    _apply_X1 = _apply_Y1 = _apply_X2 = _apply_Y2 = _apply_BorderWidth = _update_geometry

    def _repaint(self, _=None) -> None:
        if self._widget is not None:
            self._widget.update()

    _apply_BorderColor = _apply_BorderStyle = _repaint

    def _moved_points(self) -> dict[str, int]:
        """X1..Y2 after the widget was moved (the designer drags the widget)."""
        pad = self._padding()
        dx = self._widget.x() - (min(self.X1, self.X2) - pad)
        dy = self._widget.y() - (min(self.Y1, self.Y2) - pad)
        return {"X1": self.X1 + dx, "Y1": self.Y1 + dy, "X2": self.X2 + dx, "Y2": self.Y2 + dy}


# --- Shape -------------------------------------------------------------------------------

_HATCH_SPACING = 8  # pixels between a hatched fill's lines
# A FillStyle's lines: their directions as (dx, dy) steps, 2 Horizontal ... 7 Diagonal Cross
_HATCHES = {2: ((1, 0),), 3: ((0, 1),), 4: ((1, -1),), 5: ((1, 1),), 6: ((1, 0), (0, 1)),
            7: ((1, -1), (1, 1))}


def _hatch(painter: QPainter, path: QPainterPath, style: int, color: QColor) -> None:
    """Fill a path with a FillStyle's lines (drawn, not a brush pattern, so they
    stay crisp on high-resolution screens)."""
    bounds = path.boundingRect()
    painter.save()
    painter.setClipPath(path)
    painter.setPen(QPen(color, 1))
    size = bounds.width() + bounds.height()
    for dx, dy in _HATCHES[style]:
        if dy == 0:  # horizontal
            y = bounds.top() + _HATCH_SPACING / 2
            while y < bounds.bottom():
                painter.drawLine(QPointF(bounds.left(), y), QPointF(bounds.right(), y))
                y += _HATCH_SPACING
        elif dx == 0:  # vertical
            x = bounds.left() + _HATCH_SPACING / 2
            while x < bounds.right():
                painter.drawLine(QPointF(x, bounds.top()), QPointF(x, bounds.bottom()))
                x += _HATCH_SPACING
        else:  # diagonal: lines across the whole box, one spacing apart
            offset = -size
            while offset < size:
                start = QPointF(bounds.left() + offset, bounds.top() if dy > 0 else bounds.bottom())
                painter.drawLine(start, start + QPointF(size, size * dy))
                offset += _HATCH_SPACING * 1.4142
    painter.restore()


class _ShapeWidget(QWidget):
    """Paints a Shape in its rectangle; clicks go through to whatever is
    underneath (a VB Shape has no events)."""

    def __init__(self, shape: "Shape", parent: QWidget):
        super().__init__(parent)
        self._shape = shape
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        values = self._shape._values
        kind = values.get("Shape", 0)
        border_style = values.get("BorderStyle", 1)
        width = max(1, values.get("BorderWidth", 1)) if border_style else 0
        rect = QRectF(self.rect())
        if kind in (1, 3, 5):  # Square, Circle, Rounded Square: centered, as wide as high
            side = min(rect.width(), rect.height())
            rect = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side,
                          side)
        rect = rect.adjusted(width / 2, width / 2, -width / 2, -width / 2)  # (inside it)
        path = QPainterPath()
        if kind in (2, 3):
            path.addEllipse(rect)
        elif kind in (4, 5):
            radius = min(rect.width(), rect.height()) / 6
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, kind >= 2)
        text_color = self.palette().color(QPalette.WindowText)  # (follows the scheme)
        if values.get("BackStyle", 0) == 1:  # Opaque: its BackColor behind the fill
            back = values.get("BackColor")
            painter.fillPath(path, colors.to_qcolor(back) if back is not None
                             else self.palette().color(QPalette.Window))
        fill_style = values.get("FillStyle", 1)
        fill = values.get("FillColor")
        fill_color = colors.to_qcolor(fill) if fill is not None else text_color
        if fill_style == 0:  # Solid
            painter.fillPath(path, fill_color)
        elif fill_style in _HATCHES:  # (1: Transparent)
            _hatch(painter, path, fill_style, fill_color)
        if border_style:
            border = values.get("BorderColor")
            pen = QPen(colors.to_qcolor(border) if border is not None else text_color)
            pen.setWidth(width)
            pen.setStyle(_PEN_STYLES.get(border_style, Qt.SolidLine))
            pen.setJoinStyle(Qt.MiterJoin)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.end()


class Shape(Control):
    """A rectangle, square, oval, circle or rounded rectangle (Shape), with a
    border (BorderStyle, BorderColor, BorderWidth), a fill (FillStyle, solid
    or hatched, in FillColor) and, opaque, a BackColor behind it. Like VB's,
    it has no events and never takes the focus; clicks go to what is
    underneath."""

    TypeName = "Shape"
    DefaultEvent = ""
    Events: tuple[str, ...] = ()
    DefaultSize = (81, 81)
    Properties = (
        *_geometry(*DefaultSize),
        P("Shape", "enum", 0, enum_choices("Rectangle", "Square", "Oval", "Circle",
                                           "Rounded Rectangle", "Rounded Square"),
          description="Its form; a Square, Circle or Rounded Square is centered in its box"),
        P("BackStyle", "enum", 0, enum_choices("Transparent", "Opaque"),
          description="Opaque: filled with BackColor (under the FillStyle); Transparent: "
                      "what is behind shows through"),
        P("BackColor", "color", None,
          description="The color inside it when Opaque; unset = the window color"),
        P("FillStyle", "enum", 1, enum_choices(
            "Solid", "Transparent", "Horizontal Line", "Vertical Line", "Upward Diagonal",
            "Downward Diagonal", "Cross", "Diagonal Cross"),
          description="How the inside is filled with FillColor: solid, a pattern, or not"),
        P("FillColor", "color", None,
          description="The fill's color; unset = the text color of the color scheme"),
        P("BorderStyle", "enum", 1, enum_choices(
            "Transparent", "Solid", "Dash", "Dot", "Dash-Dot", "Dash-Dot-Dot", "Inside Solid"),
          description="How the border is drawn; Transparent: none"),
        P("BorderColor", "color", None,
          description="The border's color; unset = the text color of the color scheme"),
        P("BorderWidth", "int", 1, description="The border's thickness in pixels"),
        P("Visible", "bool", True, description="Whether the shape is shown at run time"),
        P("Tag", "str", "", description="Free for your own use"),
        next(spec for spec in _COMMON if spec.name == "ZIndex"),
    )

    def _create_widget(self, parent):
        return _ShapeWidget(self, parent)

    def _event_targets(self):
        return []  # no events

    def _repaint(self, _=None) -> None:
        if self._widget is not None:
            self._widget.update()

    _apply_Shape = _apply_BackStyle = _apply_BackColor = _apply_FillStyle = \
        _apply_FillColor = _apply_BorderStyle = _apply_BorderColor = _apply_BorderWidth = \
        _repaint


# --- FlexGrid ------------------------------------------------------------------------

_GRID_EDITOR_ROLE = Qt.UserRole + 10  # a cell's own editor (else its column's)
_GRID_LIST_ROLE = Qt.UserRole + 11  # a cell's own list of choices
_GRID_ROW_DATA_ROLE = Qt.UserRole + 12  # RowData, kept in the row's header item
_EDIT_NONE, _EDIT_TEXT, _EDIT_LIST, _EDIT_CHECK, _EDIT_COLOR, _EDIT_BUTTON = range(6)
_TRUE_TEXTS = ("true", "1", "-1", "yes", "checked")
_BUTTON_WIDTH = 20  # the "..." button of a Button cell


class _GridIndexed:
    """A FlexGrid per-row or per-column property, like VB's ``ColWidth(2)``:
    ``Grid1.ColWidth(2)`` (or ``[2]``) reads it, ``Grid1.ColWidth[2] = 80``
    sets it. Rows and columns count from 0, the fixed ones included."""

    def __init__(self, grid, name: str, count, read, write):
        self._grid, self._name, self._count = grid, name, count
        self._read, self._write = read, write

    def _check(self, index) -> int:
        index, count = int(index), self._count()
        if not 0 <= index < count:
            raise IndexError(f"FlexGrid '{self._grid.Name}': no {self._name}({index}) "
                             f"(there are {count})")
        return index

    def __call__(self, index):
        return self[index]

    def __getitem__(self, index):
        return self._read(self._check(index))

    def __setitem__(self, index, value):
        self._write(self._check(index), value)

    def __len__(self):
        return self._count()


class _TextMatrix:
    """FlexGrid.TextMatrix: ``TextMatrix(r, c)`` (or ``[r, c]``) is a cell's
    text, ``TextMatrix[r, c] = "x"`` sets it (VB's ``TextMatrix(r, c) = "x"``)."""

    def __init__(self, grid):
        self._grid = grid

    def __call__(self, row, col):
        return self._grid._get_text(*self._grid._check_cell(row, col))

    def __getitem__(self, cell):
        return self(*cell)

    def __setitem__(self, cell, value):
        self._grid._set_text(*self._grid._check_cell(*cell), value)


class _GridDelegate(QStyledItemDelegate):
    """The FlexGrid's cells: the editor each one's kind needs, color swatches,
    "..." buttons, check boxes toggled by the user, and the edit events."""

    def __init__(self, grid: "FlexGrid"):
        super().__init__(grid._widget)
        self.grid = grid

    def _cell(self, index) -> tuple[int, int]:
        return index.row() + self.grid._frows, index.column() + self.grid._fcols

    def _button_rect(self, rect: QRect) -> QRect:
        return QRect(rect.right() - _BUTTON_WIDTH + 1, rect.top() + 1, _BUTTON_WIDTH - 1,
                     rect.height() - 2)

    def paint(self, painter, option, index):
        grid = self.grid
        kind = grid._editor_of(*self._cell(index))
        if kind == _EDIT_COLOR:
            option = QStyleOptionViewItem(option)
            self.initStyleOption(option, index)
            color = QColor(index.data())
            text_rect = QRect(option.rect)
            if color.isValid():
                swatch = QRect(option.rect.left() + 4, option.rect.center().y() - 6, 18, 12)
                text_rect.setLeft(swatch.right() + 4)
                option.rect = text_rect
                super().paint(painter, option, index)
                painter.save()
                painter.fillRect(swatch, color)
                painter.setPen(option.palette.color(QPalette.Text))
                painter.drawRect(swatch)
                painter.restore()
                return
        super().paint(painter, option, index)
        if kind == _EDIT_BUTTON and grid._values.get("Editable"):
            rect = self._button_rect(option.rect).adjusted(1, 2, -2, -2)
            palette = grid._widget.palette()
            painter.save()
            painter.setPen(palette.color(QPalette.Mid))
            painter.setBrush(palette.color(QPalette.Button))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(palette.color(QPalette.ButtonText))
            painter.drawText(rect, Qt.AlignCenter, "...")
            painter.restore()

    def editorEvent(self, event, model, option, index):
        grid = self.grid
        row, col = self._cell(index)
        kind = grid._editor_of(row, col)
        if not grid._values.get("Editable") or grid._design_mode:
            return False
        etype = event.type()
        if kind == _EDIT_CHECK:  # a click on the cell or Space toggles it
            if (etype == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton) or \
                    (etype == QEvent.KeyPress and event.key() == Qt.Key_Space):
                checked = grid._get_text(row, col) == "True"
                if not grid._fire_cancel("BeforeEdit", row, col):
                    grid._commit(row, col, "False" if checked else "True")
                return True
            return etype in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick)
        if kind == _EDIT_BUTTON and etype == QEvent.MouseButtonRelease and \
                self._button_rect(option.rect).contains(event.position().toPoint()):
            grid._fire("CellButtonClick", row, col)
            return True
        return False

    def createEditor(self, parent, option, index):
        grid = self.grid
        row, col = self._cell(index)
        kind = grid._editor_of(row, col)
        if kind in (_EDIT_NONE, _EDIT_CHECK) or not grid._values.get("Editable"):
            return None
        if grid._fire_cancel("BeforeEdit", row, col):
            return None
        if kind == _EDIT_BUTTON:  # (F2 or Enter on it: as clicking its button)
            grid._fire("CellButtonClick", row, col)
            return None
        if kind == _EDIT_COLOR:  # a dialog, then no editor
            QTimer.singleShot(0, grid._widget, lambda: grid._pick_color(row, col))
            return None
        if kind == _EDIT_LIST:
            combo = QComboBox(parent)
            combo.addItems([str(v) for v in grid._list_of(row, col)])
            combo.activated.connect(lambda _i, c=combo: (self.commitData.emit(c),
                                                         self.closeEditor.emit(c)))
            return combo
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(max(0, editor.findText(index.data() or "")))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        text = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
        self.grid._commit(*self._cell(index), text)


class _GridTable(QTableWidget):
    """The FlexGrid's table, remembering the cell under the mouse."""

    def __init__(self, grid: "FlexGrid", parent):
        super().__init__(parent)
        self.grid = grid
        for widget in (self.viewport(), self.horizontalHeader().viewport(),
                       self.verticalHeader().viewport()):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress):
            point = event.position().toPoint()
            grid = self.grid
            if watched is self.viewport():
                row, col = self.rowAt(point.y()), self.columnAt(point.x())
                cell = (row + grid._frows if row >= 0 else -1,
                        col + grid._fcols if col >= 0 else -1)
            elif watched is self.horizontalHeader().viewport():
                col = self.horizontalHeader().logicalIndexAt(point)
                cell = (0, col + grid._fcols if col >= 0 else -1)
            else:
                row = self.verticalHeader().logicalIndexAt(point)
                cell = (row + grid._frows if row >= 0 else -1, 0)
            grid.__dict__["_mouse_cell"] = cell
        return False


def parse_format_string(text: str) -> list[tuple[str, int]]:
    """A FlexGrid FormatString: column headings separated by |, each
    optionally starting with < (left), ^ (center) or > (right):
    ``"<Name|^Qty|>Price"`` -> [("Name", 0), ("Qty", 2), ("Price", 1)]
    (alignments as vpLeftJustify, vpCenter, vpRightJustify)."""
    if not text:
        return []
    columns = []
    for piece in text.split("|"):
        align = {"<": 0, "^": 2, ">": 1}.get(piece[:1])
        columns.append((piece[1:] if align is not None else piece, align or 0))
    return columns


class FlexGrid(Control):
    """A grid of text cells like VB's MSFlexGrid: Rows and Cols (the first
    FixedRows and FixedCols are headings that stay put while scrolling),
    TextMatrix(row, col), the current cell (Row, Col, Text and the Cell...
    properties), sorting, and, unlike MSFlexGrid, editing: with Editable,
    each column (ColEditor) or cell (CellEditor) has an editor: text, a
    list, a check box, a color or a "..." button."""

    TypeName = "FlexGrid"
    DefaultEvent = "Click"
    DefaultSize = (321, 161)
    Events = ("Click", "DblClick", "EnterCell", "LeaveCell", "RowColChange", "SelChange",
              "Scroll", "BeforeEdit", "ValidateEdit", "AfterEdit", "CellButtonClick",
              "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QTableWidget"
    Properties = (
        *_geometry(*DefaultSize),
        P("Rows", "int", 2, description="How many rows, the fixed one included"),
        P("Cols", "int", 2, description="How many columns, the fixed one included"),
        P("FixedRows", "enum", 1, enum_choices("0", "1"),
          description="1: the first row is the column headings, staying put while scrolling"),
        P("FixedCols", "enum", 1, enum_choices("0", "1"),
          description="1: the first column is the row headings, staying put while scrolling"),
        P("FormatString", "str", "",
          description="Column headings and alignments: <Name|^Qty|>Price (< left, ^ center, "
                      "> right)"),
        P("Editable", "bool", False,
          description="The user can edit the cells, each with its column's or its own editor"),
        P("SelectionMode", "enum", 0, enum_choices("Free", "By Row", "By Column"),
          description="What a click selects: cells, whole rows or whole columns"),
        P("AllowUserResizing", "enum", 1, enum_choices("None", "Columns", "Rows", "Both"),
          description="What the user can resize by dragging the headings' edges"),
        P("GridLines", "bool", True, description="Lines between the cells"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_frows=1, _fcols=1, _corner="", _col_editors={},
                             _col_lists={}, _col_align={}, _mouse_cell=(-1, -1))
        table = _GridTable(self, parent)
        table.setRowCount(1)
        table.setColumnCount(1)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerItem)
        table.setItemDelegate(_GridDelegate(self))
        table.setSelectionMode(QAbstractItemView.ContiguousSelection)
        table.verticalHeader().setDefaultSectionSize(table.fontMetrics().height() + 8)
        self._widget = table
        self._fill_headers()
        return table

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        table = self._widget
        table.cellClicked.connect(lambda *_: self._fire("Click"))
        table.horizontalHeader().sectionClicked.connect(lambda *_: self._fire("Click"))
        table.verticalHeader().sectionClicked.connect(lambda *_: self._fire("Click"))
        table.currentCellChanged.connect(self._on_current_changed)
        table.itemSelectionChanged.connect(lambda: self._fire("SelChange"))
        table.verticalScrollBar().valueChanged.connect(lambda *_: self._fire("Scroll"))
        table.horizontalScrollBar().valueChanged.connect(lambda *_: self._fire("Scroll"))

    def _on_current_changed(self, row, col, previous_row, previous_col):
        if previous_row >= 0 and previous_col >= 0:
            self._fire("LeaveCell")
        if row >= 0 and col >= 0:
            self._fire("RowColChange")
            self._fire("EnterCell")

    # -- structure ------------------------------------------------------------------------
    def _fill_headers(self) -> None:
        """Empty heading items where there are none (Qt would show numbers)."""
        table = self._widget
        for col in range(table.columnCount()):
            if table.horizontalHeaderItem(col) is None:
                table.setHorizontalHeaderItem(col, QTableWidgetItem(""))
        for row in range(table.rowCount()):
            if table.verticalHeaderItem(row) is None:
                table.setVerticalHeaderItem(row, QTableWidgetItem(""))
        table.horizontalHeader().setVisible(self._frows > 0)
        table.verticalHeader().setVisible(self._fcols > 0)
        for col, editor in self._col_editors.items():  # check boxes need their items
            if editor == _EDIT_CHECK and self._fcols <= col < self.Cols:
                for row in range(self._frows, self.Rows):
                    if self._item(row, col, create=False) is None:
                        self._show_value(row, col, "False")
        if table.currentRow() < 0 and table.rowCount() and table.columnCount():
            table.setCurrentCell(0, 0)

    def _read_Rows(self):
        return self._widget.rowCount() + self._frows

    def _apply_Rows(self, v):
        self._widget.setRowCount(max(int(v), self._frows) - self._frows)
        self._fill_headers()

    def _read_Cols(self):
        return self._widget.columnCount() + self._fcols

    def _apply_Cols(self, v):
        self._widget.setColumnCount(max(int(v), self._fcols) - self._fcols)
        self._fill_headers()
        self._apply_FormatString(self._values.get("FormatString", ""))

    def _apply_FixedRows(self, v):
        v = int(v)
        if v == self._frows:
            return
        table = self._widget
        if v == 0:  # the headings become the first row
            texts = [self._get_text(0, c) for c in range(self.Cols)]
            self.__dict__["_frows"] = 0
            table.insertRow(0)
            for col, text in enumerate(texts):
                if col >= self._fcols:
                    table.setHorizontalHeaderItem(col - self._fcols, QTableWidgetItem(""))
                self._set_text(0, col, text)
        else:  # the first row becomes the headings
            if table.rowCount() == 0:
                table.insertRow(0)
            texts = [self._get_text(0, c) for c in range(self.Cols)]
            table.removeRow(0)
            self.__dict__["_frows"] = 1
            for col, text in enumerate(texts):
                self._set_text(0, col, text)
        self._fill_headers()

    def _apply_FixedCols(self, v):
        v = int(v)
        if v == self._fcols:
            return
        table = self._widget
        if v == 0:
            texts = [self._get_text(r, 0) for r in range(self.Rows)]
            self.__dict__["_fcols"] = 0
            table.insertColumn(0)
            for row, text in enumerate(texts):
                if row >= self._frows:
                    item = table.verticalHeaderItem(row - self._frows)
                    if item is not None:
                        item.setText("")
                self._set_text(row, 0, text)
        else:
            if table.columnCount() == 0:
                table.insertColumn(0)
            texts = [self._get_text(r, 0) for r in range(self.Rows)]
            table.removeColumn(0)
            self.__dict__["_fcols"] = 1
            for row, text in enumerate(texts):
                self._set_text(row, 0, text)
        self._fill_headers()

    def _apply_FormatString(self, v):
        columns = parse_format_string(v)
        if not columns:
            return
        if len(columns) > self.Cols:
            self._widget.setColumnCount(len(columns) - self._fcols)
            self._fill_headers()
        metrics = self._widget.fontMetrics()
        for col, (text, align) in enumerate(columns):
            if self._frows:
                self._set_text(0, col, text)
            if col >= self._fcols:
                self._set_col_alignment(col, align)
                width = metrics.horizontalAdvance(text) + 24
                if width > self._widget.columnWidth(col - self._fcols):
                    self._widget.setColumnWidth(col - self._fcols, width)

    def _apply_Editable(self, v):
        table = self._widget
        table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed if v else QAbstractItemView.NoEditTriggers)
        table.viewport().update()

    def _apply_SelectionMode(self, v):
        self._widget.setSelectionBehavior({1: QAbstractItemView.SelectRows,
                                           2: QAbstractItemView.SelectColumns}.get(
            int(v), QAbstractItemView.SelectItems))

    def _apply_AllowUserResizing(self, v):
        v = int(v)
        table = self._widget
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive if v in (1, 3) else QHeaderView.Fixed)
        table.verticalHeader().setSectionResizeMode(
            QHeaderView.Interactive if v in (2, 3) else QHeaderView.Fixed)

    def _apply_GridLines(self, v):
        self._widget.setShowGrid(bool(v))

    # -- cells ------------------------------------------------------------------------------
    def _check_cell(self, row, col) -> tuple[int, int]:
        row, col = int(row), int(col)
        if not (0 <= row < self.Rows and 0 <= col < self.Cols):
            raise IndexError(f"FlexGrid '{self.Name}': no cell ({row}, {col}) (Rows is "
                             f"{self.Rows}, Cols is {self.Cols})")
        return row, col

    def _item(self, row: int, col: int, create: bool = True):
        """The item behind a cell (a heading's for a fixed one); None for the
        corner, or a cell without one when ``create`` is False."""
        table, fr, fc = self._widget, self._frows, self._fcols
        if row < fr and col < fc:
            return None
        if row < fr:
            item = table.horizontalHeaderItem(col - fc)
            if item is None and create:
                item = QTableWidgetItem("")
                table.setHorizontalHeaderItem(col - fc, item)
            return item
        if col < fc:
            item = table.verticalHeaderItem(row - fr)
            if item is None and create:
                item = QTableWidgetItem("")
                table.setVerticalHeaderItem(row - fr, item)
            return item
        item = table.item(row - fr, col - fc)
        if item is None and create:
            item = QTableWidgetItem("")
            item.setTextAlignment(_QT_ALIGN.get(self._col_align.get(col, 0), Qt.AlignLeft) |
                                  Qt.AlignVCenter)
            table.setItem(row - fr, col - fc, item)
        return item

    def _get_text(self, row: int, col: int) -> str:
        if row < self._frows and col < self._fcols:
            return self._corner
        item = self._item(row, col, create=False)
        if self._editor_of(row, col) == _EDIT_CHECK:
            return "True" if item is not None and item.checkState() == Qt.Checked else "False"
        return item.text() if item is not None else ""

    def _set_text(self, row: int, col: int, value) -> None:
        text = "" if value is None else str(value)
        if row < self._frows and col < self._fcols:
            self.__dict__["_corner"] = text
            return
        item = self._item(row, col)
        if self._editor_of(row, col) == _EDIT_CHECK:
            item.setCheckState(Qt.Checked if text.strip().lower() in _TRUE_TEXTS else
                               Qt.Unchecked)
        else:
            item.setText(text)

    @property
    def TextMatrix(self) -> _TextMatrix:
        """A cell's text: ``TextMatrix(r, c)`` reads, ``TextMatrix[r, c] = "x"``
        sets (rows and columns from 0, the fixed ones included)."""
        return _TextMatrix(self)

    def _current(self) -> tuple[int, int]:
        table = self._widget
        row, col = table.currentRow(), table.currentColumn()
        return (row + self._frows if row >= 0 else self._frows,
                col + self._fcols if col >= 0 else self._fcols)

    @property
    def Text(self) -> str:
        """The current cell's text (Row, Col)."""
        row, col = self._current()
        return self._get_text(row, col) if row < self.Rows and col < self.Cols else ""

    @Text.setter
    def Text(self, value):
        self._set_text(*self._check_cell(*self._current()), value)

    # -- the current cell and the selection ---------------------------------------------------
    def _move(self, row: int, col: int) -> None:
        row, col = self._check_cell(row, col)
        if row < self._frows or col < self._fcols:
            raise IndexError(f"FlexGrid '{self.Name}': the current cell can't be a fixed one "
                             f"({row}, {col})")
        self._widget.setCurrentCell(row - self._frows, col - self._fcols)

    @property
    def Row(self) -> int:
        """The current cell's row (from 0, the fixed one included)."""
        return self._current()[0]

    @Row.setter
    def Row(self, value):
        self._move(value, self.Col)

    @property
    def Col(self) -> int:
        return self._current()[1]

    @Col.setter
    def Col(self, value):
        self._move(self.Row, value)

    def _selection(self):
        ranges = self._widget.selectedRanges()
        return ranges[0] if ranges else None

    @property
    def RowSel(self) -> int:
        """The selection's other end (the current cell is one corner of it)."""
        selected = self._selection()
        if selected is None:
            return self.Row
        row = self.Row - self._frows
        return (selected.bottomRow() if selected.topRow() == row else selected.topRow()) + \
            self._frows

    @RowSel.setter
    def RowSel(self, value):
        self._select(int(value), self.ColSel)

    @property
    def ColSel(self) -> int:
        selected = self._selection()
        if selected is None:
            return self.Col
        col = self.Col - self._fcols
        return (selected.rightColumn() if selected.leftColumn() == col else
                selected.leftColumn()) + self._fcols

    @ColSel.setter
    def ColSel(self, value):
        self._select(self.RowSel, int(value))

    def _select(self, row_sel: int, col_sel: int) -> None:
        row_sel, col_sel = self._check_cell(row_sel, col_sel)
        row, col = self.Row - self._frows, self.Col - self._fcols
        table = self._widget
        table.clearSelection()
        table.setRangeSelected(QTableWidgetSelectionRange(
            min(row, row_sel - self._frows), min(col, col_sel - self._fcols),
            max(row, row_sel - self._frows), max(col, col_sel - self._fcols)), True)

    # -- the current cell's format ---------------------------------------------------------
    def _current_item(self):
        return self._item(*self._check_cell(*self._current()))

    @property
    def CellBackColor(self):
        """The current cell's background (vpYellow, RGB(...)); None = the grid's."""
        brush = self._current_item().background()
        return colors.from_qcolor(brush.color()) if brush.style() != Qt.NoBrush else None

    @CellBackColor.setter
    def CellBackColor(self, value):
        self._current_item().setBackground(QBrush() if value is None else
                                           QBrush(colors.to_qcolor(value)))

    @property
    def CellForeColor(self):
        brush = self._current_item().foreground()
        return colors.from_qcolor(brush.color()) if brush.style() != Qt.NoBrush else None

    @CellForeColor.setter
    def CellForeColor(self, value):
        self._current_item().setForeground(QBrush() if value is None else
                                           QBrush(colors.to_qcolor(value)))

    @property
    def CellFontBold(self) -> bool:
        return self._current_item().font().bold()

    @CellFontBold.setter
    def CellFontBold(self, value):
        item = self._current_item()
        font = item.font()
        font.setBold(bool(value))
        item.setFont(font)

    @property
    def CellFontItalic(self) -> bool:
        return self._current_item().font().italic()

    @CellFontItalic.setter
    def CellFontItalic(self, value):
        item = self._current_item()
        font = item.font()
        font.setItalic(bool(value))
        item.setFont(font)

    @property
    def CellAlignment(self) -> int:
        """The current cell's alignment: vpLeftJustify, vpRightJustify, vpCenter."""
        align = self._current_item().textAlignment()
        return 1 if align & Qt.AlignRight else 2 if align & Qt.AlignHCenter else 0

    @CellAlignment.setter
    def CellAlignment(self, value):
        self._current_item().setTextAlignment(_QT_ALIGN.get(int(value), Qt.AlignLeft) |
                                              Qt.AlignVCenter)

    # -- editors ------------------------------------------------------------------------------
    def _editor_of(self, row: int, col: int) -> int:
        """A cell's editor: its own, else its column's (text by default); none
        for a fixed cell."""
        if row < self._frows or col < self._fcols:
            return _EDIT_NONE
        item = self._item(row, col, create=False)
        own = item.data(_GRID_EDITOR_ROLE) if item is not None else None
        return int(own) if own is not None else self._col_editors.get(col, _EDIT_TEXT)

    def _list_of(self, row: int, col: int) -> list:
        item = self._item(row, col, create=False)
        own = item.data(_GRID_LIST_ROLE) if item is not None else None
        return list(own) if own is not None else list(self._col_lists.get(col, []))

    def _change_editor(self, row: int, col: int, change) -> None:
        """Change a cell's editor, keeping its value (a check box's is its state)."""
        text = self._get_text(row, col)
        change()
        self._show_value(row, col, text)

    def _show_value(self, row: int, col: int, text: str) -> None:
        """Show a cell's value as its editor needs: a check box's as its state."""
        item = self._item(row, col)
        if self._editor_of(row, col) == _EDIT_CHECK:
            item.setText("")
            item.setCheckState(Qt.Checked if text.lower() in _TRUE_TEXTS else Qt.Unchecked)
        else:
            item.setData(Qt.CheckStateRole, None)
            item.setText(text)

    @property
    def CellEditor(self) -> int:
        """The current cell's editor: vpGridEditText, vpGridEditList (CellList),
        vpGridEditCheck, vpGridEditColor, vpGridEditButton (CellButtonClick) or
        vpGridEditNone (read-only); setting it gives the cell its own."""
        return self._editor_of(*self._current())

    @CellEditor.setter
    def CellEditor(self, value):
        row, col = self._check_cell(*self._current())
        self._change_editor(row, col, lambda: self._item(row, col).setData(
            _GRID_EDITOR_ROLE, None if value is None else int(value)))

    @property
    def CellList(self) -> list:
        """The current cell's choices for vpGridEditList (else its column's)."""
        return self._list_of(*self._current())

    @CellList.setter
    def CellList(self, value):
        self._current_item().setData(_GRID_LIST_ROLE, [str(v) for v in value])

    @property
    def ColEditor(self) -> _GridIndexed:
        """Each column's editor (vpGridEdit...), for its cells without their own."""
        def write(col, value):
            # (the cells without their own editor change with it, keeping their values)
            rows = [row for row in range(self._frows, self.Rows)
                    if (item := self._item(row, col, create=False)) is None or
                    item.data(_GRID_EDITOR_ROLE) is None]
            texts = {row: self._get_text(row, col) for row in rows}
            self._col_editors[col] = int(value)
            for row in rows:
                self._show_value(row, col, texts[row])
            self._widget.viewport().update()

        return _GridIndexed(self, "ColEditor", lambda: self.Cols,
                            lambda col: self._col_editors.get(col, _EDIT_TEXT), write)

    @property
    def ColList(self) -> _GridIndexed:
        """Each column's choices for vpGridEditList: ``ColList[2] = ["S", "M", "L"]``."""
        return _GridIndexed(self, "ColList", lambda: self.Cols,
                            lambda col: list(self._col_lists.get(col, [])),
                            lambda col, value: self._col_lists.__setitem__(
                                col, [str(v) for v in value]))

    def _fire_cancel(self, event: str, *args) -> bool:
        """Fire an event whose handler returns True to cancel (VB's Cancel)."""
        return self._fire(event, *args) is True

    def _commit(self, row: int, col: int, text: str) -> None:
        """The user's new value: ValidateEdit may refuse it, AfterEdit follows."""
        if self._fire_cancel("ValidateEdit", row, col, text):
            return
        self._set_text(row, col, text)
        self._fire("AfterEdit", row, col)

    def _pick_color(self, row: int, col: int) -> None:
        current = QColor(self._get_text(row, col))
        color = QColorDialog.getColor(current if current.isValid() else QColor("white"),
                                      self._widget, "Color")
        if color.isValid():
            self._commit(row, col, color.name())

    def EditCell(self) -> None:
        """Start editing the current cell, as if the user pressed F2 (Editable)."""
        table = self._widget
        index = table.currentIndex()
        if index.isValid() and self._values.get("Editable"):
            row, col = self._current()
            if self._editor_of(row, col) == _EDIT_CHECK:
                if not self._fire_cancel("BeforeEdit", row, col):
                    self._commit(row, col, "False" if self._get_text(row, col) == "True"
                                 else "True")
            else:
                table.edit(index)

    # -- rows and columns -------------------------------------------------------------------
    def _set_col_alignment(self, col: int, value: int) -> None:
        self._col_align[col] = int(value)
        flags = _QT_ALIGN.get(int(value), Qt.AlignLeft) | Qt.AlignVCenter
        for row in range(self._frows, self.Rows):
            item = self._item(row, col, create=False)
            if item is not None:
                item.setTextAlignment(flags)

    @property
    def ColAlignment(self) -> _GridIndexed:
        """Each column's alignment: vpLeftJustify, vpRightJustify, vpCenter."""
        return _GridIndexed(self, "ColAlignment", lambda: self.Cols,
                            lambda col: self._col_align.get(col, 0), self._set_col_alignment)

    @property
    def ColWidth(self) -> _GridIndexed:
        """Each column's width in pixels: ``ColWidth[1] = 120``."""
        table = self._widget

        def read(col):
            if col < self._fcols:
                return table.verticalHeader().width()
            return table.columnWidth(col - self._fcols)

        def write(col, value):
            if col < self._fcols:
                table.verticalHeader().setFixedWidth(int(value))
            else:
                table.setColumnWidth(col - self._fcols, int(value))

        return _GridIndexed(self, "ColWidth", lambda: self.Cols, read, write)

    @property
    def RowHeight(self) -> _GridIndexed:
        """Each row's height in pixels."""
        table = self._widget

        def read(row):
            if row < self._frows:
                return table.horizontalHeader().height()
            return table.rowHeight(row - self._frows)

        def write(row, value):
            if row < self._frows:
                table.horizontalHeader().setFixedHeight(int(value))
            else:
                table.setRowHeight(row - self._frows, int(value))

        return _GridIndexed(self, "RowHeight", lambda: self.Rows, read, write)

    @property
    def RowData(self) -> _GridIndexed:
        """A value kept with each row (any value), moving with it when sorted."""
        def item(row):
            if row < self._frows:
                raise IndexError(f"FlexGrid '{self.Name}': RowData is for the rows "
                                 "under the fixed one")
            header = self._widget.verticalHeaderItem(row - self._frows)
            if header is None:
                header = QTableWidgetItem("")
                self._widget.setVerticalHeaderItem(row - self._frows, header)
            return header

        return _GridIndexed(self, "RowData", lambda: self.Rows,
                            lambda row: item(row).data(_GRID_ROW_DATA_ROLE),
                            lambda row, value: item(row).setData(_GRID_ROW_DATA_ROLE, value))

    def AddItem(self, Item, Index: int | None = None) -> None:
        """Add a row: Item is its cells' texts separated by tabs ("a\\tb\\tc"),
        at the end or at Index (a row, from 0)."""
        table = self._widget
        index = self.Rows if Index is None else int(Index)
        if not self._frows <= index <= self.Rows:
            raise IndexError(f"FlexGrid '{self.Name}': can't add a row at {index}")
        table.insertRow(index - self._frows)
        table.setVerticalHeaderItem(index - self._frows, QTableWidgetItem(""))
        for col, text in enumerate(str(Item).split("\t")[:self.Cols]):
            self._set_text(index, col, text)
        self._fill_headers()

    def RemoveItem(self, Index: int) -> None:
        """Remove a row (not the fixed one)."""
        index = int(Index)
        if not self._frows <= index < self.Rows:
            raise IndexError(f"FlexGrid '{self.Name}': no row {index} to remove")
        self._widget.removeRow(index - self._frows)

    def Clear(self) -> None:
        """Empty every cell, the fixed ones too (Rows and Cols stay)."""
        for row in range(self.Rows):
            for col in range(self.Cols):
                self._set_text(row, col, "")

    @property
    def Sort(self):
        raise AttributeError(f"FlexGrid '{self.Name}': Sort is set, not read "
                             "(Grid1.Sort = vpGridSortGenericAscending)")

    @Sort.setter
    def Sort(self, value):
        """Sort the rows (not the fixed one) by the current column (Col), as
        in VB: vpGridSortGenericAscending / Descending (numbers as numbers,
        other text without case), vpGridSortNumericAscending / Descending,
        vpGridSortStringNoCaseAscending / Descending,
        vpGridSortStringAscending / Descending."""
        mode = int(value)
        if mode not in range(1, 9):
            raise ValueError(f"FlexGrid '{self.Name}': no sort {mode}")
        table, col = self._widget, self.Col - self._fcols
        rows = []
        for row in range(table.rowCount()):  # take every row's items out
            rows.append(([table.takeItem(row, c) for c in range(table.columnCount())],
                         table.takeVerticalHeaderItem(row)))

        def key(entry):
            item = entry[0][col]
            text = item.text() if item is not None else ""
            if item is not None and item.data(Qt.CheckStateRole) is not None:
                text = "1" if item.checkState() == Qt.Checked else "0"
            number = _as_number(text)
            if mode in (1, 2):
                return (0, number, "") if number is not None else (1, 0, text.casefold())
            if mode in (3, 4):
                return number if number is not None else 0.0
            return text.casefold() if mode in (5, 6) else text

        rows.sort(key=key, reverse=mode in (2, 4, 6, 8))
        for row, (items, header) in enumerate(rows):
            for c, item in enumerate(items):
                if item is not None:
                    table.setItem(row, c, item)
            table.setVerticalHeaderItem(row, header if header is not None else
                                        QTableWidgetItem(""))

    # -- scrolling and the mouse ----------------------------------------------------------------
    @property
    def TopRow(self) -> int:
        """The first row shown under the fixed one; setting it scrolls."""
        return self._widget.verticalScrollBar().value() + self._frows

    @TopRow.setter
    def TopRow(self, value):
        self._widget.updateGeometries()  # (the scroll range after new rows or sizes)
        self._widget.verticalScrollBar().setValue(int(value) - self._frows)

    @property
    def LeftCol(self) -> int:
        """The first column shown right of the fixed one; setting it scrolls."""
        return self._widget.horizontalScrollBar().value() + self._fcols

    @LeftCol.setter
    def LeftCol(self, value):
        self._widget.updateGeometries()
        self._widget.horizontalScrollBar().setValue(int(value) - self._fcols)

    @property
    def MouseRow(self) -> int:
        """The row under the mouse (0 for the headings), -1 if none."""
        return self._mouse_cell[0]

    @property
    def MouseCol(self) -> int:
        return self._mouse_cell[1]


def _as_number(text: str):
    try:
        return float(text.replace(",", "")) if text.strip() else None
    except ValueError:
        return None


# --- TreeView ------------------------------------------------------------------

_TVW_FIRST, _TVW_LAST, _TVW_NEXT, _TVW_PREVIOUS, _TVW_CHILD = range(5)  # vpTvw* constants


def parse_outline(lines) -> list[tuple[int, str, str, object]]:
    """(level, text, key, image) for each node of an outline: one node per
    line, indented under its parent (a tab counts as 4 spaces), as
    ``Text|key|image``: a key and an Image (a key or Index in the TreeView's
    ImageList, or a picture file) are optional. Blank lines are skipped."""
    nodes, indents = [], []  # indents of the current line's ancestors
    for raw in lines:
        line = str(raw).replace("\t", "    ").rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        while indents and indents[-1] >= indent:
            indents.pop()
        text, _, rest = line.strip().partition("|")
        key, _, image = rest.partition("|")
        nodes.append((len(indents), text.strip(), key.strip(),
                      _image_ref(image) if image.strip() else ""))
        indents.append(indent)
    return nodes


class Node:
    """One node of a TreeView (VB's Node object)."""

    def __init__(self, tree: "TreeView", item: QTreeWidgetItem, key: str):
        self._tree, self._item, self._key = tree, item, key
        self._image = ""
        self._check_state = None
        self.Tag = ""  # free for your own use
        item.setData(0, Qt.UserRole, self)

    def __repr__(self):
        return f"<Node {self.Text!r}{f' key={self._key!r}' if self._key else ''}>"

    # -- text and identity ------------------------------------------------------------
    @property
    def Text(self) -> str:
        return self._item.text(0)

    @Text.setter
    def Text(self, value):
        self._item.setText(0, str(value))
        self._tree._keep_sorted(self._item.parent())

    @property
    def Key(self) -> str:
        return self._key

    @Key.setter
    def Key(self, value):
        value = str(value or "")
        nodes = self._tree._nodes
        if value and value != self._key and value in nodes._by_key:
            raise ValueError(f"TreeView '{self._tree.Name}': the key {value!r} is not unique")
        nodes._by_key.pop(self._key, None)
        if value:
            nodes._by_key[value] = self
        self._key = value

    @property
    def Index(self) -> int:
        """The node's number in the Nodes collection, from 1 (VB)."""
        return self._tree._nodes._list.index(self) + 1

    @property
    def FullPath(self) -> str:
        """The texts from the root node to this one, joined by PathSeparator."""
        parts, node = [], self
        while node is not None:
            parts.append(node.Text)
            node = node.Parent
        return self._tree.PathSeparator.join(reversed(parts))

    # -- state ---------------------------------------------------------------------------
    @property
    def Expanded(self) -> bool:
        return self._item.isExpanded()

    @Expanded.setter
    def Expanded(self, value):
        with self._tree._quietly():
            self._item.setExpanded(bool(value))

    @property
    def Selected(self) -> bool:
        return self._tree._widget.currentItem() is self._item

    @Selected.setter
    def Selected(self, value):
        if value:
            self._tree.SelectedItem = self
        elif self.Selected:
            self._tree.SelectedItem = None

    @property
    def Checked(self) -> bool:
        return self._item.checkState(0) == Qt.Checked

    @Checked.setter
    def Checked(self, value):
        with self._tree._quietly():
            self._item.setCheckState(0, Qt.Checked if value else Qt.Unchecked)
        self._check_state = self._item.checkState(0)

    @property
    def Bold(self) -> bool:
        return self._item.font(0).bold()

    @Bold.setter
    def Bold(self, value):
        font = self._item.font(0)
        font.setBold(bool(value))
        self._item.setFont(0, font)

    @property
    def ForeColor(self):
        value = self._item.data(0, Qt.ForegroundRole)  # a QColor, or a QBrush
        if value is None:
            return None
        return colors.from_qcolor(value if isinstance(value, QColor) else value.color())

    @ForeColor.setter
    def ForeColor(self, value):
        self._item.setData(0, Qt.ForegroundRole,
                           None if value is None else colors.to_qcolor(value))

    @property
    def Image(self):
        """The picture before the text: with the TreeView's ImageList, a
        picture's Key or Index in it; without one, a picture file (relative to
        the form's folder)."""
        return self._image

    @Image.setter
    def Image(self, value):
        value = "" if value is None else value
        self._item.setIcon(0, _picture_icon(self._tree, value, strict=True))
        self._image = value

    @property
    def Sorted(self) -> bool:
        return bool(self._item.data(0, Qt.UserRole + 1))

    @Sorted.setter
    def Sorted(self, value):
        """Keep this node's children in alphabetical order."""
        self._item.setData(0, Qt.UserRole + 1, bool(value))
        self._tree._keep_sorted(self._item)

    def EnsureVisible(self) -> None:
        """Expand its parents and scroll so the node can be seen."""
        with self._tree._quietly():
            parent = self._item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
        self._tree._widget.scrollToItem(self._item)

    # -- relatives -----------------------------------------------------------------------
    def _node_of(self, item):
        return None if item is None else item.data(0, Qt.UserRole)

    def _siblings(self) -> QTreeWidgetItem:
        return self._item.parent() or self._tree._widget.invisibleRootItem()

    @property
    def Parent(self) -> "Node | None":
        return self._node_of(self._item.parent())

    @property
    def Children(self) -> int:
        """How many children it has (VB: a number)."""
        return self._item.childCount()

    @property
    def Child(self) -> "Node | None":
        """The first child."""
        return self._node_of(self._item.child(0)) if self._item.childCount() else None

    @property
    def Next(self) -> "Node | None":
        parent = self._siblings()
        return self._node_of(parent.child(parent.indexOfChild(self._item) + 1))

    @property
    def Previous(self) -> "Node | None":
        parent = self._siblings()
        index = parent.indexOfChild(self._item)
        return self._node_of(parent.child(index - 1)) if index > 0 else None

    @property
    def FirstSibling(self) -> "Node":
        return self._node_of(self._siblings().child(0))

    @property
    def LastSibling(self) -> "Node":
        parent = self._siblings()
        return self._node_of(parent.child(parent.childCount() - 1))

    @property
    def Root(self) -> "Node":
        node = self
        while node.Parent is not None:
            node = node.Parent
        return node


class _Nodes:
    """A TreeView's Nodes collection: ``tree.Nodes(key)``, ``tree.Nodes[key]``
    or by Index from 1 like VB, ``Add``, ``Remove``, ``Clear``, ``Count``;
    iterating gives the nodes in the order they were added."""

    def __init__(self, tree: "TreeView"):
        self._tree = tree
        self._list: list[Node] = []
        self._by_key: dict[str, Node] = {}

    def _resolve(self, ref) -> Node:
        if isinstance(ref, Node):
            if ref._tree is not self._tree or ref not in self._list:
                raise ValueError(f"{ref!r} is not in TreeView '{self._tree.Name}'")
            return ref
        if isinstance(ref, str):
            if ref not in self._by_key:
                raise KeyError(f"TreeView '{self._tree.Name}' has no node with key {ref!r}")
            return self._by_key[ref]
        if isinstance(ref, int) and not isinstance(ref, bool):
            if not 1 <= ref <= len(self._list):
                raise IndexError(f"TreeView '{self._tree.Name}' has no node {ref} "
                                 f"(1 to {len(self._list)})")
            return self._list[ref - 1]
        raise TypeError(f"A node is chosen by key, Index or Node, not {ref!r}")

    def Item(self, ref) -> Node:
        return self._resolve(ref)

    __getitem__ = __call__ = Item

    def __iter__(self):
        return iter(list(self._list))

    def __len__(self) -> int:
        return len(self._list)

    def __contains__(self, ref) -> bool:
        return ref in self._by_key if isinstance(ref, str) else ref in self._list

    @property
    def Count(self) -> int:
        return len(self._list)

    def Add(self, Relative=None, Relationship=None, Key: str = "", Text: str = "",
            Image="") -> Node:
        """Add a node, like VB: at the end of the top level; or placed by
        ``Relationship`` to the ``Relative`` node (its key, Index or Node):
        vpTvwFirst, vpTvwLast, vpTvwNext (the default) or vpTvwPrevious among
        its siblings, or vpTvwChild (its last child)."""
        if not isinstance(Key, str):
            raise TypeError("A node's Key must be text (numbers choose nodes by Index)")
        if Key and Key in self._by_key:
            raise ValueError(f"TreeView '{self._tree.Name}': the key {Key!r} is not unique")
        tree = self._tree
        item = QTreeWidgetItem([str(Text)])
        if Relative is None:
            parent = tree._widget.invisibleRootItem()
            position = 0 if Relationship == _TVW_FIRST else parent.childCount()
        else:
            relative = self._resolve(Relative)
            relationship = _TVW_NEXT if Relationship is None else Relationship
            if relationship == _TVW_CHILD:
                parent = relative._item
                position = parent.childCount()
            else:
                parent = relative._siblings()
                index = parent.indexOfChild(relative._item)
                position = {_TVW_FIRST: 0, _TVW_LAST: parent.childCount(), _TVW_NEXT: index + 1,
                            _TVW_PREVIOUS: index}.get(relationship)
                if position is None:
                    raise ValueError(f"Unknown relationship {Relationship!r}")
        node = Node(tree, item, Key)
        with tree._quietly():
            parent.insertChild(position, item)
            if tree._values.get("Checkboxes"):
                item.setCheckState(0, Qt.Unchecked)
                node._check_state = Qt.Unchecked
        if Image:
            node.Image = Image
        self._list.append(node)
        if Key:
            self._by_key[Key] = node
        tree._keep_sorted(item.parent())
        return node

    def Remove(self, ref) -> None:
        """Remove a node and its children."""
        node = self._resolve(ref)
        gone, stack = [], [node._item]
        while stack:
            item = stack.pop()
            gone.append(item.data(0, Qt.UserRole))
            stack.extend(item.child(i) for i in range(item.childCount()))
        with self._tree._quietly():
            node._siblings().removeChild(node._item)
        for doomed in gone:
            self._list.remove(doomed)
            self._by_key.pop(doomed._key, None)

    def Clear(self) -> None:
        with self._tree._quietly():
            self._tree._widget.clear()
        self._list.clear()
        self._by_key.clear()


class _Quiet:
    def __init__(self, tree):
        self._tree = tree

    def __enter__(self):
        self._tree.__dict__["_quiet"] += 1

    def __exit__(self, *_):
        self._tree.__dict__["_quiet"] -= 1


class TreeView(_UsesImageList, Control):
    """A hierarchical list of nodes, like VB's TreeView (Windows Common
    Controls). Fill it in code with ``Nodes.Add``, or in the designer with
    the ``Items`` outline. NodeClick, Expand, Collapse and NodeCheck get the
    Node."""

    TypeName = "TreeView"
    DefaultEvent = "NodeClick"
    DefaultSize = (161, 193)
    Events = ("NodeClick", "Expand", "Collapse", "NodeCheck", "Click", "DblClick", "GotFocus",
              "LostFocus", "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QTreeWidget"
    Properties = (
        *_geometry(*DefaultSize),
        P("LineStyle", "enum", 1, enum_choices("Tree Lines", "Root Lines"),
          description="Root Lines: the top-level nodes have expand/collapse buttons too"),
        P("Indentation", "int", 20, description="How far each level is indented, in pixels"),
        P("Checkboxes", "bool", False, description="A check box in front of every node"),
        P("Sorted", "bool", False, description="Keep the top-level nodes in alphabetical order"),
        P("PathSeparator", "str", "\\", description="Separates the texts in a node's FullPath"),
        P("ImageList", "str", "",
          description="The name of an ImageList on the form: the nodes' Image is then a "
                      "picture's Key or Index in it"),
        P("Items", "outline", [],
          description="The nodes, set in the designer: one per line, indented under its "
                      "parent; a vertical bar and a key at the end give the node that key"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_nodes"] = _Nodes(self)
        self.__dict__["_quiet"] = 0
        self.__dict__["_current_at_press"] = None
        widget = QTreeWidget(parent)
        widget.setHeaderHidden(True)
        widget.setColumnCount(1)
        return widget

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        widget = self._widget
        widget.currentItemChanged.connect(self._on_current_changed)
        widget.itemClicked.connect(self._on_item_clicked)
        widget.itemExpanded.connect(self._on_expanded)
        widget.itemCollapsed.connect(self._on_collapsed)
        widget.itemChanged.connect(self._on_item_changed)

    def _quietly(self) -> _Quiet:
        """Changes made by code don't fire events, only the user's do."""
        return _Quiet(self)

    def _keep_sorted(self, parent_item) -> None:
        parent_item = parent_item or self._widget.invisibleRootItem()
        top = parent_item is self._widget.invisibleRootItem()
        sorted_here = self._values.get("Sorted") if top else parent_item.data(0, Qt.UserRole + 1)
        if sorted_here:
            parent_item.sortChildren(0, Qt.AscendingOrder)

    @staticmethod
    def _node(item) -> "Node | None":
        return None if item is None else item.data(0, Qt.UserRole)

    # -- events ------------------------------------------------------------------------------
    def _on_qt_event(self, watched, event):
        if event.type() == QEvent.MouseButtonPress:
            self.__dict__["_current_at_press"] = self._widget.currentItem()
        return super()._on_qt_event(watched, event)

    def _on_current_changed(self, current, _previous):
        if not self._quiet and current is not None:
            self._fire("NodeClick", self._node(current))

    def _on_item_clicked(self, item, _column):
        # Clicking the node that was already selected: no current-item change
        if not self._quiet and item is self._current_at_press:
            self._fire("NodeClick", self._node(item))

    def _on_expanded(self, item):
        if not self._quiet:
            self._fire("Expand", self._node(item))

    def _on_collapsed(self, item):
        if not self._quiet:
            self._fire("Collapse", self._node(item))

    def _on_item_changed(self, item, _column):
        node = self._node(item)
        if node is None or self._quiet:
            return
        state = item.checkState(0)
        if node._check_state is not None and state != node._check_state:
            node._check_state = state
            self._fire("NodeCheck", node)

    # -- API -----------------------------------------------------------------------------------
    @property
    def Nodes(self) -> _Nodes:
        return self._nodes

    @property
    def SelectedItem(self) -> "Node | None":
        return self._node(self._widget.currentItem())

    @SelectedItem.setter
    def SelectedItem(self, node):
        with self._quietly():
            if node is None:
                self._widget.setCurrentItem(None)
                self._widget.clearSelection()
            else:
                self._widget.setCurrentItem(self._nodes._resolve(node)._item)

    def HitTest(self, X: int, Y: int) -> "Node | None":
        """The node at a position (as the mouse events give it), or None."""
        return self._node(self._widget.itemAt(int(X), int(Y)))

    # -- properties ----------------------------------------------------------------------------
    def _apply_LineStyle(self, v):
        self._widget.setRootIsDecorated(v == 1)

    def _apply_Indentation(self, v):
        self._widget.setIndentation(max(0, int(v)))

    def _apply_Checkboxes(self, v):
        with self._quietly():
            for node in self._nodes:
                if v:
                    node._item.setCheckState(0, Qt.Unchecked)
                    node._check_state = Qt.Unchecked
                else:
                    node._item.setData(0, Qt.CheckStateRole, None)
                    node._check_state = None

    def _apply_Sorted(self, v):
        self._keep_sorted(None)

    def _refresh_images(self) -> None:
        for node in self._nodes._list:
            node._item.setIcon(0, _picture_icon(self, node._image))

    def _apply_Items(self, lines):
        """Rebuild the tree from an outline (the designer's Items)."""
        self._nodes.Clear()
        parents: list[Node] = []
        for level, text, key, image in parse_outline(lines):
            del parents[level:]
            parent = parents[-1] if parents else None
            node = self._nodes.Add(parent, _TVW_CHILD if parent else None, key, text)
            node._image = image  # shown by _refresh_images (the ImageList may come later)
            parents.append(node)
        self._refresh_images()
        if self._design_mode:
            self._widget.expandAll()  # show the whole outline while designing


def _shortcut_choices() -> tuple[tuple[str, str], ...]:
    """VB's Shortcut list, in Qt's key names ("" = none)."""
    letters = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    keys = [f"Ctrl+{k}" for k in letters] + [f"F{n}" for n in range(1, 13)]
    keys += [f"Ctrl+F{n}" for n in range(1, 13)] + [f"Shift+F{n}" for n in range(1, 13)]
    keys += [f"Ctrl+Shift+F{n}" for n in range(1, 13)] + [f"Ctrl+Shift+{k}" for k in letters]
    keys += ["Ctrl+Ins", "Shift+Ins", "Del", "Shift+Del", "Alt+Backspace"]
    return (("", "(None)"), *((k, k) for k in keys))


SHORTCUT_CHOICES = _shortcut_choices()


class Menu(Control):
    """A menu, menu item or separator, designed with the Menu Editor.

    Menus whose parent is the form are the menu bar; the others are items in
    their parent menu::

        self.mnuFile = Menu(self, Caption='&File')
        self.mnuFileOpen = Menu(self.mnuFile, Caption='&Open...', Shortcut='Ctrl+O')
        self.mnuFileSep = Menu(self.mnuFile, Caption='-')        # a separator line

    Click fires when an item is chosen, and for a menu with items, just
    before it opens (to update its items, like VB). On macOS the menu bar is
    the system's, at the top of the screen, while the form is active.
    """

    TypeName = "Menu"
    DefaultEvent = "Click"
    Events = ("Click",)
    DefaultSize = (0, 0)
    InToolbox = False
    Properties = (
        P("Caption", "str", "", always=True,
          description="The text shown; & marks the access key (&File), and '-' makes a "
                      "separator line"),
        P("Checked", "bool", False, description="Shows a check mark next to the item"),
        P("Enabled", "bool", True, description="Whether the item can be chosen"),
        P("Visible", "bool", True, description="Whether the item is shown"),
        P("NegotiatePosition", "enum", 0, enum_choices("None", "Left", "Middle", "Right"),
          description="For a menu on the menu bar, when its form is shown in another form: "
                      "None = not shown; Left = before that window's menus, Middle = after "
                      "its first menu, Right = after its menus (before its Right ones)"),
        P("Shortcut", "shortcut", "", SHORTCUT_CHOICES,
          description="A key that chooses the item without opening the menu, from VB's list: "
                      "Ctrl+A..Z, F1..F12, Ctrl+, Shift+ and Ctrl+Shift+F1..F12, "
                      "Ctrl+Shift+A..Z, Ctrl+Ins, Shift+Ins, Del, Shift+Del, "
                      "Alt+Backspace"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def _build_widget(self) -> None:
        self._widget = None
        self.__dict__["_action"] = None
        self.__dict__["_submenu"] = None
        if not isinstance(self.Parent, Menu) and self.Parent is not self._form:
            raise TypeError(f"Menu '{self._name}': the parent must be the form or a Menu")
        if self._design_mode:
            return  # the designer draws the menus itself
        action = QAction(self._form._widget)
        action.triggered.connect(self._on_triggered)
        self.__dict__["_action"] = action
        self.Parent._add_menu_item(self)

    def _add_menu_item(self, item: "Menu") -> None:
        """An item of this menu (it gets a drop-down menu)."""
        if self._submenu is None:
            submenu = QMenu(self._form._widget)
            self._form._style_widget(submenu)
            submenu.aboutToShow.connect(self._on_about_to_show)
            self.__dict__["_submenu"] = submenu
            self._action.setMenu(submenu)
        self._submenu.addAction(item._action)
        self._form._widget.addAction(item._action)  # its Shortcut works in the window

    def _menu_container(self):
        return self._submenu

    def _place_after(self, other: Control) -> None:
        container = self.Parent._menu_container()
        if container is None or self._action is None or other._action is None:
            return
        container.removeAction(self._action)
        actions = container.actions()
        position = actions.index(other._action) + 1 if other._action in actions else len(actions)
        container.insertAction(actions[position] if position < len(actions) else None,
                               self._action)

    def _dispose(self) -> None:
        if self._action is None:
            return
        container = self.Parent._menu_container()
        if container is not None:
            container.removeAction(self._action)
        self._form._widget.removeAction(self._action)
        self._action.deleteLater()

    # -- events ------------------------------------------------------------------------------
    def _on_triggered(self, *_):
        # Qt toggles a checkable item by itself; in VB only code changes Checked
        self._action.setChecked(bool(self._values.get("Checked")))
        if "_popup_chosen" in self._form.__dict__:  # (PopupMenu is waiting: what was chosen)
            self._form.__dict__["_popup_chosen"] = self
        self._fire("Click")

    def _on_about_to_show(self):
        self._fire("Click")

    # -- properties ---------------------------------------------------------------------------
    def _apply_Caption(self, v):
        if self._action is not None:
            self._action.setSeparator(v == "-")
            self._action.setText(v)

    def _apply_Checked(self, v):
        if self._action is not None:
            self._action.setCheckable(bool(v))
            self._action.setChecked(bool(v))

    def _apply_Enabled(self, v):
        if self._action is not None:
            self._action.setEnabled(bool(v))

    def _apply_Visible(self, v):
        if self._action is not None:
            self._action.setVisible(bool(v))

    def _apply_NegotiatePosition(self, v):
        form = self._form
        if self.Parent is form and form._container is not None and self in form._controls:
            window = form._menu_window()
            if form in window._merged_forms:
                window._update_menu_bar()

    def _apply_Shortcut(self, v):
        if self._action is not None:
            self._action.setShortcut(QKeySequence(v or ""))


# --- CommonDialog -------------------------------------------------------------------------------

class DialogCancelled(Exception):
    """A CommonDialog's dialog was cancelled while its CancelError is True
    (VB's run-time error 32755, cdlCancel); ``Number`` is 32755."""

    Number = 32755

    def __init__(self, message: str = "Cancel was selected."):
        super().__init__(message)


def parse_filter(text: str) -> list[str]:
    """VB's Filter ("Text Files (*.txt)|*.txt|All Files (*.*)|*.*") as Qt's
    name filters ("Text Files (*.txt)", "All Files (*)"): descriptions and
    patterns in pairs; *.* is every file."""
    parts = [p for p in str(text or "").split("|")]
    filters = []
    for index in range(0, len(parts) - 1, 2):
        description = re.sub(r"\s*\([^()]*\)\s*$", "", parts[index]).strip()
        patterns = " ".join("*" if p.strip() == "*.*" else p.strip()
                            for p in parts[index + 1].split(";") if p.strip())
        filters.append(f"{description or patterns} ({patterns or '*'})")
    return filters


def _commondialog_design_widget(parent: QWidget) -> QLabel:
    """The icon the designer shows for a CommonDialog: a small dialog window."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.2))
    painter.setBrush(QColor("#f4f4f4"))
    painter.drawRect(3, 4, 20, 17)
    painter.fillRect(4, 5, 19, 4, QColor("#3b6fd1"))  # its title bar
    painter.setBrush(QColor("#ffe08a"))
    painter.drawRect(6, 12, 7, 6)  # a folder...
    painter.setBrush(QColor("#d8d8d8"))
    painter.drawRect(15, 15, 6, 3)  # ...and a button
    painter.end()
    label = QLabel(parent)
    label.setFixedSize(32, 32)
    label.setAlignment(Qt.AlignCenter)
    label.setFrameStyle(QFrame.Panel | QFrame.Raised)
    label.setPixmap(pixmap)
    return label


class CommonDialog(Control):
    """VB's CommonDialog: the system's Open, Save As, Color, Font and Print
    dialogs (ShowOpen, ShowSave, ShowColor, ShowFont, ShowPrinter) and help
    (ShowHelp). Invisible at run time. Set its properties first (Filter,
    InitDir, Color...), show a dialog, then read what was chosen (FileName,
    Color, FontName...). Each Show... returns True, or False when cancelled;
    with CancelError, cancelling raises DialogCancelled (VB's error 32755)."""

    TypeName = "CommonDialog"
    DefaultEvent = ""
    Events: tuple[str, ...] = ()
    DefaultSize = (32, 32)
    Properties = (
        P("Left", "int", 0, always=True, description="Position in the designer only"),
        P("Top", "int", 0, always=True, description="Position in the designer only"),
        P("DialogTitle", "str", "", description="The dialog's title; unset = the system's"),
        P("CancelError", "bool", False,
          description="Cancelling a dialog raises DialogCancelled (VB's error 32755)"),
        P("Flags", "int", 0,
          description="Options added together: vpOFN... (Open, Save), vpCC... (Color), "
                      "vpCF... (Font), vpPD... (Printer)"),
        P("FileName", "str", "", description="The file chosen (a full path); also the "
                                             "first one suggested"),
        P("Filter", "str", "",
          description="The file types offered: description|patterns pairs, "
                      "e.g. Text Files (*.txt)|*.txt|All Files (*.*)|*.*"),
        P("FilterIndex", "int", 1, description="The Filter pair chosen, from 1"),
        P("InitDir", "str", "", description="The folder a file dialog starts in"),
        P("DefaultExt", "str", "",
          description="Added to a file name typed without an extension (Save As)"),
        P("Color", "color", 0x000000, description="The color chosen (the dialog starts with it)"),
        P("FontName", "str", "", description="The font chosen (the dialog starts with it)"),
        P("FontSize", "int", 0, description="Its size in points (0: the system's)"),
        P("FontBold", "bool", False, description="Bold"),
        P("FontItalic", "bool", False, description="Italic"),
        P("FontUnderline", "bool", False, description="Underlined"),
        P("FontStrikethru", "bool", False, description="Struck through"),
        P("Copies", "int", 1, description="Copies to print (the Print dialog)"),
        P("FromPage", "int", 0, description="The first page to print (with vpPDPageNums)"),
        P("ToPage", "int", 0, description="The last page to print (with vpPDPageNums)"),
        P("Min", "int", 1, description="The first page there is"),
        P("Max", "int", 9999, description="The last page there is"),
        P("Orientation", "enum", 1, ((1, "1 - Portrait"), (2, "2 - Landscape")),
          description="Portrait or landscape (the Print dialog)"),
        P("HelpFile", "file", "", description="What ShowHelp opens: a file or web address"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__["FileNames"] = []
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        return _commondialog_design_widget(parent) if self._design_mode else None

    def _read_Width(self):
        return 32

    def _read_Height(self):
        return 32

    # (its Font... properties are what the Font dialog chose, not its own font)
    def _apply_font(self, _=None):
        pass

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font

    @property
    def FileTitle(self) -> str:
        """The chosen file's name, without its folder."""
        return os.path.basename(self._values.get("FileName", ""))

    def _parent_window(self) -> QWidget | None:
        widget = self._form._widget
        return widget.window() if widget is not None else None

    def _cancelled(self) -> bool:
        if self._values.get("CancelError"):
            raise DialogCancelled()
        return False

    def _flag(self, value: int) -> bool:
        return bool(int(self._values.get("Flags", 0)) & value)

    # -- files ---------------------------------------------------------------------------------
    def _file_dialog(self, save: bool) -> bool:
        dialog = QFileDialog(self._parent_window(), self._values.get("DialogTitle") or
                             ("Save As" if save else "Open"))
        name = self._values.get("FileName", "")
        folder = self._values.get("InitDir") or (os.path.dirname(name) if name else "")
        if folder:
            dialog.setDirectory(resolve_path(self._form, folder))
        if name:
            dialog.selectFile(os.path.basename(name))
        filters = parse_filter(self._values.get("Filter", ""))
        if filters:
            dialog.setNameFilters(filters)
            index = self._values.get("FilterIndex", 1) - 1
            dialog.selectNameFilter(filters[index if 0 <= index < len(filters) else 0])
        if self._values.get("DefaultExt"):
            dialog.setDefaultSuffix(self._values["DefaultExt"].lstrip("."))
        if save:
            dialog.setAcceptMode(QFileDialog.AcceptSave)
            dialog.setFileMode(QFileDialog.AnyFile)
            if not self._flag(0x2):  # (vpOFNOverwritePrompt: ask before replacing)
                dialog.setOption(QFileDialog.DontConfirmOverwrite, True)
        else:
            dialog.setFileMode(QFileDialog.ExistingFiles if self._flag(0x200)
                               else QFileDialog.ExistingFile)
        if dialog.exec() != QDialog.Accepted or not dialog.selectedFiles():
            return self._cancelled()
        files = dialog.selectedFiles()
        self.__dict__["FileNames"] = list(files)
        self._values["FileName"] = files[0]
        if filters and dialog.selectedNameFilter() in filters:
            self._values["FilterIndex"] = filters.index(dialog.selectedNameFilter()) + 1
        return True

    def ShowOpen(self) -> bool:
        """The Open dialog: FileName (and FileNames, with vpOFNAllowMultiselect)
        is the file chosen. False if cancelled."""
        return self._file_dialog(save=False)

    def ShowSave(self) -> bool:
        """The Save As dialog (vpOFNOverwritePrompt asks before replacing a
        file); FileName is the file chosen. False if cancelled."""
        return self._file_dialog(save=True)

    # -- color, font, printer, help ---------------------------------------------------------------
    def ShowColor(self) -> bool:
        """The Color dialog, starting with Color; Color is the color chosen."""
        dialog = QColorDialog(colors.to_qcolor(self._values.get("Color", 0)),
                              self._parent_window())
        if self._values.get("DialogTitle"):
            dialog.setWindowTitle(self._values["DialogTitle"])
        if dialog.exec() != QDialog.Accepted:
            return self._cancelled()
        self._values["Color"] = colors.from_qcolor(dialog.currentColor())  # (the one chosen)
        return True

    def ShowFont(self) -> bool:
        """The Font dialog, starting with FontName, FontSize, FontBold...; they
        are the font chosen."""
        values = self._values
        font = QFont(values.get("FontName") or QApplication.font().family())
        if values.get("FontSize"):
            font.setPointSize(values["FontSize"])
        font.setBold(bool(values.get("FontBold")))
        font.setItalic(bool(values.get("FontItalic")))
        font.setUnderline(bool(values.get("FontUnderline")))
        font.setStrikeOut(bool(values.get("FontStrikethru")))
        dialog = QFontDialog(font, self._parent_window())
        if values.get("DialogTitle"):
            dialog.setWindowTitle(values["DialogTitle"])
        if dialog.exec() != QDialog.Accepted:
            return self._cancelled()
        chosen = dialog.currentFont()  # (the one chosen)
        values.update(FontName=chosen.family(), FontSize=max(chosen.pointSize(), 0),
                      FontBold=chosen.bold(), FontItalic=chosen.italic(),
                      FontUnderline=chosen.underline(), FontStrikethru=chosen.strikeOut())
        return True

    def ShowPrinter(self) -> bool:
        """The Print dialog: Copies, the page range (with vpPDPageNums: FromPage,
        ToPage, between Min and Max) and Orientation are what was chosen."""
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter

        values = self._values
        printer = QPrinter()
        printer.setCopyCount(max(1, values.get("Copies", 1)))
        printer.setPageOrientation(QPageLayout.Landscape if values.get("Orientation") == 2
                                   else QPageLayout.Portrait)
        dialog = QPrintDialog(printer, self._parent_window())
        dialog.setMinMax(values.get("Min", 1), max(values.get("Max", 9999), values.get("Min", 1)))
        if self._flag(0x2):  # vpPDPageNums: a page range
            dialog.setOption(QAbstractPrintDialog.PrintPageRange, True)
            dialog.setFromTo(values.get("FromPage", 0), values.get("ToPage", 0))
            dialog.setPrintRange(QAbstractPrintDialog.PageRange)
        if values.get("DialogTitle"):
            dialog.setWindowTitle(values["DialogTitle"])
        if dialog.exec() != QDialog.Accepted:
            return self._cancelled()
        values.update(Copies=printer.copyCount(), FromPage=dialog.fromPage(),
                      ToPage=dialog.toPage(),
                      Orientation=2 if printer.pageLayout().orientation() ==
                      QPageLayout.Landscape else 1)
        return True

    def ShowHelp(self) -> bool:
        """Open HelpFile (a file, relative to the form's folder, or a web
        address) with the program the system has for it."""
        target = self._values.get("HelpFile", "")
        if not target:
            raise ValueError(f"CommonDialog '{self.Name}': no HelpFile to show")
        url = QUrl(target) if "://" in target else \
            QUrl.fromLocalFile(resolve_path(self._form, target))
        return bool(QDesktopServices.openUrl(url))


CONTROL_TYPES: dict[str, type[Control]] = {
    cls.TypeName: cls for cls in (
        PictureBox, Label, TextBox, Frame, CommandButton, CheckBox, OptionButton,
        ComboBox, ListBox, HScrollBar, VScrollBar, Timer, DriveListBox, DirListBox,
        FileListBox, Shape, Line, Image, TreeView, Splitter,
        ProgressBar, Slider, UpDown, StatusBar, TabStrip, ImageList, Toolbar, ListView,
        RichTextBox, CodeBox, FlexGrid, DockPanel, CommonDialog, Menu,
    )
}


_CAUSES_VALIDATION = P(
    "CausesValidation", "bool", True,
    description="Moving the focus here first fires the Validate event of the control "
                "leaving it (False: e.g. a Help or Cancel button that mustn't wait for "
                "a valid value)")


def _add_validation(cls) -> None:
    """A control that takes the focus gets CausesValidation and Validate."""
    if "GotFocus" not in cls.Events or "CausesValidation" in cls._specs:
        return
    cls.Properties = tuple(cls.Properties) + (_CAUSES_VALIDATION,)
    cls._specs = {**cls._specs, "CausesValidation": _CAUSES_VALIDATION}
    cls.CausesValidation = _make_property("CausesValidation")
    cls.Events = tuple(cls.Events) + ("Validate",)


for _cls in CONTROL_TYPES.values():
    _add_validation(_cls)


# --- the mouse: pointers, and drag and drop -------------------------------------------------------

_CURSORS = {1: Qt.ArrowCursor, 2: Qt.CrossCursor, 3: Qt.IBeamCursor, 4: Qt.ArrowCursor,
            5: Qt.SizeAllCursor, 6: Qt.SizeBDiagCursor, 7: Qt.SizeVerCursor,
            8: Qt.SizeFDiagCursor, 9: Qt.SizeHorCursor, 10: Qt.UpArrowCursor,
            11: Qt.WaitCursor, 12: Qt.ForbiddenCursor, 13: Qt.BusyCursor,
            14: Qt.WhatsThisCursor, 15: Qt.SizeAllCursor}
POINTER_CHOICES = tuple((value, f"{value} - {label}") for value, label in (
    (0, "Default"), (1, "Arrow"), (2, "Cross"), (3, "I-Beam"), (4, "Icon"), (5, "Size"),
    (6, "Size NE SW"), (7, "Size N S"), (8, "Size NW SE"), (9, "Size W E"), (10, "Up Arrow"),
    (11, "Hourglass"), (12, "No Drop"), (13, "Arrow and Hourglass"),
    (14, "Arrow and Question"), (15, "Size All"), (99, "Custom")))


def pointer_cursor(value: int, icon: str = "") -> QCursor | None:
    """A MousePointer value as a cursor: None for vpDefault (the control's
    own), the MouseIcon picture for vpCustom (None if it can't be read)."""
    value = int(value or 0)
    if value == 0:
        return None
    if value == 99:
        pixmap = QPixmap(icon) if icon else QPixmap()
        return QCursor(pixmap) if not pixmap.isNull() else None
    return QCursor(_CURSORS.get(value, Qt.ArrowCursor))


_MOUSE_PROPERTIES = (
    P("MousePointer", "enum", 0, POINTER_CHOICES,
      description="The mouse pointer's shape over it (Custom: its MouseIcon picture)"),
    P("MouseIcon", "file", "", description="The pointer's picture when MousePointer is Custom"),
    P("DragMode", "enum", 0, enum_choices("Manual", "Automatic"),
      description="Automatic: pressing the mouse on it drags it (no Click or MouseDown); "
                  "Manual: its Drag method does"),
    P("DragIcon", "file", "",
      description="The picture shown while it is dragged; unset = an image of the control"),
    P("OLEDropMode", "enum", 0, enum_choices("None", "Manual"),
      description="Manual: text and files dropped from other programs fire OLEDragOver and "
                  "OLEDragDrop (None: the control's own behavior)"),
)
_DRAG_EVENTS = ("DragDrop", "DragOver", "OLEDragDrop", "OLEDragOver")
_NO_MOUSE_MEMBERS = ("Timer", "Line", "Shape", "ImageList", "Menu", "Splitter", "CommonDialog")


def _add_mouse_members(cls) -> None:
    """A visible control gets MousePointer, MouseIcon, DragMode, DragIcon,
    OLEDropMode and the drag and drop events."""
    if cls.TypeName in _NO_MOUSE_MEMBERS or "MousePointer" in cls._specs:
        return
    cls.Properties = tuple(cls.Properties) + _MOUSE_PROPERTIES
    cls._specs = {**cls._specs, **{spec.name: spec for spec in _MOUSE_PROPERTIES}}
    for spec in _MOUSE_PROPERTIES:
        setattr(cls, spec.name, _make_property(spec.name))
    cls.Events = tuple(cls.Events) + _DRAG_EVENTS


for _cls in CONTROL_TYPES.values():
    _add_mouse_members(_cls)

# VB's drag in progress: the control being dragged, the QDrag, the control (or
# form) it is over and where
_VP6_DRAG_MIME = "application/x-vp6-control"
_DRAGGING: dict = {"source": None, "drag": None, "target": None, "pos": (0, 0)}
VP_ENTER, VP_LEAVE, VP_OVER = 0, 1, 2  # DragOver's State


class DataObject:
    """What was dropped from another program (OLEDragDrop's Data): its text and
    files. ``GetFormat(vpCFText)``, ``GetData(vpCFText)``, ``Files``."""

    def __init__(self, mime):
        self._text = mime.text() if mime.hasText() else None
        self.Files = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def GetFormat(self, Format: int) -> bool:
        """Whether it has that format: vpCFText (1) or vpCFFiles (15)."""
        return {1: self._text is not None, 15: bool(self.Files)}.get(int(Format), False)

    def GetData(self, Format: int = 1):
        """Its text (vpCFText) or its files' paths (vpCFFiles); None if it has none."""
        if int(Format) == 15:
            return list(self.Files) or None
        if int(Format) == 1:
            return self._text
        return None

    def __repr__(self):
        return f"<DataObject text={self._text!r} files={self.Files!r}>"


def handle_drag_event(owner, event, pos) -> bool:
    """A drag event over a control or form (``owner``, ``pos`` in it): VB's
    DragOver / DragDrop for a VP6 drag, OLEDragOver / OLEDragDrop for one from
    another program when its OLEDropMode is Manual. True: handled here."""
    etype = event.type()
    if etype == QEvent.DragLeave:
        if _DRAGGING["target"] is owner:
            _DRAGGING["target"] = None
            owner._fire("DragOver", _DRAGGING["source"], *_DRAGGING["pos"], VP_LEAVE)
        elif owner.__dict__.get("_ole_over"):
            owner.__dict__["_ole_over"] = False
            owner._fire("OLEDragOver", None, 0, 0, 0, 0, 0, VP_LEAVE)
        return False
    mime = event.mimeData()
    x, y = pos.x(), pos.y()
    if mime.hasFormat(_VP6_DRAG_MIME) and _DRAGGING["source"] is not None:
        source = _DRAGGING["source"]
        if etype == QEvent.Drop:
            _DRAGGING["target"] = None
            event.acceptProposedAction()
            owner._fire("DragDrop", source, x, y)
            return True
        state = VP_ENTER if _DRAGGING["target"] is not owner else VP_OVER
        _DRAGGING.update(target=owner, pos=(x, y))
        refused = owner._fire("DragOver", source, x, y, state) is False
        _accept_drag(event, refused)
        return True
    if owner._values.get("OLEDropMode") == 1 and (mime.hasText() or mime.hasUrls()):
        data = DataObject(mime)
        buttons, shift = vp_buttons(event.buttons()), vp_shift(event.modifiers())
        if etype == QEvent.Drop:
            owner.__dict__["_ole_over"] = False
            event.acceptProposedAction()
            owner._fire("OLEDragDrop", data, 1, buttons, shift, x, y)
            return True
        state = VP_OVER if owner.__dict__.get("_ole_over") else VP_ENTER
        owner.__dict__["_ole_over"] = True
        effect = owner._fire("OLEDragOver", data, 1, buttons, shift, x, y, state)
        _accept_drag(event, isinstance(effect, int) and not isinstance(effect, bool) and
                     effect == 0)  # (vpDropEffectNone: not here)
        return True
    return False


def _accept_drag(event, refused: bool) -> None:
    """Take a drag event here: refused, no drop (the no-drop pointer). (Ignoring
    it would hand it to the container, which might take the drop instead.)"""
    if refused:
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
    else:
        event.acceptProposedAction()


class ControlArray:
    """A VB control array: controls sharing one name, told apart by ``Index``.

    The designer writes::

        self.cmdDigit = ControlArray()
        self.cmdDigit[0] = CommandButton(self, Caption='0', ...)
        self.cmdDigit[1] = CommandButton(self, Caption='1', ...)

    and the event handlers get the element's Index first::

        def cmdDigit_Click(self, Index):
            self.txtDisplay.Text += self.cmdDigit[Index].Caption

    Elements are ``self.cmdDigit[i]`` or, like VB, ``self.cmdDigit(i)``.
    Iterating gives the elements in Index order. Indexes needn't be
    contiguous. ``Load(i)`` adds an element at run time, ``Unload(i)``
    removes one that was added that way.
    """

    def __init__(self):
        self._name = ""  # set when assigned to a form attribute
        self._items: dict[int, Control] = {}

    def __repr__(self):
        return f"<ControlArray {self._name or '?'} {sorted(self._items)}>"

    # -- elements --------------------------------------------------------------------------
    def __setitem__(self, index: int, control: Control) -> None:
        if not isinstance(control, Control):
            raise TypeError(f"Control array '{self._name}': elements must be controls")
        index = self._check_index(index)
        if index in self._items:
            raise ValueError(f"Control array '{self._name}' already has an element {index}")
        others = next(iter(self._items.values()), None)
        if others is not None and type(others) is not type(control):
            raise TypeError(f"Control array '{self._name}' holds {others.TypeName} controls, "
                            f"not {control.TypeName}")
        control.__dict__["_name"] = self._name
        control.__dict__["_index"] = index
        self._items[index] = control

    def __getitem__(self, index: int) -> Control:
        try:
            return self._items[index]
        except (KeyError, TypeError):
            raise IndexError(f"Control array element '{self._name}({index})' "
                             "doesn't exist") from None

    __call__ = __getitem__  # VB style: self.cmdDigit(3)

    def Item(self, index: int) -> Control:
        """The element with this Index (like ``array[index]``)."""
        return self[index]

    def __contains__(self, index) -> bool:
        return index in self._items

    def __iter__(self):
        return iter([self._items[i] for i in sorted(self._items)])

    def __len__(self) -> int:
        return len(self._items)

    @property
    def Count(self) -> int:
        """The number of elements."""
        return len(self._items)

    @property
    def LBound(self) -> int:
        """The lowest Index."""
        return min(self._items, default=0)

    @property
    def UBound(self) -> int:
        """The highest Index."""
        return max(self._items, default=-1)

    def _check_index(self, index) -> int:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 32767:
            raise ValueError(f"Control array '{self._name}': Index must be a whole number "
                             f"from 0 to 32767, not {index!r}")
        return index

    # -- run-time elements -------------------------------------------------------------------
    def Load(self, index: int) -> Control:
        """Add element ``index`` at run time, like VB's ``Load cmdDigit(index)``.
        It copies the properties of the lowest element except Visible (False,
        so position it and set Visible = True) and TabIndex (the last one)."""
        index = self._check_index(index)
        if index in self._items:
            raise ValueError(f"Control array element '{self._name}({index})' already exists")
        if not self._items:
            raise ValueError(f"Control array '{self._name}' has no element to copy")
        template = self._items[self.LBound]
        props = {}
        for name in template._specs:
            if name in ("Visible", "TabIndex"):
                continue
            try:
                props[name] = getattr(template, name)
            except Exception:  # noqa: BLE001 - a property that can't be read is left out
                pass
        form = template._form
        if "TabIndex" in template._specs:
            props["TabIndex"] = 1 + max((c.TabIndex for c in form._controls
                                         if "TabIndex" in c._specs), default=-1)
        if "Visible" in template._specs:
            props["Visible"] = False
        control = type(template)(template.Parent, **props)
        control.__dict__["_loaded_at_runtime"] = True
        control._place_after(self._items[self.UBound])  # menus: after the last element
        self[index] = control
        return control

    def Unload(self, index: int) -> None:
        """Remove element ``index``; only elements added with ``Load`` can be."""
        control = self[index]
        if not control._loaded_at_runtime:
            raise ValueError(f"Can't unload '{self._name}({index})': it was created in the "
                             "designer (hide it with Visible = False instead)")
        del self._items[index]
        form = control._form
        if control in form._controls:
            form._controls.remove(control)
        control._dispose()


__all__ = [*CONTROL_TYPES, "ControlArray", "Node"]
