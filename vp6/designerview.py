"""Designing forms in a program: the ``DesignerView`` control.

A DesignerView shows a form from its file (a VP6 form, ``Form1.py``) the
way the IDE's designer does: its controls in design mode (no events of
theirs run), in the platform's window frame with its menu bar, ready to be
changed with the mouse and the keyboard: selecting (clicking, Shift/Ctrl
for more, a rubber band), grab handles to resize, moving (into and out of
containers and pages), the grid and snapping, arrow keys to nudge,
drawing a new control with ``Tool`` (the Toolbox's choice), locked
controls, and a context menu::

    self.dsgForm.FileName = "Form1.py"
    self.dsgForm.Tool = "CommandButton"                 # the next drag draws one

    def dsgForm_SelChange(self):
        self.lblSelected.Caption = ", ".join(self.dsgForm.SelectedControls) or "(form)"

    def dsgForm_ControlAdded(self, Name):
        self.lstLog.AddItem(f"added {Name}")

* ``FileName`` (or ``LoadForm(FileName)``) opens a form's file; ``Source``
  is its text with the changes, ``Save()`` writes it, ``Modified`` tells
  whether there are changes to save.
* ``SelectedControls`` (names; empty: the form), ``SelectControls(Names)``,
  ``ControlNames``, ``ControlType(Name)``; ``GetProperty(Name, Property)``
  and ``SetProperty(Property, Value)`` (on the selection) are the
  Properties window's; ``AddControl``, ``DeleteSelection``, ``Undo`` and
  ``Redo``; ``Locked`` locks the controls in place.
* Events: ``SelChange``; ``ControlAdded(Name)``, ``ControlDeleted(Name)``,
  ``ControlMoved(Name)``, ``ControlResized(Name)``, ``PropertyChanged(Name,
  Property)`` (Name "" is the form) and ``Change`` after each change (also
  undoing); ``GoToCode(Name, Event)`` when a control is double-clicked
  (its default event).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ._props import P
from .controls import _COMMON, CONTROL_TYPES, EVENT_ARGS, Control, _geometry, resolve_path
from .picture import Picture

EVENT_ARGS.update({"ControlAdded": "Name", "ControlDeleted": "Name", "ControlMoved": "Name",
                   "ControlResized": "Name", "PropertyChanged": "Name, Property",
                   "GoToCode": "Name, Event", "DrawFrame": "Frame", "PaintFrame": "Frame",
                   "FormRenamed": "OldName, NewName"})

_PLACE = ("Left", "Top")
_SIZE = ("Width", "Height")


def _snapshot(form_def) -> dict:
    """A form's definition as {key: (type, props)}, "" for the form itself."""
    controls = {c.key: (c.type, dict(c.props), c.parent) for c in form_def.controls}
    controls[""] = ("Form", dict(form_def.props), None)
    return controls


