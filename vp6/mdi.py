"""MDI forms, as VB's: an ``MDIForm`` is a window whose client area is a
workspace for its child forms, the forms with ``MDIChild = True``.

* Showing a child shows it in the workspace (a ``QMdiSubWindow``), loading
  and showing the MDI form first if needed (the project's ``MDIForm``
  subclass, by its default instance). Loading a child shows it too while the
  MDI form's ``AutoShowChildren`` is True (the default).
* Controls aligned to the MDI form's edges (toolbars, status bars, docked
  PictureBoxes) stay around the workspace, which fills the rest.
* ``ActiveForm`` is the active child; ``Arrange(vpCascade / vpTileHorizontal
  / vpTileVertical / vpArrangeIcons)`` arranges the children. A child's
  Activate and Deactivate fire as it becomes the active child or stops.
* While the active child has menus, they replace the MDI form's on its menu
  bar (as in VB); a Menu whose ``WindowList`` is True lists the children
  (checking the active one), to activate one.
* Its event handlers are ``MDIForm_Load``, ``MDIForm_QueryUnload`` and so on,
  as in VB (``Form_...`` names work too).
* Unloading the MDI form unloads its children first: each one's
  QueryUnload (UnloadMode ``vpFormMDIForm``) and Unload can cancel it.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QPalette
from PySide6.QtWidgets import QApplication, QMdiArea, QMdiSubWindow

from . import colors
from ._props import P
from .form import VP_FORM_CODE, Form, _loaded_forms

VP_FORM_MDI_FORM = 4  # Form_QueryUnload's UnloadMode: its MDI form is closing
VP_CASCADE, VP_TILE_HORIZONTAL, VP_TILE_VERTICAL, VP_ARRANGE_ICONS = 0, 1, 2, 3

# Form properties an MDI form doesn't have (as VB's): it is always a sizable window,
# its client area is the workspace (no drawing, no font, no keys of its own)
_NOT_ON_MDI = {"MDIChild", "BorderStyle", "ControlBox", "MinButton", "MaxButton",
               "KeyPreview", "ForeColor", "FontName", "FontSize", "FontBold", "FontItalic",
               "FontUnderline", "AutoRedraw", "DrawWidth", "DrawStyle", "FillStyle",
               "FillColor", "NegotiateMenus"}


class MDIForm(Form):
    """A window for MDI child forms (the module's documentation)."""

    _vp_base = True  # (MDIForm itself has no default instance: a project's has)
    TypeName = "MDIForm"
    Properties = tuple(spec for spec in Form.Properties if spec.name not in _NOT_ON_MDI) + (
        P("AutoShowChildren", "bool", True,
          description="Loading a child form (Load) shows it too"),
        P("ScrollBars", "bool", True,
          description="Scroll bars when child forms reach beyond the workspace"),
    )
    # (what the left-out properties are on an MDI form)
    MDIChild = False
    BorderStyle, ControlBox, MinButton, MaxButton = 2, True, True, True
    KeyPreview, NegotiateMenus = False, True
    ForeColor = FontName = FontSize = FillColor = None
    FontBold = FontItalic = FontUnderline = AutoRedraw = False
    DrawWidth, DrawStyle, FillStyle = 1, 0, 1

    def __init__(self):
        self.__dict__["_mdi_children"] = []
        self.__dict__["_active_child"] = None
        super().__init__()

    def _fire(self, event: str, *args):
        """Its handlers are MDIForm_Load and so on, as in VB (Form_Load works too)."""
        if self._design_mode:
            return None
        handler = getattr(self, f"MDIForm_{event}", None)
        if handler is None:
            return super()._fire(event, *args)
        from .app import call_handler

        return call_handler(handler, *args)

    # -- the workspace -------------------------------------------------------------------------
    def _workspace(self) -> QMdiArea:
        area = self.__dict__.get("_area")
        if area is None:
            area = QMdiArea(self._container_widget())
            area.subWindowActivated.connect(self._on_child_activated)
            self.__dict__["_area"] = area
            area.show()
            self._apply_workspace_look()
            self._apply_ScrollBars(self._values.get("ScrollBars", True))
        return area

    def _layout_aligned(self) -> None:
        super()._layout_aligned()  # the aligned controls first: the workspace is what's left
        area = self._workspace()
        if area.parent() is not self._container_widget():  # (a menu bar made a client area)
            area.setParent(self._container_widget())
            area.show()
        left, top, right, bottom = self._free_area
        area.setGeometry(QRect(left, top, max(right - left, 0), max(bottom - top, 0)))

    def _apply_workspace_look(self) -> None:
        area = self.__dict__.get("_area")
        if area is None:
            return
        picture = self._background_picture()
        back = self._values.get("BackColor")
        if picture is not None:
            area.setBackground(QBrush(picture))
        elif back is not None:
            area.setBackground(QBrush(colors.to_qcolor(back)))
        else:  # VB's application workspace color
            area.setBackground(QBrush(area.palette().color(QPalette.Dark)))

    def _apply_colors(self, _=None):
        super()._apply_colors()
        self._apply_workspace_look()

    _apply_BackColor = _apply_colors

    def _apply_Picture(self, v):
        super()._apply_Picture(v)  # (the picture: the workspace's background)
        self._apply_workspace_look()

    def _apply_ScrollBars(self, v):
        area = self.__dict__.get("_area")
        if area is not None:
            policy = Qt.ScrollBarAsNeeded if v else Qt.ScrollBarAlwaysOff
            area.setHorizontalScrollBarPolicy(policy)
            area.setVerticalScrollBarPolicy(policy)

    def _apply_window_flags(self) -> None:  # (always a sizable window)
        if self._container is not None:
            return
        self._widget.setWindowFlags(Qt.Window)

    def _apply_fixed_size(self) -> None:
        pass

    # -- the children ----------------------------------------------------------------------------
    @property
    def ActiveForm(self):
        """The active MDI child form, or None."""
        child = self._active_child
        return child if child in self._mdi_children else None

    def _show_child(self, child: Form) -> None:
        area = self._workspace()
        sub = child.__dict__.get("_mdi_sub")
        if sub is None:
            size = QSize(child._widget.width(), child._widget.height())
            sub = QMdiSubWindow()
            sub.setWidget(child._widget)
            icon = child._widget.windowIcon()  # (its Icon, else the program's)
            sub.setWindowIcon(icon if not icon.isNull() else QApplication.windowIcon())
            area.addSubWindow(sub)
            child.__dict__.update(_mdi_sub=sub, _mdi_parent=self, _shown_once=True)
            self._mdi_children.append(child)
            sub.show()
            sub.resize(_framed(sub, size))
            if child.StartUpPosition == 0:  # Manual: where Left and Top say
                sub.move(child._values.get("Left", 0), child._values.get("Top", 0))
        state = child.WindowState
        if state == 2:
            sub.showMaximized()
        elif state == 1:
            sub.showMinimized()
        else:
            sub.show()
        area.setActiveSubWindow(sub)
        self._update_menu_bar()

    def _remove_child(self, child: Form) -> None:
        """An unloaded child leaves the workspace (it can be shown again)."""
        sub = child.__dict__.get("_mdi_sub")
        if sub is None:
            return
        area = self.__dict__.get("_area")
        sub.hide()
        widget = sub.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)  # (back to a window of its own: the subwindow goes)
        if area is not None:
            area.removeSubWindow(sub)
        sub.deleteLater()
        child.__dict__.update(_mdi_sub=None, _mdi_parent=None, _shown_once=False)
        if child in self._mdi_children:
            self._mdi_children.remove(child)
        if self._active_child is child:
            self.__dict__["_active_child"] = None
        self._update_menu_bar()

    def _on_child_activated(self, sub) -> None:
        if not shiboken6.isValid(self._widget):  # (its window is going: e.g. at exit)
            return
        if sub is None:  # (the workspace's window was deactivated: the child stays active)
            if self.ActiveForm is not None and self.ActiveForm._mdi_sub_visible():
                return
        child = next((c for c in self._mdi_children if c.__dict__.get("_mdi_sub") is sub), None)
        before = self.ActiveForm
        if child is before:
            return
        self.__dict__["_active_child"] = child
        if before is not None and before._loaded:
            before._fire("Deactivate")
        if child is not None and child._loaded:
            child._fire("Activate")
        self._update_menu_bar()

    def Arrange(self, Arrangement: int) -> None:
        """Arrange the child forms: vpCascade, vpTileHorizontal (one above the
        other), vpTileVertical (side by side) or vpArrangeIcons (the minimized
        ones along the bottom)."""
        area = self._workspace()
        subs = [s for s in area.subWindowList() if s.isVisible()]
        normal = [s for s in subs if not s.isMinimized()]
        arrangement = int(Arrangement)
        if arrangement == VP_CASCADE:
            area.cascadeSubWindows()
        elif arrangement in (VP_TILE_HORIZONTAL, VP_TILE_VERTICAL) and normal:
            rect = area.viewport().rect()
            count = len(normal)
            for index, sub in enumerate(normal):
                sub.showNormal()
                if arrangement == VP_TILE_HORIZONTAL:
                    height = rect.height() // count
                    sub.setGeometry(0, index * height, rect.width(), height)
                else:
                    width = rect.width() // count
                    sub.setGeometry(index * width, 0, width, rect.height())
        elif arrangement == VP_ARRANGE_ICONS:
            x = 0
            for sub in (s for s in subs if s.isMinimized()):
                sub.move(x, area.viewport().height() - sub.height())
                x += sub.width()

    def _activate_child(self, child: Form) -> None:
        sub = child.__dict__.get("_mdi_sub")
        if sub is not None:
            if sub.isMinimized():
                sub.showNormal()
            self._workspace().setActiveSubWindow(sub)

    # -- menus: the active child's replace its own ----------------------------------------------
    def _update_menu_bar(self) -> None:
        child = self.ActiveForm
        menus = child._top_menus() if child is not None else []
        if not menus:
            if self._menubar is not None:
                bar = self._menubar
                for action in bar.actions():
                    bar.removeAction(action)
                for menu in self._top_menus():
                    bar.addAction(menu._action)
                self._layout_menu_bar()
            return
        bar = self._ensure_menu_bar()
        for action in bar.actions():
            bar.removeAction(action)
        for menu in menus:
            bar.addAction(menu._action)
        self._layout_menu_bar()

    # -- closing: the children first ------------------------------------------------------------
    def _query_unload(self, force: bool = False, mode: int = VP_FORM_CODE) -> bool:
        if self._loaded and self._fire("QueryUnload", mode) and not force:
            return False
        for child in list(self._mdi_children):  # (each can cancel, unless forced)
            if child._loaded and not child._query_unload(force=force, mode=VP_FORM_MDI_FORM):
                return False
            self._remove_child(child)
        return self._finish_unload(force)


