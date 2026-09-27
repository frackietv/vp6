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
    kind: str = "str"  # str, text, int, bool, enum, color, list, outline, panels, tabs, font, file
    default: object = None
    choices: tuple = ()  # enum: ((value, "label"), ...)
    always: bool = False  # always written to the designer region
    description: str = ""


def P(name, kind="str", default=None, choices=(), always=False, description=""):
    return PropSpec(name, kind, default, tuple(choices), always, description)


def enum_choices(*labels: str) -> tuple:
    """enum_choices("None", "Fixed Single") -> ((0, "0 - None"), (1, "1 - Fixed Single"))"""
    return tuple((i, f"{i} - {label}") for i, label in enumerate(labels))


def normalize(kind: str, value):
    if value is None:
        return None
    if kind in ("str", "text", "file", "font", "shortcut"):
        return str(value)
    if kind in ("int", "enum"):
        return int(value)
    if kind == "bool":
        return bool(value)
    if kind == "color":
        return colors.normalize(value)
    if kind in ("list", "outline", "panels", "tabs"):
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