class DesignerView(Control):
    """Designs a form, as the IDE's designer (the module's documentation)."""

    TypeName = "DesignerView"
    DefaultEvent = "SelChange"
    DefaultSize = (401, 301)
    Events = ("SelChange", "Change", "ControlAdded", "ControlDeleted", "ControlMoved",
              "ControlResized", "PropertyChanged", "GoToCode", "DrawFrame", "PaintFrame",
              "FormRenamed", "DragDrop", "DragOver")
    Properties = (
        *_geometry(*DefaultSize),
        P("FileName", "file", "",
          description="The form's file being designed (relative to the form's folder)"),
        P("Tool", "str", "",
          description="The control type the next drag (or click) on the form draws; \"\" is "
                      "the pointer"),
        P("Locked", "bool", False,
          description="The controls stay where they are: the mouse and the arrow keys don't "
                      "move or resize them"),
        P("ShowGrid", "bool", True,
          description="The grid of dots on the form (controls snap to it either way)"),
        *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_designer=None, _before=None, _taken=[], _scheme=None)
        if self._design_mode:
            label = QLabel("DesignerView\n(a form is designed here at run time)", parent)
            label.setAlignment(Qt.AlignCenter)
            label.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
            return label
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        return widget

    # -- the form ----------------------------------------------------------------------------
    def _apply_FileName(self, v):
        if v and not self._design_mode:
            self.LoadForm(v)

    def LoadForm(self, FileName, Source=None) -> None:
        """Design the form in FileName (relative to the form's folder); with a
        Source, that text is the form's (e.g. one not saved yet), the file
        only saying where its pictures are."""
        from .ide.designer import FormDesigner
        from .ide.documents import FormDocument

        if self._design_mode:
            return
        path = resolve_path(self._form, str(FileName))
        if Source is None and not os.path.isfile(path):
            raise FileNotFoundError(f"DesignerView '{self.Name}': no form file {path}")
        old = self._designer
        scheme = {} if self._scheme is None else {"project_scheme": self._scheme}
        designer = FormDesigner(FormDocument(path, None if Source is None else str(Source)),
                                os.path.dirname(path), self._widget, **scheme)
        designer.form_name_taken = lambda name: name in self._taken
        # (the workspace around the form in the program's look, the grid as it says)
        designer.ide_dark = lambda: self._form is not None and self._form._is_dark()
        designer.show_grid = lambda: bool(self._values.get("ShowGrid", True))
        designer.formRenamed.connect(lambda old_name, new_name, d=designer:
                                     d is self._designer and
                                     self._fire("FormRenamed", old_name, new_name))
        designer.selectionChanged.connect(lambda d=designer: d is self._designer and
                                          self._fire("SelChange"))
        designer.designChanged.connect(lambda d=designer: d is self._designer and
                                       self._changed())
        designer.viewCodeRequested.connect(
            lambda name, event, d=designer: d is self._designer and
            self._fire("GoToCode", "" if name == "Form" else name, event))
        designer.toolConsumed.connect(lambda d=designer: d is self._designer and
                                      self._tool_used())
        designer.frame_drawer = _PictureFrame(self, designer)  # (DrawFrame, when handled)
        self._widget.layout().addWidget(designer)
        if old is not None:
            old.hide()
            old.setParent(None)
            old.deleteLater()
        self.__dict__.update(_designer=designer, _before=_snapshot(designer.form_def))
        self._values["FileName"] = str(FileName)
        designer.set_locked(bool(self._values.get("Locked")))
        self._apply_Tool(self._values.get("Tool", ""))
        designer.show()

    def _need_form(self):
        if self._designer is None:
            raise RuntimeError(f"DesignerView '{self.Name}' has no form: set its FileName")
        return self._designer

    @property
    def Source(self) -> str:
        """The form's file as it is now, with the changes made here; set it to
        another text of the form (e.g. its code edited elsewhere): the
        designer follows its designer region."""
        return self._need_form().document.text

    @Source.setter
    def Source(self, value) -> None:
        document = self._need_form().document
        text = str(value)
        if text != document.text:
            document.reload(text)
            self.__dict__["_before"] = _snapshot(self._designer.form_def)

    def Reload(self) -> None:
        """Make the form and its controls again (e.g. a user control on it
        changed), keeping the selection."""
        designer = self._need_form()
        selection = list(designer.selection)
        designer.load_def(designer.form_def)
        designer.select([key for key in selection if key in designer.controls])

    @property
    def PreferredWidth(self) -> int:
        """The width that shows the whole form, its window frame and the room for
        the selection handles around it (e.g. for the window it is in)."""
        return self._need_form().preferred_size().width()

    @property
    def PreferredHeight(self) -> int:
        return self._need_form().preferred_size().height()

    @property
    def Modified(self) -> bool:
        """Whether the form was changed since it was opened (or saved)."""
        return self._designer is not None and self._designer.document.modified

    def Save(self, FileName=None) -> None:
        """Write the form's file (to FileName, relative to the form's folder,
        when given: the view goes on with that one)."""
        designer = self._need_form()
        document = designer.document
        if FileName:
            path = resolve_path(self._form, str(FileName))
            with open(path, "w", encoding="utf-8") as file:
                file.write(document.text)
            self.LoadForm(FileName)
            return
        document.save()

    # -- the selection ------------------------------------------------------------------------
    @property
    def SelectedControls(self) -> list[str]:
        """The selected controls' names (an array's element: "cmd(2)"); an empty
        list when the form itself is selected."""
        return list(self._designer.selection) if self._designer is not None else []

    def SelectControls(self, Names=()) -> None:
        """Select these controls (a name, or a list of them); none: the form."""
        names = [Names] if isinstance(Names, str) else list(Names)
        designer = self._need_form()
        unknown = [n for n in names if n not in designer.controls]
        if unknown:
            raise KeyError(f"DesignerView '{self.Name}': no control {unknown[0]!r} on the form")
        designer.select(names)

    @property
    def ControlNames(self) -> list[str]:
        """Every control on the form (menus included), in the form file's order."""
        designer = self._need_form()
        return [c.key for c in designer.form_def.controls]

    def ControlType(self, Name) -> str:
        """A control's type ("Form" for "")."""
        if not Name:
            return "Form"
        control = self._need_form().form_def.control(str(Name))
        if control is None:
            raise KeyError(f"DesignerView '{self.Name}': no control {Name!r} on the form")
        return control.type

    # -- properties ---------------------------------------------------------------------------
    def GetProperty(self, Name, Property):
        """A control's property as designed (Name "" is the form); "Name" is
        its name (a control array's elements share it), "Index" its Index in
        an array (None: not in one)."""
        designer = self._need_form()
        if Property in ("Name", "Index"):
            if not Name:
                return designer.form_def.class_name if Property == "Name" else None
            control = designer.form_def.control(str(Name))
            if control is None:
                raise KeyError(f"DesignerView '{self.Name}': no control {Name!r} on the form")
            return control.name if Property == "Name" else control.index
        target = designer.form if not Name else designer.controls.get(str(Name))
        if target is None or Property not in target._specs:
            raise KeyError(f"DesignerView '{self.Name}': no {Property!r} for {Name or 'the form'}")
        return target._values.get(Property, target._specs[Property].default)

    def ObjectProperties(self, Name="") -> list:
        """The properties of a control (Name "" the form, or a user control's
        surface) as the Properties window lists them: PropertyInfo objects
        (Name, Kind, Default, Choices, Category, Description), by name."""
        from .metadata import PropertyInfo

        designer = self._need_form()
        target = designer.form if not Name else designer.controls.get(str(Name))
        if target is None:
            raise KeyError(f"DesignerView '{self.Name}': no control {Name!r} on the form")
        return sorted((PropertyInfo(spec) for spec in target._specs.values()),
                      key=lambda info: info.Name)

    def ObjectNames(self) -> list:
        """(name, type) of the form and every control on it, as the Properties
        window's list has them (the form first)."""
        return list(self._need_form().all_objects())

    def SupportsIndex(self, Name) -> bool:
        """Whether the control can be in a control array (an Index)."""
        designer = self._need_form()
        control = designer.controls.get(str(Name)) if Name else None
        return control is not None and designer.supports_index(control)

    def SetProperty(self, Property, Value) -> None:
        """Set a property of the selected controls (or the form), as the
        Properties window does: one step Undo takes back. A value the
        property can't take raises ValueError."""
        error = self._need_form().set_property(str(Property), Value)
        if error:
            raise ValueError(error)

    # -- changes ------------------------------------------------------------------------------
    def AddControl(self, TypeName, Left=None, Top=None, Width=None, Height=None,
                   Container: str = "") -> str:
        """Add a control (its default size where left out; in the middle of
        the form without Left and Top), selected; returns its name."""
        from PySide6.QtCore import QPoint, QRect

        designer = self._need_form()
        if TypeName not in CONTROL_TYPES:
            raise KeyError(f"DesignerView '{self.Name}': no control type {TypeName!r}")
        if Left is None or Top is None:
            designer.add_control_centered(str(TypeName))
            return designer.selection[0] if designer.selection else ""
        width, height = CONTROL_TYPES[TypeName].DefaultSize
        container = str(Container) or None
        origin = designer._container_widget(container).mapTo(designer.canvas, QPoint(0, 0))
        rect = QRect(origin.x() + int(Left), origin.y() + int(Top),
                     int(Width if Width is not None else width),
                     int(Height if Height is not None else height))
        return designer.create_control(str(TypeName), rect, container)

    def DropControl(self, TypeName, X, Y) -> str:
        """Add a control (its default size) where X, Y is in the DesignerView
        (a drop's: DragDrop's X and Y), in the container there; returns its
        name."""
        from PySide6.QtCore import QPoint, QRect

        designer = self._need_form()
        if TypeName not in CONTROL_TYPES:
            raise KeyError(f"DesignerView '{self.Name}': no control type {TypeName!r}")
        point = designer.canvas.mapFrom(self._widget, QPoint(int(X), int(Y)))
        width, height = CONTROL_TYPES[TypeName].DefaultSize
        return designer.create_control(str(TypeName), QRect(point.x(), point.y(), width, height),
                                       designer.container_at(point))

    def DeleteSelection(self) -> None:
        """Delete the selected controls (and what is in them)."""
        self._need_form().delete_selection()

    def Undo(self) -> None:
        self._need_form().undo()

    # -- the Format and Edit menus -------------------------------------------------------------
    def Align(self, How: str) -> None:
        """Align the selected controls to the last one selected: "left",
        "center", "right", "top", "middle" or "bottom"; "grid": each to the
        grid."""
        self._need_form().align(str(How))

    def MakeSameSize(self, How: str) -> None:
        """The selected controls as wide ("width"), as high ("height") or as
        large ("both") as the last one selected."""
        self._need_form().make_same_size(str(How))

    def CenterInForm(self, Horizontal: bool = True) -> None:
        """Center the selected controls in the form, across (or up and down)."""
        self._need_form().center_in_form(bool(Horizontal))

    def BringToFront(self) -> None:
        self._need_form().z_order(True)

    def SendToBack(self) -> None:
        self._need_form().z_order(False)

    def Cut(self) -> None:
        self._need_form().cut_selection()

    def Copy(self) -> None:
        """The selected controls on the clipboard (a form's region text)."""
        self._need_form().copy_selection()

    def Paste(self) -> None:
        self._need_form().paste()

    def SelectAll(self) -> None:
        self._need_form().select_all()

    # -- the menus (the Menu Editor) ------------------------------------------------------------
    def MenuEntries(self) -> list:
        """The form's menus as the Menu Editor lists them (MenuEntry objects of
        ``vp6.ide.logic.menus``: level, caption, name, index, shortcut...)."""
        return self._need_form().menu_entries()

    def SetMenus(self, Entries) -> None:
        """Replace the form's menus (one step Undo takes back); renamed menus
        take their handlers along. Entries that aren't right raise ValueError."""
        error = self._need_form().set_menus(list(Entries))
        if error:
            raise ValueError(error)

    def MenuNamesTaken(self) -> set:
        """The names the form's menus can't have (its other controls', its own)."""
        return self._need_form()._names_besides_menus()

    # -- the project around it ------------------------------------------------------------------
    @property
    def ProjectColorScheme(self):
        """The color scheme of the form's project, for a form whose ColorScheme
        is Project Default (vpSchemeSystem, vpSchemeLight...); None: the
        program's."""
        return self._scheme

    @ProjectColorScheme.setter
    def ProjectColorScheme(self, value) -> None:
        self.__dict__["_scheme"] = None if value is None else int(value)
        if self._designer is not None and value is not None:
            self._designer.set_project_scheme(int(value))

    @property
    def FormNamesTaken(self) -> list:
        """Names the form itself can't be renamed to (the project's other forms)."""
        return list(self._taken)

    @FormNamesTaken.setter
    def FormNamesTaken(self, value) -> None:
        self.__dict__["_taken"] = list(value or [])

    def Redo(self) -> None:
        self._need_form().redo()

    @property
    def CanUndo(self) -> bool:
        return self._designer is not None and bool(self._designer._undo)

    @property
    def CanRedo(self) -> bool:
        return self._designer is not None and bool(self._designer._redo)

    def _apply_Tool(self, v):
        if v and v not in CONTROL_TYPES:
            self._values["Tool"] = (self._designer.tool or "") if self._designer else ""
            raise ValueError(f"DesignerView '{self.Name}': no control type {v!r}")
        if self._designer is not None:
            self._designer.set_tool(v or None)

    def _tool_used(self) -> None:
        """A control was drawn with the Tool: the pointer again (as the Toolbox)."""
        self._values["Tool"] = ""
        self._designer.set_tool(None)

    def _apply_ShowGrid(self, v):
        designer = self._designer
        if designer is not None and designer.form is not None:
            designer.form._apply_colors()
            designer.canvas.update()

    def _apply_Locked(self, v):
        if self._designer is not None:
            self._designer.set_locked(bool(v))

    def _changed(self) -> None:
        """The designer changed the form: what changed, as events, then Change."""
        designer = self._designer
        after, before = _snapshot(designer.form_def), self._before or {}
        self.__dict__["_before"] = after
        for key in [k for k in before if k not in after]:
            self._fire("ControlDeleted", key)
        for key, (kind, props, parent) in after.items():
            if key not in before:
                self._fire("ControlAdded", key)
                continue
            old_props, old_parent = before[key][1], before[key][2]
            moved = parent != old_parent or any(props.get(p) != old_props.get(p)
                                                for p in _PLACE)
            if moved and key:
                self._fire("ControlMoved", key)
            if any(props.get(p) != old_props.get(p) for p in _SIZE):
                self._fire("ControlResized", key)
            for name in sorted(set(props) | set(old_props)):
                if name not in _PLACE + _SIZE and props.get(name) != old_props.get(name):
                    self._fire("PropertyChanged", key, name)
        self._fire("Change")


