"""More buttons: ``CommandLink``, ``ToolButton`` and ``ButtonBox``.

* **CommandLink** is the Vista-style link button of wizards and task
  dialogs: a large ``Caption`` with a ``Description`` under it and an arrow
  (or its ``Picture``) before them. Like a CommandButton it can be the form's
  ``Default`` (Enter) or ``Cancel`` (Esc) button; ``Click`` fires.
* **ToolButton** is a standalone flat button, like a Toolbar's: a
  ``Picture``, a ``Caption``, ``ButtonStyle`` (icon, text, both),
  ``AutoRaise`` (flat until the mouse is over it), ``Checkable`` with
  ``Value``, an ``ArrowType`` instead of a picture, and a drop-down
  ``PopupMenu`` (one of the form's menus, by name: make it invisible in the
  Menu Editor to have it only here) opened as its ``PopupMode`` says.
  ``Click`` fires (``DblClick`` too, on a double-click), and
  ``ButtonMenuClick(ButtonMenu)`` when one of its menu's items is chosen there
  (the item's own Click fires too). ``IconSize`` sets its picture's size;
  ``Alignment`` Left puts the picture at the left with the Caption beside it,
  as in a list of tools.
* **ButtonBox** shows the platform's standard dialog buttons in the
  platform's order (OK left or right of Cancel...). ``Buttons`` lists them,
  one per line: a standard button's name (OK, Cancel, Yes, No, Apply, Help,
  Close, Save, Discard, Open, Reset, RestoreDefaults, SaveAll, YesToAll,
  NoToAll, Abort, Retry, Ignore), or ``Caption|role`` for a button of your
  own (the role: accept, reject, destructive, action, help, yes, no, reset,
  apply). ``ButtonClick(Index)`` fires with the button's number in that list
  (from 0), ``Accepted`` after an accept (or yes) button, ``Rejected`` after a
  reject (or no) button. Its accept button is the form's Default (Enter), its
  reject button the form's Cancel (Esc).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (QCommandLinkButton, QDialogButtonBox, QPushButton, QStyle,
                               QStyleOptionToolButton, QStylePainter, QToolButton)

from ._props import P, enum_choices
from .controls import (_COLORS, _COMMON, _FONT, _ORIENTATION, CONTROL_TYPES, EVENT_ARGS,
                       Control, Menu, _add_mouse_members, _add_validation, _geometry,
                       _PerItem)
from .picture import picture_icon

EVENT_ARGS.update({"ButtonMenuClick": "ButtonMenu", "Accepted": "", "Rejected": ""})


def _picture_icon(control, value) -> QIcon:
    return picture_icon(control, value or "")


# --- CommandLink ---------------------------------------------------------------------------

class CommandLink(Control):
    """The Vista-style link button (the module's documentation)."""

    TypeName = "CommandLink"
    DefaultSize = (257, 57)
    Events = ("Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QCommandLinkButton"
    Properties = (
        P("Caption", "str", "", always=True, description="The text; & marks the access key"),
        *_geometry(*DefaultSize),
        P("Description", "text", "", description="The smaller text under the Caption"),
        P("Picture", "file", "",
          description="The picture before the text; empty = the platform's arrow"),
        P("Default", "bool", False, description="Clicked when Enter is pressed on the form"),
        P("Cancel", "bool", False, description="Clicked when Esc is pressed on the form"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        button = QCommandLinkButton(parent)
        button.setAutoDefault(False)
        self.__dict__["_arrow"] = button.icon()  # (the platform's)
        return button

    def _connect_signals(self):
        self._widget.clicked.connect(lambda *_: self._fire("Click"))

    def _apply_Caption(self, v):
        self._widget.setText(v)

    def _apply_Description(self, v):
        self._widget.setDescription(v)

    def _apply_Picture(self, v):
        icon = _picture_icon(self, v)
        self._widget.setIcon(self._arrow if icon.isNull() else icon)

    def _apply_Default(self, v):
        self._widget.setDefault(bool(v))

    def _default_cancel(self, wanted: str) -> bool:
        if not self._values.get(wanted):
            return False
        self._widget.click()
        return True

    @property
    def Value(self) -> bool:
        return False

    @Value.setter
    def Value(self, v):
        """Setting Value = True clicks it (as a CommandButton's)."""
        if v:
            self._widget.click()


# --- ToolButton ------------------------------------------------------------------------------

class _AlignedToolButton(QToolButton):
    """A ToolButton's widget: as QToolButton's, or (``left``) its icon at the
    left with its text beside it (QToolButton centres them)."""

    left = False
    PADDING, GAP = 4, 6  # (left of the icon and right of the text; between them)

    def paintEvent(self, event):
        if not self.left:
            super().paintEvent(event)
            return
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.text = ""
        option.icon = QIcon()
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ToolButton, option)  # (hovered, checked)
        size = self.iconSize()
        left = self.PADDING
        if not self.icon().isNull() and self.toolButtonStyle() != Qt.ToolButtonTextOnly:
            self.icon().paint(painter, QRect(left, (self.height() - size.height()) // 2,
                                             size.width(), size.height()),
                              Qt.AlignCenter, QIcon.Normal if self.isEnabled() else
                              QIcon.Disabled)
            left += size.width() + self.GAP
        if self.toolButtonStyle() != Qt.ToolButtonIconOnly:
            text = self.rect().adjusted(left, 0, -self.PADDING, 0)
            painter.setPen(option.palette.color(QPalette.ButtonText))
            painter.drawText(text, Qt.AlignVCenter | Qt.AlignLeft,
                             self.fontMetrics().elidedText(self.text(), Qt.ElideRight,
                                                           text.width()))


_TOOL_STYLES = (Qt.ToolButtonIconOnly, Qt.ToolButtonTextOnly, Qt.ToolButtonTextBesideIcon,
                Qt.ToolButtonTextUnderIcon)
_POPUP_MODES = (QToolButton.DelayedPopup, QToolButton.MenuButtonPopup, QToolButton.InstantPopup)
_ARROWS = (Qt.NoArrow, Qt.UpArrow, Qt.DownArrow, Qt.LeftArrow, Qt.RightArrow)


class ToolButton(Control):
    """A flat button with a picture and maybe a drop-down menu (the module's
    documentation)."""

    TypeName = "ToolButton"
    DefaultSize = (33, 33)
    Events = ("Click", "DblClick", "ButtonMenuClick", "GotFocus", "LostFocus", "KeyDown",
              "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QToolButton"
    Properties = (
        P("Caption", "str", "", description="The text (shown as ButtonStyle says)"),
        *_geometry(*DefaultSize),
        P("Picture", "file", "", description="Its picture (relative to the form's folder)"),
        P("ButtonStyle", "enum", 0,
          enum_choices("Icon Only", "Text Only", "Text Beside Icon", "Text Under Icon"),
          description="The picture, the Caption, or both (a button without a Picture shows "
                      "its Caption)"),
        P("AutoSize", "bool", False,
          description="As large as its picture and Caption need (the style's size for "
                      "them), as a tool button in a toolbar"),
        P("IconSize", "int", 0,
          description="The side of its picture in pixels; 0 = the picture's own size"),
        P("Alignment", "enum", 2, enum_choices("Left", "Right", "Center"),
          description="Where its picture and Caption are: Center as a toolbar's; Left, the "
                      "picture at the left and the Caption beside it (a list of tools)"),
        P("AutoRaise", "bool", True,
          description="Flat, raised only while the mouse is over it (as on a toolbar)"),
        P("Checkable", "bool", False,
          description="A toggle: a click presses it in, the next lets it out (Value)"),
        P("Value", "bool", False, description="Whether a Checkable button is pressed in"),
        P("ArrowType", "enum", 0, enum_choices("None", "Up", "Down", "Left", "Right"),
          description="An arrow instead of the Picture"),
        P("PopupMenu", "str", "",
          description="The name of one of the form's menus (with items): they drop down "
                      "from the button"),
        P("PopupMode", "enum", 1, enum_choices("Delayed", "Menu Button", "Instant"),
          description="How the PopupMenu opens: holding the button down, from an arrow part "
                      "beside it (a click on the rest is Click), or with any click"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        button = _AlignedToolButton(parent)
        button.setFocusPolicy(Qt.StrongFocus)
        button.setIconSize(QSize(20, 20))
        return button


    def _connect_signals(self):
        self._widget.clicked.connect(self._on_clicked)

    def _on_clicked(self, *_):
        self._values["Value"] = self._widget.isChecked()
        self._fire("Click")

    def _apply_Caption(self, v):
        self._widget.setText(v)
        self._apply_ButtonStyle(self._values.get("ButtonStyle", 0))

    def _apply_AutoSize(self, v=None):
        if self._values.get("AutoSize") and self._widget is not None:
            hint = self._widget.sizeHint()
            if (hint.width(), hint.height()) != (self._values.get("Width"),
                                                 self._values.get("Height")):
                self.Width, self.Height = hint.width(), hint.height()

    def _apply_Picture(self, v):
        icon = _picture_icon(self, v)
        self._widget.setIcon(icon)
        self._apply_IconSize(self._values.get("IconSize", 0))
        self._apply_ButtonStyle(self._values.get("ButtonStyle", 0))

    def _apply_IconSize(self, v):
        if v:
            self._widget.setIconSize(QSize(int(v), int(v)))
            self._apply_AutoSize()
            return
        icon = self._widget.icon()
        if not icon.isNull():
            size = icon.availableSizes()[0] if icon.availableSizes() else QSize(20, 20)
            self._widget.setIconSize(size.boundedTo(QSize(48, 48)))

    def _apply_Alignment(self, v):
        self._widget.left = int(v) == 0
        self._widget.update()

    def _apply_ButtonStyle(self, v):
        style = _TOOL_STYLES[int(v) if 0 <= int(v) <= 3 else 0]
        if style == Qt.ToolButtonIconOnly and self._widget.icon().isNull() and \
                not self._values.get("ArrowType"):
            style = Qt.ToolButtonTextOnly  # (nothing else to show)
        self._widget.setToolButtonStyle(style)
        self._apply_AutoSize()

    def _apply_AutoRaise(self, v):
        self._widget.setAutoRaise(bool(v))
        self._apply_AutoSize()

    def _apply_font(self, _=None):
        super()._apply_font(_)
        self._apply_AutoSize()

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_FontWeight = _apply_font

    def _apply_Checkable(self, v):
        self._widget.setCheckable(bool(v))
        self._widget.setChecked(bool(v) and bool(self._values.get("Value")))

    def _read_Value(self):
        return self._widget.isChecked()

    def _apply_Value(self, v):
        self._widget.setChecked(bool(v) and self._widget.isCheckable())

    def _apply_ArrowType(self, v):
        self._widget.setArrowType(_ARROWS[int(v) if 0 <= int(v) <= 4 else 0])
        self._apply_ButtonStyle(self._values.get("ButtonStyle", 0))

    # -- the drop-down menu ---------------------------------------------------------------------
    def _menu_control(self) -> Menu | None:
        name = self._values.get("PopupMenu", "")
        if not name:
            return None
        menu = self._form.__dict__.get(name)
        return menu if isinstance(menu, Menu) else None

    def _apply_PopupMenu(self, v):
        if self._design_mode:
            return
        old = self.__dict__.get("_menu")
        if old is not None:
            try:
                old.triggered.disconnect(self._on_menu_triggered)
            except (RuntimeError, TypeError):
                pass
        menu = self._menu_control()
        submenu = menu._submenu if menu is not None else None
        self._widget.setMenu(submenu)
        self.__dict__["_menu"] = submenu
        if submenu is not None:
            submenu.triggered.connect(self._on_menu_triggered)
        self._apply_PopupMode(self._values.get("PopupMode", 1))

    def _form_loaded(self) -> None:
        if self.__dict__.get("_menu") is None:  # (the menus come after it in the region)
            self._apply_PopupMenu(self._values.get("PopupMenu", ""))

    def _on_menu_triggered(self, action):
        if not self._widget.isDown():  # (chosen from the menu bar, not from here)
            return
        for control in self._form._controls:
            if isinstance(control, Menu) and control._action is action:
                self._fire("ButtonMenuClick", control)
                return

    def _apply_PopupMode(self, v):
        # (without a menu: no arrow part)
        self._widget.setPopupMode(_POPUP_MODES[int(v) if 0 <= int(v) <= 2 else 1]
                                  if self._widget.menu() is not None else _POPUP_MODES[0])

    def ShowMenu(self) -> None:
        """Drop its PopupMenu down now."""
        if self._widget.menu() is not None:
            self._widget.showMenu()


# --- ButtonBox -------------------------------------------------------------------------------

_STANDARD = {name.casefold(): getattr(QDialogButtonBox, name) for name in (
    "Ok", "Open", "Save", "Cancel", "Close", "Discard", "Apply", "Reset", "RestoreDefaults",
    "Help", "SaveAll", "Yes", "YesToAll", "No", "NoToAll", "Abort", "Retry", "Ignore")}
_ROLES = ("accept", "reject", "destructive", "action", "help", "yes", "no", "reset", "apply")
_QT_ROLES = (QDialogButtonBox.AcceptRole, QDialogButtonBox.RejectRole,
             QDialogButtonBox.DestructiveRole, QDialogButtonBox.ActionRole,
             QDialogButtonBox.HelpRole, QDialogButtonBox.YesRole, QDialogButtonBox.NoRole,
             QDialogButtonBox.ResetRole, QDialogButtonBox.ApplyRole)


def parse_box_button(line: str) -> tuple[str, int | None, object]:
    """A ButtonBox line: (caption, role, standard button or None). "OK" is a
    standard button; "&Print|action" one of your own, its role a word or a
    number (vpRoleAccept...)."""
    caption, _, role = str(line).partition("|")
    caption, role = caption.strip(), role.strip().casefold()
    if not role:
        standard = _STANDARD.get(caption.replace(" ", "").casefold())
        if standard is not None:
            return caption, None, standard
        return caption, 3, None  # (an unknown name: a button of its own, an action)
    if role.isdigit():
        number = int(role)
    else:
        number = _ROLES.index(role) if role in _ROLES else 3
    return caption, number if 0 <= number < len(_ROLES) else 3, None


class ButtonBox(Control):
    """The platform's standard dialog buttons, in its order (the module's
    documentation)."""

    TypeName = "ButtonBox"
    DefaultEvent = "ButtonClick"
    DefaultSize = (257, 33)
    Events = ("ButtonClick", "Accepted", "Rejected", "GotFocus", "LostFocus", "KeyDown",
              "KeyPress", "KeyUp")
    EventArgs = {"ButtonClick": "Index"}
    Properties = (
        *_geometry(*DefaultSize),
        P("Buttons", "list", ["OK", "Cancel"],
          description="Its buttons, one per line: a standard button (OK, Cancel, Yes, No, "
                      "Apply, Help, Close, Save, Discard, Open, Reset, RestoreDefaults, "
                      "SaveAll, YesToAll, NoToAll, Abort, Retry, Ignore) or Caption|role "
                      "(accept, reject, destructive, action, help, yes, no, reset, apply)"),
        P("Orientation", "enum", 0, _ORIENTATION,
          description="Horizontal (in a row) or Vertical (in a column)"),
        P("CenterButtons", "bool", False, description="The buttons in the middle"),
        *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_buttons"] = []  # [(QPushButton, caption, role)], in the list's order
        box = QDialogButtonBox(parent)
        return box

    def _event_targets(self):
        return [self._widget, *(button for button, _caption, _role in self._buttons)]

    def _connect_signals(self):
        self._widget.clicked.connect(self._on_clicked)
        self._widget.accepted.connect(lambda: self._fire("Accepted"))
        self._widget.rejected.connect(lambda: self._fire("Rejected"))

    def _on_qt_event(self, watched, event):
        if watched is not self._widget and event.type() in (
                QEvent.FocusIn, QEvent.FocusOut, QEvent.KeyPress, QEvent.KeyRelease):
            return Control._on_qt_event(self, self._widget, event)  # (its buttons' are its)
        return super()._on_qt_event(watched, event)

    def _on_clicked(self, clicked):
        for index, (button, _caption, _role) in enumerate(self._buttons):
            if button is clicked:
                self._fire("ButtonClick", index)
                return

    def _apply_Buttons(self, lines):
        box = self._widget
        box.clear()
        self._buttons.clear()
        for line in lines or []:
            caption, role, standard = parse_box_button(line)
            if standard is not None:
                button = box.addButton(standard)
                role = _QT_ROLES.index(box.buttonRole(button)) \
                    if box.buttonRole(button) in _QT_ROLES else 3
            else:
                button = box.addButton(caption, _QT_ROLES[role])
            button.setAutoDefault(False)
            self._buttons.append((button, button.text(), role))
        if self._bridge is not None:  # (its buttons' events are its own)
            for button, _caption, _role in self._buttons:
                button.installEventFilter(self._bridge)
        self._apply_default()

    def _apply_default(self) -> None:
        for button, _caption, role in self._buttons:
            button.setDefault(role in (0, 5) and button is self._role_button((0, 5)))

    def _role_button(self, roles) -> QPushButton | None:
        return next((button for button, _caption, role in self._buttons if role in roles), None)

    def _default_cancel(self, wanted: str) -> bool:
        button = self._role_button((0, 5) if wanted == "Default" else (1, 6))
        if button is None or not button.isEnabled():
            return False
        button.click()
        return True

    def _apply_Orientation(self, v):
        self._widget.setOrientation(Qt.Vertical if v == 1 else Qt.Horizontal)

    def _apply_CenterButtons(self, v):
        self._widget.setCenterButtons(bool(v))

    # -- the buttons at run time --------------------------------------------------------------
    @property
    def ListCount(self) -> int:
        """How many buttons it has."""
        return len(self._buttons)

    def _check(self, index) -> int:
        index = int(index)
        if not 0 <= index < len(self._buttons):
            raise IndexError(f"ButtonBox '{self.Name}': no button {index} (it has "
                             f"{len(self._buttons)})")
        return index

    def AddButton(self, Caption: str, ButtonRole: int = 3) -> int:
        """Add a button of your own (its role vpRoleAction unless said); returns
        its Index (ButtonClick's)."""
        lines = list(self._values.get("Buttons") or []) + [f"{Caption}|{int(ButtonRole)}"]
        self.Buttons = lines
        return len(self._buttons) - 1

    def RemoveButton(self, Index: int) -> None:
        """Remove button Index (the ones after it move down by one)."""
        lines = list(self._values.get("Buttons") or [])
        del lines[self._check(Index)]
        self.Buttons = lines

    @property
    def ButtonCaption(self) -> _PerItem:
        """A button's text: ``ButtonCaption(0)``; ``ButtonCaption[0] = "&Go"``."""
        def write(index, value):
            self._buttons[index][0].setText(str(value))
        return _PerItem(self, "ButtonCaption", lambda i: self._buttons[i][0].text(), write)

    @property
    def ButtonEnabled(self) -> _PerItem:
        """Whether a button can be clicked: ``ButtonEnabled[1] = False``."""
        def write(index, value):
            self._buttons[index][0].setEnabled(bool(value))
        return _PerItem(self, "ButtonEnabled", lambda i: self._buttons[i][0].isEnabled(),
                        write)

    @property
    def ButtonRole(self) -> _PerItem:
        """A button's role (vpRoleAccept, vpRoleReject...), read-only."""
        def write(index, value):
            raise AttributeError("ButtonRole is read-only: set it in Buttons (Caption|role)")
        return _PerItem(self, "ButtonRole", lambda i: self._buttons[i][2], write)


_TYPES = (CommandLink, ToolButton, ButtonBox)
for _cls in _TYPES:
    _add_validation(_cls)
    _add_mouse_members(_cls)
    CONTROL_TYPES[_cls.TypeName] = _cls  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
