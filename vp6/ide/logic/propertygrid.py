"""The Properties window's ways with values, without Qt: how a property's
value reads in the grid (``value_text``), what text typed there means
(``parse_text``), and the titles and hints of the editors of list properties
(a ListBox's List, a TreeView's Items, a StatusBar's Panels...)."""

from __future__ import annotations

LIST_TITLES = {"list": "List", "outline": "Tree", "panels": "Panels", "tabs": "Tabs",
               "images": "Pictures", "buttons": "Buttons", "columns": "Columns",
               "listitems": "Items"}

LIST_HINTS = {
    "list": "One item per line:",
    "outline": "One node per line. Indent a node (spaces or a tab) to make it a child of the "
               "node above; add |key at the end to give it a key, e.g. \"Cats|cats\". A third "
               "part is the node's Image: a Key or Index in the TreeView's ImageList, e.g. "
               "\"Cats|cats|cat\".",
    "panels": "One panel per line: Text|Key|options. The options are words: a width in "
              "pixels, spring (shares the space left) or contents (as wide as its text), "
              "caps, num, ins, scrl, time or date (what it shows), center or right. E.g. "
              "\"Ready|status|spring\" or \"|clock|time 80 right\".",
    "tabs": "One tab per line: Caption|Key|ToolTipText|Image, e.g. \"&General|general|Name "
            "and size|gear\". An & in the Caption underlines the letter of its access key; "
            "the Image is a Key or Index in the TabStrip's ImageList.",
    "images": "One picture per line: path|key, the path relative to the form's folder, e.g. "
              "\"images/open.png|open\". Add Pictures… adds files.",
    "buttons": "One button per line: Caption|Key|Image|ToolTipText|options, the Image a Key "
               "or Index in the Toolbar's ImageList, the options words: check or group (a "
               "button of a group, one of which is pressed), pressed, disabled, hidden. A "
               "line of just - is a separator. E.g. \"Open|open|open|Open a file\" or "
               "\"|bold|bold|Bold|check\".",
    "columns": "One column per line: Text|Key|Width|alignment, the alignment left, right or "
               "center, e.g. \"Size|size|80|right\". The first column shows the items' "
               "Text, the next ones their SubItems.",
    "listitems": "One item per line: Text|Key|Icon|SmallIcon|SubItem 1|SubItem 2..., the "
                 "icons Keys or Indexes in the Icons and SmallIcons ImageLists, e.g. "
                 "\"Earth|earth|planet|planet|12756 km|1 moon\".",
}
LIST_KINDS = tuple(LIST_TITLES)
DEFAULT = "(Default)"


def color_text(value) -> str:
    """A VB color (BGR) as a form file writes it (0x0000FF: red); None: (Default)."""
    if value is None:
        return DEFAULT
    return f"0x{int(value):06X}"


def color_value(text: str):
    """#rrggbb (or &H...& / 0x... VB colors) as a VB color; (Default) or "": None."""
    text = str(text or "").strip()
    if not text or text == DEFAULT:
        return None
    if text.startswith("#") and len(text) == 7:
        red, green, blue = int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
        return red | (green << 8) | (blue << 16)
    if text.upper().startswith("&H"):
        return int(text[2:].rstrip("&"), 16)
    return int(text, 0)


def value_text(kind: str, value, choices=()) -> str:
    """How a value reads in the grid's second column."""
    if kind == "bool":
        return "True" if value else "False"
    if kind in ("enum", "shortcut"):
        return next((label for choice, label in choices if choice == value),
                    "" if value is None else str(value))
    if kind == "color":
        return color_text(value)
    if kind == "font":
        return value or DEFAULT
    if kind in LIST_KINDS:
        count = len(value or [])
        if kind == "list":
            return f"(List: {count} items)"
        if kind == "outline":
            return f"(Tree: {sum(1 for line in value or [] if str(line).strip())} nodes)"
        return f"({LIST_TITLES[kind]}: {count})"
    if value is None:
        return ""
    if kind == "text":
        return str(value).replace("\n", "¶")
    return str(value)


def value_hint(kind: str, value) -> str:
    """What the grid shows greyed in an empty value field: (Default) for a
    whole number left unset."""
    return DEFAULT if kind == "int" and value is None else ""


def parse_text(kind: str, text: str, original=None, default=None, choices=()):
    """The value text typed (or chosen) in the grid means. Raises ValueError
    for text that isn't one."""
    text = str(text)
    if kind == "bool":
        return text.strip().lower() == "true"
    if kind in ("enum", "shortcut"):
        for choice, label in choices:
            if label == text:
                return choice
        if kind == "shortcut":
            return "" if text in ("", "(None)") else text.strip()
        raise ValueError(f"'{text}' is not one of the choices")
    if kind == "color":
        return color_value(text)
    if kind == "font":
        return None if text in ("", DEFAULT) else text
    if kind == "int":
        if text.strip() in ("", DEFAULT):
            return None if default is None else original
        return int(text.strip())
    if kind == "number":
        if text.strip() in ("", DEFAULT):
            return None if default is None else original
        number = float(text.strip())
        return int(number) if number.is_integer() else number
    if kind == "index":
        return int(text) if text.strip() else None
    if kind == "text":
        return text.replace("¶", "\n")
    return text