class DesignerFrame:
    """The window frame a DesignerView's DrawFrame event draws around the
    form: what the window is (read them), and the frame (set them).

    The form's window: ``Caption``, ``BorderStyle``, ``ControlBox``,
    ``MinButton``, ``MaxButton``, ``TitleDark`` (its title bar is dark),
    ``FormDark`` (the form is), ``Width`` and ``Height`` (the form's inside),
    ``MenuHeight`` (its menu bar's, drawn by the designer; 0 without one).

    The frame: ``TitleHeight`` and ``BorderWidth``; ``Margin``, room around the
    frame in the picture (for a shadow); ``CornerRadius``, the window's
    rounded bottom corners (0: square), drawn again over the form; and
    ``Picture``, the frame drawn: (Width + 2 BorderWidth + 2 Margin) x (Height
    + TitleHeight + MenuHeight + 2 BorderWidth + 2 Margin), the window's top
    left at Margin, Margin. Without a Picture, the designer draws its own.

    With a PaintFrame handler, DrawFrame sets the metrics only and PaintFrame
    draws the frame each time the designer paints it: its Frame's Picture
    then paints straight onto the designer (its graphics methods, as a form's
    Paint event's), the window's top left at Margin, Margin. ``Part`` says
    what: 0 the frame; with a CornerRadius the designer then paints the
    window's rounded bottom corners over the (square) form: 1 the shadow,
    clipped to the corners outside the window (filled with the workspace's
    color already), and 2 the window's outline, clipped to those corners and
    the form."""

    def __init__(self, info, width: int, height: int, menu_height: int):
        self.Caption = info.caption
        self.BorderStyle = info.border_style
        self.ControlBox = info.control_box
        self.MinButton = info.min_button
        self.MaxButton = info.max_button
        self.TitleDark = info.title_dark
        self.FormDark = info.form_dark
        self.Width, self.Height, self.MenuHeight = width, height, menu_height
        self.TitleHeight = self.BorderWidth = self.Margin = self.CornerRadius = 0
        self.Picture = None
        self.Part = 0  # (PaintFrame: what to paint)

    def __repr__(self):
        return f"<DesignerFrame {self.Caption!r} {self.Width} x {self.Height}>"