def _framed(sub: QMdiSubWindow, inside: QSize) -> QSize:
    """A subwindow's size for this inside: its border and title bar added, from its
    margins (measuring sizes fails while its MDI form isn't laid out yet, e.g. in
    MDIForm_Load)."""
    sub.ensurePolished()
    margins = sub.contentsMargins()
    return QSize(inside.width() + margins.left() + margins.right(),
                 inside.height() + margins.top() + margins.bottom())


def mdi_form_for(child: Form) -> MDIForm:
    """The MDI form an MDI child is shown in: the loaded one, else the project's
    MDIForm (its default instance), loaded and shown."""
    for form in _loaded_forms:
        if isinstance(form, MDIForm):
            return form
    classes = [cls for cls in _subclasses(MDIForm)
               if not cls.__dict__.get("_vp_no_default") and not cls._design_mode]
    if not classes:
        raise RuntimeError(f"'{type(child).__name__}' is an MDI child form (MDIChild = True): "
                           "the project needs an MDIForm to show it in")
    form = classes[-1]._vp_default_instance()
    form.Show()
    return form


def _subclasses(cls) -> list:
    found = []
    for sub in cls.__subclasses__():
        found += [sub] + _subclasses(sub)
    return found


def show_child(child: Form) -> None:
    """Show an MDI child in its MDI form (Form.Show)."""
    mdi_form_for(child)._show_child(child)


def after_unload(child: Form) -> None:
    """An MDI child was unloaded: out of the workspace once its close is over."""
    parent = child.__dict__.get("_mdi_parent")
    if parent is not None:
        QTimer.singleShot(0, lambda: parent._remove_child(child))


def window_list_actions(menu) -> list:
    """For a Menu with WindowList: (caption, checked, child) for each child form
    of its form's MDI form (its own, or the MDI form it is a child of)."""
    form = menu._form
    mdi = form if isinstance(form, MDIForm) else form.__dict__.get("_mdi_parent")
    if mdi is None:
        return []
    return [(child.Caption, child is mdi.ActiveForm, child)
            for child in mdi._mdi_children if child._mdi_sub_visible()]

