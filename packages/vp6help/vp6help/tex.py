"""Mathematics in Markdown, in pure Python (no Qt): TeX formulas (a subset)
found in Markdown, parsed and laid out the way TeX lays them out, as boxes
with baselines, TeX's spacing classes (ordinary, operator, binary, relation,
opening, closing, punctuation, inner) and its four styles (display, text,
script, scriptscript).

``$…$`` is a formula in the text, ``$$…$$`` one displayed (on its own,
centred). A ``$`` opening a formula is followed by a character that isn't a
space, the closing one follows one and isn't followed by a digit, so
``$5 and $10`` stays text; ``\\$`` is a dollar sign; code is never maths.

    for span in math_spans(markdown): ...       # where the formulas are
    shape = layout(r"\\frac{1}{2}", metrics)    # what to draw: Text, Rule, Shape
    shape = render(source, metrics)             # the same, or the source in red

What is understood: fractions (``\\frac``, ``\\dfrac``, ``\\tfrac``, ``\\binom``),
exponents and subscripts, primes, roots (``\\sqrt[n]{x}``), Greek letters,
relations, operators and arrows, absolute values and norms, delimiters
that grow (``\\left( … \\middle| … \\right)``, ``\\big`` to ``\\Bigg``), sums,
products, integrals and limits with their bounds (``\\limits``,
``\\nolimits``), functions (``\\sin``, ``\\log``, ``\\operatorname``), matrices
(``matrix``, ``pmatrix``, ``bmatrix``, ``Bmatrix``, ``vmatrix``, ``Vmatrix``,
``smallmatrix``, ``array``), ``cases``, ``aligned`` and ``gathered``, text
(``\\text``, ``\\textbf``...), fonts (``\\mathrm``, ``\\mathbf``, ``\\mathbb``,
``\\mathcal``...), accents and vectors (``\\vec``, ``\\hat``, ``\\bar``...,
``\\overrightarrow``, ``\\overleftrightarrow``), ``\\overline`` (repeating
decimals), ``\\underline``, braces (``\\underbrace``), ``\\overset``,
``\\boxed``, ``\\cancel``, ``\\not``, ``\\pmod``, colours (``\\color``,
``\\textcolor``), spaces and styles (``\\,``, ``\\quad``, ``\\displaystyle``...).

The layout measures glyphs through a ``Metrics`` (vp6help's ``texdraw``
measures a Qt font; this module's own makes every glyph the same size, for
tests). Sizes are pixels; ``y`` grows downwards from the baseline.
"""

from __future__ import annotations

import re
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NamedTuple

__all__ = ["TexError", "MathSpan", "math_spans", "Metrics", "Text", "Rule", "Shape",
           "Layout", "parse", "layout", "render", "ERROR_COLOR"]

ERROR_COLOR = "error"  # (a primitive's colour: the one shown for a formula that doesn't parse)


class TexError(ValueError):
    """A formula that can't be read: ``position`` is where in its source."""

    def __init__(self, message: str, position: int = 0):
        super().__init__(message)
        self.position = position


# --- finding the formulas in Markdown --------------------------------------------------------

class MathSpan(NamedTuple):
    start: int  # (the first $)
    end: int  # (after the last $)
    tex: str
    display: bool


_FENCE_LINE = re.compile(r"^ {0,3}(`{3,}|~{3,})", re.M)


def _code_ranges(text: str) -> list[tuple[int, int]]:
    """Where the code is: fenced blocks and code spans (no maths in them)."""
    ranges: list[tuple[int, int]] = []
    if "`" not in text and "~" not in text:
        return ranges
    fence, opened, offset = None, 0, 0
    for line in text.splitlines(keepends=True):
        match = _FENCE_LINE.match(line)
        if fence is None and match:
            fence, opened = match.group(1), offset
        elif fence is not None and match and match.group(1)[0] == fence[0] and \
                len(match.group(1)) >= len(fence) and not line[match.end():].strip():
            ranges.append((opened, offset + len(line.rstrip("\n"))))
            fence = None
        offset += len(line)
    if fence is not None:
        ranges.append((opened, len(text)))
    spans = []
    i, n, r = 0, len(text), 0
    while i < n:
        if r < len(ranges) and i >= ranges[r][0]:
            i = max(i, ranges[r][1])
            r += 1
            continue
        if text[i] == "\\":
            i += 2
            continue
        if text[i] != "`":
            i += 1
            continue
        run = len(text[i:]) - len(text[i:].lstrip("`"))
        close = re.compile(r"(?<!`)" + "`" * run + r"(?!`)").search(text, i + run)
        limit = ranges[r][0] if r < len(ranges) else n
        if close is None or close.start() >= limit:
            i += run
            continue
        spans.append((i, close.end()))
        i = close.end()
    return sorted(ranges + spans)


def math_spans(text: str) -> list[MathSpan]:
    """The formulas of some Markdown, in order: ``$…$`` (inline) and
    ``$$…$$`` (display), outside code and not after a backslash."""
    if "$" not in text:
        return []
    code = _code_ranges(text)
    spans: list[MathSpan] = []
    i, n, r = 0, len(text), 0
    while i < n:
        while r < len(code) and code[r][1] <= i:
            r += 1
        if r < len(code) and code[r][0] <= i:
            i = code[r][1]
            continue
        limit = code[r][0] if r < len(code) else n
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c != "$":
            i += 1
            continue
        if text.startswith("$$", i):
            end = _display_end(text, i + 2, limit)
            if end is not None and text[i + 2:end].strip():
                spans.append(MathSpan(i, end + 2, text[i + 2:end].strip(), True))
                i = end + 2
            else:
                i += 2
            continue
        end = _inline_end(text, i + 1, limit)
        if end is not None:
            spans.append(MathSpan(i, end + 1, text[i + 1:end], False))
            i = end + 1
        else:
            i += 1
    return spans


def _blank_line_at(text: str, k: int) -> bool:
    """Whether the newline at k ends a paragraph (a blank line follows)."""
    rest = text[k + 1:]
    return rest.lstrip(" \t").startswith("\n") or not rest.strip()


def _inline_end(text: str, j: int, limit: int) -> int | None:
    if j >= limit or text[j].isspace() or text[j] == "$":
        return None
    k = j
    while k < limit:
        ch = text[k]
        if ch == "\\":
            k += 2
            continue
        if ch == "\n" and _blank_line_at(text, k):
            return None
        if ch == "$":
            if text[k - 1].isspace() or (k + 1 < len(text) and text[k + 1].isdigit()):
                return None
            return k
        k += 1
    return None


def _display_end(text: str, j: int, limit: int) -> int | None:
    k = j
    while k < limit - 1:
        ch = text[k]
        if ch == "\\":
            k += 2
            continue
        if ch == "\n" and _blank_line_at(text, k):
            return None
        if text.startswith("$$", k):
            return k
        k += 1
    return None


# --- the font: what the layout needs to know of it -------------------------------------------

class Metrics:
    """A font's sizes in pixels. This one is made up (every glyph half an em
    wide), for tests and for laying out without a font: a real one (vp6help's
    ``texdraw.QtMetrics``) measures its glyphs. ``font`` is ``rm`` (upright),
    ``it`` (italic), ``bf``, ``bfit`` or ``tt``; ``scale`` the style's size."""

    _TALL = set("ABCDEFGHIJKLMNOPQRSTUVWXYZbdfhklt0123456789()[]{}|/\\!?∑∏∫√δθλβ‖⟨⟩")
    _DEEP = set("gjpqy()[]{}|,;/\\∑∏∫βγζημξρφχψ‖⟨⟩")

    def __init__(self, em: float = 16.0):
        self.em = float(em)

    def measure(self, text: str, font: str, scale: float) -> tuple[float, float, float, float]:
        """(advance width, ascent above the baseline, descent below it, italic
        correction) of some text."""
        size = self.em * scale
        if not text.strip():
            return 0.25 * size * len(text), 0.0, 0.0, 0.0
        tall = any(ch in self._TALL for ch in text)
        deep = any(ch in self._DEEP for ch in text)
        return (0.5 * size * len(text), (0.7 if tall else 0.45) * size,
                (0.2 if deep else 0.0) * size, 0.0)

    def x_height(self, scale: float = 1.0) -> float:
        return 0.45 * self.em * scale

    def axis_height(self, scale: float = 1.0) -> float:
        """The height of the maths axis: the middle of a minus sign."""
        return 0.25 * self.em * scale

    def rule_thickness(self, scale: float = 1.0) -> float:
        return 0.05 * self.em * scale


# --- what is drawn -----------------------------------------------------------------------------

class Text(NamedTuple):
    x: float
    y: float  # (the baseline)
    text: str
    font: str
    scale: float
    color: str | None  # (None: the text's colour)


class Rule(NamedTuple):
    x: float
    y: float  # (the top)
    width: float
    height: float
    color: str | None


