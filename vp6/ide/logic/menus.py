"""The Menu Editor's model: a form's menus as one indented list, VB's way.
An entry's level is how deep it is (0 = the menu bar, 1 = an item of a menu
bar menu, ...); each has a Caption ("-" for a separator), a Name, an optional
Index (menu control arrays), a Shortcut, and the Checked, Enabled and Visible
flags; its other properties (Group, Picture, WindowList, NegotiatePosition,
Tag) are kept in ``props``.

``entries_from(form_def)`` reads a form's menus, ``validate(entries, taken)``
checks them and ``menu_defs(entries)`` turns them back into the form's
``Menu`` ControlDefs. The IDE's Menu Editor (``vp6.ide.menueditor``) edits
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vp6.formfile import ControlDef, FormDef, control_key

MAX_LEVEL = 5  # like VB: the menu bar plus five levels of submenus
INDENT = "····"


@dataclass
class MenuEntry:
    level: int = 0
    caption: str = ""
    name: str = ""
    index: int | None = None
    shortcut: str = ""
    checked: bool = False
    enabled: bool = True
    visible: bool = True
    props: dict = field(default_factory=dict)  # other properties (e.g. Tag), kept as they are
    original: str | None = None  # the menu's key before editing (None = new)

    @property
    def key(self) -> str:
        return control_key(self.name, self.index)

    def is_blank(self) -> bool:
        return not self.caption and not self.name


def entries_from(form_def: FormDef) -> list[MenuEntry]:
    """The form's menus in menu order (depth first)."""
    menus = [c for c in form_def.controls if c.type == "Menu"]
    entries = []

    def add(parent: str | None, level: int) -> None:
        for control in menus:
            if control.parent == parent:
                props = dict(control.props)
                entries.append(MenuEntry(
                    level, props.pop("Caption", ""), control.name, control.index,
                    props.pop("Shortcut", ""), props.pop("Checked", False),
                    props.pop("Enabled", True), props.pop("Visible", True), props,
                    control.key))
                add(control.key, level + 1)

    add(None, 0)
    return entries


def validate(entries: list[MenuEntry], taken: set[str]) -> str | None:
    """An error message for the first problem, or None. ``taken`` are names
    used by the form and its other controls."""
    seen: dict[str, bool] = {}  # name -> whether it has an Index
    keys = set()
    previous_level = -1
    for number, entry in enumerate(entries, 1):
        where = f"Item {number} ({entry.caption or entry.name or 'blank'})"
        if not entry.name:
            return f"{where}: every menu item needs a Name"
        if not entry.name.isidentifier():
            return f"{where}: '{entry.name}' is not a valid name"
        if entry.name in taken:
            return f"{where}: the name '{entry.name}' is already used on the form"
        if entry.key in keys:
            return f"{where}: '{entry.key}' is used twice"
        has_index = entry.index is not None
        if seen.get(entry.name, has_index) != has_index:
            return (f"{where}: menus named '{entry.name}' form a control array, so each "
                    "needs an Index")
        if has_index and not 0 <= entry.index <= 32767:
            return f"{where}: Index must be from 0 to 32767"
        if entry.level > previous_level + 1:
            return f"{where}: it is indented more than one level below the item above"
        if entry.level > MAX_LEVEL:
            return f"{where}: menus can be at most {MAX_LEVEL} levels deep"
        if entry.caption == "-" and entry.level == 0:
            return f"{where}: a separator can't be on the menu bar"
        following = entries[number] if number < len(entries) else None
        if entry.caption == "-" and following is not None and following.level > entry.level:
            return f"{where}: a separator can't have items of its own"
        seen[entry.name] = has_index
        keys.add(entry.key)
        previous_level = entry.level
    return None


def menu_defs(entries: list[MenuEntry]) -> list[ControlDef]:
    """``Menu`` ControlDefs for valid entries, parents from the levels."""
    defs, parents = [], []  # parents[level] = key of the latest entry at that level
    for entry in entries:
        props = dict(entry.props)
        props["Caption"] = entry.caption
        for name, value, default in (("Checked", entry.checked, False),
                                     ("Enabled", entry.enabled, True),
                                     ("Visible", entry.visible, True),
                                     ("Shortcut", entry.shortcut, "")):
            if value != default:  # like the form file: only what differs from the default
                props[name] = value
        parent = parents[entry.level - 1] if entry.level > 0 else None
        defs.append(ControlDef("Menu", entry.name, parent, props, entry.index))
        del parents[entry.level:]
        parents.append(entry.key)
    return defs
