"""The VB6 style Form.

    class Form1(Form):
        def InitializeComponent(self):          # written by the IDE designer
            self.Caption = "Hello"
            self.Command1 = CommandButton(self, Caption="Click me", Left=16, Top=16)

        def Form_Load(self):
            ...

        def Command1_Click(self):
            MsgBox("Hello, world!")

    run(Form1)
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QEventLoop, Qt
from PySide6.QtGui import QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from . import appearance, colors
from ._props import P, PropertyHost, enum_choices
from .app import call_handler, ensure_app, run_event_loop
from .controls import (_FONT, CommandButton, Control, ControlArray, TextBox, Timer,
                       vp_buttons, vp_key_code, vp_shift)

_loaded_forms: list["Form"] = []


class _FormsCollection:
    """VB's ``Forms`` collection: all currently loaded forms."""

    def __iter__(self):
        return iter(list(_loaded_forms))

    def __len__(self):
        return len(_loaded_forms)

    def __getitem__(self, index):
        return _loaded_forms[index]

    @property
    def Count(self) -> int:
        return len(_loaded_forms)


Forms = _FormsCollection()


class _FormWidget(QWidget):
    def __init__(self, form: "Form"):
        super().__init__()
        self._vp_form = form
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def closeEvent(self, event):
        if self._vp_form._query_unload():
            event.accept()
        else:
            event.ignore()

    def hideEvent(self, event):
        super().hideEvent(event)
        loop = self._vp_form._modal_loop
        if loop is not None and not self.isVisible():
            loop.quit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._vp_form._fire("Resize")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange:
            self._vp_form._fire("Activate" if self.isActiveWindow() else "Deactivate")

    def _mouse(self, name, event, buttons):
        pos = event.position().toPoint()
        self._vp_form._fire(name, vp_buttons(buttons), vp_shift(event.modifiers()),
                            pos.x(), pos.y())

    def mousePressEvent(self, event):
        self._mouse("MouseDown", event, event.button())

    def mouseReleaseEvent(self, event):
        self._mouse("MouseUp", event, event.button())
        if self.rect().contains(event.position().toPoint()):
            self._vp_form._fire("Click")

    def mouseMoveEvent(self, event):
        self._mouse("MouseMove", event, event.buttons())

    def mouseDoubleClickEvent(self, event):
        self._vp_form._fire("DblClick")

    def keyPressEvent(self, event):
        form = self._vp_form
        form._fire("KeyDown", vp_key_code(event.key()), vp_shift(event.modifiers()))
        if len(event.text()) == 1:
            form._fire("KeyPress", ord(event.text()))
        if not form._handle_default_cancel(None, event):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self._vp_form._fire("KeyUp", vp_key_code(event.key()), vp_shift(event.modifiers()))