class Shape(NamedTuple):
    """A path: ("M", x, y), ("L", x, y), ("C", x1, y1, x2, y2, x, y), ("Z",)
    commands, filled or stroked (``width``, ``cap`` "flat" or "round")."""
    commands: tuple
    fill: bool
    width: float
    color: str | None
    cap: str = "round"


class Layout(NamedTuple):
    width: float
    ascent: float
    descent: float
    items: list
    error: str | None = None


def _moved(item, dx: float, dy: float):
    if isinstance(item, (Text, Rule)):
        return item._replace(x=item.x + dx, y=item.y + dy)
    commands = []
    for command in item.commands:
        values = list(command[1:])
        for k in range(0, len(values), 2):
            values[k] += dx
            values[k + 1] += dy
        commands.append((command[0], *values))
    return item._replace(commands=tuple(commands))


def _extent(item) -> tuple[float, float]:
    """(height above, depth below) the baseline of a primitive."""
    if isinstance(item, Rule):
        return -item.y, item.y + item.height
    ys = [command[k] for command in item.commands for k in range(2, len(command), 2)]
    pad = 0 if item.fill else item.width / 2
    return (-min(ys) + pad, max(ys) + pad) if ys else (0.0, 0.0)


class Box:
    """Something laid out: its width, its height above the baseline and its
    depth below, and what it holds (boxes and primitives) at offsets."""

    __slots__ = ("width", "height", "depth", "items", "italic", "char")

    def __init__(self, width: float = 0.0, height: float = 0.0, depth: float = 0.0,
                 italic: float = 0.0, char: str | None = None):
        self.width, self.height, self.depth = width, height, depth
        self.items: list = []
        self.italic = italic  # (how far the ink leans out past the width)
        self.char = char  # (a single glyph's font: scripts and accents sit by its shape)

    def add(self, x: float, y: float, thing) -> None:
        self.items.append((x, y, thing))
        if isinstance(thing, Box):
            height, depth = thing.height - y, thing.depth + y
        else:
            height, depth = _extent(thing)
            height, depth = height - y, depth + y
        self.height = max(self.height, height)
        self.depth = max(self.depth, depth)

    def flatten(self, x: float, y: float, out: list) -> None:
        for dx, dy, thing in self.items:
            if isinstance(thing, Box):
                thing.flatten(x + dx, y + dy, out)
            else:
                out.append(_moved(thing, x + dx, y + dy))


# --- the parse tree ----------------------------------------------------------------------------

@dataclass(slots=True)
class Atom:
    kind: str  # ord op bin rel open close punct inner
    nucleus: object
    sup: list | None = None
    sub: list | None = None
    limits: bool | None = None  # (operators: None = below and above when displayed)
    color: str | None = None


@dataclass(slots=True)
class Sym:
    text: str
    font: str  # rm it bf bfit tt


@dataclass(slots=True)
class BigOp:
    text: str
    family: str  # "sum" or "int"


@dataclass(slots=True)
class Frac:
    num: list
    den: list
    bar: bool = True
    style: int | None = None  # (\dfrac: display, \tfrac: text)
    left: str = ""
    right: str = ""


@dataclass(slots=True)
class Radical:
    body: list
    index: list | None = None


@dataclass(slots=True)
class Delimited:
    left: str
    body: list
    right: str


@dataclass(slots=True)
class Middle:
    delimiter: str


@dataclass(slots=True)
class SizedDelim:
    delimiter: str
    size: float = 0.0  # (pixels; or)
    level: int = 0  # (\big 1 to \Bigg 4)


@dataclass(slots=True)
class Accent:
    name: str
    body: list


@dataclass(slots=True)
class Decoration:
    name: str  # overline underline over...arrow underbrace overbrace cancel boxed phantom
    body: list


@dataclass(slots=True)
class Stack:
    base: list
    over: list | None = None
    under: list | None = None


@dataclass(slots=True)
class Array:
    env: str
    rows: list
    aligns: list | None = None


@dataclass(slots=True)
class TextRun:
    text: str
    font: str


@dataclass(slots=True)
class Negated:
    nucleus: object


@dataclass(slots=True)
class Space:
    mu: float


@dataclass(slots=True)
class StyleSet:
    size: int


# --- the symbols -------------------------------------------------------------------------------

def _table(pairs: str) -> dict[str, str]:
    parts = pairs.split()
    return dict(zip(parts[::2], parts[1::2]))


_GREEK = _table(
    "alpha α beta β gamma γ delta δ epsilon ϵ varepsilon ε zeta ζ eta η theta θ vartheta ϑ "
    "iota ι kappa κ lambda λ mu μ nu ν xi ξ omicron ο pi π varpi ϖ rho ρ varrho ϱ sigma σ "
    "varsigma ς tau τ upsilon υ phi ϕ varphi φ chi χ psi ψ omega ω digamma ϝ "
    "Gamma Γ Delta Δ Theta Θ Lambda Λ Xi Ξ Pi Π Sigma Σ Upsilon Υ Phi Φ Psi Ψ Omega Ω")

_SYMBOLS: dict[str, tuple[str, str]] = {}
for _kind, _pairs in (
        ("ord", "infty ∞ partial ∂ nabla ∇ emptyset ∅ varnothing ∅ forall ∀ exists ∃ "
                "nexists ∄ neg ¬ lnot ¬ angle ∠ measuredangle ∡ triangle △ square □ Box □ "
                "degree ° prime ′ ldots … dots … cdots ⋯ dotsb ⋯ dotsc … vdots ⋮ ddots ⋱ "
                "hbar ℏ ell ℓ Re ℜ Im ℑ aleph ℵ wp ℘ top ⊤ bot ⊥ surd √ flat ♭ sharp ♯ "
                "natural ♮ clubsuit ♣ diamondsuit ♢ heartsuit ♡ spadesuit ♠ checkmark ✓ "
                "S § P ¶ copyright © pounds £ euro € backslash \\ vert | Vert ‖ imath ı "
                "jmath ȷ infin ∞ circledR ®"),
        ("bin", "pm ± mp ∓ times × div ÷ cdot · ast ∗ star ⋆ circ ∘ bullet • cup ∪ cap ∩ "
                "setminus ∖ smallsetminus ∖ wedge ∧ land ∧ vee ∨ lor ∨ oplus ⊕ ominus ⊖ "
                "otimes ⊗ odot ⊙ oslash ⊘ uplus ⊎ sqcup ⊔ sqcap ⊓ triangleleft ◁ "
                "triangleright ▷ wr ≀ amalg ⨿ dagger † ddagger ‡ diamond ⋄ bigcirc ◯ "
                "centerdot ·"),
        ("rel", "le ≤ leq ≤ ge ≥ geq ≥ leqslant ⩽ geqslant ⩾ ne ≠ neq ≠ approx ≈ sim ∼ "
                "simeq ≃ cong ≅ equiv ≡ propto ∝ in ∈ notin ∉ ni ∋ owns ∋ subset ⊂ "
                "subseteq ⊆ supset ⊃ supseteq ⊇ subsetneq ⊊ supsetneq ⊋ nsubseteq ⊈ "
                "nsupseteq ⊉ sqsubseteq ⊑ sqsupseteq ⊒ sqsubset ⊏ sqsupset ⊐ parallel ∥ "
                "nparallel ∦ perp ⊥ mid ∣ nmid ∤ to → rightarrow → leftarrow ← gets ← "
                "leftrightarrow ↔ Rightarrow ⇒ Leftarrow ⇐ Leftrightarrow ⇔ implies ⟹ "
                "impliedby ⟸ iff ⟺ mapsto ↦ longmapsto ⟼ longrightarrow ⟶ longleftarrow ⟵ "
                "longleftrightarrow ⟷ Longrightarrow ⟹ Longleftarrow ⟸ Longleftrightarrow ⟺ "
                "uparrow ↑ downarrow ↓ updownarrow ↕ Uparrow ⇑ Downarrow ⇓ nearrow ↗ "
                "searrow ↘ swarrow ↙ nwarrow ↖ hookrightarrow ↪ hookleftarrow ↩ "
                "rightleftharpoons ⇌ leftrightharpoons ⇋ rightharpoonup ⇀ ll ≪ gg ≫ lll ⋘ "
                "ggg ⋙ prec ≺ succ ≻ preceq ⪯ succeq ⪰ models ⊨ vdash ⊢ dashv ⊣ asymp ≍ "
                "doteq ≐ bowtie ⋈ smile ⌣ frown ⌢ lesssim ≲ gtrsim ≳ ncong ≇ nsim ≁ "
                "nleq ≰ ngeq ≱ nless ≮ ngtr ≯ therefore ∴ because ∵ coloneqq ≔ approxeq ≊ "
                "triangleq ≜ nequiv ≢"),
        ("open", "langle ⟨ lfloor ⌊ lceil ⌈ lbrace { lbrack [ lvert | lVert ‖ lgroup ⟮"),
        ("close", "rangle ⟩ rfloor ⌋ rceil ⌉ rbrace } rbrack ] rvert | rVert ‖ rgroup ⟯"),
        ("punct", "colon : ldotp .")):
    for _name, _char in _table(_pairs).items():
        _SYMBOLS[_name] = (_char, _kind)

