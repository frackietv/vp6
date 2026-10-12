"""What VP6 knows about its controls, for programs: the control types, their
properties and their events, the way the IDE's Toolbox, Properties window,
Object Browser and code window see them::

    for name in ControlTypes("Common"):                 # in the Toolbox's order
        info = ControlInfo(name)
        lstTypes.AddItem(f"{info.Name} ({info.Category})")

    info = ControlInfo("TextBox")
    info.DefaultSize                                    # (97, 33)
    info.Property("MaxLength").Description              # the Properties window's text
    [e.Name for e in info.Events]                       # "Change", "Click", ...
    info.Event("KeyDown").Arguments                     # ["KeyCode", "Shift"]
    picIcon.Picture = info.Icon                         # its Toolbox icon, a Picture

* ``ControlTypes(Category)``: the names of the control types, in the
  Toolbox's order (the user controls registered last); with a Category,
  just its own. ``ControlCategories()``: the Toolbox's categories in order.
* ``ControlInfo(TypeName)``: a ``ControlTypeInfo`` (also for "Form" and
  "MDIForm"): Name, Category, Description, DefaultSize, DefaultEvent,
  IsContainer, InToolbox, Icon (a Picture, its Toolbox icon in the current
  light or dark look), Properties (``PropertyInfo``: Name, Kind, Default,
  Choices as (value, label) pairs, Category, Description), Events
  (``EventInfo``: Name, Arguments, IsDefault), and Property(name) /
  Event(name) for one of them.
"""

from __future__ import annotations

import inspect

from ._props import category_of

# The Toolbox's categories when grouped, in order, each with its tools in order; a
# control type that none of them names goes in Other (the IDE puts the project's user
# controls in User Controls)
TOOLBOX_CATEGORIES = (
    ("Common", ("Label", "TextBox", "CommandButton", "CheckBox", "OptionButton", "ComboBox",
                "ListBox", "Slider", "UpDown", "ProgressBar", "HScrollBar", "VScrollBar")),
    ("Input", ("SpinBox", "DTPicker", "MonthView", "Dial", "FontComboBox", "HotKey",
               "LCDNumber")),
    ("Buttons", ("CommandLink", "ToolButton", "ButtonBox")),
    ("Containers", ("Frame", "TabStrip", "ToolBox", "PageFrame", "ScrollPanel", "Splitter",
                    "DockPanel", "Toolbar", "StatusBar")),
    ("Graphics", ("PictureBox", "Image", "SvgImage", "Shape", "Line", "ImageList",
                  "GraphicsView", "Chart", "OpenGLView")),
    ("Lists", ("TreeView", "ListView", "ColumnView", "FlexGrid", "UndoView")),
    ("Text", ("RichTextBox", "CodeBox", "MarkdownBox")),
    ("Files", ("DriveListBox", "DirListBox", "FileListBox", "CommonDialog", "FileWatcher")),
    ("Media", ("MediaPlayer", "PdfViewer", "QuickView")),
    ("System", ("Timer", "Process", "Terminal", "Winsock")),
    ("Web", ("WebView", "WebBrowser")),
    ("Data", ("Data", "DBGrid")),
    ("Design", ("DesignerView",)),
)
OTHER = "Other"


def _types() -> dict:
    from .controls import CONTROL_TYPES

    return CONTROL_TYPES


def category_of_type(type_name: str) -> str:
    """The Toolbox category a control type is in (Other when none names it)."""
    return next((title for title, names in TOOLBOX_CATEGORIES if type_name in names), OTHER)


def ControlCategories() -> list[str]:
    """The Toolbox's categories, in order (Other last, when a type is in it)."""
    titles = [title for title, _names in TOOLBOX_CATEGORIES]
    if any(category_of_type(name) == OTHER for name, cls in _types().items()
           if cls.InToolbox):
        titles.append(OTHER)
    return titles


