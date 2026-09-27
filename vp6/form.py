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

from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt
from PySide6.QtGui import QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QMenuBar, QWidget

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
        self._vp_form._layout_menu_bar()
        self._vp_form._layout_aligned()  # before Form_Resize, so it sees the panes' sizes
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


class _ContainerWatcher(QObject):
    """Keeps a form shown in a container (Form.ShowIn) as large as the
    container, whenever the container is resized."""

    def __init__(self, form: "Form", container_widget: QWidget):
        super().__init__(container_widget)
        self._form = form

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            self._form._fit_to_container()
        return False


class _FormClient(QWidget):
    """The form's area below a menu bar drawn in the window (Windows, Linux):
    the controls are on it. Its mouse events are the form's."""

    def __init__(self, form_widget: _FormWidget):
        super().__init__(form_widget)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        self.parentWidget().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.parentWidget().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self.parentWidget().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.parentWidget().mouseDoubleClickEvent(event)


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
        d["_menubar"] = None  # created with the first Menu
        d["_client"] = None  # the controls' area when the menu bar is in the window
        d["_menu_height"] = 0  # height of a menu bar in the window
        d["_container"] = None  # the control (or form) it is shown in, see ShowIn
        d["_fill"] = True  # shown in a container: fill it
        d["_watcher"] = None
        d["_embedded"] = []  # the forms shown in this form (or its containers)
        d["_widget"] = _FormWidget(self)
        self._widget.resize(480, 360)
        self._init_values({"Caption": type(self).__name__})
        initialize = getattr(self, "InitializeComponent", None)
        if initialize is not None:
            initialize()
        self._layout_aligned()
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
        return self._client if self._client is not None else self._widget

    # -- menus ---------------------------------------------------------------------------------
    def _menu_container(self):
        return self._menubar

    def _add_menu_item(self, menu) -> None:
        """A top-level Menu: on the menu bar (created with the first one)."""
        if self._menubar is None:
            bar = QMenuBar(self._widget)
            self.__dict__["_menubar"] = bar
            self._style_widget(bar)
            if not bar.isNativeMenuBar():  # macOS: the system menu bar, no room needed
                self._make_client()
        self._menubar.addAction(menu._action)
        self._widget.addAction(menu._action)
        self._layout_menu_bar()

    def _make_client(self) -> None:
        """Move the controls onto a client widget, so the menu bar can go above
        them without changing their positions (or the form's Height)."""
        client = _FormClient(self._widget)
        for child in self._widget.children():
            if isinstance(child, QWidget) and child not in (client, self._menubar) and \
                    not child.isWindow():
                shown = not child.isHidden()
                child.setParent(client)
                if shown:
                    child.show()
        self.__dict__["_client"] = client
        client.show()

    def _layout_menu_bar(self) -> None:
        """Keep an in-window menu bar at the top and the client area below it.
        The form's Height stays the client area's, so the window grows."""
        if self._client is None:
            return
        widget = self._widget
        height = self._menubar.heightForWidth(widget.width())
        if height <= 0:
            height = self._menubar.sizeHint().height()
        if height != self._menu_height:
            client_height = widget.height() - self._menu_height
            self.__dict__["_menu_height"] = height
            widget.setMinimumSize(0, 0)
            widget.setMaximumSize(16777215, 16777215)
            widget.resize(widget.width(), client_height + height)
            if self._shown_once:
                self._apply_fixed_size()
        self._menubar.setGeometry(0, 0, widget.width(), height)
        self._client.setGeometry(0, height, widget.width(), widget.height() - height)
        self._layout_aligned()

    def _layout_aligned(self) -> None:
        """Dock the PictureBoxes whose Align is set to the edges of the form's
        client area, in the order they were created: each takes its edge of
        the space the earlier ones left, keeping its height (Top, Bottom) or
        width (Left, Right). Hidden ones take no space (at run time)."""
        area = self._container_widget().rect()
        left, top, right, bottom = 0, 0, area.width(), area.height()
        for control in self._controls:
            align = control._values.get("Align", 0) if "Align" in control._specs else 0
            widget = control._widget
            if not align or widget is None or control.Parent is not self:
                continue
            if not self._design_mode and not control._values.get("Visible", True):
                continue
            width, height = max(right - left, 0), max(bottom - top, 0)
            if align == 1:  # Top
                size = min(widget.height(), height)
                widget.setGeometry(left, top, width, size)
                top += size
            elif align == 2:  # Bottom
                size = min(widget.height(), height)
                widget.setGeometry(left, bottom - size, width, size)
                bottom -= size
            elif align == 3:  # Left
                size = min(widget.width(), width)
                widget.setGeometry(left, top, size, height)
                left += size
            elif align == 4:  # Right
                size = min(widget.width(), width)
                widget.setGeometry(right - size, top, size, height)
                right -= size

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
        if control._values.get("Align"):  # e.g. an aligned PictureBox created in code
            self._layout_aligned()

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
        if self._container is not None:  # shown in a container: not a window
            return
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
        if self._design_mode or self._container is not None:
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
        return self._widget.height() - self._menu_height

    def _apply_Width(self, v):
        self._widget.setMinimumSize(0, 0)
        self._widget.setMaximumSize(16777215, 16777215)
        self._widget.resize(max(v, 1), self._widget.height())
        if self._shown_once:
            self._apply_fixed_size()

    def _apply_Height(self, v):
        self._widget.setMinimumSize(0, 0)
        self._widget.setMaximumSize(16777215, 16777215)
        self._widget.resize(self._widget.width(), max(v, 1) + self._menu_height)
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
        if not self._shown_once or self._design_mode or self._container is not None:
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
        return self._widget.height() - self._menu_height

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
        if self._container is not None:  # shown in a container (ShowIn)
            self._fit_to_container()
            widget.show()
            widget.raise_()
            return
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

    def _query_unload(self, force: bool = False) -> bool:
        """Fire Form_Unload (which can cancel, unless ``force``), then unload
        the forms shown in this one."""
        if self._loaded:
            result = self._fire("Unload")
            if result and not force:  # Form_Unload returned True -> Cancel
                return False
            self.__dict__["_loaded"] = False
            if self in _loaded_forms:
                _loaded_forms.remove(self)
        for control in self._controls:
            if isinstance(control, Timer) and control._timer is not None:
                control._timer.stop()
        for form in list(self._embedded):  # they go with their host, and can't cancel
            form._query_unload(force=True)
            form._widget.hide()
            form._leave_container()
        return True

    # -- showing a form inside another ------------------------------------------------------
    @property
    def Container(self):
        """The control (or form) this form is shown in with ShowIn, or None
        for a form in its own window."""
        return self._container

    def ShowIn(self, Container, Fill: bool = True) -> None:
        """Show this form inside a container of another form: a PictureBox or
        Frame, or the form itself. With ``Fill`` it fills the container and
        follows its size (Form_Resize fires); otherwise it keeps its size at
        its Left/Top. Form_Load fires as for Show. ``ShowIn(None)`` makes it a
        window again. Its Caption and BorderStyle apply only as a window."""
        if Container is None:
            if self._container is not None:
                self._leave_container()
            self.Show()
            return
        is_form = isinstance(Container, Form)
        if not is_form and not getattr(Container, "IsContainer", False):
            raise TypeError(f"Can't show {self.Name} in {Container!r}: use a container "
                            "(PictureBox, Frame) or a form")
        host = Container if is_form else Container._owner_form()
        if host is self or self._hosts(host):
            raise ValueError(f"Can't show {self.Name} inside itself")
        if self._container is not Container:
            if self._container is not None:
                self._leave_container()
            self._enter_container(Container, host)
        self.__dict__["_fill"] = bool(Fill)
        self.Show()

    def _hosts(self, form: "Form") -> bool:
        """Whether ``form`` is shown in this one, directly or not."""
        return any(child is form or child._hosts(form) for child in self._embedded)

    def _enter_container(self, container, host: "Form") -> None:
        widget, parent = self._widget, container._container_widget()
        visible = widget.isVisible()
        widget.setParent(parent, Qt.Widget)  # a child widget, no longer a window
        if visible:
            widget.show()
        watcher = _ContainerWatcher(self, parent)
        parent.installEventFilter(watcher)
        self.__dict__.update(_container=container, _watcher=watcher)
        host._embedded.append(self)

    def _leave_container(self) -> None:
        """Back to a window of its own (hidden until shown)."""
        container = self._container
        if container is None:
            return
        host = container if isinstance(container, Form) else container._owner_form()
        if self in host._embedded:
            host._embedded.remove(self)
        watcher = self._watcher
        if watcher is not None:
            watcher.parent().removeEventFilter(watcher)
            watcher.deleteLater()
        self.__dict__.update(_container=None, _watcher=None, _shown_once=False)
        self._widget.hide()
        self._widget.setParent(None, Qt.Window)

    def _fit_to_container(self) -> None:
        if self._container is None:
            return
        if self._fill:
            self._widget.setGeometry(self._container._container_widget().contentsRect())
        else:
            self._widget.move(self._values.get("Left", 0), self._values.get("Top", 0))

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
