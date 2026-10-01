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

import json
import os
import sys
import types

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor, QFont, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMenuBar, QWidget

from . import appearance, colors
from ._props import P, PropertyHost, enum_choices
from .app import call_handler, ensure_app, run_event_loop
from .drawing import DRAWING_PROPERTIES, Drawing
from .picture import picture_pixmap
from .controls import (_FONT, POINTER_CHOICES, CommandButton, Control, ControlArray, TextBox,
                       Timer, handle_drag_event, pointer_cursor, vp_buttons, vp_key_code,
                       vp_shift)
from .controls import Menu as MenuControl

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
        self.setAcceptDrops(True)  # (drag and drop: the form's events)
        # (the widget's own slot: disconnected when it goes)
        appearance.watcher().changed.connect(self._on_appearance_changed)

    def _on_appearance_changed(self):
        self._vp_form._appearance_changed()

    def _on_application_state(self, state):
        # A popup (ShowPopup) hides when the program goes to the background
        if self._vp_form.__dict__.get("_popup") and state != Qt.ApplicationActive:
            self.hide()

    def closeEvent(self, event):
        # Why it closes: Unload() in code, Ctrl+C (close_all_windows), else the user
        mode = self._vp_form.__dict__.pop("_unload_mode", None)
        if self._vp_form._query_unload(mode=VP_FORM_CONTROL_MENU if mode is None else mode):
            event.accept()
        else:
            event.ignore()

    def showEvent(self, event):
        super().showEvent(event)
        self._vp_form._embedded_visibility(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        loop = self._vp_form._modal_loop
        if loop is not None and not self.isVisible():
            loop.quit()
        self._vp_form._embedded_visibility(False)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._vp_form._container_widget() is self:  # (else its client area is drawn on)
            self._vp_form._paint_drawing(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._vp_form._layout_menu_bar()
        self._vp_form._layout_aligned()  # before Form_Resize, so it sees the panes' sizes
        self._vp_form._fire("Resize")

    def changeEvent(self, event):
        super().changeEvent(event)
        # Only a window follows window activation; a form shown in a container
        # is activated by being shown there (Form._embedded_visibility)
        if event.type() == QEvent.ActivationChange and self._vp_form._container is None and \
                self._vp_form.__dict__.get("_mdi_parent") is None:  # (MDI: the workspace's)
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

    def event(self, event):
        if self._form_drag_event(event, self):
            return True
        return super().event(event)

    def _form_drag_event(self, event, widget) -> bool:
        """A drag over the form itself (not over one of its controls): the
        form's DragOver / DragDrop or OLEDragOver / OLEDragDrop."""
        if event.type() not in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave,
                                QEvent.Drop) or self._vp_form._design_mode:
            return False
        pos = event.position().toPoint() if event.type() != QEvent.DragLeave else QPoint()
        # (the client area's own coordinates are the form's, as Left and Top are)
        # (a user control's surface: the user control, on its form)
        owner = self._vp_form.__dict__.get("_owner") or self._vp_form
        return handle_drag_event(owner, event, pos)


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
        self.setAcceptDrops(True)

    def paintEvent(self, event):
        super().paintEvent(event)
        self.parentWidget()._vp_form._paint_drawing(self)  # (the graphics methods')

    def mousePressEvent(self, event):
        self.parentWidget().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.parentWidget().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self.parentWidget().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.parentWidget().mouseDoubleClickEvent(event)

    def event(self, event):  # drag and drop over it: the form's
        parent = self.parentWidget()
        if isinstance(parent, _FormWidget) and parent._form_drag_event(event, self):
            return True
        return super().event(event)


# Form_QueryUnload's UnloadMode (constants.vpFormControlMenu ...)
VP_FORM_CONTROL_MENU, VP_FORM_CODE, VP_APP_TASK_MANAGER, VP_FORM_OWNER = 0, 1, 3, 5


class _FormType(type):
    """Default form instances, as in VB: a form's class name stands for one
    instance of it, made the first time it is used. ``frmOptions.Show()``,
    ``frmOptions.txtName.Text`` and ``frmOptions.Caption = "x"`` are the
    default instance's (``run(Form1)`` makes the running form Form1's). Only
    public names of a form class are forwarded: its methods, its properties
    and what only an instance has (its controls, its variables); not Form
    itself, classmethods, constants or names starting with _."""

    def __init__(cls, name, bases, namespace, **kwargs):
        super().__init__(name, bases, namespace, **kwargs)
        type.__setattr__(cls, "_vp_ready", True)  # (its class body is done)

    def _forwards(cls, name: str) -> bool:
        own = type.__getattribute__(cls, "__dict__")
        return not name.startswith("_") and own.get("_vp_ready", False) and \
            "_vp_base" not in own and not type.__getattribute__(cls, "_vp_no_default")

    def __getattribute__(cls, name):
        value = type.__getattribute__(cls, name)
        if isinstance(value, (types.FunctionType, property)) and \
                type(cls)._forwards(cls, name):
            return getattr(cls._vp_default_instance(), name)
        return value

    def __getattr__(cls, name):  # (not on the class: the default instance's, e.g. a control)
        if type(cls)._forwards(cls, name):
            return getattr(cls._vp_default_instance(), name)
        raise AttributeError(f"type object {cls.__name__!r} has no attribute {name!r}")

    def __setattr__(cls, name, value):
        if type(cls)._forwards(cls, name):
            found = next((c.__dict__[name] for c in cls.__mro__ if name in c.__dict__), None)
            default = type.__getattribute__(cls, "__dict__").get("_vp_default")
            if isinstance(found, property) or (default is not None and
                                               name in default.__dict__):
                setattr(cls._vp_default_instance(), name, value)
                return
        type.__setattr__(cls, name, value)


class Form(Drawing, PropertyHost, metaclass=_FormType):
    _vp_base = True  # (Form itself: its names are its own, never a default instance's)
    TypeName = "Form"
    DefaultEvent = "Load"
    Events = ("Load", "QueryUnload", "Unload", "Initialize", "Activate", "Deactivate", "Resize",
              "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp",
              "KeyDown", "KeyPress", "KeyUp", "DragDrop", "DragOver", "OLEDragDrop",
              "OLEDragOver", "Paint", "ColorSchemeChanged")
    Properties = (
        P("Caption", "str", "", always=True,
          description="The window title; defaults to the form's class name"),
        P("Width", "int", 480, always=True, description="Client area width in pixels"),
        P("Height", "int", 360, always=True, description="Client area height in pixels"),
        P("Left", "int", 0, description="Screen position; used with StartUpPosition Manual"),
        P("Top", "int", 0, description="Screen position; used with StartUpPosition Manual"),
        P("MDIChild", "bool", False,
          description="An MDI child form: shown inside the project's MDIForm"),
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
        P("NegotiateMenus", "bool", True,
          description="The menus of forms shown in this one (ShowIn) join its menu bar while "
                      "they are visible, placed by their NegotiatePosition"),
        P("ColorScheme", "enum", 0,
          enum_choices("Project Default", "System", "Light", "Dark", "IDE"),
          description="Light or dark appearance. Project Default uses the project's "
                      "color scheme; System follows the operating system; IDE follows "
                      "the VP6 IDE's light/dark setting (System when run on its own)."),
        P("BackColor", "color", None, description="Background color; unset = the default"),
        P("ForeColor", "color", None, description="Text color; unset = the default"),
        *_FONT,
        *DRAWING_PROPERTIES,
        P("Picture", "file", "",
          description="A picture on the form's background, at its top left (a file relative "
                      "to the form's folder)"),
        P("Enabled", "bool", True, description="Whether the form responds to the user"),
        P("MousePointer", "enum", 0, POINTER_CHOICES,
          description="The mouse pointer's shape over the form (Custom: its MouseIcon)"),
        P("MouseIcon", "file", "", description="The pointer's picture when MousePointer is Custom"),
        P("OLEDropMode", "enum", 0, enum_choices("None", "Manual"),
          description="Manual: text and files dropped from other programs fire OLEDragOver and "
                      "OLEDragDrop"),
        P("Icon", "file", "",
          description="The window's icon: an image file (relative to the form's folder); "
                      "unset = the program's icon"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    # The IDE designer instantiates a subclass with this set to True.
    _design_mode = False
    # Forms that are not the program's own (the designer's, a user control's surface)
    # have no default instance
    _vp_no_default = False

    @classmethod
    def _vp_default_instance(cls) -> "Form":
        """The form's default instance (VB's), made the first time it is needed."""
        default = type.__getattribute__(cls, "__dict__").get("_vp_default")
        if default is None:
            default = cls()
            type.__setattr__(cls, "_vp_default", default)
        return default

    def __init__(self):
        ensure_app()
        d = self.__dict__
        d["_values"] = {}
        d["_controls"] = []
        d["_loaded"] = False
        d["_shown_once"] = False
        d["_modal_loop"] = None
        d["_scheme_forced"] = False  # a forced light/dark scheme: drawn with Fusion
        d["_menubar"] = None  # created with the first Menu
        d["_client"] = None  # the controls' area when the menu bar is in the window
        d["_menu_height"] = 0  # height of a menu bar in the window
        d["_container"] = None  # the control (or form) it is shown in, see ShowIn
        d["_fill"] = True  # shown in a container: fill it
        d["_watcher"] = None
        d["_embedded"] = []  # the forms shown in this form (or its containers)
        d["_active_in_container"] = False  # shown in its container: Activate fired
        d["_merged_forms"] = []  # forms in it whose menus are on its menu bar (in order)
        d["_native_menu_bar"] = False  # a menu bar of the system's (macOS) as a window
        d["_free_area"] = (0, 0, 480, 360)  # the client area the docked panes leave
        d["_widget"] = _FormWidget(self)
        self._widget.resize(480, 360)
        self._init_values({"Caption": type(self).__name__})
        initialize = getattr(self, "InitializeComponent", None)
        if initialize is not None:
            initialize()
        for control in self._controls:  # Images from ImageLists created after their users
            refresh = getattr(control, "_refresh_images", None)
            if refresh is not None:
                refresh()
            named = getattr(control, "_named", None)  # (the controls have their names now)
            if named is not None:
                named()
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

    def _fill_widget(self) -> QWidget:
        return self._container_widget()

    def _drawing_surface(self) -> QWidget:  # (the graphics methods draw on its client area)
        return self._container_widget()

    def _handles_paint(self) -> bool:
        return getattr(self, "Form_Paint", None) is not None

    def _fill_rect(self, designed) -> QRect:
        return self._container_widget().contentsRect()

    # -- menus ---------------------------------------------------------------------------------
    def _menu_container(self):
        return self._menubar

    def _ensure_menu_bar(self) -> QMenuBar:
        """The form's menu bar, created with its first menu (or the first menus
        another form negotiates into it)."""
        if self._menubar is None:
            bar = QMenuBar(self._widget)
            self.__dict__.update(_menubar=bar, _native_menu_bar=bar.isNativeMenuBar())
            self._style_widget(bar)
            if self._container is not None or self._values.get("MDIChild"):
                bar.setNativeMenuBar(False)  # in a container or MDI: never the system's
                bar.hide()  # (its menus are on its window's, or MDI form's, menu bar)
            elif not bar.isNativeMenuBar():  # macOS: the system menu bar, no room needed
                self._make_client()
        return self._menubar

    def _add_menu_item(self, menu) -> None:
        """A top-level Menu: on the menu bar (created with the first one)."""
        self._ensure_menu_bar()
        self._widget.addAction(menu._action)  # its shortcuts work in the window
        window = self._menu_window()
        if window is not self:
            self._menubar.addAction(menu._action)
            if self in window._merged_forms:
                window._update_menu_bar()
        elif self._merged_forms:
            self._update_menu_bar()  # keeps the merged menus in place
        else:
            self._menubar.addAction(menu._action)
        self._layout_menu_bar()

    # -- menu negotiation: the menus of forms shown in this one -------------------------------------
    def _top_menus(self) -> list:
        return [c for c in self._controls
                if c.TypeName == "Menu" and c.Parent is self and c._action is not None]

    def _menu_window(self) -> "Form":
        """The form whose window this one is in (itself, unless in a container)."""
        form = self
        while form._container is not None:
            container = form._container
            form = container if isinstance(container, Form) else container._owner_form()
        return form.__dict__.get("_mdi_parent") or form  # (an MDI child: its MDI form's)

    def _negotiate(self, visible: bool) -> None:
        """A form in a container became visible or hidden there: its menus join
        or leave its window's menu bar."""
        window = self._menu_window()
        if window is self:
            return
        merged = window._merged_forms
        if visible and self not in merged:
            merged.append(self)
        elif not visible and self in merged:
            merged.remove(self)
        else:
            return
        window._update_menu_bar()

    def _update_menu_bar(self) -> None:
        """This window's menu bar: its own menus, and the menus of the forms
        shown in it, placed by their NegotiatePosition: Left before its menus,
        Middle after its first menu, Right after its menus but before those
        of its own menus whose NegotiatePosition is Right (e.g. Help)."""
        own = self._top_menus()
        guests = {1: [], 2: [], 3: []}
        if self.NegotiateMenus:
            for form in self._merged_forms:
                for menu in form._top_menus():
                    position = menu._values.get("NegotiatePosition", 0)
                    if position in guests:
                        guests[position].append(menu)
        if self._menubar is None and not any(guests.values()):
            return
        main = [m for m in own if m._values.get("NegotiatePosition", 0) != 3]
        last = [m for m in own if m._values.get("NegotiatePosition", 0) == 3]
        order = guests[1] + main[:1] + guests[2] + main[1:] + guests[3] + last
        bar = self._ensure_menu_bar()
        for action in bar.actions():
            bar.removeAction(action)
        for menu in order:
            bar.addAction(menu._action)
        self._layout_menu_bar()

    def _apply_NegotiateMenus(self, v):
        if self._merged_forms:
            self._update_menu_bar()

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
        if self._menubar is not None and (self._container is not None or
                                          self._values.get("MDIChild")):
            self._menubar.hide()  # in a container: its menus are on its window's bar
        if self._client is None:
            return
        widget = self._widget
        embedded = self._container is not None  # its menus are on its window's bar
        self._menubar.setVisible(not embedded)
        height = 0 if embedded else self._menubar.heightForWidth(widget.width())
        if height <= 0 and not embedded:
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
        width (Left, Right). Then Fill ones take all the space left. Hidden
        ones take no space (at run time)."""
        area = self._container_widget().rect()
        left, top, right, bottom = 0, 0, area.width(), area.height()
        places = []  # (widget, rect): computed first, applied below
        fills = []  # Align = Fill: the space the others leave, after them
        for control in self._controls:
            align = control._values.get("Align", 0) if "Align" in control._specs else 0
            widget = control._widget
            if not align or widget is None or control.Parent is not self or \
                    control.__dict__.get("_floating"):  # (a DockPanel in its own window)
                continue
            if not self._design_mode and not control._values.get("Visible", True):
                continue
            if align == 5:  # Fill
                fills.append(widget)
                continue
            width, height = max(right - left, 0), max(bottom - top, 0)
            # Its thickness: the Height (Top, Bottom) or Width (Left, Right) it was given
            thick_h = control._values.get("Height", widget.height())
            thick_w = control._values.get("Width", widget.width())
            if align == 1:  # Top
                size = min(thick_h, height)
                places.append((widget, QRect(left, top, width, size)))
                top += size
            elif align == 2:  # Bottom
                size = min(thick_h, height)
                places.append((widget, QRect(left, bottom - size, width, size)))
                bottom -= size
            elif align == 3:  # Left
                size = min(thick_w, width)
                places.append((widget, QRect(left, top, size, height)))
                left += size
            elif align == 4:  # Right
                size = min(thick_w, width)
                places.append((widget, QRect(right - size, top, size, height)))
                right -= size
        rest = QRect(left, top, max(right - left, 0), max(bottom - top, 0))
        places += [(widget, rest) for widget in fills]
        self.__dict__["_free_area"] = (left, top, right, bottom)  # what the edge panes left
        # Moves first, resizes last: a pane's Resize handler then sees every
        # pane (e.g. the Splitter beside it) already in its new place
        places.sort(key=lambda place: place[0].size() != place[1].size())
        for widget, rect in places:
            widget.setGeometry(rect)

    # -- dock panels ------------------------------------------------------------------------------
    def _dock_panels(self) -> list:
        return [c for c in self._controls if c.TypeName == "DockPanel" and c.Parent is self]

    @staticmethod
    def _dock_key(panel) -> str:
        return panel._name if panel._index is None else f"{panel._name}({panel._index})"

    @property
    def DockLayout(self) -> str:
        """Where the form's DockPanels are: each one's edge, size, place among
        the others, floating window and visibility, as text (JSON). Keep it
        (e.g. in a file) and set it again to put them back."""
        panels = []
        for panel in self._dock_panels():
            rect = panel._float_geometry()
            panels.append({
                "name": self._dock_key(panel), "align": panel._values.get("Align", 3),
                "width": panel._values.get("Width"), "height": panel._values.get("Height"),
                "floating": bool(panel._floating),
                "float": [rect.x(), rect.y(), rect.width(), rect.height()] if rect else None,
                "visible": bool(panel._values.get("Visible", True)),
            })
        return json.dumps({"dock_panels": panels})

    @DockLayout.setter
    def DockLayout(self, value) -> None:
        try:
            entries = json.loads(value)["dock_panels"] if value else []
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Form {type(self).__name__}: not a DockLayout ({exc})") from None
        panels = {self._dock_key(p): p for p in self._dock_panels()}
        ordered = [panels[e["name"]] for e in entries if e.get("name") in panels]
        # Their order (each edge's panels from the outside in): in the same slots
        slots = [i for i, c in enumerate(self._controls) if c in ordered]
        for slot, panel in zip(slots, ordered):
            self._controls[slot] = panel
        for entry in entries:
            panel = panels.get(entry.get("name"))
            if panel is None:
                continue
            if entry.get("float"):
                panel.FloatMove(*entry["float"])
            panel.Align = int(entry.get("align", 3))  # (floating: where it docks back to)
            panel.Floating = bool(entry.get("floating"))
            for name in ("width", "height"):
                if entry.get(name):
                    setattr(panel, name.title(), int(entry[name]))
            panel.Visible = bool(entry.get("visible", True))
        self._layout_aligned()

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
        scheme = self._effective_scheme()
        if scheme == appearance.vpSchemeSystem and self._container is not None:
            return self._menu_window()._is_dark()  # (shown in a form: it looks like it)
        return appearance.is_dark(scheme)

    def _render_scheme(self) -> int:
        """The scheme used to draw the form (the designer may force System)."""
        return self._effective_scheme()

    @property
    def _scheme_style(self):
        """Fusion for a forced light/dark scheme, None = native. (Fetched each
        time, never kept: see appearance.fusion_style.)"""
        return appearance.fusion_style() if self._scheme_forced else None

    def _apply_ColorScheme(self, _=None):
        self.__dict__["_scheme_forced"] = self._render_scheme() != appearance.vpSchemeSystem
        appearance.style_tree(self._widget, self._scheme_style)
        self._apply_colors()
        self._dark_changed()

    @property
    def DarkMode(self) -> bool:
        """Whether the form is light or dark now: its ColorScheme as it applies
        (System: the OS appearance, which Screen.DarkMode tells)."""
        return self._is_dark()

    def _appearance_changed(self) -> None:
        """The OS switched between light and dark, or the IDE's scheme changed:
        draw the form again with its scheme (a forced one may have changed: IDE),
        and tell it (ColorSchemeChanged) if it is now the other way."""
        if self._render_scheme() != appearance.vpSchemeSystem or self._scheme_forced:
            self._apply_ColorScheme()
        else:
            self._dark_changed()
        self._widget.update()

    def _dark_changed(self) -> None:
        """Fire ColorSchemeChanged(Dark) when the form turned light or dark."""
        dark = self._is_dark()
        before = self.__dict__.get("_was_dark")
        self.__dict__["_was_dark"] = dark
        if before is not None and before != dark and self._loaded:
            self._fire("ColorSchemeChanged", dark)
        for form in self.__dict__.get("_embedded", ()):  # (forms shown in it look like it)
            form._dark_changed()

    def _style_widget(self, widget: QWidget) -> None:
        if self._scheme_style is not None:
            appearance.style_tree(widget, self._scheme_style)

    def _register_control(self, control: Control) -> None:
        self._controls.append(control)
        if control._values.get("Align"):  # e.g. an aligned PictureBox created in code
            self._layout_aligned()
        if control.TypeName == "Menu" and control.Parent is self and self._container is not None:
            window = self._menu_window()  # a menu added in code to a form shown in another
            if self in window._merged_forms:
                window._update_menu_bar()

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
        if self._container is not None or self.__dict__.get("_mdi_sub") is not None:
            return  # shown in a container or an MDI form: not a window
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
        if self._design_mode or self._container is not None or \
                self.__dict__.get("_mdi_sub") is not None:
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
            owner_widget = owner._widget if isinstance(owner, Form) else \
                QApplication.activeWindow()
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

    def _apply_MousePointer(self, v):
        cursor = pointer_cursor(self._values.get("MousePointer", 0),
                                picture_pixmap(self, self._values.get("MouseIcon", "")))
        if cursor is None:
            self._widget.unsetCursor()
        else:
            self._widget.setCursor(cursor)

    _apply_MouseIcon = _apply_MousePointer

    def _apply_Icon(self, v):
        # (none, or a file that can't be read: the program's icon)
        pixmap = picture_pixmap(self, v)  # (a file, or a Picture)
        self._widget.setWindowIcon(QIcon(pixmap) if not pixmap.isNull() else QIcon())

    def _apply_Picture(self, v):
        """A picture on the form's background, at the top left (under the
        drawing and the controls)."""
        pixmap = picture_pixmap(self, v)
        self.__dict__["_background"] = None if pixmap.isNull() else pixmap
        self._drawing_surface().update()

    def _background_picture(self):
        return self.__dict__.get("_background")

    def _read_Width(self):
        return self._widget.width()

    def _read_Height(self):
        return self._widget.height() - self._menu_height

    def _apply_Width(self, v):
        self._widget.setMinimumSize(0, 0)
        self._widget.setMaximumSize(16777215, 16777215)
        self._widget.resize(max(v, 1), self._widget.height())
        self._fit_mdi_sub()
        if self._shown_once:
            self._apply_fixed_size()

    def _apply_Height(self, v):
        self._widget.setMinimumSize(0, 0)
        self._widget.setMaximumSize(16777215, 16777215)
        self._widget.resize(self._widget.width(), max(v, 1) + self._menu_height)
        self._fit_mdi_sub()
        if self._shown_once:
            self._apply_fixed_size()

    def _frame(self) -> QWidget:
        """What Left and Top move: the window, or an MDI child's subwindow."""
        return self.__dict__.get("_mdi_sub") or self._widget

    def _read_Left(self):
        return self._frame().x() if self._shown_once else self._values.get("Left", 0)

    def _read_Top(self):
        return self._frame().y() if self._shown_once else self._values.get("Top", 0)

    def _apply_Left(self, v):
        if self._shown_once:
            self._frame().move(v, self._frame().y())

    def _apply_Top(self, v):
        if self._shown_once:
            self._frame().move(self._frame().x(), v)

    def _fit_mdi_sub(self) -> None:
        """An MDI child resized: its subwindow fits it (Width, Height: its inside)."""
        sub = self.__dict__.get("_mdi_sub")
        if sub is not None and sub.widget() is not None:
            from .mdi import _framed

            sub.resize(_framed(sub, self._widget.size()))

    def _apply_WindowState(self, v):
        sub = self.__dict__.get("_mdi_sub")
        if sub is not None:  # an MDI child: its subwindow
            {1: sub.showMinimized, 2: sub.showMaximized}.get(v, sub.showNormal)()
            return
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
            if self._values.get("MDIChild") and not self._design_mode and self._loaded and \
                    not self.__dict__.get("_showing"):  # (Load of an MDI child: shown too)
                from .mdi import mdi_form_for

                if mdi_form_for(self).AutoShowChildren:
                    self.Show()

    def Show(self, Modal: int = 0, OwnerForm: "Form | None" = None) -> None:
        self.__dict__["_showing"] = True
        try:
            self.Load()
        finally:
            self.__dict__["_showing"] = False
        if not self._loaded:  # Form_Load unloaded the form
            return
        if self._values.get("MDIChild") and not self._design_mode:
            if Modal:
                raise RuntimeError(f"'{type(self).__name__}' is an MDI child form: it can't "
                                   "be shown modally")
            from .mdi import show_child

            show_child(self)  # (in the MDI form's workspace)
            return
        if self.__dict__.pop("_popup", False):  # (shown as a popup before: a window again)
            self.__dict__["_shown_once"] = False
            self._widget.setAttribute(Qt.WA_ShowWithoutActivating, False)
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
        sub = self.__dict__.get("_mdi_sub")
        if sub is not None:  # (an MDI child: its subwindow)
            sub.hide()
        self._widget.hide()

    def ShowPopup(self, X=None, Y=None, Owner: "Form | None" = None) -> None:
        """Show the form as a popup: borderless, on top, without taking the focus
        from the form that opened it (e.g. a list of choices under a TextBox
        that keeps the typing). X, Y: in the owner's client area (default: the
        active form), or on the screen without one; left out: at the mouse. It
        hides when the program goes to the background, or with Hide."""
        self.Load()
        if not self._loaded:
            return
        if Owner is None:
            Owner = getattr(QApplication.activeWindow(), "_vp_form", None)
        widget = self._widget
        widget.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                              Qt.WindowDoesNotAcceptFocus)
        widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if X is None or Y is None:
            position = QCursor.pos()
        elif Owner is not None:
            position = Owner._container_widget().mapToGlobal(QPoint(int(X), int(Y)))
        else:
            position = QPoint(int(X), int(Y))
        widget.move(position)
        self.__dict__.update(_popup=True, _shown_once=True)
        if not self.__dict__.get("_popup_watch"):
            QGuiApplication.instance().applicationStateChanged.connect(
                widget._on_application_state)
            self.__dict__["_popup_watch"] = True
        widget.show()
        widget.raise_()

    def _mdi_sub_visible(self) -> bool:
        sub = self.__dict__.get("_mdi_sub")
        return sub is not None and sub.isVisible()

    def Unload(self) -> bool:
        """Close the form. Returns False if Form_QueryUnload or Form_Unload
        cancelled it."""
        sub = self.__dict__.get("_mdi_sub")
        if sub is not None and sub.isVisible():  # (an MDI child: its subwindow closes)
            self.__dict__["_unload_mode"] = VP_FORM_CODE
            return sub.close()
        if self._widget.isVisible():
            self.__dict__["_unload_mode"] = VP_FORM_CODE
            return self._widget.close()
        return self._query_unload(mode=VP_FORM_CODE)

    def _query_unload(self, force: bool = False, mode: int = VP_FORM_CODE) -> bool:
        """Fire Form_QueryUnload(UnloadMode), then Form_Unload (each can cancel,
        unless ``force``), then unload the forms shown in this one."""
        if self._loaded and self._fire("QueryUnload", mode) and not force:  # True -> Cancel
            return False
        return self._finish_unload(force)

    def _finish_unload(self, force: bool = False) -> bool:
        """Form_Unload (it can cancel, unless ``force``), then the unloading."""
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
            form._query_unload(force=True, mode=VP_FORM_OWNER)
            form._widget.hide()
            form._leave_container()
        if self.__dict__.get("_mdi_parent") is not None:  # out of its MDI form's workspace
            from .mdi import after_unload

            after_unload(self)
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
        if Fill:  # it replaces the other forms filling that container
            for other in list(host._embedded):
                if other is not self and other._container is Container and other._fill and \
                        other._widget.isVisible():
                    other.Hide()
        self.Show()

    def _embedded_visibility(self, shown: bool) -> None:
        """A form in a container gets Activate when it becomes visible there
        (also when its container is shown) and Deactivate when it stops being
        visible (hidden, its container hidden); once each way, and only while
        loaded."""
        if self._container is None or self._design_mode:
            return
        shown = shown and self._widget.isVisible()
        if shown == self._active_in_container or (shown and not self._loaded):
            return
        self._negotiate(shown)  # its menus join or leave the window's menu bar
        self.__dict__["_active_in_container"] = shown
        if self._loaded:
            self._fire("Activate" if shown else "Deactivate")

    def _hosts(self, form: "Form") -> bool:
        """Whether ``form`` is shown in this one, directly or not."""
        return any(child is form or child._hosts(form) for child in self._embedded)

    def _enter_container(self, container, host: "Form") -> None:
        widget, parent = self._widget, container._container_widget()
        visible = widget.isVisible()
        follows = container._fill_widget()  # e.g. a scrolling PictureBox's visible area
        watcher = _ContainerWatcher(self, follows)
        follows.installEventFilter(watcher)
        # In its container before being shown there, so that counts as Activate
        self.__dict__.update(_container=container, _watcher=watcher)
        host._embedded.append(self)
        if self._menubar is not None:  # its menus go on its window's menu bar
            self._menubar.setNativeMenuBar(False)
            self._layout_menu_bar()
        widget.setParent(parent, Qt.Widget)  # a child widget, no longer a window
        self.__dict__["_was_dark"] = self._is_dark()  # (it looks like its host now)
        if visible:
            widget.show()

    def _leave_container(self) -> None:
        """Back to a window of its own (hidden until shown)."""
        container = self._container
        if container is None:
            return
        host = container if isinstance(container, Form) else container._owner_form()
        if self in host._embedded:
            host._embedded.remove(self)
        if self._active_in_container:  # leaving: deactivated there first
            self._negotiate(False)
            self.__dict__["_active_in_container"] = False
            if self._loaded:
                self._fire("Deactivate")
        watcher = self._watcher
        if watcher is not None:
            watcher.parent().removeEventFilter(watcher)
            watcher.deleteLater()
        self.__dict__.update(_container=None, _watcher=None, _shown_once=False)
        self.__dict__["_was_dark"] = self._is_dark()  # (its own look again)
        self._widget.hide()
        self._widget.setParent(None, Qt.Window)
        bar = self._menubar
        if bar is not None:  # a window again: its own menu bar is back
            bar.setNativeMenuBar(self._native_menu_bar)
            bar.show()
            if not self._native_menu_bar and self._client is None:
                self._make_client()
            self._layout_menu_bar()

    def _fit_to_container(self) -> None:
        if self._container is None:
            return
        if self._fill:  # its own (designed) size matters in a scrolling PictureBox
            designed = QSize(self._values.get("Width", 480), self._values.get("Height", 360))
            self._widget.setGeometry(self._container._fill_rect(designed))
        else:
            self._widget.move(self._values.get("Left", 0), self._values.get("Top", 0))

    @property
    def ActiveControl(self):
        """The form's control with the focus (a control on a user control's
        surface: the user control), or None if the focus is elsewhere."""
        widget = QApplication.focusWidget()
        while widget is not None:
            control = getattr(widget, "_vp_control", None)
            if control is not None and control._form is self:
                return control
            if getattr(widget, "_vp_form", None) not in (None, self):
                return None  # (in another form shown in this one: its own)
            widget = widget.parentWidget()
        return None

    def PopupMenu(self, Menu: MenuControl, Flags: int = 0, X: int | None = None,
                  Y: int | None = None,
                  DefaultMenu: MenuControl | None = None) -> MenuControl | None:
        """Show a menu's items as a context menu, e.g. in a MouseUp handler for
        the right button (VB's PopupMenu). The menu is one of the form's, often
        a menu-bar menu made invisible in the Menu Editor so it is only a
        popup. At X, Y (in the form; the mouse's position for what is left
        out); Flags: vpPopupMenuLeftAlign (its left edge there),
        vpPopupMenuCenterAlign, vpPopupMenuRightAlign. DefaultMenu is shown in
        bold. It waits until the menu closes (the chosen item's Click has
        fired by then) and returns the chosen item, or None."""
        if not isinstance(Menu, MenuControl):
            raise TypeError(f"PopupMenu: {Menu!r} is not a Menu")
        submenu = Menu._submenu
        if self._design_mode:
            return None
        if submenu is None:
            raise ValueError(f"PopupMenu: menu '{Menu.Name}' has no items")
        area = self._container_widget()
        mouse = area.mapFromGlobal(QCursor.pos())
        point = area.mapToGlobal(QPoint(int(mouse.x() if X is None else X),
                                        int(mouse.y() if Y is None else Y)))
        width = submenu.sizeHint().width()
        align = int(Flags) & 12  # (2 and 0: which button may choose: both always can)
        if align == 4:
            point -= QPoint(width // 2, 0)
        elif align == 8:
            point -= QPoint(width, 0)
        submenu.setDefaultAction(DefaultMenu._action if DefaultMenu is not None else None)
        self.__dict__["_popup_chosen"] = None  # (set by the chosen item: Menu._on_triggered)
        try:
            submenu.exec(point)
        finally:
            submenu.setDefaultAction(None)
        return self.__dict__.pop("_popup_chosen", None)

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
    # A class: its default instance (Form1 in other code is the running form)
    instance = form._vp_default_instance() if isinstance(form, type) else form
    instance.Show()
    return run_event_loop()


__all__ = ["Form", "Forms", "Load", "Unload", "run"]
