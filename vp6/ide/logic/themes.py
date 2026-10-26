"""The code editors' color themes and the IDE's light/dark choice, as data.

``BUILTIN_THEMES`` are Light and Dark; every theme can be customized and new
ones made (``Theme``: its UI colors, ``UI_ROLES``, and its syntax styles,
``SYNTAX_ROLES``). ``EditorSettings`` is what Tools > Options edits: the
selected theme (a theme's name, or "System" to follow the operating system's
appearance with the themes chosen for light and dark), the code font, the
designer's window frame and grid. ``read_settings(store)`` and
``write_settings(state, store)`` keep it in a settings object (``value``,
``setValue``); ``resolve(state, system_dark)`` is the theme in use.

The IDE's ThemeManager (``vp6.ide.theme``) applies it.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field

SYSTEM = "System"
LIGHT = "Light"
DARK = "Dark"

# (key, label) - editor surface colors
UI_ROLES = [
    ("background", "Background"),
    ("foreground", "Text"),
    ("selection_background", "Selection background"),
    ("selection_foreground", "Selection text"),
    ("current_line", "Current line"),
    ("breakpoint", "Breakpoint line"),
    ("execution_point", "Execution point (paused)"),
    ("gutter_background", "Line numbers background"),
    ("gutter_foreground", "Line numbers"),
    ("designer_region", "Designer region background"),
    ("fold_marker", "Fold marker"),
    ("output_error", "Immediate: errors"),
    ("output_info", "Immediate: messages"),
    ("output_input", "Immediate: your input"),
]

# (key, label) - syntax styles (color + bold + italic)
SYNTAX_ROLES = [
    ("keyword", "Keywords"),
    ("builtin", "Python built-ins"),
    ("vp6", "VP6 names (MsgBox, vpYes…)"),
    ("self", "self"),
    ("string", "Strings"),
    ("comment", "Comments"),
    ("number", "Numbers"),
    ("defname", "Function / class names"),
    ("decorator", "Decorators"),
]


@dataclass
class TextStyle:
    color: str
    bold: bool = False
    italic: bool = False


@dataclass
class Theme:
    name: str
    dark: bool
    colors: dict[str, str]
    syntax: dict[str, TextStyle] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict, fallback: "Theme") -> "Theme":
        """Build a theme, filling missing roles from ``fallback``."""
        colors = dict(fallback.colors)
        colors.update({k: v for k, v in data.get("colors", {}).items() if k in colors})
        syntax = copy.deepcopy(fallback.syntax)
        for key, style in data.get("syntax", {}).items():
            if key in syntax and isinstance(style, dict):
                syntax[key] = TextStyle(style.get("color", syntax[key].color),
                                        bool(style.get("bold")), bool(style.get("italic")))
        return cls(data.get("name", fallback.name), bool(data.get("dark", fallback.dark)),
                   colors, syntax)


BUILTIN_THEMES: dict[str, Theme] = {
    LIGHT: Theme(LIGHT, False, {
        "background": "#ffffff", "foreground": "#000000",
        "selection_background": "#add6ff", "selection_foreground": "#000000",
        "current_line": "#fffbdd", "breakpoint": "#f7d4d1", "execution_point": "#fff19c",
        "gutter_background": "#f3f3f3",
        "gutter_foreground": "#6e7781", "designer_region": "#eef0f4",
        "fold_marker": "#808080", "output_error": "#c0392b", "output_info": "#7f8c8d",
        "output_input": "#1f5fbf",
    }, {
        "keyword": TextStyle("#0000ff"), "builtin": TextStyle("#795e26"),
        "vp6": TextStyle("#267f99"), "self": TextStyle("#808080", italic=True),
        "string": TextStyle("#a31515"), "comment": TextStyle("#008000", italic=True),
        "number": TextStyle("#098658"), "defname": TextStyle("#000000", bold=True),
        "decorator": TextStyle("#af00db"),
    }),
    DARK: Theme(DARK, True, {
        "background": "#1e1e1e", "foreground": "#d4d4d4",
        "selection_background": "#264f78", "selection_foreground": "#ffffff",
        "current_line": "#2a2d2e", "breakpoint": "#4b2424", "execution_point": "#4b4618",
        "gutter_background": "#1e1e1e",
        "gutter_foreground": "#858585", "designer_region": "#252a33",
        "fold_marker": "#c5c5c5", "output_error": "#f48771", "output_info": "#9d9d9d",
        "output_input": "#4fc1ff",
    }, {
        "keyword": TextStyle("#569cd6"), "builtin": TextStyle("#dcdcaa"),
        "vp6": TextStyle("#4ec9b0"), "self": TextStyle("#9cdcfe", italic=True),
        "string": TextStyle("#ce9178"), "comment": TextStyle("#6a9955", italic=True),
        "number": TextStyle("#b5cea8"), "defname": TextStyle("#dcdcaa", bold=True),
        "decorator": TextStyle("#c586c0"),
    }),
}


@dataclass
class EditorSettings:
    """Everything the Options dialog edits."""

    selection: str = SYSTEM
    system_light: str = LIGHT
    system_dark: str = DARK
    font_family: str = ""  # "" = default monospace font
    font_size: int = 0  # 0 = default size
    frame_style: str = "auto"  # designer window frame, see chrome.FRAME_STYLES
    show_grid: bool = True  # designer grid dots (snapping works either way)
    themes: dict[str, Theme] = field(default_factory=dict)


def read_settings(store) -> EditorSettings:
    """The editor settings kept in a settings object (built-in themes with
    their customizations, and the custom themes)."""
    themes = copy.deepcopy(BUILTIN_THEMES)
    try:
        custom = json.loads(store.value("editor/themes", "{}") or "{}")
    except (TypeError, ValueError):
        custom = {}
    for name, data in custom.items():
        fallback = themes.get(name) or themes[DARK if data.get("dark") else LIGHT]
        themes[name] = Theme.from_dict({**data, "name": name}, fallback)
    state = EditorSettings(
        selection=store.value("editor/theme", SYSTEM) or SYSTEM,
        system_light=store.value("editor/system_light", LIGHT) or LIGHT,
        system_dark=store.value("editor/system_dark", DARK) or DARK,
        font_family=store.value("editor/font_family", "") or "",
        font_size=int(store.value("editor/font_size", 0) or 0),
        frame_style=store.value("designer/frame_style", "auto") or "auto",
        show_grid=str(store.value("designer/show_grid", True)).lower() not in ("false", "0"),
        themes=themes,
    )
    if state.selection != SYSTEM and state.selection not in themes:
        state.selection = SYSTEM
    return state


def write_settings(state: EditorSettings, store) -> None:
    """Keep the editor settings in a settings object (only the themes that
    differ from the built-in ones)."""
    store.setValue("editor/theme", state.selection)
    store.setValue("editor/system_light", state.system_light)
    store.setValue("editor/system_dark", state.system_dark)
    store.setValue("editor/font_family", state.font_family)
    store.setValue("editor/font_size", state.font_size)
    store.setValue("designer/frame_style", state.frame_style)
    store.setValue("designer/show_grid", state.show_grid)
    custom = {name: theme.to_dict() for name, theme in state.themes.items()
              if BUILTIN_THEMES.get(name) != theme}
    store.setValue("editor/themes", json.dumps(custom))


def resolve(state: EditorSettings, system_dark: bool) -> Theme:
    """The theme in use: the selected one, or with System the one chosen for
    the operating system's appearance."""
    name = state.selection
    if name == SYSTEM:
        name = state.system_dark if system_dark else state.system_light
    return state.themes.get(name) or state.themes[DARK if system_dark else LIGHT]


def app_is_dark(state: EditorSettings, system_dark: bool) -> bool:
    """Whether the IDE's windows are dark: the operating system's appearance
    with System, else the selected theme's."""
    if state.selection == SYSTEM:
        return system_dark
    return resolve(state, system_dark).dark