class _LivePicture(Picture):
    """PaintFrame's Picture: its graphics methods paint with the designer's
    painter (moved to the frame's corner), as a form's in its Paint event."""

    def __init__(self, width: int, height: int, painter):
        super().__init__(1, 1)
        self.__dict__["_live_size"] = (int(width), int(height))
        self._draw_state()["painter"] = painter

    @property
    def Width(self) -> int:
        return self._live_size[0]

    @property
    def Height(self) -> int:
        return self._live_size[1]

    def _draw_area_size(self) -> QSize:
        return QSize(*self._live_size)


class _PictureFrame:
    """The designer's frame drawer for a DesignerView: its DrawFrame event's
    picture when the form handles it (made once for each look and size),
    else the designer's own frames."""

    def __init__(self, view: DesignerView, designer):
        self.view, self.designer = view, designer
        self._frames: dict = {}

    def _handled(self) -> bool:
        form = self.view._form
        return form is not None and getattr(form, f"{self.view.Name}_DrawFrame", None) is not None

    def frame(self, info) -> DesignerFrame | None:
        if not self._handled():
            return None
        from .ide import chrome

        size = self.designer.form_widget().size()
        key = (repr(info), size.width(), size.height())
        frame = self._frames.get(key)
        if frame is None:
            if len(self._frames) > 16:
                self._frames.clear()
            frame = DesignerFrame(info, size.width(), size.height(), chrome.menu_height(info))
            self.view._fire("DrawFrame", frame)
            self._frames[key] = frame
        return frame if frame.Picture is not None or self._paints() else None

    def _paints(self) -> bool:
        form = self.view._form
        return form is not None and \
            getattr(form, f"{self.view.Name}_PaintFrame", None) is not None

    def _paint_live(self, painter, frame, corner) -> None:
        """PaintFrame: the frame painted now, straight onto the designer."""
        width = frame.Width + 2 * (int(frame.BorderWidth) + frame.Margin)
        height = frame.Height + frame.MenuHeight + int(frame.TitleHeight) + \
            2 * (int(frame.BorderWidth) + frame.Margin)
        painter.save()
        painter.translate(corner)
        live = _LivePicture(width, height, painter)
        picture, frame.Picture = frame.Picture, live
        try:
            self.view._fire("PaintFrame", frame)
        finally:
            frame.Picture = picture
            live._draw_state()["painter"] = None  # (the paint's own: not kept past it)
            painter.restore()

    def metrics(self, info) -> tuple[int, int]:
        from .ide import chrome

        frame = self.frame(info)
        if frame is None:
            return chrome.metrics(self.designer.frame_style(), info)
        return int(frame.TitleHeight), int(frame.BorderWidth)

    def _pixmap(self, frame):
        from .picture import picture_pixmap

        return picture_pixmap(self.view, frame.Picture)

    def paint(self, painter, client, info) -> None:
        from PySide6.QtCore import QPointF

        from .ide import chrome

        frame = self.frame(info)
        if frame is None:
            chrome.paint(painter, self.designer.frame_style(), client, info)
            return
        title, border = int(frame.TitleHeight), int(frame.BorderWidth)
        top = client.top() - chrome.menu_height(info) - title - border - frame.Margin
        corner = QPointF(client.left() - border - frame.Margin, top)
        if self._paints():
            self._paint_live(painter, frame, corner)
        else:
            painter.drawPixmap(corner, self._pixmap(frame))
        if info.menus:
            chrome._menu_bar(painter, client, info)

    def paint_corners(self, painter, client, info, workspace) -> None:
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QPainter, QPainterPath

        from .ide import chrome

        frame = self.frame(info)
        if frame is None:
            chrome.paint_corners(painter, self.designer.frame_style(), client, info, workspace)
            return
        radius = float(frame.CornerRadius)
        if not radius:
            return
        rect = QRectF(self.designer.frame_rect())
        strip = QPainterPath()
        strip.addRect(QRectF(rect.left(), rect.bottom() - radius, rect.width(), radius + 2))
        corners = strip.subtracted(chrome._rounded(rect, 0, radius))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipPath(corners)
        painter.fillRect(rect.adjusted(-1, -1, 1, 1), workspace)
        title, border = int(frame.TitleHeight), int(frame.BorderWidth)
        top = client.top() - chrome.menu_height(info) - title - border - frame.Margin
        corner = QPointF(client.left() - border - frame.Margin, top)
        if self._paints():  # (as the designer's own: the shadow in the corners, then the
            try:            # outline there and over the form)
                frame.Part = 1
                self._paint_live(painter, frame, corner)
                covered = QPainterPath()
                covered.addRect(QRectF(client))
                painter.setClipPath(corners.united(covered))
                frame.Part = 2
                self._paint_live(painter, frame, corner)
            finally:
                frame.Part = 0
        else:
            painter.drawPixmap(corner, self._pixmap(frame))
        painter.restore()


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["DesignerView"] = DesignerView
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