_BY_CHAR: dict[str, str] = {}  # (a symbol typed as itself: its class)
for _char, _kind in _SYMBOLS.values():
    _BY_CHAR.setdefault(_char, _kind)
_BY_CHAR.update({"−": "bin", "–": "bin", "=": "rel", "<": "rel", ">": "rel", "+": "bin"})

_BIG_OPERATORS = {name: (char, "sum") for name, char in _table(
    "sum ∑ prod ∏ coprod ∐ bigcup ⋃ bigcap ⋂ bigvee ⋁ bigwedge ⋀ bigoplus ⨁ "
    "bigotimes ⨂ bigodot ⨀ biguplus ⨄ bigsqcup ⨆").items()}
_BIG_OPERATORS.update({name: (char, "int") for name, char in _table(
    "int ∫ iint ∬ iiint ∭ oint ∮ oiint ∯").items()})
for _name, (_char, _family) in list(_BIG_OPERATORS.items()):
    _BY_CHAR[_char] = "op"

_FUNCTIONS = set("arccos arcsin arctan arg cos cosh cot coth csc csch deg dim exp hom ker lg "
                 "ln log sec sech sin sinh tan tanh".split())
_LIMIT_FUNCTIONS = {"det": "det", "gcd": "gcd", "inf": "inf", "lim": "lim",
                    "liminf": "lim inf", "limsup": "lim sup", "max": "max", "min": "min",
                    "Pr": "Pr", "sup": "sup", "injlim": "inj lim", "projlim": "proj lim"}

_DELIMITERS = {"(": "(", ")": ")", "[": "[", "]": "]", "|": "|", "/": "/", ".": "",
               "<": "⟨", ">": "⟩", "⟨": "⟨", "⟩": "⟩", "‖": "‖", "⌊": "⌊", "⌋": "⌋",
               "⌈": "⌈", "⌉": "⌉"}
_DELIMITER_COMMANDS = {"{": "{", "}": "}", "lbrace": "{", "rbrace": "}", "langle": "⟨",
                       "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈",
                       "rceil": "⌉", "vert": "|", "lvert": "|", "rvert": "|", "Vert": "‖",
                       "lVert": "‖", "rVert": "‖", "|": "‖", "backslash": "\\",
                       "lbrack": "[", "rbrack": "]", "mid": "|"}
_BIG = {"big": 1, "Big": 2, "bigg": 3, "Bigg": 4}
_BIG_SIZES = (0, 1.2, 1.8, 2.4, 3.0)  # (ems)

_NEGATIONS = {"=": "≠", "<": "≮", ">": "≯", "≤": "≰", "≥": "≱", "∈": "∉", "≡": "≢",
              "⊂": "⊄", "⊃": "⊅", "⊆": "⊈", "⊇": "⊉", "∼": "≁", "≅": "≇", "≈": "≉",
              "∣": "∤", "∥": "∦", "∃": "∄", "∋": "∌"}

_ACCENTS = {"hat", "widehat", "check", "widecheck", "tilde", "widetilde", "bar", "dot",
            "ddot", "dddot", "vec", "acute", "grave", "breve", "mathring"}
_DECORATIONS = {"overline", "underline", "overrightarrow", "overleftarrow",
                "overleftrightarrow", "underrightarrow", "underleftarrow",
                "underleftrightarrow", "overbrace", "underbrace", "cancel", "bcancel",
                "xcancel", "boxed", "phantom"}

_SPACES = {",": 3, ":": 4, ">": 4, ";": 5, "!": -3, " ": 6, "quad": 18, "qquad": 36,
           "enspace": 9, "thinspace": 3, "medspace": 4, "thickspace": 5, "negthinspace": -3,
           "negmedspace": -4, "negthickspace": -5, "space": 6, "nobreakspace": 6}

D, T, S, SS = 0, 1, 2, 3
_STYLES = {"displaystyle": D, "textstyle": T, "scriptstyle": S, "scriptscriptstyle": SS}

_FONTS = {"mathrm": "rm", "mathbf": "bf", "mathit": "it", "mathsf": "rm", "mathtt": "tt",
          "mathbb": "bb", "mathcal": "cal", "mathscr": "cal", "boldsymbol": "bsym",
          "bm": "bsym", "mathnormal": None}
_TEXT_FONTS = {"text": "rm", "textrm": "rm", "mbox": "rm", "textnormal": "rm", "textup": "rm",
               "textbf": "bf", "textit": "it", "emph": "it", "texttt": "tt", "textsf": "rm"}

_MATRICES = {"matrix": ("", ""), "pmatrix": ("(", ")"), "bmatrix": ("[", "]"),
             "Bmatrix": ("{", "}"), "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"),
             "smallmatrix": ("", "")}
_ENVIRONMENTS = set(_MATRICES) | {"array", "cases", "dcases", "rcases", "aligned", "align",
                                  "align*", "split", "gathered", "gather", "gather*"}

_PRIMES = {1: "′", 2: "″", 3: "‴"}
_BB_BMP = {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}
_CAL_BMP = {"B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ", "M": "ℳ",
            "R": "ℛ", "e": "ℯ", "g": "ℊ", "o": "ℴ"}


def _letter_in(font: str, char: str) -> str:
    """A letter (or digit) in the blackboard or calligraphic alphabet."""
    if font == "bb":
        if char in _BB_BMP:
            return _BB_BMP[char]
        if "A" <= char <= "Z":
            return chr(0x1D538 + ord(char) - ord("A"))
        if "a" <= char <= "z":
            return chr(0x1D552 + ord(char) - ord("a"))
        if "0" <= char <= "9":
            return chr(0x1D7D8 + ord(char) - ord("0"))
    elif font == "cal":
        if char in _CAL_BMP:
            return _CAL_BMP[char]
        if "A" <= char <= "Z":
            return chr(0x1D49C + ord(char) - ord("A"))
        if "a" <= char <= "z":
            return chr(0x1D4B6 + ord(char) - ord("a"))
    return char


# --- the parser --------------------------------------------------------------------------------

_END = ("end", None)


