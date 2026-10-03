"""Declarative VB-style properties.

Every form/control class lists its designable properties as ``PropSpec``
entries. For each one a Python property is generated that:

* normalizes the assigned value (``kind``),
* stores it in ``self._values``,
* calls ``self._apply_<Name>(value)`` so the class can update the Qt widget.

A class can define ``_read_<Name>()`` when the live value comes from the
widget (e.g. the text the user typed into a TextBox).

The same metadata drives the IDE: the property grid, the designer region
serializer and default-value elision.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import colors


@dataclass(frozen=True)
class PropSpec:
    name: str
    # str, text, int, bool, enum, color, font, file, shortcut; list and outline (lines
    # of text); panels, tabs, images, buttons, columns and listitems (lines of
    # text that are a collection at run time: StatusBar.Panels, TabStrip.Tabs, ...)
    kind: str = "str"
    default: object = None
    choices: tuple = ()  # enum: ((value, "label"), ...)
    always: bool = False  # always written to the designer region
    description: str = ""
    # The Properties window's Categorized view; "" = from PROPERTY_CATEGORIES
    category: str = ""


def P(name, kind="str", default=None, choices=(), always=False, description="", category=""):
    return PropSpec(name, kind, default, tuple(choices), always, description, category)


# The Properties window's Categorized view (VB's categories), by property name
_CATEGORY_NAMES = {
    "Appearance": "Alignment BackColor BackStyle BorderColor BorderStyle BorderWidth Caption "
                  "Checkboxes ColorScheme CurrentLineColor DisabledPicture DownPicture "
                  "FillColor FillStyle ForeColor GridLines HideColumnHeaders "
                  "HighlightCurrentLine Icon Indentation LineNumbers LineStyle Orientation "
                  "Picture Placement ProtectedColor Shape Stretch Style TextAlignment "
                  "TickFrequency TickStyle View",
    "Behavior": "AcceptsTab AllowUserResizing AutoIndent AutoRedraw AutoSize Cancel "
                "CausesValidation Checked Closable Default DragMode DrawStyle DrawWidth "
                "Editable Enabled Floatable Floating Hidden Increment Interval KeyPreview "
                "LargeChange Locked Max Min MinSize MultiSelect NegotiateMenus "
                "NegotiatePosition OLEDropMode Resizable ScrollBars SelectionMode ShowHidden "
                "SmallChange SortKey SortOrder Sorted SyncBuddy TabWidth UseMnemonic UseTabs "
                "Value Visible WindowState WordWrap Wrap",
    "Data": "BOFAction DatabaseName DataField DataSource EOFAction ReadOnly RecordSource",
    "Font": "FontBold FontItalic FontName FontSize FontStrikethru FontUnderline",
    "List": "Buttons Cols ColumnHeaders FixedCols FixedRows FormatString Icons ImageHeight "
            "ImageList ImageWidth Items List ListImages ListItems Panels Rows SmallIcons Tabs",
    "Position": "Align Height Left StartUpPosition Top Width X1 X2 Y1 Y2 ZIndex",
    "Text": "Language MaxLength MultiLine PasswordChar SimpleText Text TextFormat",
}
PROPERTY_CATEGORIES = {name: category for category, names in _CATEGORY_NAMES.items()
                       for name in names.split()}


def category_of(spec: PropSpec) -> str:
    """The spec's category in the Properties window: its own, else VB's for
    its name, else Misc (Name, Tag, TabIndex, ToolTipText, MousePointer...)."""
    return spec.category or PROPERTY_CATEGORIES.get(spec.name, "Misc")


def enum_choices(*labels: str) -> tuple:
    """enum_choices("None", "Fixed Single") -> ((0, "0 - None"), (1, "1 - Fixed Single"))"""
    return tuple((i, f"{i} - {label}") for i, label in enumerate(labels))


def normalize(kind: str, value):
    if value is None:
        return None
    if kind == "file" and hasattr(value, "_pixmap") and not isinstance(value, str):
        return value  # a Picture object (vp6.picture), kept as it is
    if kind in ("str", "text", "file", "font", "shortcut"):
        return str(value)
    if kind in ("int", "enum"):
        return int(value)
    if kind == "bool":
        return bool(value)
    if kind == "color":
        return colors.normalize(value)
    if kind in ("list", "outline", "panels", "tabs", "images", "buttons", "columns",
                "listitems"):
        if isinstance(value, str):
            value = value.splitlines()
        return [str(v) for v in value]
    return value


def _make_property(name: str) -> property:
    def fget(self):
        reader = getattr(self, "_read_" + name, None)
        if reader is not None:
            return reader()
        return self._values.get(name, self._specs[name].default)

    def fset(self, value):
        self._set_prop(name, value)

    return property(fget, fset, doc=f"VB property {name}")


class PropertyHost:
    Properties: tuple[PropSpec, ...] = ()
    _specs: dict[str, PropSpec] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._specs = {spec.name: spec for spec in cls.Properties}
        for spec in cls.Properties:
            if not isinstance(getattr(cls, spec.name, None), property):
                setattr(cls, spec.name, _make_property(spec.name))

    def _init_values(self, props: dict) -> None:
        """Apply defaults, then the given property values, in spec order."""
        unknown = set(props) - set(self._specs)
        if unknown:
            raise AttributeError(
                f"{type(self).__name__} has no properties: {', '.join(sorted(unknown))}")
        for spec in self.Properties:
            self._set_prop(spec.name, props.get(spec.name, spec.default))

    def _set_prop(self, name: str, value) -> None:
        spec = self._specs[name]
        value = normalize(spec.kind, value)
        self._values[name] = value
        applier = getattr(self, "_apply_" + name, None)
        if applier is not None:
            applier(value)

    @classmethod
    def properties(cls) -> tuple[PropSpec, ...]:
        return cls.Properties
