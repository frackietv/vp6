"""Generate the reference tables in docs/api.md from the code.

docs/api.md mixes hand-written prose with generated blocks:

    <!-- BEGIN GENERATED: control TextBox -->
    ...tables written by this script...
    <!-- END GENERATED -->

This script rewrites every generated block from the controls' own metadata
(``Properties`` / ``PropSpec``, ``Events``, ``DefaultEvent``, ``DefaultSize``)
and from the constants modules, so the tables can't drift from the code.

    python tools/apidocs.py          # rewrite docs/api.md
    python tools/apidocs.py --check  # exit 1 if docs/api.md is out of date

``tests/test_docs.py`` runs the check.

Block keys:
    form-properties, form-events       the Form
    control <TypeName>                 one control's section
    common-properties                  the property groups shared by controls
    event-arguments                    every event and its parameters
    constants                          the vp* constants
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from vp6 import appearance, colors, constants  # noqa: E402
from vp6.controls import (_COLORS, _COMMON, _FONT, CONTROL_TYPES,  # noqa: E402
                          EVENT_ARGS, _geometry)
from vp6.form import Form  # noqa: E402

API_MD = ROOT / "docs" / "api.md"
BLOCK_RE = re.compile(r"(<!-- BEGIN GENERATED: (?P<key>[^>]+?) -->\n)(?P<body>.*?)"
                      r"(<!-- END GENERATED -->)", re.S)

KIND = {"str": "str", "text": "str (multi-line)", "int": "int", "bool": "bool", "enum": "enum",
        "color": "color", "list": "list[str]", "font": "font name", "file": "file path",
        "shortcut": "shortcut key", "outline": "list[str] (an indented outline)"}

# The property groups shared by controls, in the order they're documented
GROUPS = [
    ("Position", _geometry(0, 0)),
    ("Colors", _COLORS),
    ("Font", _FONT),
    ("Common", _COMMON),
]


# --- formatting helpers -----------------------------------------------------------------------

def _default(spec) -> str:
    if spec.kind == "enum":
        return next((label for value, label in spec.choices if value == spec.default),
                    repr(spec.default))
    if spec.default is None:
        return "(default)"
    return f"`{spec.default!r}`"


def _notes(spec) -> str:
    parts = []
    if spec.kind == "enum":
        parts.append(", ".join(label for _, label in spec.choices))
    if spec.description:
        parts.append(spec.description)
    return ". ".join(parts)


def _table(specs, default_column=True) -> str:
    rows = ["| Property | Type | Default | Notes |", "|---|---|---|---|"]
    for spec in sorted(specs, key=lambda s: s.name):
        default = _default(spec) if default_column else "per control"
        rows.append(f"| `{spec.name}` | {KIND.get(spec.kind, spec.kind)} | {default} | "
                    f"{_notes(spec)} |")
    return "\n".join(rows)


def _events(cls) -> str:
    if not cls.Events:
        return "No events."
    items = []
    for event in cls.Events:
        args = EVENT_ARGS.get(event, "")
        items.append(f"`{event}({args})`" if args else f"`{event}`")
    return (f"Events: {', '.join(items)}. Default event (double-click in the designer): "
            f"`{cls.DefaultEvent}`.")


def _groups_of(cls) -> tuple[list[str], list]:
    """(names of the complete shared groups, the class's other specs)."""
    names = set(cls._specs)
    groups, covered = [], set()
    for title, specs in GROUPS:
        group_names = {s.name for s in specs}
        if group_names <= names:
            groups.append(title)
            covered |= group_names
    return groups, [s for s in cls.Properties if s.name not in covered]


# --- blocks -----------------------------------------------------------------------------------

def form_properties() -> str:
    return _table(Form.Properties)


def form_events() -> str:
    return _events(Form)


def control(type_name: str) -> str:
    cls = CONTROL_TYPES[type_name]
    groups, own = _groups_of(cls)
    width, height = cls.DefaultSize
    if not cls.InToolbox:
        summary = ["Not in the Toolbox: designed with the Menu Editor."]
    elif "X1" in cls._specs:
        summary = ["Placed by its two ends, (X1, Y1) and (X2, Y2), instead of a position "
                   "and size."]
    else:
        summary = [f"Default size {width} × {height}."]
    if cls.IsContainer:
        summary.append("A container: other controls can be placed on it.")
    if groups:
        summary.append(f"Property groups: {', '.join(groups)}.")
    parts = [" ".join(summary)]
    if own:
        parts.append(_table(own))
    parts.append(_events(cls))
    return "\n\n".join(parts)


def common_properties() -> str:
    rows = ["| Group | Property | Type | Default | Notes |", "|---|---|---|---|---|"]
    for title, specs in GROUPS:
        for spec in specs:
            default = "per control" if title == "Position" and spec.name in ("Width", "Height") \
                else _default(spec)
            rows.append(f"| {title} | `{spec.name}` | {KIND.get(spec.kind, spec.kind)} | "
                        f"{default} | {_notes(spec)} |")
    return "\n".join(rows)


def event_arguments() -> str:
    rows = ["| Event | Arguments |", "|---|---|"]
    for event, args in EVENT_ARGS.items():
        rows.append(f"| `{event}` | {args or 'none'} |")
    return "\n".join(rows)


def _constant_sections() -> list[tuple[str, list[tuple[str, object]]]]:
    """(title, [(name, value), ...]) from the '# --- Title ---' sections of
    constants.py, in source order."""
    source = Path(constants.__file__).read_text()
    sections, current = [], None
    for line in source.splitlines():
        header = re.match(r"# --- (.+?) -+$", line)
        if header:
            current = (header.group(1), [])
            sections.append(current)
            continue
        assignment = re.match(r"(vp\w+) = ", line)
        if assignment and current is not None:
            name = assignment.group(1)
            current[1].append((name, getattr(constants, name)))
    return sections


def _key_ranges() -> list[tuple[str, str]]:
    """Key codes generated in loops, as ('vpKeyA..vpKeyZ', '65-90') rows."""
    rows = []
    for first, last in (("0", "9"), ("A", "Z"), ("F1", "F12")):
        a, b = getattr(constants, f"vpKey{first}"), getattr(constants, f"vpKey{last}")
        rows.append((f"`vpKey{first}`..`vpKey{last}`", f"{a}-{b}"))
    return rows


def _value(value) -> str:
    return f"`{value!r}`" if isinstance(value, str) else str(value)


def constants_block() -> str:
    rows = ["| Group | Constants | Values |", "|---|---|---|"]
    keys = None
    for title, items in _constant_sections():
        if title.startswith("Key codes"):
            keys = items
            continue
        names = ", ".join(f"`{n}`" for n, _ in items)
        values = ", ".join(_value(v) for _, v in items)
        rows.append(f"| {title} | {names} | {values} |")
    color_names = ["vpBlack", "vpRed", "vpGreen", "vpYellow", "vpBlue", "vpMagenta", "vpCyan",
                   "vpWhite"]
    rows.append("| Colors (BGR) | " + ", ".join(f"`{n}`" for n in color_names) + " | "
                + ", ".join(f"`0x{getattr(colors, n):06X}`" for n in color_names) + " |")
    schemes = [n for n in appearance.__all__ if n.startswith("vpScheme")]
    rows.append("| Color schemes | " + ", ".join(f"`{n}`" for n in schemes) + " | "
                + ", ".join(str(getattr(appearance, n)) for n in schemes) + " |")

    key_rows = ["| Key constant | Value |", "|---|---|"]
    key_rows += [f"| `{name}` | {value} |" for name, value in keys or []]
    key_rows += [f"| {names} | {values} |" for names, values in _key_ranges()]
    return "\n".join(rows) + "\n\n**Key codes** (for `KeyDown` / `KeyUp`):\n\n" + \
        "\n".join(key_rows)


def render(key: str) -> str:
    key = key.strip()
    if key.startswith("control "):
        return control(key.split(" ", 1)[1])
    blocks = {
        "form-properties": form_properties,
        "form-events": form_events,
        "common-properties": common_properties,
        "event-arguments": event_arguments,
        "constants": constants_block,
    }
    if key not in blocks:
        raise KeyError(f"Unknown generated block {key!r} in {API_MD}")
    return blocks[key]()


def update(text: str) -> str:
    """The text with every generated block re-rendered."""
    return BLOCK_RE.sub(lambda m: m.group(1) + render(m.group("key")) + "\n" + m.group(4),
                        text)


def block_keys(text: str) -> list[str]:
    return [m.group("key").strip() for m in BLOCK_RE.finditer(text)]


def main(argv: list[str]) -> int:
    text = API_MD.read_text()
    new = update(text)
    if "--check" in argv:
        if new != text:
            print(f"{API_MD} is out of date: run python tools/apidocs.py", file=sys.stderr)
            return 1
        return 0
    if new != text:
        API_MD.write_text(new)
        print(f"Updated {API_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