class _Parser:
    def __init__(self, source: str):
        self.s = source
        self.i = 0
        self.font: str | None = None  # (\mathrm{...} and the like)
        self.color: str | None = None
        self.lefts = 0  # (\left nesting: \middle needs one)

    def error(self, message: str):
        raise TexError(message, self.i)

    # -- tokens --
    def skip_spaces(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def next(self) -> tuple[str, str | None]:
        self.skip_spaces()
        s, i = self.s, self.i
        if i >= len(s):
            return _END
        if s[i] == "\\":
            if i + 1 >= len(s):
                self.i = len(s)
                self.error("a lone \\ at the end")
            j = i + 1
            if s[j].isalpha() and s[j].isascii():
                while j < len(s) and s[j].isalpha() and s[j].isascii():
                    j += 1
                name = s[i + 1:j]
                if j < len(s) and s[j] == "*" and name in ("operatorname", "align", "gather"):
                    j += 1
                    name += "*"
                self.i = j
                return ("cmd", name)
            self.i = j + 1
            return ("cmd", s[j])
        self.i = i + 1
        return ("char", s[i])

    def peek(self) -> tuple[str, str | None]:
        i = self.i
        try:
            return self.next()
        finally:
            self.i = i

    @contextmanager
    def group(self):
        saved = self.font, self.color
        try:
            yield
        finally:
            self.font, self.color = saved

    # -- lists --
    def math_list(self, stops: tuple, missing: str) -> list:
        items: list = []
        while True:
            token = self.peek()
            if token in stops:
                return items
            if token == _END:
                self.error(missing)
            self.item(items)

    def expect(self, token: tuple, message: str) -> None:
        if self.next() != token:
            self.error(message)

    def argument(self, what: str = "an argument") -> list:
        token = self.peek()
        if token == ("char", "{"):
            self.next()
            with self.group():
                items = self.math_list((("char", "}"),), "a { without its }")
            self.next()
            return items
        if token == _END or token in (("char", "}"), ("char", "&"), ("char", "^"),
                                      ("char", "_"), ("cmd", "\\")):
            self.error(f"missing {what}")
        self.next()
        return [self.single(token)]

    def raw_argument(self, what: str = "an argument") -> str:
        """The text between braces as it is (\\text, \\color, environments' names)."""
        self.skip_spaces()
        s = self.s
        if self.i >= len(s) or s[self.i] != "{":
            if self.i < len(s) and s[self.i] not in "}\\":
                self.i += 1
                return s[self.i - 1]
            self.error(f"missing {what}")
        depth, j = 0, self.i
        while j < len(s):
            ch = s[j]
            if ch == "\\":
                j += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = s[self.i + 1:j]
                    self.i = j + 1
                    return text
            j += 1
        self.i = len(s)
        self.error("a { without its }")

    def atom(self, kind: str, nucleus, **values) -> Atom:
        return Atom(kind, nucleus, color=self.color, **values)

    def item(self, items: list) -> None:
        start = self.i
        token = self.next()
        kind, value = token
        if kind == "char":
            if value in "^_":
                self.script(items, value)
                return
            if value == "'":
                count = 1
                while self.s.startswith("'", self.i):
                    self.i += 1
                    count += 1
                text = _PRIMES.get(count, "′" * count)
                items.append(self.atom("ord", Sym(text, "rm")))
                return
            if value == "~":
                items.append(Space(6))
                return
            if value == "}":
                self.error("a } without its {")
            if value == "&":
                self.error("& is only for matrices, cases and aligned")
        else:
            if value in ("limits", "nolimits"):
                last = items[-1] if items else None
                if not isinstance(last, Atom) or last.kind != "op":
                    self.error(f"\\{value} only follows an operator (\\sum, \\int...)")
                last.limits = value == "limits"
                return
            if value == "color":
                self.color = self.raw_argument("a colour").strip()
                return
            if value in _STYLES:
                items.append(StyleSet(_STYLES[value]))
                return
            if value in _SPACES:
                items.append(Space(_SPACES[value]))
                return
            if value == "middle":
                if not self.lefts:
                    self.error("\\middle without \\left")
                items.append(Middle(self.delimiter("\\middle")))
                return
            if value in ("pmod", "mod"):
                argument = self.argument()
                items.append(Space(8))
                if value == "pmod":
                    items.append(self.atom("open", Sym("(", "rm")))
                items.append(self.atom("ord", Sym("mod", "rm")))
                items.append(Space(6))
                items.append(self.atom("ord", argument))
                if value == "pmod":
                    items.append(self.atom("close", Sym(")", "rm")))
                return
            if value == "\\":
                self.error("\\\\ is only for the rows of matrices, cases and aligned")
            if value in ("right", "end"):
                self.i = start
                self.next()
                self.error(f"\\{value} without \\{'left' if value == 'right' else 'begin'}")
        items.append(self.single(token))

    def script(self, items: list, which: str) -> None:
        last = items[-1] if items and isinstance(items[-1], Atom) else None
        if last is None:
            last = self.atom("ord", [])
            items.append(last)
        argument = self.argument("a superscript" if which == "^" else "a subscript")
        if which == "^":
            if last.sup is not None:
                self.error("two superscripts (put braces around one: {x^a}^b)")
            last.sup = argument
        else:
            if last.sub is not None:
                self.error("two subscripts (put braces around one: {x_a}_b)")
            last.sub = argument

    def letter(self, char: str) -> Sym:
        font = self.font
        if font in ("bb", "cal"):
            return Sym(_letter_in(font, char), "rm")
        if font == "bsym":
            return Sym(char, "bfit" if char.isalpha() else "bf")
        if font is not None:
            return Sym(char, font)
        return Sym(char, "it" if char.isalpha() else "rm")

    def single(self, token: tuple) -> Atom:
        """One thing: a symbol, a group, a command with its arguments."""
        kind, value = token
        if kind == "char":
            return self.character(value)
        if value in _GREEK:
            char = _GREEK[value]
            upright = char.isupper() or self.font in ("rm", "bf")
            font = self.font if self.font in ("rm", "bf", "bfit", "tt") else \
                ("bfit" if self.font == "bsym" and not upright else
                 "bf" if self.font == "bsym" else "rm" if upright else "it")
            return self.atom("ord", Sym(char, font))
        if value in _SYMBOLS:
            char, cls = _SYMBOLS[value]
            return self.atom(cls, Sym(char, "bf" if self.font in ("bf", "bsym") else "rm"))
        if value in "%$#&_":
            return self.atom("ord", Sym(value, "rm"))
        if value == "|":
            return self.atom("ord", Sym("‖", "rm"))
        if value == "{":
            return self.atom("open", Sym("{", "rm"))
        if value == "}":
            return self.atom("close", Sym("}", "rm"))
        if value in _BIG_OPERATORS:
            char, family = _BIG_OPERATORS[value]
            return self.atom("op", BigOp(char, family), limits=False if family == "int" else None)
        if value in _FUNCTIONS:
            return self.atom("op", Sym(value, "rm"), limits=False)
        if value in _LIMIT_FUNCTIONS:
            return self.atom("op", Sym(_LIMIT_FUNCTIONS[value], "rm"))
        if value in ("operatorname", "operatorname*"):
            name = self.raw_argument("an operator's name").strip()
            return self.atom("op", Sym(name, "rm"), limits=None if value.endswith("*") else False)
        if value in ("frac", "dfrac", "tfrac", "cfrac", "binom", "dbinom", "tbinom"):
            num = self.argument("a numerator")
            den = self.argument("a denominator")
            style = D if value in ("dfrac", "cfrac", "dbinom") else \
                T if value in ("tfrac", "tbinom") else None
            if value.endswith("binom"):
                return self.atom("ord", Frac(num, den, False, style, "(", ")"))
            return self.atom("ord", Frac(num, den, True, style))
        if value == "sqrt":
            index = None
            if self.peek() == ("char", "["):
                self.next()
                with self.group():
                    index = self.math_list((("char", "]"),), "a [ without its ]")
                self.next()
            return self.atom("ord", Radical(self.argument("what is under the root"), index))
        if value == "left":
            left = self.delimiter("\\left")
            self.lefts += 1
            with self.group():
                body = self.math_list((("cmd", "right"),), "\\left without \\right")
            self.lefts -= 1
            self.next()
            right = self.delimiter("\\right")
            return self.atom("inner", Delimited(left, body, right))
        base = value.rstrip("lrm") if value.rstrip("lrm") in _BIG else value
        if base in _BIG:
            suffix = value[len(base):]
            cls = {"l": "open", "r": "close", "m": "rel"}.get(suffix, "ord")
            return self.atom(cls, SizedDelim(self.delimiter(f"\\{value}"), level=_BIG[base]))
        if value in _ACCENTS:
            return self.atom("ord", Accent(value, self.argument()))
        if value in _DECORATIONS:
            body = self.argument()
            if value in ("overbrace", "underbrace"):
                return self.atom("op", Decoration(value, body), limits=True)
            return self.atom("ord", Decoration(value, body))
        if value in ("overset", "underset", "stackrel"):
            script = self.argument()
            base_list = self.argument()
            cls = base_list[0].kind if len(base_list) == 1 and isinstance(base_list[0], Atom) \
                and base_list[0].kind in ("rel", "bin") else "ord"
            if value == "stackrel":
                cls = "rel"
            if value == "underset":
                return self.atom(cls, Stack(base_list, under=script))
            return self.atom(cls, Stack(base_list, over=script))
        if value in _TEXT_FONTS:
            text = self.raw_argument("the text")
            text = re.sub(r"\\([{}$%&#_ ])", r"\1", text).replace("~", " ")
            text = re.sub(r"\s+", " ", text)
            return self.atom("ord", TextRun(text, _TEXT_FONTS[value]))
        if value in _FONTS:
            with self.group():
                self.font = _FONTS[value]
                body = self.argument()
            return self.atom("ord", body)
        if value == "textcolor":
            color = self.raw_argument("a colour").strip()
            with self.group():
                self.color = color
                body = self.argument()
                return self.atom("ord", body)
        if value == "not":
            token = self.peek()
            if token == _END:
                self.error("\\not without what it negates")
            self.next()
            negated = self.single(token)
            if isinstance(negated.nucleus, Sym) and negated.nucleus.text in _NEGATIONS:
                negated.nucleus = Sym(_NEGATIONS[negated.nucleus.text], negated.nucleus.font)
                return negated
            negated.nucleus = Negated(negated.nucleus)
            return negated
        if value == "begin":
            return self.environment()
        if value == "bmod":
            return self.atom("bin", Sym("mod", "rm"))
        self.i -= len(value) + 1
        self.error(f"unknown command \\{value}")

    def character(self, char: str) -> Atom:
        s, i = self.s, self.i
        if char == "{":
            with self.group():
                items = self.math_list((("char", "}"),), "a { without its }")
            self.next()
            return self.atom("ord", items)
        if char in "^_":
            self.error(f"missing the base of {char}")
        if char.isdigit() and char.isascii():
            return self.atom("ord", self.letter(char) if self.font in ("bb", "bf", "bsym", "tt")
                             else Sym(char, "rm"))
        if char.isascii() and char.isalpha():
            return self.atom("ord", self.letter(char))
        font = "bf" if self.font in ("bf", "bsym") else "rm"
        simple = {"+": ("bin", "+"), "-": ("bin", "−"), "*": ("bin", "∗"), "=": ("rel", "="),
                  "<": ("rel", "<"), ">": ("rel", ">"), ":": ("rel", ":"), "(": ("open", "("),
                  "[": ("open", "["), ")": ("close", ")"), "]": ("close", "]"),
                  "!": ("close", "!"), "?": ("close", "?"), ";": ("punct", ";"),
                  ".": ("ord", "."), "/": ("ord", "/"), "|": ("ord", "|")}
        if char in simple:
            cls, text = simple[char]
            return self.atom(cls, Sym(text, font))
        if char == ",":  # (between digits, a thousands separator: 1,000)
            between = i < len(s) and s[i].isdigit() and i >= 2 and s[i - 2].isdigit()
            return self.atom("ord" if between else "punct", Sym(",", font))
        if char in _BY_CHAR:
            return self.atom(_BY_CHAR[char], Sym(char, font) if _BY_CHAR[char] != "op" else
                             BigOp(char, "int" if char in "∫∬∭∮∯" else "sum"),
                             **({"limits": False} if char in "∫∬∭∮∯" else {}))
        if char.isalpha():
            upright = char.isupper() and unicodedata.name(char, "").startswith("GREEK")
            return self.atom("ord", Sym(char, "rm" if upright else "it"))
        return self.atom("ord", Sym(char, font))

    def delimiter(self, what: str) -> str:
        token = self.next()
        kind, value = token
        if kind == "char" and value in _DELIMITERS:
            return _DELIMITERS[value]
        if kind == "cmd" and value in _DELIMITER_COMMANDS:
            return _DELIMITER_COMMANDS[value]
        self.error(f"{what} needs a delimiter: ( ) [ ] \\{{ \\}} | \\| \\langle \\rangle . ...")

    def environment(self) -> Atom:
        name = self.raw_argument("an environment's name").strip()
        if name not in _ENVIRONMENTS:
            self.error(f"unknown environment {name}")
        aligns = None
        if name == "array":
            spec = self.raw_argument("the columns (l, c, r)")
            aligns = [c for c in re.sub(r"@\{[^}]*\}", "", spec) if c in "lcr"]
            if not aligns:
                self.error("an array needs its columns: \\begin{array}{cc}")
        rows: list[list] = [[]]
        stops = (("char", "&"), ("cmd", "\\"), ("cmd", "end"))
        while True:
            with self.group():
                cell = self.math_list(stops, f"\\begin{{{name}}} without \\end{{{name}}}")
            rows[-1].append(cell)
            token = self.next()
            if token == ("char", "&"):
                continue
            if token == ("cmd", "\\"):
                self.skip_spaces()
                if self.s.startswith("[", self.i):  # (\\[2pt]: the spacing is ignored)
                    end = self.s.find("]", self.i)
                    self.i = end + 1 if end >= 0 else len(self.s)
                rows.append([])
                continue
            end = self.raw_argument("an environment's name").strip()
            if end != name:
                self.error(f"\\begin{{{name}}} ended by \\end{{{end}}}")
            break
        if len(rows) > 1 and all(not cell for cell in rows[-1]):
            rows.pop()  # (a \\ before \end)
        delimited = name in _MATRICES and _MATRICES[name][0] or name.endswith("cases")
        return self.atom("inner" if delimited else "ord", Array(name, rows, aligns))


def parse(source: str) -> list:
    """A formula's math list (atoms, spaces, style changes); TexError if it
    can't be read."""
    parser = _Parser(source)
    items = parser.math_list((_END,), "")
    return items


# --- the layout --------------------------------------------------------------------------------

_SCALES = (1.0, 1.0, 0.7, 0.5)
_SIGMA = dict(num1=.677, num2=.394, num3=.444, denom1=.686, denom2=.345, sup1=.413,
              sup2=.363, sup3=.289, sub1=.150, sub2=.247, sup_drop=.386, sub_drop=.050,
              delim1=2.39, delim2=1.01)  # (Computer Modern's, in ems)
_BIG_OP_SPACING = (.111, .167, .200, .600, .100)

_CLASSES = ("ord", "op", "bin", "rel", "open", "close", "punct", "inner")
# TeX's spacing between atoms: 1 thin, 2 medium, 3 thick; negative: not in scripts
_SPACING = [[int(v.strip("()")) * (-1 if "(" in v else 1) if v != "*" else 0
             for v in row.split()] for row in (
    "0 1 (2) (3) 0 0 0 (1)",
    "1 1 * (3) 0 0 0 (1)",
    "(2) (2) * * (2) * * (2)",
    "(3) (3) * 0 (3) 0 0 (3)",
    "0 0 * 0 0 0 0 0",
    "0 1 (2) (3) 0 0 0 (1)",
    "(1) (1) * (1) (1) (1) (1) (1)",
    "(1) 1 (2) (3) (1) 0 (1) (1)")]
_MU = (0, 3, 4, 5)


class _Style(NamedTuple):
    size: int
    cramped: bool = False

    @property
    def scale(self) -> float:
        return _SCALES[self.size]

    def sup(self) -> "_Style":
        return _Style(S if self.size <= T else SS, self.cramped)

    def sub(self) -> "_Style":
        return _Style(S if self.size <= T else SS, True)

    def num(self) -> "_Style":
        return _Style(self.size + 1 if self.size < SS else SS, self.cramped)

    def den(self) -> "_Style":
        return _Style(self.size + 1 if self.size < SS else SS, True)

    def cramp(self) -> "_Style":
        return _Style(self.size, True)


class _Layout:
    """Laying out a math list with a font's metrics."""

    def __init__(self, metrics: Metrics):
        self.m = metrics
        self.em = metrics.em
        ratio = metrics.x_height(1.0) / (0.431 * self.em) if self.em else 1.0
        self.shift = min(1.25, max(0.9, ratio))  # (a font with taller small letters: higher scripts)

    def sigma(self, name: str, style: _Style) -> float:
        value = _SIGMA[name] * self.em * style.scale
        return value * self.shift if not name.startswith("delim") else value

    # -- lists --
    def hlist(self, items: list, style: _Style, color: str | None) -> Box:
        entries: list[list] = []  # [class or None, box, style]
        for item in items:
            if isinstance(item, StyleSet):
                style = _Style(item.size, style.cramped)
            elif isinstance(item, Space):
                entries.append([None, Box(item.mu * self.em * style.scale / 18), style])
            elif isinstance(item, Atom):
                entries.append([item.kind, self.atom(item, style, item.color or color), style])
        previous = None
        for entry in entries:  # (a binary operator with nothing to join is ordinary: -x)
            if entry[0] is None:
                continue
            if entry[0] == "bin" and (previous is None or
                                      previous[0] in ("bin", "op", "rel", "open", "punct")):
                entry[0] = "ord"
            if entry[0] in ("rel", "close", "punct") and previous is not None and \
                    previous[0] == "bin":
                previous[0] = "ord"
            previous = entry
        if previous is not None and previous[0] == "bin":
            previous[0] = "ord"
        box = Box()
        x, last = 0.0, None
        for cls, child, child_style in entries:
            if cls is not None:
                if last is not None:
                    amount = _SPACING[_CLASSES.index(last)][_CLASSES.index(cls)]
                    if amount > 0 or (amount < 0 and child_style.size <= T):
                        x += _MU[abs(amount)] * self.em * child_style.scale / 18
                last = cls
            box.add(x, 0.0, child)
            x += child.width
        box.width = x
        return box

    def atom(self, atom: Atom, style: _Style, color: str | None) -> Box:
        if atom.kind == "op":
            return self.operator(atom, style, color)
        box = self.nucleus(atom.nucleus, style, color)
        if atom.sup is None and atom.sub is None:
            if box.char in ("it", "bfit") and box.italic:
                box.width += box.italic
            return box
        return self.scripts(box, atom, style, color)

    def glyph(self, text: str, font: str, scale: float, color: str | None) -> Box:
        width, ascent, descent, italic = self.m.measure(text, font, scale)
        box = Box(width, ascent, descent, italic, font if len(text) == 1 else None)
        box.items.append((0.0, 0.0, Text(0.0, 0.0, text, font, scale, color)))
        return box

    def nucleus(self, nucleus, style: _Style, color: str | None) -> Box:
        if isinstance(nucleus, Sym):
            return self.glyph(nucleus.text, nucleus.font, style.scale, color)
        if isinstance(nucleus, list):
            return self.hlist(nucleus, style, color)
        if isinstance(nucleus, Frac):
            return self.fraction(nucleus, style, color)
        if isinstance(nucleus, Radical):
            return self.radical(nucleus, style, color)
        if isinstance(nucleus, Delimited):
            return self.delimited(nucleus, style, color)
        if isinstance(nucleus, SizedDelim):
            size = nucleus.size or _BIG_SIZES[nucleus.level] * self.em * style.scale
            return self.delimiter(nucleus.delimiter, size, style, color)
        if isinstance(nucleus, Accent):
            return self.accent(nucleus, style, color)
        if isinstance(nucleus, Decoration):
            return self.decoration(nucleus, style, color)
        if isinstance(nucleus, Stack):
            return self.stack(nucleus, style, color)
        if isinstance(nucleus, Array):
            return self.array(nucleus, style, color)
        if isinstance(nucleus, TextRun):
            box = self.glyph(nucleus.text, nucleus.font, style.scale, color)
            box.char = None
            return box
        if isinstance(nucleus, Negated):
            return self.negated(nucleus, style, color)
        if isinstance(nucleus, BigOp):
            return self.glyph(nucleus.text, "rm", style.scale, color)
        raise TexError(f"can't lay out {type(nucleus).__name__}")

    # -- scripts (TeX's rule 18) --
    def scripts(self, box: Box, atom: Atom, style: _Style, color: str | None) -> Box:
        m, scale = self.m, style.scale
        sup_style, sub_style = style.sup(), style.sub()
        if box.char:
            u = v = 0.0
        else:
            u = box.height - self.sigma("sup_drop", sup_style)
            v = box.depth + self.sigma("sub_drop", sub_style)
        x_height = m.x_height(scale)
        theta = m.rule_thickness(scale)
        result = Box()
        result.add(0.0, 0.0, box)
        end = box.width
        sub = self.hlist(atom.sub, sub_style, color) if atom.sub is not None else None
        sup = self.hlist(atom.sup, sup_style, color) if atom.sup is not None else None
        if sup is None:
            v = max(v, self.sigma("sub1", style), sub.height - 0.8 * x_height)
        else:
            p = self.sigma("sup1" if style.size == D and not style.cramped else
                           "sup3" if style.cramped else "sup2", style)
            u = max(u, p, sup.depth + x_height / 4)
            if sub is not None:
                v = max(v, self.sigma("sub2", style))
                gap = (u - sup.depth) - (sub.height - v)
                if gap < 4 * theta:
                    v += 4 * theta - gap
                    psi = 0.8 * x_height - (u - sup.depth)
                    if psi > 0:
                        u += psi
                        v -= psi
        script_space = 0.05 * self.em * scale
        if sup is not None:
            result.add(box.width + box.italic, -u, sup)
            end = max(end, box.width + box.italic + sup.width)
        if sub is not None:
            result.add(box.width, v, sub)
            end = max(end, box.width + sub.width)
        result.width = end + script_space
        return result

    # -- operators (rule 13) --
    def operator(self, atom: Atom, style: _Style, color: str | None) -> Box:
        nucleus = atom.nucleus
        scale = style.scale
        if isinstance(nucleus, BigOp):
            # (a text font's ∑ is about a capital's height: TeX's is taller)
            factor = {"sum": (1.9, 1.3), "int": (2.0, 1.35)}[nucleus.family][style.size != D]
            glyph = self.glyph(nucleus.text, "rm", scale * factor, color)
            shift = (glyph.height - glyph.depth) / 2 - self.m.axis_height(scale)
            box = Box(glyph.width, 0.0, 0.0, glyph.italic)
            box.add(0.0, shift, glyph)
        else:
            box = self.nucleus(nucleus, style, color)
            box.char = None
            if isinstance(nucleus, Sym):
                box.italic = 0.0
        limits = atom.limits if atom.limits is not None else style.size == D
        if atom.sup is None and atom.sub is None:
            box.width += box.italic
            return box
        if not limits:
            box.char = None
            return self.scripts(box, atom, style, color)
        sup = self.hlist(atom.sup, style.sup(), color) if atom.sup is not None else None
        sub = self.hlist(atom.sub, style.sub(), color) if atom.sub is not None else None
        width = max(box.width, sup.width if sup else 0.0, sub.width if sub else 0.0)
        delta = box.italic
        em = self.em * scale
        result = Box(width)
        result.add((width - box.width) / 2, 0.0, box)
        if sup is not None:
            gap = max(_BIG_OP_SPACING[0] * em, _BIG_OP_SPACING[2] * em - sup.depth)
            result.add((width - sup.width) / 2 + delta / 2, -(box.height + gap + sup.depth), sup)
            result.height += _BIG_OP_SPACING[4] * em
        if sub is not None:
            gap = max(_BIG_OP_SPACING[1] * em, _BIG_OP_SPACING[3] * em - sub.height)
            result.add((width - sub.width) / 2 - delta / 2, box.depth + gap + sub.height, sub)
            result.depth += _BIG_OP_SPACING[4] * em
        return result

    # -- fractions (rule 15) --
    def fraction(self, frac: Frac, style: _Style, color: str | None) -> Box:
        if frac.style is not None:
            style = _Style(frac.style, style.cramped)
        num = self.hlist(frac.num, style.num(), color)
        den = self.hlist(frac.den, style.den(), color)
        scale = style.scale
        rule = self.m.rule_thickness(scale)
        theta = rule if frac.bar else 0.0
        axis = self.m.axis_height(scale)
        display = style.size == D
        u = self.sigma("num1" if display else "num2" if frac.bar else "num3", style)
        v = self.sigma("denom1" if display else "denom2", style)
        if frac.bar:
            phi = 3 * theta if display else theta
            gap = (u - num.depth) - (axis + theta / 2)
            if gap < phi:
                u += phi - gap
            gap = (axis - theta / 2) - (den.height - v)
            if gap < phi:
                v += phi - gap
        else:
            phi = 7 * rule if display else 3 * rule
            psi = (u - num.depth) - (den.height - v)
            if psi < phi:
                u += (phi - psi) / 2
                v += (phi - psi) / 2
        width = max(num.width, den.width)
        pad = 0.0 if frac.left else 0.12 * self.em * scale
        box = Box(width + 2 * pad)
        box.add(pad + (width - num.width) / 2, -u, num)
        box.add(pad + (width - den.width) / 2, v, den)
        if frac.bar:
            box.add(0.0, 0.0, Rule(pad, -(axis + theta / 2), width, theta, color))
        if not frac.left:
            return box
        size = self.sigma("delim1" if display else "delim2", style)
        return self.row([self.delimiter(frac.left, size, style, color), box,
                         self.delimiter(frac.right, size, style, color)])

    @staticmethod
    def row(boxes: list) -> Box:
        result = Box()
        x = 0.0
        for box in boxes:
            result.add(x, 0.0, box)
            x += box.width
        result.width = x
        return result

    # -- roots (rule 11) --
    def radical(self, radical: Radical, style: _Style, color: str | None) -> Box:
        body = self.hlist(radical.body, style.cramp(), color)
        scale = style.scale
        em = self.em * scale
        theta = self.m.rule_thickness(scale)
        phi = theta + (self.m.x_height(scale) if style.size == D else theta) / 4
        need = body.height + body.depth + phi + theta
        total = max(need, 1.0 * em)
        phi += (total - need) / 2
        top = -(body.height + phi + theta)
        bottom = top + total
        width = em * (0.55 + min(0.35, 0.08 * max(0.0, total / em - 1)))
        surd = Box(width)
        hook = min(total, em)
        a = (0.06 * width, bottom - 0.45 * hook)
        b = (0.22 * width, bottom - 0.53 * hook)
        v = (0.5 * width, bottom)
        p = (width, top + theta / 2)
        for (x0, y0), (x1, y1), thickness in ((a, b, 1.1 * theta), (b, v, 2.4 * theta),
                                              (v, p, 1.05 * theta)):
            surd.add(0.0, 0.0, Shape((("M", x0, y0), ("L", x1, y1)), False, thickness, color))
        over = body.width + 0.06 * em
        surd.add(0.0, 0.0, Rule(width - 0.02 * em, top, over + 0.02 * em, theta, color))
        surd.add(width, 0.0, body)
        surd.width = width + over
        surd.height = max(surd.height, -top + theta)
        if radical.index is None:
            return surd
        index = self.hlist(radical.index, _Style(SS), color)
        mu = em / 18
        raise_ = 0.6 * (surd.height - surd.depth)
        result = Box()
        x = 5 * mu
        result.add(x, -raise_, index)
        x = max(0.0, x + index.width - 10 * mu)
        result.add(x, 0.0, surd)
        result.width = x + surd.width
        return result

    # -- delimiters (rule 19) --
    def delimited(self, delimited: Delimited, style: _Style, color: str | None) -> Box:
        plain = [item for item in delimited.body if not isinstance(item, Middle)]
        body = self.hlist(plain, style, color)
        size = self.delimiter_size(body, style)
        if len(plain) != len(delimited.body):
            body = self.hlist([Atom("ord", SizedDelim(item.delimiter, size), color=None)
                               if isinstance(item, Middle) else item
                               for item in delimited.body], style, color)
        return self.row([self.delimiter(delimited.left, size, style, color), body,
                         self.delimiter(delimited.right, size, style, color)])

    def delimiter_size(self, body: Box, style: _Style) -> float:
        axis = self.m.axis_height(style.scale)
        delta = max(body.height - axis, body.depth + axis)
        return max(2 * delta * 0.901, 2 * delta - 0.5 * self.em * style.scale)

    def delimiter(self, char: str, size: float, style: _Style, color: str | None) -> Box:
        """A delimiter at least ``size`` tall, centred on the axis: the font's
        glyph when that is tall enough, else drawn."""
        scale = style.scale
        em = self.em * scale
        if not char:
            return Box(0.12 * em)
        glyph = self.glyph(char, "rm", scale, color)
        glyph.char = None
        if size <= (glyph.height + glyph.depth) * 1.1:
            return glyph
        axis = self.m.axis_height(scale)
        top, bottom = -axis - size / 2, -axis + size / 2
        middle = -axis
        theta = self.m.rule_thickness(scale)
        thick = theta * min(3.2, 1.6 + 0.25 * size / em)
        thin = theta * 0.8
        tall = size / em
        box = Box()
        if char in "()":
            width = em * min(0.62, 0.38 + 0.05 * tall)
            end = width * 0.85
            mid = width * 0.12
            k = size * 0.3
            a = end - thin / 2
            c = (4 * mid - a) / 3
            a2 = end + thin / 2
            c2 = (4 * (mid + thick) - a2) / 3
            commands = [("M", a, top), ("C", c, top + k, c, bottom - k, a, bottom),
                        ("L", a2, bottom), ("C", c2, bottom - k, c2, top + k, a2, top), ("Z",)]
            if char == ")":
                commands = [_mirror(command, width) for command in commands]
            box.add(0.0, 0.0, Shape(tuple(commands), True, 0.0, color))
        elif char in "[]⌊⌋⌈⌉":
            width = em * 0.4
            left = char in "[⌊⌈"
            x0 = width * 0.3 if left else width * 0.7 - thick * 0.8
            box.add(0.0, 0.0, Rule(x0, top, thick * 0.8, size, color))
            arm = width * 0.5
            ax = x0 if left else x0 + thick * 0.8 - arm
            if char in "[]⌈⌉":
                box.add(0.0, 0.0, Rule(ax, top, arm, thin * 1.3, color))
            if char in "[]⌊⌋":
                box.add(0.0, 0.0, Rule(ax, bottom - thin * 1.3, arm, thin * 1.3, color))
        elif char in "{}":
            width = em * 0.55
            x_tip, x_mid, x_end = width * 0.12, width * 0.5, width * 0.88
            r = min(0.12 * size, 0.3 * em)
            commands = [("M", x_end, top), ("C", x_mid, top, x_mid, top, x_mid, top + r),
                        ("L", x_mid, middle - r),
                        ("C", x_mid, middle - r * 0.2, x_tip + (x_mid - x_tip) * 0.3, middle,
                         x_tip, middle),
                        ("C", x_tip + (x_mid - x_tip) * 0.3, middle, x_mid, middle + r * 0.2,
                         x_mid, middle + r),
                        ("L", x_mid, bottom - r),
                        ("C", x_mid, bottom, x_mid, bottom, x_end, bottom)]
            if char == "}":
                commands = [_mirror(command, width) for command in commands]
            box.add(0.0, 0.0, Shape(tuple(commands), False, thick * 0.75, color, "flat"))
        elif char in "|‖":
            width = em * (0.3 if char == "|" else 0.5)
            bars = (0.5,) if char == "|" else (0.32, 0.68)
            for at in bars:
                box.add(0.0, 0.0, Rule(width * at - thick * 0.3, top, thick * 0.6, size, color))
        elif char in "⟨⟩":
            width = em * min(0.6, 0.4 + 0.04 * tall)
            commands = [("M", width * 0.85, top), ("L", width * 0.15, middle),
                        ("L", width * 0.85, bottom)]
            if char == "⟩":
                commands = [_mirror(command, width) for command in commands]
            box.add(0.0, 0.0, Shape(tuple(commands), False, theta * 1.2, color))
        elif char in "/\\":
            width = min(size * 0.45, em * 1.2)
            commands = [("M", width * 0.9, top), ("L", width * 0.1, bottom)]
            if char == "\\":
                commands = [_mirror(command, width) for command in commands]
            box.add(0.0, 0.0, Shape(tuple(commands), False, theta * 1.2, color))
        else:
            return glyph
        box.width = width
        box.height = max(box.height, -top)
        box.depth = max(box.depth, bottom)
        return box

    # -- accents --
    def accent(self, accent: Accent, style: _Style, color: str | None) -> Box:
        body = self.hlist(accent.body, style.cramp(), color)
        scale = style.scale
        em = self.em * scale
        theta = self.m.rule_thickness(scale)
        single = len(accent.body) == 1 and isinstance(accent.body[0], Atom) and \
            isinstance(accent.body[0].nucleus, Sym) and accent.body[0].sup is None and \
            accent.body[0].sub is None and accent.body[0].nucleus.font in ("it", "bfit")
        name = accent.name
        wide = name.startswith("wide")
        cx = body.width / 2 + (0.1 * body.height if single else 0.0)
        base = -(max(body.height, self.m.x_height(scale)) + 0.08 * em)
        width = max(body.width, 0.5 * em) if wide else 0.42 * em
        x0, x1 = cx - width / 2, cx + width / 2
        box = Box(body.width)
        box.add(0.0, 0.0, body)
        stroke = theta * 1.15
        if name in ("hat", "widehat", "check", "widecheck"):
            height = 0.2 * em + (0.04 * width if wide else 0.0)
            peak, foot = (base - height, base) if "hat" in name else (base, base - height)
            box.add(0.0, 0.0, Shape((("M", x0, foot), ("L", cx, peak), ("L", x1, foot)),
                                    False, stroke, color))
        elif name in ("tilde", "widetilde"):
            height = 0.12 * em + (0.03 * width if wide else 0.0)
            box.add(0.0, 0.0, Shape((("M", x0, base - height * 0.25),
                                     ("C", x0 + width * 0.33, base - height * 1.45,
                                      x0 + width * 0.67, base + height * 0.45,
                                      x1, base - height * 0.75)), False, stroke * 1.1, color))
        elif name == "bar":
            width = max(0.42 * em, min(body.width, 0.6 * em))
            box.add(0.0, 0.0, Rule(cx - width / 2, base - theta, width, theta * 1.1, color))
        elif name in ("dot", "ddot", "dddot"):
            r = 0.065 * em
            count = {"dot": 1, "ddot": 2, "dddot": 3}[name]
            for k in range(count):
                x = cx + (k - (count - 1) / 2) * 0.22 * em
                box.add(0.0, 0.0, Shape(_circle(x, base - r, r), True, 0.0, color))
        elif name == "vec":
            y = base - 0.08 * em
            box.add(0.0, 0.0, _arrow(x0, x1, y, em, stroke, color, right=True))
        elif name in ("acute", "grave"):
            commands = (("M", cx - 0.07 * em, base), ("L", cx + 0.09 * em, base - 0.2 * em))
            if name == "grave":
                commands = tuple(_mirror(command, 2 * cx) for command in commands)
            box.add(0.0, 0.0, Shape(commands, False, stroke * 1.2, color))
        elif name == "breve":
            box.add(0.0, 0.0, Shape((("M", cx - 0.17 * em, base - 0.18 * em),
                                     ("C", cx - 0.15 * em, base + 0.02 * em,
                                      cx + 0.15 * em, base + 0.02 * em,
                                      cx + 0.17 * em, base - 0.18 * em)), False, stroke, color))
        elif name == "mathring":
            r = 0.08 * em
            box.add(0.0, 0.0, Shape(_circle(cx, base - r, r), False, stroke, color))
        return box

    def decoration(self, decoration: Decoration, style: _Style, color: str | None) -> Box:
        name = decoration.name
        if name == "boxed":
            style = _Style(D)
        cramped = style.cramp() if name == "overline" else style
        body = self.hlist(decoration.body, cramped, color)
        scale = style.scale
        em = self.em * scale
        theta = self.m.rule_thickness(scale)
        box = Box(body.width)
        if name == "phantom":
            box.height, box.depth = body.height, body.depth
            return box
        if name == "boxed":
            pad = 0.3 * em
            frame = Box(body.width + 2 * (pad + theta))
            frame.add(pad + theta, 0.0, body)
            top, bottom = -(body.height + pad + theta), body.depth + pad + theta
            for rule in (Rule(0.0, top, frame.width, theta, color),
                         Rule(0.0, bottom - theta, frame.width, theta, color),
                         Rule(0.0, top, theta, bottom - top, color),
                         Rule(frame.width - theta, top, theta, bottom - top, color)):
                frame.add(0.0, 0.0, rule)
            return frame
        box.add(0.0, 0.0, body)
        if name == "overline":
            box.add(0.0, 0.0, Rule(0.0, -(body.height + 4 * theta), body.width, theta, color))
            box.height = body.height + 5 * theta
        elif name == "underline":
            box.add(0.0, 0.0, Rule(0.0, body.depth + 3 * theta, body.width, theta, color))
            box.depth = body.depth + 5 * theta
        elif name.endswith("arrow"):
            over = name.startswith("over")
            width = max(body.width, 0.6 * em)
            x0 = (body.width - width) / 2
            if over:
                y = -(max(body.height, self.m.x_height(scale)) + 0.2 * em)
            else:
                y = body.depth + 0.2 * em
            both = "leftright" in name
            box.add(0.0, 0.0, _arrow(x0, x0 + width, y, em, theta * 1.15, color,
                                     right="right" in name, left="left" in name or both))
            if over:
                box.height = max(box.height, -y + 0.12 * em)
            else:
                box.depth = max(box.depth, y + 0.12 * em)
        elif name in ("overbrace", "underbrace"):
            depth = 0.28 * em
            gap = 0.1 * em
            if name == "underbrace":
                edge, tip = body.depth + gap, body.depth + gap + depth
            else:
                edge, tip = -(body.height + gap), -(body.height + gap + depth)
            box.add(0.0, 0.0, _horizontal_brace(0.0, body.width, edge, tip, theta * 1.6, color))
        elif name in ("cancel", "bcancel", "xcancel"):
            low, high = body.depth + 0.05 * em, -(body.height + 0.05 * em)
            if name in ("cancel", "xcancel"):
                box.add(0.0, 0.0, Shape((("M", 0.0, low), ("L", body.width, high)), False,
                                        theta * 1.1, color))
            if name in ("bcancel", "xcancel"):
                box.add(0.0, 0.0, Shape((("M", 0.0, high), ("L", body.width, low)), False,
                                        theta * 1.1, color))
        return box

    def stack(self, stack: Stack, style: _Style, color: str | None) -> Box:
        base = self.hlist(stack.base, style, color)
        em = self.em * style.scale
        script = self.hlist(stack.over if stack.over is not None else stack.under,
                            style.sup(), color)
        width = max(base.width, script.width)
        box = Box(width)
        box.add((width - base.width) / 2, 0.0, base)
        gap = 0.12 * em
        if stack.over is not None:
            box.add((width - script.width) / 2, -(base.height + gap + script.depth), script)
        else:
            box.add((width - script.width) / 2, base.depth + gap + script.height, script)
        return box

    def negated(self, negated: Negated, style: _Style, color: str | None) -> Box:
        box = self.nucleus(negated.nucleus, style, color)
        theta = self.m.rule_thickness(style.scale)
        em = self.em * style.scale
        result = Box(box.width)
        result.add(0.0, 0.0, box)
        low = max(box.depth, 0.1 * em)
        high = -max(box.height, 0.6 * em)
        result.add(0.0, 0.0, Shape((("M", box.width * 0.3, low), ("L", box.width * 0.7, high)),
                                   False, theta * 1.2, color))
        return result

    # -- matrices, cases, aligned --
    def array(self, array: Array, style: _Style, color: str | None) -> Box:
        env = array.env
        cell_style = _Style(S) if env == "smallmatrix" else \
            _Style(D) if env in ("aligned", "align", "align*", "split", "gathered", "gather",
                                 "gather*", "dcases") else _Style(T)
        em = self.em * cell_style.scale
        aligned = env in ("aligned", "align", "align*", "split")
        columns = max((len(row) for row in array.rows), default=0)
        if aligned:
            aligns = ["r" if k % 2 == 0 else "l" for k in range(columns)]
        elif env.endswith("cases"):
            aligns = ["l"] * columns
        elif array.aligns:
            aligns = array.aligns + ["c"] * max(0, columns - len(array.aligns))
        else:
            aligns = ["c"] * columns
        cells = []
        for row in array.rows:
            boxes = []
            for k, cell in enumerate(row):
                if aligned and k % 2 == 1:  # ({}=: a relation spaced as after something)
                    cell = [Atom("ord", [])] + cell
                boxes.append(self.hlist(cell, cell_style, color))
            cells.append(boxes)
        widths = [max((row[k].width for row in cells if k < len(row)), default=0.0)
                  for k in range(columns)]
        gap = 0.33 * em if env == "smallmatrix" else em
        strut_height, strut_depth = 0.85 * em, 0.35 * em
        jot = 0.3 * em if aligned or env.startswith("gather") else 0.0
        if env == "smallmatrix":
            strut_height, strut_depth = 0.6 * em, 0.25 * em
        heights = [max([strut_height] + [b.height for b in row]) for row in cells]
        depths = [max([strut_depth] + [b.depth for b in row]) for row in cells]
        total = sum(heights) + sum(depths) + jot * max(0, len(cells) - 1)
        axis = self.m.axis_height(style.scale)
        y = -axis - total / 2
        box = Box()
        for r, row in enumerate(cells):
            y += heights[r]
            x = 0.0
            for k in range(columns):
                if k:
                    x += 0.0 if aligned and k % 2 == 1 else gap
                if k < len(row):
                    cell = row[k]
                    slack = widths[k] - cell.width
                    offset = 0.0 if aligns[k] == "l" else slack if aligns[k] == "r" else slack / 2
                    box.add(x + offset, y, cell)
                x += widths[k]
            box.width = max(box.width, x)
            y += depths[r] + jot
        box.height = max(box.height, axis + total / 2)
        box.depth = max(box.depth, total / 2 - axis)
        if env in _MATRICES:
            left, right = _MATRICES[env]
        elif env == "rcases":
            left, right = "", "}"
        elif env.endswith("cases"):
            left, right = "{", ""
        else:
            return box
        if not left and not right:
            return box
        size = self.delimiter_size(box, style)
        parts = [self.delimiter(left, size, style, color)]
        if env.endswith("cases") and left:
            parts.append(Box(3 * em / 18))
        parts.append(box)
        parts.append(self.delimiter(right, size, style, color))
        return self.row(parts)


def _mirror(command: tuple, width: float) -> tuple:
    values = list(command[1:])
    for k in range(0, len(values), 2):
        values[k] = width - values[k]
    return (command[0], *values)


def _circle(x: float, y: float, r: float) -> tuple:
    k = 0.5523 * r
    return (("M", x + r, y), ("C", x + r, y + k, x + k, y + r, x, y + r),
            ("C", x - k, y + r, x - r, y + k, x - r, y),
            ("C", x - r, y - k, x - k, y - r, x, y - r),
            ("C", x + k, y - r, x + r, y - k, x + r, y), ("Z",))


def _arrow(x0: float, x1: float, y: float, em: float, stroke: float, color, right=True,
           left=False) -> Shape:
    head, spread = 0.13 * em, 0.08 * em
    commands = [("M", x0, y), ("L", x1, y)]
    if right:
        commands += [("M", x1 - head, y - spread), ("L", x1, y), ("L", x1 - head, y + spread)]
    if left:
        commands += [("M", x0 + head, y - spread), ("L", x0, y), ("L", x0 + head, y + spread)]
    return Shape(tuple(commands), False, stroke, color)


def _horizontal_brace(x0: float, x1: float, edge: float, tip: float, stroke: float,
                      color) -> Shape:
    """A brace across [x0, x1], its ends at ``edge`` and its point at ``tip``."""
    middle_y = (edge + tip) / 2
    cx = (x0 + x1) / 2
    r = min(abs(tip - edge) / 2, (x1 - x0) / 4)
    commands = (("M", x0, edge), ("C", x0, middle_y, x0, middle_y, x0 + r, middle_y),
                ("L", cx - r, middle_y), ("C", cx, middle_y, cx, middle_y, cx, tip),
                ("C", cx, middle_y, cx, middle_y, cx + r, middle_y),
                ("L", x1 - r, middle_y), ("C", x1, middle_y, x1, middle_y, x1, edge))
    return Shape(commands, False, stroke, color)


def layout(source: str, metrics: Metrics, display: bool = False) -> Layout:
    """Lay a formula out (in display style or as in a line of text): its
    size and what to draw, from its baseline at (0, 0). TexError if it can't
    be read."""
    items = parse(source)
    box = _Layout(metrics).hlist(items, _Style(D if display else T), None)
    out: list = []
    box.flatten(0.0, 0.0, out)
    return Layout(box.width, box.height, box.depth, out)


def render(source: str, metrics: Metrics, display: bool = False) -> Layout:
    """``layout``, or for a formula that doesn't parse its source (with its
    dollars) in the error colour, ``error`` saying why."""
    try:
        return layout(source, metrics, display)
    except TexError as error:
        text = ("$$" if display else "$") + source + ("$$" if display else "$")
        width, ascent, descent, _italic = metrics.measure(text, "rm", 1.0)
        return Layout(width, ascent, descent, [Text(0.0, 0.0, text, "rm", 1.0, ERROR_COLOR)],
                      str(error))
    except RecursionError:
        text = ("$$" if display else "$") + source + ("$$" if display else "$")
        width, ascent, descent, _italic = metrics.measure(text, "rm", 1.0)
        return Layout(width, ascent, descent, [Text(0.0, 0.0, text, "rm", 1.0, ERROR_COLOR)],
                      "nested too deeply")
