"""VB6 style intrinsic controls built on Qt widgets.

Events are dispatched by name: a control named ``Command1`` on a form fires
``Command1_Click`` if the form defines it. Handlers may declare fewer
parameters than VB passes (``def Text1_KeyPress(self, KeyAscii)`` or just
``def Text1_KeyPress(self)``).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFrame, QGroupBox, QLabel,
    QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QRadioButton, QScrollBar, QWidget,
)

from . import colors
from ._props import P, PropertyHost, enum_choices
from .app import call_handler

# Parameters passed to each event handler; used by the IDE to generate stubs.
EVENT_ARGS = {
    "Click": "", "DblClick": "", "Change": "", "Scroll": "", "Timer": "",
    "GotFocus": "", "LostFocus": "",
    "MouseDown": "Button, Shift, X, Y", "MouseUp": "Button, Shift, X, Y",
    "MouseMove": "Button, Shift, X, Y",
    "KeyDown": "KeyCode, Shift", "KeyUp": "KeyCode, Shift", "KeyPress": "KeyAscii",
    "Initialize": "", "Load": "", "Unload": "", "Activate": "", "Deactivate": "",
    "Resize": "",
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


def resolve_path(owner, path: str) -> str:
    if not path or os.path.isabs(path):
        return path
    base = owner._base_dir() if hasattr(owner, "_base_dir") else os.getcwd()
    return os.path.join(base, path)


# --- property groups ------------------------------------------------------------

def _geometry(width, height):
    return (P("Left", "int", 0, always=True), P("Top", "int", 0, always=True),
            P("Width", "int", width, always=True), P("Height", "int", height, always=True))


_FONT = (
    P("FontName", "font", None), P("FontSize", "int", None),
    P("FontBold", "bool", False), P("FontItalic", "bool", False),
    P("FontUnderline", "bool", False),
)
_COLORS = (P("BackColor", "color", None), P("ForeColor", "color", None))
_COMMON = (P("Enabled", "bool", True), P("Visible", "bool", True),
           P("TabIndex", "int", 0), P("ToolTipText", "str", ""), P("Tag", "str", ""))
_ALIGNMENT = enum_choices("Left Justify", "Right Justify", "Center")
_QT_ALIGN = {0: Qt.AlignLeft, 1: Qt.AlignRight, 2: Qt.AlignHCenter}


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

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.setdefault("_values", {})
        self.__dict__["_name"] = Name
        self.__dict__["Parent"] = parent
        self._form = parent._owner_form()
        self._design_mode = getattr(self._form, "_design_mode", False)
        self._key_resend = False
        self._widget = None
        self._bridge = None
        self._build_widget()
        self._init_values(props)
        self._form._register_control(self)

    # -- identity ------------------------------------------------------------
    @property
    def Name(self) -> str:
        return self._name

    @property
    def Container(self):
        return self.Parent

    def __repr__(self):
        return f"<{self.TypeName} {self._name or '?'}>"

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
        notify = getattr(self._form, "_control_widget_changed", None)
        if notify:
            notify(self)

    def _event_targets(self) -> list[QWidget]:
        return [self._widget]

    def _connect_signals(self) -> None:
        pass

    # -- event dispatch ----------------------------------------------------------------
    def _handler(self, event: str):
        if self._design_mode or not self._name:
            return None
        return getattr(self._form, f"{self._name}_{event}", None)

    def _fire(self, event: str, *args):
        handler = self._handler(event)
        if handler is None:
            return None
        return call_handler(handler, *args)

    def _on_qt_event(self, watched: QWidget, event: QEvent) -> bool:
        if self._design_mode:
            return False
        etype = event.type()
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
            self._fire("GotFocus")
        elif etype == QEvent.FocusOut:
            self._fire("LostFocus")
        return False

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
        """0 brings the control to the front, 1 sends it to the back."""
        if self._widget:
            self._widget.raise_() if Position == 0 else self._widget.lower()


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

class Label(Control):
    TypeName = "Label"
    DefaultSize = (97, 25)
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QLabel"
    Properties = (
        P("Caption", "str", "", always=True),
        *_geometry(*DefaultSize),
        P("Alignment", "enum", 0, _ALIGNMENT),
        P("AutoSize", "bool", False),
        P("WordWrap", "bool", False),
        P("BorderStyle", "enum", 0, enum_choices("None", "Fixed Single")),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        label = QLabel(parent)
        label.setTextFormat(Qt.PlainText)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        return label

    def _apply_Caption(self, v):
        self._widget.setText(strip_mnemonic(v))
        if self._values.get("AutoSize"):
            self._widget.adjustSize()

    def _apply_Alignment(self, v):
        self._widget.setAlignment(_QT_ALIGN.get(v, Qt.AlignLeft) | Qt.AlignTop)

    def _apply_AutoSize(self, v):
        if v:
            self._widget.adjustSize()

    def _apply_WordWrap(self, v):
        self._widget.setWordWrap(v)

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.Box | QFrame.Plain if v else QFrame.NoFrame)


# --- TextBox ------------------------------------------------------------------------

class TextBox(Control):
    TypeName = "TextBox"
    DefaultEvent = "Change"
    DefaultSize = (121, 25)
    Events = ("Change", "Click", "DblClick", "GotFocus", "LostFocus",
              "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    Properties = (
        P("MultiLine", "bool", False),
        P("Text", "text", "", always=True),
        *_geometry(*DefaultSize),
        P("Alignment", "enum", 0, _ALIGNMENT),
        P("PasswordChar", "str", ""),
        P("MaxLength", "int", 0),
        P("Locked", "bool", False),
        P("ScrollBars", "enum", 0, enum_choices("None", "Horizontal", "Vertical", "Both")),
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


# --- CommandButton ------------------------------------------------------------------

class CommandButton(Control):
    TypeName = "CommandButton"
    Events = ("Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QPushButton"
    Properties = (
        P("Caption", "str", "", always=True),
        *_geometry(*Control.DefaultSize),
        P("Default", "bool", False, description="Clicked when Enter is pressed"),
        P("Cancel", "bool", False, description="Clicked when Esc is pressed"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        button = QPushButton(parent)
        button.setAutoDefault(False)
        return button

    def _connect_signals(self):
        self._widget.clicked.connect(lambda *_: self._fire("Click"))

    def _apply_Caption(self, v):
        self._widget.setText(v)

    def _apply_Default(self, v):
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

class CheckBox(Control):
    TypeName = "CheckBox"
    Events = ("Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QCheckBox"
    Properties = (
        P("Caption", "str", "", always=True),
        *_geometry(121, 25),
        P("Value", "enum", 0, enum_choices("Unchecked", "Checked", "Grayed")),
        *_COLORS, *_FONT, *_COMMON,
    )
    DefaultSize = (121, 25)

    def _create_widget(self, parent):
        box = QCheckBox(parent)
        box.setTristate(False)
        return box

    def _connect_signals(self):
        self._widget.stateChanged.connect(lambda *_: self._fire("Click"))

    def _apply_Caption(self, v):
        self._widget.setText(v)

    def _read_Value(self):
        state = self._widget.checkState()
        return {Qt.Unchecked: 0, Qt.Checked: 1}.get(state, 2)

    def _apply_Value(self, v):
        if v == 2:
            self._widget.setTristate(True)
        self._widget.setCheckState({0: Qt.Unchecked, 1: Qt.Checked}.get(v, Qt.PartiallyChecked))


class OptionButton(Control):
    TypeName = "OptionButton"
    Events = CheckBox.Events
    _qss_type = "QRadioButton"
    DefaultSize = (121, 25)
    Properties = (
        P("Caption", "str", "", always=True),
        *_geometry(121, 25),
        P("Value", "bool", False),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        return QRadioButton(parent)

    def _connect_signals(self):
        self._widget.toggled.connect(lambda checked: checked and self._fire("Click"))

    def _apply_Caption(self, v):
        self._widget.setText(v)

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
        P("Caption", "str", "", always=True),
        *_geometry(*DefaultSize),
        *_COLORS, *_FONT,
        P("Enabled", "bool", True), P("Visible", "bool", True),
        P("TabIndex", "int", 0), P("ToolTipText", "str", ""), P("Tag", "str", ""),
    )

    def _create_widget(self, parent):
        return QGroupBox(parent)

    def _apply_Caption(self, v):
        self._widget.setTitle(v)

    def _apply_colors(self, _=None):
        _container_palette(self)

    _apply_BackColor = _apply_ForeColor = _apply_colors


# --- ListBox / ComboBox --------------------------------------------------------------------

class _ListMixin:
    """AddItem / RemoveItem / Clear / ListCount / ListIndex / List shared by
    ListBox and ComboBox."""

    def AddItem(self, Item, Index: int | None = None) -> None:
        self._insert(len(self._items()) if Index is None else int(Index), str(Item))

    def RemoveItem(self, Index: int) -> None:
        self._remove(int(Index))

    def Clear(self) -> None:
        self._widget.clear()

    @property
    def ListCount(self) -> int:
        return len(self._items())

    def _read_List(self):
        return self._items()

    def _apply_List(self, items):
        self._widget.clear()
        for item in items:
            self._insert(len(self._items()), item)


class ListBox(_ListMixin, Control):
    TypeName = "ListBox"
    DefaultSize = (121, 97)
    Events = ("Click", "DblClick", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QListWidget"
    Properties = (
        *_geometry(*DefaultSize),
        P("List", "list", []),
        P("Sorted", "bool", False),
        P("MultiSelect", "enum", 0, enum_choices("None", "Simple", "Extended")),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        return QListWidget(parent)

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        self._widget.currentRowChanged.connect(lambda *_: self._fire("Click"))

    def _items(self):
        return [self._widget.item(i).text() for i in range(self._widget.count())]

    def _insert(self, index, text):
        self._widget.insertItem(index, text)
        if self._values.get("Sorted"):
            self._widget.sortItems()

    def _remove(self, index):
        self._widget.takeItem(index)

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

    def Selected(self, Index: int) -> bool:
        item = self._widget.item(int(Index))
        return bool(item and item.isSelected())


class ComboBox(_ListMixin, Control):
    TypeName = "ComboBox"
    DefaultSize = (121, 25)
    Events = ("Change", "Click", "DblClick", "GotFocus", "LostFocus", "KeyDown", "KeyPress",
              "KeyUp")
    _qss_type = "QComboBox"
    Properties = (
        P("Style", "enum", 0, ((0, "0 - Dropdown Combo"), (2, "2 - Dropdown List"))),
        *_geometry(*DefaultSize),
        P("List", "list", []),
        P("Text", "str", "", always=True),
        P("Sorted", "bool", False),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        return QComboBox(parent)

    def _connect_signals(self):
        self._widget.currentIndexChanged.connect(lambda *_: self._fire("Click"))
        self._widget.editTextChanged.connect(lambda *_: self._fire("Change"))

    def _items(self):
        return [self._widget.itemText(i) for i in range(self._widget.count())]

    def _insert(self, index, text):
        self._widget.insertItem(index, text)
        if self._values.get("Sorted"):
            self._widget.model().sort(0)

    def _remove(self, index):
        self._widget.removeItem(index)

    def _apply_Style(self, v):
        self._widget.setEditable(v != 2)
        if v != 2:
            self._widget.lineEdit().installEventFilter(self._bridge)

    def _apply_Sorted(self, v):
        if v:
            self._widget.model().sort(0)

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


# --- Timer ------------------------------------------------------------------------------------

class Timer(Control):
    """Invisible at run time; fires the Timer event every Interval ms."""

    TypeName = "Timer"
    DefaultEvent = "Timer"
    DefaultSize = (32, 32)
    Events = ("Timer",)
    Properties = (
        P("Left", "int", 0, always=True), P("Top", "int", 0, always=True),
        P("Interval", "int", 0, description="Milliseconds between Timer events (0 = off)"),
        P("Enabled", "bool", True),
        P("Tag", "str", ""),
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
        P("Min", "int", 0), P("Max", "int", 32767), P("Value", "int", 0),
        P("SmallChange", "int", 1), P("LargeChange", "int", 1),
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


# --- PictureBox ---------------------------------------------------------------------------------

class PictureBox(Control):
    TypeName = "PictureBox"
    DefaultSize = (121, 97)
    IsContainer = True
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("Picture", "file", "", description="Image file (relative to the form's folder)"),
        P("Stretch", "bool", False),
        P("AutoSize", "bool", False),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single")),
        *_COLORS, *_COMMON,
    )

    def _create_widget(self, parent):
        label = QLabel(parent)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        return label

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

    _apply_BackColor = _apply_ForeColor = _apply_colors

    def Cls(self) -> None:
        self._widget.clear()


# Controls in toolbox order.
CONTROL_TYPES: dict[str, type[Control]] = {
    cls.TypeName: cls for cls in (
        PictureBox, Label, TextBox, Frame, CommandButton, CheckBox, OptionButton,
        ComboBox, ListBox, HScrollBar, VScrollBar, Timer,
    )
}

__all__ = list(CONTROL_TYPES)