class Form(PropertyHost):
    TypeName = "Form"
    DefaultEvent = "Load"
    Events = ("Load", "Unload", "Initialize", "Activate", "Deactivate", "Resize",
              "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp",
              "KeyDown", "KeyPress", "KeyUp")
    Properties = (
        P("Caption", "str", "", always=True,
          description="The window title; defaults to the form's class name"),
        P("Width", "int", 480, always=True, description="Client area width in pixels"),
        P("Height", "int", 360, always=True, description="Client area height in pixels"),
        P("Left", "int", 0, description="Screen position; used with StartUpPosition Manual"),
        P("Top", "int", 0, description="Screen position; used with StartUpPosition Manual"),
        P("StartUpPosition", "enum", 2,
          enum_choices("Manual", "CenterOwner", "CenterScreen", "Windows Default"),
          description="Where the window first appears"),
        P("BorderStyle", "enum", 2, enum_choices(
            "None", "Fixed Single", "Sizable", "Fixed Dialog", "Fixed ToolWindow",
            "Sizable ToolWindow"),
          description="The kind of window frame; fixed styles can't be resized"),
        P("WindowState", "enum", 0, enum_choices("Normal", "Minimized", "Maximized"),
          description="Normal, minimized or maximized window"),
        P("ControlBox", "bool", True, description="Show the window buttons"),
        P("MinButton", "bool", True, description="Show a minimize button"),
        P("MaxButton", "bool", True, description="Show a maximize button (sizable forms)"),
        P("KeyPreview", "bool", False,
          description="Form receives key events before its controls"),
        P("ColorScheme", "enum", 0,
          enum_choices("Project Default", "System", "Light", "Dark", "IDE"),
          description="Light or dark appearance. Project Default uses the project's "
                      "color scheme; System follows the operating system; IDE follows "
                      "the VP6 IDE's light/dark setting (System when run on its own)."),
        P("BackColor", "color", None, description="Background color; unset = the default"),
        P("ForeColor", "color", None, description="Text color; unset = the default"),
        *_FONT,
        P("Enabled", "bool", True, description="Whether the form responds to the user"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    # The IDE designer instantiates a subclass with this set to True.
    _design_mode = False

    def __init__(self):
        ensure_app()
        d = self.__dict__
        d["_values"] = {}
        d["_controls"] = []
        d["_loaded"] = False
        d["_shown_once"] = False
        d["_modal_loop"] = None
        d["_scheme_style"] = None  # Fusion for forced light/dark, None = native
        d["_widget"] = _FormWidget(self)
        self._widget.resize(480, 360)
        self._init_values({"Caption": type(self).__name__})
        initialize = getattr(self, "InitializeComponent", None)
        if initialize is not None:
            initialize()
        self._apply_tab_order()
        self._fire("Initialize")

    def __setattr__(self, name, value):
        # `self.Command1 = CommandButton(self, ...)` names the control, and
        # `self.cmdDigit = ControlArray()` the control array.
        if isinstance(value, (Control, ControlArray)) and not value._name:
            value.__dict__["_name"] = name
        object.__setattr__(self, name, value)

    def __repr__(self):
        return f"<Form {type(self).__name__}>"

    # -- infrastructure used by controls ----------------------------------------------
    def _owner_form(self):
        return self

    def _container_widget(self) -> QWidget:
        return self._widget

    def _base_dir(self) -> str:
        module = sys.modules.get(type(self).__module__)
        path = getattr(module, "__file__", None)
        return os.path.dirname(os.path.abspath(path)) if path else os.getcwd()

    # -- color scheme -------------------------------------------------------------------
    def _project_scheme(self) -> int:
        return appearance.project_scheme_for(self._base_dir())

    def _effective_scheme(self) -> int:
        """vpSchemeSystem, vpSchemeLight or vpSchemeDark."""
        return appearance.resolve(self._values.get("ColorScheme", 0) or self._project_scheme())

    def _is_dark(self) -> bool:
        return appearance.is_dark(self._effective_scheme())

    def _render_scheme(self) -> int:
        """The scheme used to draw the form (the designer may force System)."""
        return self._effective_scheme()

    def _apply_ColorScheme(self, _=None):
        forced = self._render_scheme() != appearance.vpSchemeSystem
        self.__dict__["_scheme_style"] = appearance.fusion_style() if forced else None
        appearance.style_tree(self._widget, self._scheme_style)
        self._apply_colors()

    def _style_widget(self, widget: QWidget) -> None:
        if self._scheme_style is not None:
            appearance.style_tree(widget, self._scheme_style)

    def _register_control(self, control: Control) -> None:
        self._controls.append(control)

    def _fire(self, event: str, *args):
        if self._design_mode:
            return None
        handler = getattr(self, f"Form_{event}", None)
        if handler is None:
            return None
        return call_handler(handler, *args)

    def _preview_key(self, event: str, key_code: int, shift: int) -> bool:
        """KeyPreview: the form sees KeyDown/KeyUp first. Returning 0 from the
        form's handler cancels the key."""
        if not self.KeyPreview:
            return False
        result = self._fire(event, key_code, shift)
        return isinstance(result, int) and not isinstance(result, bool) and result == 0

    def _handle_default_cancel(self, control, event) -> bool:
        """Enter clicks the Default button, Esc clicks the Cancel button."""
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if isinstance(control, CommandButton):
                control._widget.click()
                return True
            if isinstance(control, TextBox) and control.MultiLine:
                return False
            wanted = "Default"
        elif key == Qt.Key_Escape:
            wanted = "Cancel"
        else:
            return False
        for c in self._controls:
            if (isinstance(c, CommandButton) and c._values.get(wanted)
                    and c._widget.isEnabled() and c._widget.isVisible()):
                c._widget.click()
                return True
        return False

    def _apply_tab_order(self) -> None:
        widgets = [c._widget for c in sorted(self._controls, key=lambda c: c.TabIndex
                                             if "TabIndex" in c._specs else 0)
                   if c._widget is not None and "TabIndex" in c._specs]
        for first, second in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(first, second)

    def _apply_window_flags(self) -> None:
        style = self.BorderStyle
        if style in (4, 5):
            flags = Qt.Tool
        elif style == 3:
            flags = Qt.Dialog
        else:
            flags = Qt.Window
        flags |= Qt.CustomizeWindowHint | Qt.WindowTitleHint
        if style == 0:
            flags |= Qt.FramelessWindowHint
        if self.ControlBox:
            flags |= Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
            if self.MinButton and style in (1, 2):
                flags |= Qt.WindowMinimizeButtonHint
            if self.MaxButton and style == 2:
                flags |= Qt.WindowMaximizeButtonHint
        self._widget.setWindowFlags(flags)
        self._apply_fixed_size()

    def _apply_fixed_size(self) -> None:
        if self._design_mode:
            return
        if self.BorderStyle in (1, 3, 4):
            self._widget.setFixedSize(self._widget.size())
        else:
            self._widget.setMinimumSize(0, 0)
            self._widget.setMaximumSize(16777215, 16777215)

    def _position_on_first_show(self, owner) -> None:
        position = self.StartUpPosition
        if position == 0:
            self._widget.move(self._values.get("Left", 0), self._values.get("Top", 0))
            return
        if position == 3:
            return
        frame = self._widget.frameGeometry()
        target = None
        if position == 1:
            owner_widget = owner._widget if isinstance(owner, Form) else QApplication.activeWindow()
            if owner_widget is not None:
                target = owner_widget.frameGeometry().center()
        if target is None:
            screen = QGuiApplication.primaryScreen()
            target = screen.availableGeometry().center()
        frame.moveCenter(target)
        self._widget.move(frame.topLeft())

    # -- properties -------------------------------------------------------------------------
    def _apply_Caption(self, v):
        self._widget.setWindowTitle(v)

    def _read_Width(self):
        return self._widget.width()

    def _read_Height(self):
        return self._widget.height()

    def _apply_Width(self, v):
        self._widget.setMinimumSize(0, 0)
        self._widget.setMaximumSize(16777215, 16777215)
        self._widget.resize(max(v, 1), self._widget.height())
        if self._shown_once:
            self._apply_fixed_size()

    def _apply_Height(self, v):
        self._widget.setMinimumSize(0, 0)
        self._widget.setMaximumSize(16777215, 16777215)
        self._widget.resize(self._widget.width(), max(v, 1))
        if self._shown_once:
            self._apply_fixed_size()

    def _read_Left(self):
        return self._widget.x() if self._shown_once else self._values.get("Left", 0)

    def _read_Top(self):
        return self._widget.y() if self._shown_once else self._values.get("Top", 0)

    def _apply_Left(self, v):
        if self._shown_once:
            self._widget.move(v, self._widget.y())

    def _apply_Top(self, v):
        if self._shown_once:
            self._widget.move(self._widget.x(), v)

    def _apply_WindowState(self, v):
        if not self._shown_once or self._design_mode:
            return
        state = {1: Qt.WindowMinimized, 2: Qt.WindowMaximized}.get(v, Qt.WindowNoState)
        self._widget.setWindowState(state)

    def _apply_BorderStyle(self, v):
        if self._shown_once and not self._design_mode:
            visible = self._widget.isVisible()
            self._apply_window_flags()
            if visible:
                self._widget.show()

    _apply_ControlBox = _apply_MinButton = _apply_MaxButton = _apply_BorderStyle

    def _apply_Enabled(self, v):
        self._widget.setEnabled(v)

    def _apply_colors(self, _=None):
        scheme = self._render_scheme()
        # System: an empty palette, so the form follows the OS appearance live
        palette = QPalette() if scheme == appearance.vpSchemeSystem else \
            appearance.scheme_palette(scheme == appearance.vpSchemeDark)
        back, fore = self._values.get("BackColor"), self._values.get("ForeColor")
        if back is not None:
            palette.setColor(QPalette.Window, colors.to_qcolor(back))
        if fore is not None:
            palette.setColor(QPalette.WindowText, colors.to_qcolor(fore))
        self._widget.setPalette(palette)
        self._widget.setAutoFillBackground(back is not None)

    _apply_BackColor = _apply_ForeColor = _apply_colors

    def _apply_font(self, _=None):
        values = self._values
        font = QFont()
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

    # -- VB API --------------------------------------------------------------------------------
    @property
    def Me(self) -> "Form":
        return self

    @property
    def Name(self) -> str:
        return type(self).__name__

    @property
    def Controls(self) -> list[Control]:
        return list(self._controls)

    @property
    def ScaleWidth(self) -> int:
        return self._widget.width()

    @property
    def ScaleHeight(self) -> int:
        return self._widget.height()

    @property
    def Visible(self) -> bool:
        return self._widget.isVisible()

    @Visible.setter
    def Visible(self, value):
        self.Show() if value else self.Hide()

    def Load(self) -> None:
        """Fire Form_Load once (Show does this automatically)."""
        if not self._loaded:
            self.__dict__["_loaded"] = True
            _loaded_forms.append(self)
            self._fire("Load")

    def Show(self, Modal: int = 0, OwnerForm: "Form | None" = None) -> None:
        self.Load()
        if not self._loaded:  # Form_Load unloaded the form
            return
        widget = self._widget
        if not self._shown_once:
            self._apply_window_flags()
            self._position_on_first_show(OwnerForm)
            self.__dict__["_shown_once"] = True
        if Modal:
            widget.setWindowModality(Qt.ApplicationModal)
        state = self.WindowState
        if state == 2:
            widget.showMaximized()
        elif state == 1:
            widget.showMinimized()
        else:
            widget.show()
        widget.raise_()
        widget.activateWindow()
        if Modal:
            loop = QEventLoop()
            self.__dict__["_modal_loop"] = loop
            try:
                loop.exec()
            finally:
                self.__dict__["_modal_loop"] = None
                widget.setWindowModality(Qt.NonModal)

    def Hide(self) -> None:
        self._widget.hide()

    def Unload(self) -> bool:
        """Close the form. Returns False if Form_Unload cancelled it."""
        if self._widget.isVisible():
            return self._widget.close()
        return self._query_unload()

    def _query_unload(self) -> bool:
        if self._loaded:
            result = self._fire("Unload")
            if result:  # Form_Unload returned True -> Cancel
                return False
            self.__dict__["_loaded"] = False
            if self in _loaded_forms:
                _loaded_forms.remove(self)
        for control in self._controls:
            if isinstance(control, Timer) and control._timer is not None:
                control._timer.stop()
        return True

    def Move(self, Left, Top=None, Width=None, Height=None) -> None:
        self.__dict__["_shown_once"] = self._shown_once or self._widget.isVisible()
        self._widget.move(int(Left), int(Top if Top is not None else self._widget.y()))
        if Width is not None:
            self.Width = Width
        if Height is not None:
            self.Height = Height

    def Refresh(self) -> None:
        self._widget.update()

    def SetFocus(self) -> None:
        self._widget.activateWindow()
        self._widget.setFocus()

    @classmethod
    def Run(cls) -> int:
        return run(cls)


def Load(obj, Index: int | None = None):
    """``Load(form)`` loads a form (fires Form_Load); ``Load(self.cmdDigit, 5)``
    adds element 5 to a control array and returns it (VB: Load cmdDigit(5))."""
    if isinstance(obj, ControlArray):
        if Index is None:
            raise TypeError("Load(control_array, Index): which element to load?")
        return obj.Load(Index)
    obj.Load()
    return None


def Unload(obj, Index: int | None = None):
    """``Unload(form)`` closes a form (False if Form_Unload cancelled);
    ``Unload(self.cmdDigit, 5)`` removes a control array element added with
    Load."""
    if isinstance(obj, ControlArray):
        if Index is None:
            raise TypeError("Unload(control_array, Index): which element to unload?")
        obj.Unload(Index)
        return None
    return obj.Unload()


def run(form) -> int:
    """Show a form (class or instance) and run the event loop until all
    windows are closed. Returns the application's exit code."""
    ensure_app()
    instance = form() if isinstance(form, type) else form
    instance.Show()
    return run_event_loop()


__all__ = ["Form", "Forms", "Load", "Unload", "run"]