def ControlTypes(Category: str | None = None) -> list[str]:
    """The control types' names in the Toolbox's order: each category's in
    its own order, then the others (e.g. user controls) as registered. With
    a Category, just that category's. (Menu, made with the Menu Editor, is
    not in the Toolbox, so not here.)"""
    types = [name for name, cls in _types().items() if cls.InToolbox]
    ordered = [name for _title, names in TOOLBOX_CATEGORIES for name in names if name in types]
    ordered += [name for name in types if name not in ordered]
    if Category is None:
        return ordered
    return [name for name in ordered if category_of_type(name) == str(Category)]


class PropertyInfo:
    """A property of a control type, as the Properties window shows it."""

    def __init__(self, spec):
        self.Name = spec.name
        # str, text, int, number, bool, enum, color, font, file, shortcut, list, ...
        self.Kind = spec.kind
        self.Default = spec.default
        self.Choices = [tuple(choice) for choice in spec.choices]  # [(value, label), ...]
        self.Category = category_of(spec)
        self.Description = spec.description
        self.Always = bool(spec.always)  # (always written to the form file)

    def __repr__(self):
        return f"<PropertyInfo {self.Name}: {self.Kind}>"


class EventInfo:
    """An event of a control type: its name and its handler's arguments."""

    def __init__(self, name: str, arguments: str, default: bool):
        self.Name = name
        self.Arguments = [a.strip() for a in arguments.split(",") if a.strip()]
        self.IsDefault = default  # (double-clicking the control in the designer goes here)

    def __repr__(self):
        return f"<EventInfo {self.Name}({', '.join(self.Arguments)})>"


class ControlTypeInfo:
    """What a control type (or Form, MDIForm) is: see the module."""

    def __init__(self, cls):
        from .controls import EVENT_ARGS

        self._cls = cls
        self.Name = cls.TypeName
        self.Category = category_of_type(self.Name) if self.Name not in (
            "Form", "MDIForm") else "Forms"
        doc = inspect.getdoc(cls) or ""
        self.Description = " ".join(doc.split("\n\n", 1)[0].split())
        self.DefaultSize = tuple(getattr(cls, "DefaultSize", (0, 0)))
        self.DefaultEvent = cls.DefaultEvent or ""
        self.IsContainer = bool(getattr(cls, "IsContainer", False))
        self.InToolbox = bool(getattr(cls, "InToolbox", False))
        self.Properties = sorted((PropertyInfo(spec) for spec in cls.Properties),
                                 key=lambda p: p.Name.lower())
        own = getattr(cls, "EventArgs", None) or {}
        self.Events = [EventInfo(name, own.get(name, EVENT_ARGS.get(name, "")),
                                 name == self.DefaultEvent) for name in cls.Events]

    def __repr__(self):
        return f"<ControlTypeInfo {self.Name}>"

    def Property(self, Name: str) -> PropertyInfo:
        """One of its properties, by name (any case)."""
        found = next((p for p in self.Properties if p.Name.lower() == str(Name).lower()), None)
        if found is None:
            raise KeyError(f"{self.Name} has no property {Name!r}")
        return found

    def Event(self, Name: str) -> EventInfo:
        """One of its events, by name (any case)."""
        found = next((e for e in self.Events if e.Name.lower() == str(Name).lower()), None)
        if found is None:
            raise KeyError(f"{self.Name} has no event {Name!r}")
        return found

    @property
    def Icon(self):
        """Its Toolbox icon as a Picture (48 pixels, in the IDE's current light
        or dark look)."""
        from PySide6.QtCore import QSize

        from .app import ensure_app
        from .ide import icons
        from .picture import Picture

        ensure_app()
        pixmap = icons.icon(self.Name).pixmap(QSize(48, 48))
        return Picture(_image=pixmap.toImage())


def ControlInfo(TypeName: str) -> ControlTypeInfo:
    """What a control type is (its properties, events, category, icon...):
    any in ControlTypes(), Menu, or "Form" / "MDIForm"."""
    name = str(TypeName)
    if name in ("Form", "MDIForm"):
        from .form import Form
        from .mdi import MDIForm

        return ControlTypeInfo(Form if name == "Form" else MDIForm)
    cls = _types().get(name)
    if cls is None:
        raise KeyError(f"No control type {TypeName!r} (ControlTypes() lists them)")
    return ControlTypeInfo(cls)
