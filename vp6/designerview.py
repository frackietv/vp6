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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ._props import P
from .controls import _COMMON, CONTROL_TYPES, EVENT_ARGS, Control, _geometry, resolve_path

EVENT_ARGS.update({"ControlAdded": "Name", "ControlDeleted": "Name", "ControlMoved": "Name",
                   "ControlResized": "Name", "PropertyChanged": "Name, Property",
                   "GoToCode": "Name, Event"})

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
              "ControlResized", "PropertyChanged", "GoToCode")
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
        *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_designer=None, _before=None)
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

    def LoadForm(self, FileName) -> None:
        """Design the form in FileName (relative to the form's folder)."""
        from .ide.designer import FormDesigner
        from .ide.documents import FormDocument

        if self._design_mode:
            return
        path = resolve_path(self._form, str(FileName))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"DesignerView '{self.Name}': no form file {path}")
        old = self._designer
        designer = FormDesigner(FormDocument(path), os.path.dirname(path), self._widget)
        designer.selectionChanged.connect(lambda d=designer: d is self._designer and
                                          self._fire("SelChange"))
        designer.designChanged.connect(lambda d=designer: d is self._designer and
                                       self._changed())
        designer.viewCodeRequested.connect(
            lambda name, event, d=designer: d is self._designer and
            self._fire("GoToCode", "" if name == "Form" else name, event))
        designer.toolConsumed.connect(lambda d=designer: d is self._designer and
                                      self._tool_used())
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
        """The form's file as it is now, with the changes made here."""
        return self._need_form().document.text

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
        """A control's property as designed (Name "" is the form)."""
        designer = self._need_form()
        target = designer.form if not Name else designer.controls.get(str(Name))
        if target is None or Property not in target._specs:
            raise KeyError(f"DesignerView '{self.Name}': no {Property!r} for {Name or 'the form'}")
        return target._values.get(Property, target._specs[Property].default)

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

    def DeleteSelection(self) -> None:
        """Delete the selected controls (and what is in them)."""
        self._need_form().delete_selection()

    def Undo(self) -> None:
        self._need_form().undo()

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


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["DesignerView"] = DesignerView
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
