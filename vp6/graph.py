"""The ``Graph``: a coordinate plane for mathematics, a number line, or a
plot of data, with things to drag and answers to place.

    self.grfPlane.AddFunction("x^2 - 3", Label="parabola")
    a = self.grfPlane.AddPoint(1, 2, Draggable=True, Label="A")
    b = self.grfPlane.AddPoint(4, 3, Draggable=True, Label="B")
    self.grfPlane.AddLine(a, b)                  # the line through A and B follows them

* **The plane:** ``XMin``, ``XMax``, ``YMin``, ``YMax`` (what is shown),
  ``EqualScales`` (a unit as long across as up: the shorter range grows),
  ``XStep``/``YStep`` (the numbered ticks; 0: as many as fit), ``PiTicks``
  (the X axis in multiples of π: π/2, π, 3π/2...), ``ShowGrid``,
  ``ShowAxes``, ``ShowNumbers``, ``XLabel``/``YLabel`` (``$…$`` is
  maths), ``GridColor``. ``PanZoom``: dragging the plane moves it and the
  wheel zooms (at run time). ``ZoomToFit()``, ``ResetView()``.
* ``Mode``: vpGraphPlane, vpGraphNumberLine (one axis: points and
  intervals, for Prealgebra and inequalities) or vpGraphData (axes at the
  edges, for statistics; adding data fits the view to it).
* **Plots** (each ``Add…`` returns a ``GraphItem``, also in ``Items``, by
  Index from 1 or by ``Key``): ``AddFunction`` (a Python callable or
  expression text such as ``"2x + 1"``, ``"sin x"``, ``"y = 1/(x - 2)"``,
  with a domain; asymptotes and holes are left unjoined),
  ``AddParametric`` (X and Y of t), ``AddPolar`` (R of θ), ``AddPoint``
  (open or closed; ``Draggable``; ``On`` a function: it slides along it),
  ``AddSegment``, ``AddRay``, ``AddLine``, ``AddVector`` (two points, or
  two point items they follow), ``AddPolygon``, ``AddRegion`` (shaded
  between two curves), ``AddInequality`` (``"y < 2x + 1"``: the half-plane
  shaded, its edge dashed when strict), ``AddLabel`` (text with ``$…$``
  maths), ``AddInterval`` (on a number line: ends open or closed, or
  infinite); for data ``AddHistogram``, ``AddDotPlot``, ``AddBoxPlot`` and
  ``AddScatter`` (``FitLine``: the least-squares line, its ``Slope``,
  ``Intercept`` and ``Correlation``).
* **Items** have ``Color`` (unset: the next of the graph's colors, for light
  or dark), ``Width``, ``Style`` (vpSolid, vpDash, vpDot...), ``FillColor``,
  ``Visible``, ``Label``, ``Tag``, ``Remove()`` and their own: a point's
  ``X``, ``Y``, ``Open``, ``Size``; a line's ``X1``…``Y2`` and ``Points``;
  a function's ``Value(X)``; an interval's ``Low``, ``High``, ``LowClosed``,
  ``HighClosed``; a box plot's ``Min``, ``Q1``, ``Median``, ``Q3``,
  ``Max``...
* **Interaction:** ``PointMoved(Item)`` fires as the user drags a point (in
  steps of ``Snap``); ``Click(X, Y)`` gives where the plane was clicked, in
  its coordinates, as do the mouse events. ``PlaceMode`` lets the user place
  an answer: vpPlacePoint (a click puts the point), vpPlaceLine (two clicks:
  a line through two points) or vpPlaceInterval (dragging along the number
  line; clicking an end opens or closes it; past the edge: no end).
  ``Answer`` is what was placed, as ``vp6edu.answers`` checks it (a point
  has X and Y, a line Points, intervals ``Interval``\\ s); ``Intervals`` are
  all the number line's; ``ClearAnswer()``.
* The graphics methods (Line, Circle, PSet, Print...) draw in the graph's
  coordinates, over the plots: in ``Paint``, or outside it (kept and
  drawn again as the view moves, until ``Cls``). ``Picture`` and
  ``EditCopy()`` give what it shows; it follows the form's light or dark
  scheme.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QFontMetricsF, QImage, QPainter, QPainterPath,
                           QPainterPathStroker, QPalette, QPen, QPolygonF)
from PySide6.QtWidgets import QApplication, QFrame

from . import colors
from ._props import P, enum_choices
from .controls import (_COMMON, _FONT, CONTROL_TYPES, EVENT_ARGS, Control, _add_mouse_members,
                       _add_validation, _geometry)
from .drawing import _DRAW_PENS, DRAWING_PROPERTIES, VP_USER, Drawing

EVENT_ARGS.update({"PointMoved": "Item"})

PLANE, NUMBER_LINE, DATA = 0, 1, 2  # Mode
PLACE_NONE, PLACE_POINT, PLACE_LINE, PLACE_INTERVAL = 0, 1, 2, 3  # PlaceMode
_NAN, _INF = math.nan, math.inf
_HANDLE = 8.0  # (how near, in pixels, the mouse must be to take a point)

# The colors plots take in turn (on a light background, on a dark one)
PLOT_COLORS = (("#1f63d6", "#5e9bff"), ("#d4332b", "#ff6f66"), ("#1d9142", "#53cf78"),
               ("#8a3ac9", "#c08cf5"), ("#e07800", "#ffab4a"), ("#0e8fa8", "#38cde6"))


# --- expressions: typed maths as Python functions ------------------------------------------------

def _pow(a, b, numerator, denominator):
    """a ** b, real: a negative number's odd root (an exponent known to be p/q, q odd)."""
    if a < 0 and b != int(b):
        if denominator % 2:
            root = (-a) ** b
            return -root if numerator % 2 else root
        return _NAN
    return a ** b


def _cbrt(x):
    return math.copysign(abs(x) ** (1 / 3), x)


_NAMESPACE = {
    "_pow": _pow, "_e": math.e, "_pi": math.pi, "_inf": _INF, "_sin": math.sin,
    "_cos": math.cos, "_tan": math.tan, "_sec": lambda x: 1 / math.cos(x),
    "_csc": lambda x: 1 / math.sin(x), "_cot": lambda x: math.cos(x) / math.sin(x),
    "_arcsin": math.asin, "_asin": math.asin, "_arccos": math.acos, "_acos": math.acos,
    "_arctan": math.atan, "_atan": math.atan, "_ln": math.log, "_log": math.log10,
    "_exp": math.exp, "_sqrt": math.sqrt, "_cbrt": _cbrt, "_fact": lambda x: math.gamma(x + 1),
    "__builtins__": {"abs": abs},
}


def _exact(node):
    """A formula without letters as a Fraction (a power's exponent), else None."""
    op, args = node.op, node.args
    try:
        if op == "num":
            return Fraction(node.value)
        if op == "mixed":
            return args[0].value + args[1].value / args[2].value
        parts = [_exact(arg) for arg in args]
        if op not in ("neg", "add", "sub", "mul", "div") or None in parts:
            return None
        if op == "neg":
            return -parts[0]
        return {"add": lambda a, b: a + b, "sub": lambda a, b: a - b,
                "mul": lambda a, b: a * b, "div": lambda a, b: a / b}[op](*parts)
    except ZeroDivisionError:
        return None


def _python(node, variables) -> str:
    """A formula (vp6edu.answers.read's) as Python code over floats."""
    op, args = node.op, node.args
    if op == "num":
        return repr(float(node.value))
    if op == "mixed":
        return repr(float(_exact(node)))
    if op == "var":
        if node.value in variables:
            return node.value
        if node.value == "e":
            return "_e"
        raise ValueError(f"“{node.value}” has no value here (the variables are "
                         f"{', '.join(variables)})")
    if op == "const":
        return "_pi" if node.value == "pi" else "_inf"
    code = [_python(arg, variables) for arg in args]
    if op == "neg":
        return f"(-{code[0]})"
    if op in ("add", "sub", "mul", "div"):
        return f"({code[0]} {'+-*/'[('add', 'sub', 'mul', 'div').index(op)]} {code[1]})"
    if op == "pow":
        exponent = _exact(args[1])
        numerator, denominator = (exponent.numerator, exponent.denominator) \
            if exponent is not None else (0, 0)
        return f"_pow({code[0]}, {code[1]}, {numerator}, {denominator})"
    if op == "func":
        return f"_{node.value}({code[0]})"
    if op == "abs":
        return f"abs({code[0]})"
    if op == "percent":
        return f"({code[0]} / 100)"
    if op == "fact":
        return f"_fact({code[0]})"
    raise ValueError(f"can't plot {op}")


def _definition(text: str, variables) -> str:
    """``y = …``, ``f(x) = …``, ``r = …``: what is after the equals sign."""
    match = re.match(r"\s*(?:[A-Za-z]+\s*\(\s*\w+\s*\)|([A-Za-z]))\s*=(?![=<>])", text)
    if match and match.group(1) not in variables:
        return text[match.end():]
    return text


def function_of(text: str, variables=("x",)):
    """Typed maths (as ``vp6edu.answers.read`` reads it: ``2x + 1``,
    ``x²``, ``sin x``, ``√x``, ``y = 3x``) as a Python function of the
    variables: floats in, a float out (nan where it isn't defined).
    ValueError when it can't be read."""
    from vp6edu.answers import read

    variables = tuple(variables)
    names = tuple("θ" if v == "theta" else v for v in variables)
    node = read(_definition(str(text), names))
    namespace = dict(_NAMESPACE)
    exec(f"def _f({', '.join(names)}):\n    return {_python(node, names)}", namespace)
    return _real(namespace["_f"])


def _real(function):
    """A function made safe to sample: nan where it fails or isn't real."""
    def value(*args):
        try:
            y = function(*args)
        except (ArithmeticError, ValueError):
            return _NAN
        if isinstance(y, complex):
            return y.real if not y.imag else _NAN
        try:
            return float(y)
        except (TypeError, ValueError):
            return _NAN
    value.__wrapped__ = function
    return value


def _callable(value, variables, what: str):
    if callable(value):
        return _real(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return lambda *_: number
    if isinstance(value, str):
        return function_of(value, variables)
    raise TypeError(f"{what} is a function or its expression as text, not {value!r}")


# --- relations: inequalities' sides -------------------------------------------------------------

_RELATION = re.compile(r"<=|>=|≤|≥|⩽|⩾|=<|=>|<|>")
_OPS = {"<": "<", ">": ">", "<=": "<=", ">=": ">=", "≤": "<=", "≥": ">=", "⩽": "<=",
        "⩾": ">=", "=<": "<=", "=>": ">="}


def _relations(text: str):
    """``y < 2x + 1``, ``-2 <= x < 3``: [(g, op)] with g(x, y) op 0 for each."""
    parts = _RELATION.split(str(text))
    ops = [_OPS[op] for op in _RELATION.findall(str(text))]
    if not ops:
        raise ValueError(f"An inequality needs <, >, <= or >=: {text!r}")
    return [(function_of(f"({left}) - ({right})", ("x", "y")), op)
            for left, op, right in zip(parts, ops, parts[1:])]


def _holds(value: float, op: str) -> bool:
    return {"<": value < 0, ">": value > 0, "<=": value <= 0, ">=": value >= 0}[op]


# --- numbers on the axes -----------------------------------------------------------------------

def nice_step(units: float, pixels: float, least: float) -> float:
    """A tick step of 1, 2 or 5 times a power of ten, at least ``least`` pixels apart."""
    if units <= 0 or pixels <= 0:
        return 1.0
    raw = units * least / pixels
    power = 10 ** math.floor(math.log10(raw))
    return next(m * power for m in (1, 2, 5, 10) if m * power >= raw * (1 - 1e-9))


def pi_step(units: float, pixels: float, least: float) -> Fraction:
    """A step in multiples of π (π/6, π/4, π/2, π, 2π, 4π...) as a Fraction of π."""
    raw = units * least / pixels / math.pi if pixels > 0 else 1
    for step in (Fraction(1, 12), Fraction(1, 6), Fraction(1, 4), Fraction(1, 2)):
        if step >= raw:
            return step
    step = Fraction(1)
    while step < raw:
        step *= 2
    return step


def number_text(value: float, step: float) -> str:
    """A tick's number, with as many decimals as the step needs (− for minus)."""
    if abs(value) < abs(step) * 1e-9:
        return "0"
    if abs(value) >= 1e6 or abs(value) < 1e-4:
        text = f"{value:.6g}"
    else:
        places = max(0, -math.floor(math.log10(abs(step)) + 1e-9)) if step else 0
        text = f"{value:.{places}f}"
    return text.replace("-", "−")


def pi_text(multiple: Fraction) -> str:
    """π/2, 3π/2, −π, 2π for a Fraction of π."""
    if multiple == 0:
        return "0"
    sign = "−" if multiple < 0 else ""
    multiple = abs(multiple)
    top = "π" if multiple.numerator == 1 else f"{multiple.numerator}π"
    return sign + (top if multiple.denominator == 1 else f"{top}/{multiple.denominator}")


def _ticks(low: float, high: float, step: float) -> list[int]:
    """The multiples k of step with low ≤ k·step ≤ high."""
    if step <= 0 or high < low or (high - low) / step > 2000:
        return []
    return list(range(math.ceil(low / step - 1e-9), math.floor(high / step + 1e-9) + 1))


# --- statistics ---------------------------------------------------------------------------------

def _median(values: list[float]) -> float:
    n = len(values)
    return (values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2) \
        if n else _NAN


def five_numbers(values) -> tuple[float, float, float, float, float]:
    """(minimum, Q1, median, Q3, maximum): the quartiles as medians of the
    lower and upper halves (the middle value left out), as OpenStax's
    statistics does."""
    data = sorted(float(v) for v in values)
    if not data:
        return (_NAN,) * 5
    half = len(data) // 2
    lower, upper = data[:half], data[half + len(data) % 2:]
    return (data[0], _median(lower or data), _median(data), _median(upper or data), data[-1])


def histogram_bins(values, bins=None) -> tuple[list[float], list[int]]:
    """(edges, counts): ``bins`` a number of bins (unset: Sturges' rule) or
    the edges themselves; each bin holds its left edge, the last both."""
    data = [float(v) for v in values]
    if isinstance(bins, (list, tuple)):
        edges = sorted(float(e) for e in bins)
    else:
        count = int(bins) if bins else max(1, math.ceil(math.log2(len(data) or 1) + 1))
        low, high = (min(data), max(data)) if data else (0.0, 1.0)
        if high == low:
            low, high = low - 0.5, high + 0.5
        edges = [low + (high - low) * i / count for i in range(count + 1)]
    counts = [0] * max(0, len(edges) - 1)
    for v in data:
        for i in range(len(counts)):
            if edges[i] <= v < edges[i + 1] or (i == len(counts) - 1 and v == edges[-1]):
                counts[i] += 1
                break
    return edges, counts


def least_squares(points) -> tuple[float, float, float]:
    """(slope, intercept, correlation r) of the line fitted to (x, y) points."""
    points = [(float(x), float(y)) for x, y in points]
    n = len(points)
    if n < 2:
        return _NAN, _NAN, _NAN
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    syy = sum((y - my) ** 2 for _, y in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    if not sxx:
        return _NAN, _NAN, _NAN
    slope = sxy / sxx
    r = sxy / math.sqrt(sxx * syy) if syy else _NAN
    return slope, my - slope * mx, r


# --- the items ----------------------------------------------------------------------------------

_LINE_KINDS = ("Segment", "Ray", "Line", "Vector")
_COMMON_FIELDS = {"Color": None, "Width": 2, "Style": 0, "FillColor": None, "Visible": True,
                  "Label": "", "Tag": ""}
_FIELDS = {
    "Function": {"F": None, "XMin": None, "XMax": None},
    "Parametric": {"X": None, "Y": None, "TMin": 0.0, "TMax": 2 * math.pi},
    "Polar": {"R": None, "ThetaMin": 0.0, "ThetaMax": 2 * math.pi},
    "Point": {"X": 0.0, "Y": 0.0, "Open": False, "Size": 4.5, "Draggable": False, "On": None},
    **{kind: {"X1": 0.0, "Y1": 0.0, "X2": 1.0, "Y2": 1.0} for kind in _LINE_KINDS},
    "Polygon": {"Points": ()},
    "Region": {"F": None, "G": None, "XMin": None, "XMax": None},
    "Inequality": {"Text": ""},
    "Label": {"Text": "", "X": 0.0, "Y": 0.0, "Alignment": 0},
    "Interval": {"Low": 0.0, "High": 1.0, "LowClosed": True, "HighClosed": True,
                 "Draggable": False},
    "Histogram": {"Values": (), "Bins": None},
    "DotPlot": {"Values": ()},
    "BoxPlot": {"Values": (), "Y": 1.0, "Height": 0.6},
    "Scatter": {"Points": (), "FitLine": False},
}
_NUMBERS = {"X", "Y", "X1", "Y1", "X2", "Y2", "Width", "Size", "TMin", "TMax", "ThetaMin",
            "ThetaMax", "Low", "High", "Height"}
_FILLED = ("Polygon", "Region", "Inequality", "Histogram", "BoxPlot")  # (drawn first)
_ON_TOP = ("Point", "Label", "Interval", "DotPlot", "Scatter")  # (over the axes)


def _five(item):
    return five_numbers(item.Values)


def _fit(item):
    return least_squares(item.Points)


_COMPUTED = {  # read-only values of an item, by kind
    "BoxPlot": {"Min": lambda i: _five(i)[0], "Q1": lambda i: _five(i)[1],
                "Median": lambda i: _five(i)[2], "Q3": lambda i: _five(i)[3],
                "Max": lambda i: _five(i)[4]},
    "Histogram": {"Edges": lambda i: histogram_bins(i.Values, i.Bins)[0],
                  "Counts": lambda i: histogram_bins(i.Values, i.Bins)[1]},
    "Scatter": {"Slope": lambda i: _fit(i)[0], "Intercept": lambda i: _fit(i)[1],
                "Correlation": lambda i: _fit(i)[2]},
    **{kind: {"Points": lambda i: [(i.X1, i.Y1), (i.X2, i.Y2)]} for kind in _LINE_KINDS},
}


def _xy(point) -> tuple[float, float]:
    """A point given as (x, y) or as a point item."""
    if isinstance(point, GraphItem):
        return float(point.X), float(point.Y)
    x, y = point
    return float(x), float(y)


class GraphItem:
    """Something drawn on a Graph (the module's documentation): its fields
    depend on its ``Kind``."""

    def __init__(self, graph: "Graph", kind: str, key: str, fields: dict):
        d = self.__dict__
        d.update(_graph=graph, _kind=kind, _key=key, _fields={**_COMMON_FIELDS, **_FIELDS[kind]},
                 _ends=None, _compiled={}, _error=None, _auto=graph._next_color())
        for name, value in fields.items():
            if value is not None or name not in ("Color", "FillColor"):
                self._set(name, value)

    def __repr__(self):
        return f"<GraphItem {self._kind}{f' {self._key!r}' if self._key else ''}>"

    @property
    def Kind(self) -> str:
        """Function, Parametric, Polar, Point, Segment, Ray, Line, Vector,
        Polygon, Region, Inequality, Label, Interval, Histogram, DotPlot,
        BoxPlot or Scatter."""
        return self._kind

    @property
    def Key(self) -> str:
        return self._key

    @property
    def Index(self) -> int:
        """Its number in Items (from 1)."""
        return self._graph._items._list.index(self) + 1

    def __getattr__(self, name):
        fields = self.__dict__.get("_fields")
        if fields is not None and name in fields:
            ends = self.__dict__["_ends"]
            if ends is not None and name in ("X1", "Y1", "X2", "Y2"):
                point = ends[0] if name.endswith("1") else ends[1]
                return point.X if name[0] == "X" else point.Y
            if name == "Points" and self._kind == "Polygon":
                return [_xy(p) for p in fields["Points"]]
            if name == "Y" and self._kind == "Point" and fields["On"] is not None:
                return fields["On"].Value(fields["X"])
            return fields[name]
        computed = _COMPUTED.get(self.__dict__.get("_kind"), {}).get(name)
        if computed is not None:
            return computed(self)
        raise AttributeError(f"A {self.__dict__.get('_kind')} item has no {name}")

    def __setattr__(self, name, value):
        if name in self._fields:
            self._set(name, value)
            self._graph._changed()
        elif name in _COMPUTED.get(self._kind, {}):
            raise AttributeError(f"A {self._kind} item's {name} can't be set")
        else:
            raise AttributeError(f"A {self._kind} item has no {name}")

    def _set(self, name: str, value) -> None:
        if name not in self._fields:
            raise TypeError(f"Add{self._kind} has no argument {name}")
        if name in ("X1", "Y1", "X2", "Y2") and self.__dict__["_ends"] is not None:
            raise AttributeError(f"This {self._kind} follows its points: move them")
        if name in ("Color", "FillColor"):
            value = None if value is None else colors.normalize(value)
        elif name in _NUMBERS and not (self._kind == "Parametric" and name in ("X", "Y")):
            value = float(value)
        elif name == "Values":
            value = tuple(float(v) for v in value)
        elif name == "Points" and self._kind == "Scatter":
            value = tuple(_xy(p) for p in value)
        elif name == "Points":
            value = tuple(value)
        elif name == "On" and value is not None and getattr(value, "Kind", "") != "Function":
            raise TypeError("A point's On is a function item (AddFunction's)")
        self._fields[name] = value
        self._compiled.clear()
        self.__dict__["_error"] = None

    def Value(self, X) -> float:
        """A function's value at X (nan where it isn't defined)."""
        if self._kind != "Function":
            raise AttributeError(f"A {self._kind} item has no Value")
        return self._function("F", ("x",))(float(X))

    def _function(self, name: str, variables):
        found = self._compiled.get(name)
        if found is None:
            found = self._compiled[name] = _callable(self._fields[name], variables,
                                                     f"{self._kind}'s {name}")
        return found

    def Remove(self) -> None:
        """Take it off the graph."""
        self._graph._items.Remove(self)


class _Items:
    """Graph.Items: its plots, by Index (from 1) or Key."""

    def __init__(self, graph: "Graph"):
        self._graph = graph
        self._list: list[GraphItem] = []

    def __iter__(self):
        return iter(list(self._list))

    def __len__(self):
        return len(self._list)

    @property
    def Count(self) -> int:
        return len(self._list)

    def __call__(self, ref) -> GraphItem:
        if isinstance(ref, GraphItem):
            return ref
        if isinstance(ref, str):
            found = next((item for item in self._list if item._key == ref), None)
            if found is None:
                raise KeyError(f"Graph '{self._graph.Name}' has no item {ref!r}")
            return found
        ref = int(ref)
        if not 1 <= ref <= len(self._list):
            raise IndexError(f"Graph '{self._graph.Name}' has no item {ref} "
                             f"(1 to {len(self._list)})")
        return self._list[ref - 1]

    Item = __getitem__ = __call__

    def _add(self, kind: str, Key, **fields) -> GraphItem:
        key = str(Key or "")
        if key and any(item._key == key for item in self._list):
            raise ValueError(f"Graph '{self._graph.Name}': the key {key!r} is not unique")
        item = GraphItem(self._graph, kind, key, fields)
        self._list.append(item)
        self._graph._changed()
        return item

    def Remove(self, ref) -> None:
        item = self(ref)
        self._list.remove(item)
        graph = self._graph
        if item in graph._placed:
            graph._placed.remove(item)
        for other in list(self._list):  # (what follows it goes too)
            ends = other._ends or ()
            if other not in self._list:
                continue  # (gone with another)
            if item in ends or (other._kind == "Polygon" and item in other._fields["Points"]):
                self.Remove(other)
            elif other._kind == "Point" and other._fields["On"] is item:
                other._fields["On"] = None
        graph._changed()

    def Clear(self) -> None:
        self._list.clear()
        self._graph._placed.clear()
        self._graph.__dict__["_colors_used"] = 0  # (the next plot: the first color again)
        self._graph._changed()


# --- the control ----------------------------------------------------------------------------------

class _GraphWidget(QFrame):
    """A Graph's widget: it paints the graph, then its frame."""

    def __init__(self, parent, graph: "Graph"):
        super().__init__(parent)
        self._vp_control = graph
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, event):
        self._vp_control._paint(self)
        super().paintEvent(event)


_RECORDED = ("PSet", "Line", "Circle", "Polygon", "RoundRect", "DrawPath", "Print", "DrawText",
             "PaintPicture")
_DRAWING_STATE = ("DrawWidth", "DrawStyle", "DrawCap", "DrawJoin", "FontScale", "FillStyle",
                  "FillColor", "ForeColor")


def _recorded(name: str):
    method = getattr(Drawing, name)

    def wrapper(self, *args, **kwargs):
        return self._record(method, args, kwargs)

    wrapper.__name__ = name
    wrapper.__doc__ = method.__doc__ + "\n\n(On a Graph: in the graph's coordinates, kept " \
        "over the plots as the view moves, until Cls.)"
    return wrapper


class Graph(Drawing, Control):
    """A coordinate plane, number line or data plot (the module's documentation)."""

    TypeName = "Graph"
    DefaultEvent = "Click"
    DefaultSize = (321, 241)
    Events = ("Click", "PointMoved", "Paint", "DblClick", "GotFocus", "LostFocus", "KeyDown",
              "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    EventArgs = {"Click": "X, Y"}
    Properties = (
        *_geometry(*DefaultSize),
        P("Mode", "enum", PLANE, enum_choices("Plane", "Number Line", "Data"),
          description="A coordinate plane, a number line (one axis: points and intervals) or "
                      "a plot of data (axes at the edges)"),
        P("XMin", "number", -10, description="The smallest X shown"),
        P("XMax", "number", 10, description="The largest X shown"),
        P("YMin", "number", -10, description="The smallest Y shown"),
        P("YMax", "number", 10, description="The largest Y shown"),
        P("EqualScales", "bool", True,
          description="A unit as long across as up (the shorter range grows to fit); not in "
                      "Data mode"),
        P("XStep", "number", 0, description="The numbered ticks' step along X; 0: as many as "
                                            "fit"),
        P("YStep", "number", 0, description="The numbered ticks' step along Y; 0: as many as "
                                            "fit"),
        P("PiTicks", "bool", False,
          description="The X axis numbered in multiples of π (π/2, π, 3π/2...), for "
                      "trigonometry"),
        P("ShowGrid", "bool", True, description="Grid lines at the ticks"),
        P("ShowAxes", "bool", True, description="The axes"),
        P("ShowNumbers", "bool", True, description="The ticks' numbers"),
        P("XLabel", "str", "x", description="The X axis's name (maths between dollar signs)"),
        P("YLabel", "str", "y", description="The Y axis's name (maths between dollar signs)"),
        P("PanZoom", "bool", True,
          description="Dragging the plane moves it and the mouse wheel zooms (at run time)"),
        P("PlaceMode", "enum", PLACE_NONE, enum_choices("None", "Point", "Line", "Interval"),
          description="What the user places as an answer (Answer): a point with a click, a "
                      "line with two, intervals dragged along a number line"),
        P("Snap", "number", 1,
          description="Points dragged or placed move in steps of Snap (0: anywhere)"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A border around it"),
        P("BackColor", "color", None, description="The background; unset = the scheme's"),
        P("ForeColor", "color", None,
          description="The axes, numbers and labels, and the graphics methods; unset = the "
                      "scheme's"),
        P("GridColor", "color", None, description="The grid lines; unset = a faint ForeColor"),
        *(spec for spec in DRAWING_PROPERTIES if spec.name not in ("AutoRedraw", "ScaleMode")),
        *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_items=_Items(self), _placed=[], _press=None, _drag=None,
                             _drawn=[], _colors_used=0, _home=None, _building=True)
        self._values["ScaleMode"] = VP_USER  # (the graphics methods: the graph's coordinates)
        return _GraphWidget(parent, self)

    def _init_values(self, props):
        super()._init_values(props)
        self.__dict__["_building"] = False
        self.__dict__["_home"] = self._set_range()

    def _set_range(self) -> tuple:
        values = self._values
        return tuple(float(values.get(name, default)) for name, default in
                     (("XMin", -10), ("XMax", 10), ("YMin", -10), ("YMax", 10)))

    def _changed(self, _=None) -> None:
        if self._widget is not None:
            self._widget.update()

    _apply_Mode = _apply_EqualScales = _apply_XStep = _apply_YStep = _apply_PiTicks = \
        _apply_ShowGrid = _apply_ShowAxes = _apply_ShowNumbers = _apply_XLabel = \
        _apply_YLabel = _apply_GridColor = _apply_BackColor = _apply_ForeColor = _changed

    _apply_XMin = _apply_XMax = _apply_YMin = _apply_YMax = _changed  # (XMax <= XMin: a unit)

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken if v else QFrame.NoFrame)
        self._changed()

    def _apply_font(self, _=None):
        super()._apply_font()
        self._changed()

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_FontWeight = _apply_font

    def _scheme_changed(self, dark: bool) -> None:
        self._changed()

    def _next_color(self) -> int:
        used = self._colors_used
        self.__dict__["_colors_used"] = used + 1
        return used

    # -- the view ----------------------------------------------------------------------------------
    def _area(self) -> QRectF:
        """Where the plane is drawn, in the widget's pixels (Data: inside the
        numbers along the axes)."""
        rect = QRectF(self._widget.contentsRect())
        if self._values.get("Mode") == DATA:
            metrics = QFontMetricsF(self._widget.font())
            left = math.ceil(metrics.horizontalAdvance("−00000")) + 10
            bottom = math.ceil(metrics.lineSpacing()) + 8
            if self._values.get("YLabel"):
                left += math.ceil(metrics.lineSpacing()) + 4
            if self._values.get("XLabel"):
                bottom += math.ceil(metrics.lineSpacing()) + 2
            rect.adjust(left, 10, -12, -bottom)
        if rect.width() < 1 or rect.height() < 1:
            rect.setSize(rect.size().expandedTo(QSize(1, 1)))
        return rect

    def _view(self) -> tuple[float, float, float, float]:
        """What is shown (x0, x1, y0, y1): the ranges set, one grown for EqualScales
        (a number line: around 0 up and down)."""
        x0, x1, y0, y1 = self._set_range()
        if x1 <= x0:
            x1 = x0 + 1
        if y1 <= y0:
            y1 = y0 + 1
        mode = self._values.get("Mode", PLANE)
        area = self._area()
        if mode == NUMBER_LINE:
            half = (x1 - x0) * area.height() / area.width() / 2
            return x0, x1, -half, half
        if mode == PLANE and self._values.get("EqualScales", True):
            per_pixel = max((x1 - x0) / area.width(), (y1 - y0) / area.height())
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            half_x, half_y = per_pixel * area.width() / 2, per_pixel * area.height() / 2
            return cx - half_x, cx + half_x, cy - half_y, cy + half_y
        return x0, x1, y0, y1

    def _set_view(self, x0, x1, y0, y1) -> None:
        values = self._values
        if self._values.get("Mode") == NUMBER_LINE:  # (only across)
            y0, y1 = values.get("YMin", -10), values.get("YMax", 10)
        for name, value in zip(("XMin", "XMax", "YMin", "YMax"), (x0, x1, y0, y1)):
            values[name] = float(value)
        self._changed()

    def _mapping(self):
        """(to pixels, from pixels): functions of a point."""
        x0, x1, y0, y1 = self._view()
        area = self._area()
        sx, sy = area.width() / (x1 - x0), area.height() / (y1 - y0)
        left, bottom = area.left(), area.bottom()

        def to_px(x, y):
            return left + (x - x0) * sx, bottom - (y - y0) * sy

        def from_px(px, py):
            return x0 + (px - left) / sx, y0 + (bottom - py) / sy

        return to_px, from_px

    def ZoomToFit(self) -> None:
        """Show everything plotted (functions over their domains), with a margin."""
        boxes = [box for item in self._items._list if item.Visible
                 for box in [self._bounds(item)] if box is not None]
        if not boxes:
            return
        x0 = min(b[0] for b in boxes)
        x1 = max(b[1] for b in boxes)
        y0 = min(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        data = self._values.get("Mode") == DATA
        if x1 - x0 < 1e-9:
            x0, x1 = x0 - 1, x1 + 1
        if y1 - y0 < 1e-9:
            y0, y1 = y0 - 1, y1 + 1
        mx, my = (x1 - x0) * 0.08, (y1 - y0) * 0.08
        self._set_view(x0 - mx, x1 + mx, (y0 if data and y0 == 0 else y0 - my), y1 + my)

    def _bounds(self, item: GraphItem):
        kind, f = item._kind, item._fields
        points: list[tuple[float, float]] = []
        if kind in ("Point", "Label"):
            points = [(item.X, item.Y)]
        elif kind in _LINE_KINDS:
            points = item.Points
        elif kind in ("Polygon", "Scatter"):
            points = list(item.Points)
        elif kind == "Interval":
            points = [(v, 0.0) for v in (f["Low"], f["High"]) if math.isfinite(v)]
        elif kind == "Histogram":
            edges, counts = histogram_bins(f["Values"], f["Bins"])
            points = [(edges[0], 0.0), (edges[-1], float(max(counts, default=0)))]
        elif kind == "DotPlot":
            values = f["Values"]
            stack = max((values.count(v) for v in values), default=0)
            points = [(min(values, default=0), 0.0), (max(values, default=0), float(stack))]
        elif kind == "BoxPlot":
            low, *_, high = five_numbers(f["Values"])
            points = [(low, f["Y"] - f["Height"]), (high, f["Y"] + f["Height"])]
        elif kind in ("Function", "Region") and f["XMin"] is not None and f["XMax"] is not None:
            fn = item._function("F", ("x",))
            for k in range(101):
                x = f["XMin"] + (f["XMax"] - f["XMin"]) * k / 100
                points.append((x, fn(x)))
        elif kind in ("Parametric", "Polar"):
            points = self._curve_points(item, 200)
        points = [(x, y) for x, y in points if math.isfinite(x) and math.isfinite(y)]
        if not points:
            return None
        return (min(p[0] for p in points), max(p[0] for p in points),
                min(p[1] for p in points), max(p[1] for p in points))

    def ResetView(self) -> None:
        """Back to the view it was made with (XMin... as designed)."""
        if self._home is not None:
            self._set_view(*self._home)

    def _zoom(self, factor: float, x: float, y: float) -> None:
        x0, x1, y0, y1 = self._view()
        if self._values.get("Mode") == NUMBER_LINE:
            y = 0.0
        self._set_view(x + (x0 - x) * factor, x + (x1 - x) * factor,
                       y + (y0 - y) * factor, y + (y1 - y) * factor)

    # -- the graphics methods (drawing.Drawing), in the graph's coordinates ---------------------
    def _drawing_surface(self):
        return self._widget

    def _drawing_origin(self) -> QPoint:
        return self._area().topLeft().toPoint()

    def _draw_area_size(self) -> QSize:
        return self._area().size().toSize()

    def _scale_factors(self):
        x0, x1, y0, y1 = self._view()
        area = self._area()
        return x0, y1, area.width() / (x1 - x0), -area.height() / (y1 - y0)

    def _scaled(self) -> bool:
        return True

    def _set_scale_part(self, index: int, value) -> None:
        scale = list(self._scale_rect())
        scale[index] = float(value)
        left, top, width, height = scale
        if width <= 0 or height >= 0:
            raise ValueError("A Graph's X goes to the right and its Y up: ScaleWidth > 0, "
                             "ScaleHeight < 0")
        self._set_view(left, left + width, top + height, top)

    def Scale(self, X1=None, Y1=None, X2=None, Y2=None) -> None:
        """Show X1 to X2 across, Y1 to Y2 up (any corners); without them: ResetView."""
        if X1 is None:
            self.ResetView()
            return
        if X1 == X2 or Y1 == Y2:
            raise ValueError("Scale: the corners must differ")
        self._set_view(min(X1, X2), max(X1, X2), min(Y1, Y2), max(Y1, Y2))

    def _apply_ScaleMode(self, v):
        pass

    def _record(self, method, args, kwargs):
        """A graphics method: in Paint, drawn now; outside it, kept (to draw at
        every paint, where the view then is) and the current point moved."""
        state = self._draw_state()
        if state["painter"] is not None:
            return method(self, *args, **kwargs)
        drawn = (method, args, kwargs, state["x"], state["y"], state["dash"],
                 {name: self._values.get(name) for name in _DRAWING_STATE})
        scratch = QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
        state["painter"] = QPainter(scratch)
        try:
            result = method(self, *args, **kwargs)
        finally:
            state["painter"].end()
            state["painter"] = None
        self._drawn.append(drawn)
        self._changed()
        return result

    def Cls(self) -> None:
        """Clear what the graphics methods drew (not the plots), and move the current point
        to 0, 0."""
        self._drawn.clear()
        super().Cls()

    def _replay(self, painter: QPainter) -> None:
        state = self._draw_state()
        current = state["x"], state["y"], state["dash"]
        values = {name: self._values.get(name) for name in _DRAWING_STATE}
        state["painter"] = painter
        try:
            for method, args, kwargs, x, y, dash, drawing in self._drawn:
                state["x"], state["y"], state["dash"] = x, y, dash
                self._values.update(drawing)
                method(self, *args, **kwargs)
        finally:
            state["painter"] = None
            state["x"], state["y"], state["dash"] = current
            self._values.update(values)

    # -- adding plots -----------------------------------------------------------------------------
    @property
    def Items(self) -> _Items:
        return self._items

    def Clear(self) -> None:
        """Remove every plot (the graphics methods' drawing stays: Cls)."""
        self._items.Clear()

    def AddFunction(self, F, XMin=None, XMax=None, Color=None, Width=2, Style=0, Label="",
                    Key: str = "") -> GraphItem:
        """y = F(x): a Python function or expression text (``"x^2 - 3"``,
        ``"y = sin x"``); XMin and XMax limit its domain."""
        item = self._items._add("Function", Key, F=F, XMin=XMin, XMax=XMax, Color=Color,
                                Width=Width, Style=Style, Label=Label)
        item._function("F", ("x",))  # (text that can't be read: the error now)
        return item

    def AddParametric(self, X, Y, TMin=0.0, TMax=2 * math.pi, Color=None, Width=2, Style=0,
                      Label="", Key: str = "") -> GraphItem:
        """The curve (X(t), Y(t)) for t from TMin to TMax (functions or text in t)."""
        item = self._items._add("Parametric", Key, X=X, Y=Y, TMin=TMin, TMax=TMax, Color=Color,
                                Width=Width, Style=Style, Label=Label)
        item._function("X", ("t",))
        item._function("Y", ("t",))
        return item

    def AddPolar(self, R, ThetaMin=0.0, ThetaMax=2 * math.pi, Color=None, Width=2, Style=0,
                 Label="", Key: str = "") -> GraphItem:
        """r = R(θ) for θ from ThetaMin to ThetaMax (a function, or text in θ,
        ``theta`` or t)."""
        item = self._items._add("Polar", Key, R=R, ThetaMin=ThetaMin, ThetaMax=ThetaMax,
                                Color=Color, Width=Width, Style=Style, Label=Label)
        item._function("R", ("theta", "t"))
        return item

    def AddPoint(self, X, Y=0.0, Color=None, Size=4.5, Open=False, Draggable=False, On=None,
                 Label="", Key: str = "") -> GraphItem:
        """A point (Open: a hollow circle, e.g. a hole); Draggable by the user
        (PointMoved); On a function item: it stays on that curve."""
        return self._items._add("Point", Key, X=X, Y=Y, Color=Color, Size=Size, Open=Open,
                                Draggable=Draggable, On=On, Label=Label)

    def _add_line(self, kind, X1, Y1, X2, Y2, Color, Width, Style, Label, Key) -> GraphItem:
        if isinstance(X1, GraphItem):  # (two point items: it follows them)
            ends = (X1, Y1)
            if not all(isinstance(p, GraphItem) and p._kind == "Point" for p in ends):
                raise TypeError(f"Add{kind} takes X1, Y1, X2, Y2, or two point items")
            item = self._items._add(kind, Key, Color=Color, Width=Width, Style=Style,
                                    Label=Label)
            item.__dict__["_ends"] = ends
            return item
        return self._items._add(kind, Key, X1=X1, Y1=Y1, X2=X2, Y2=Y2, Color=Color, Width=Width,
                                Style=Style, Label=Label)

    def AddSegment(self, X1, Y1, X2=None, Y2=None, Color=None, Width=2, Style=0, Label="",
                   Key: str = "") -> GraphItem:
        """A segment from X1, Y1 to X2, Y2, or between two point items."""
        return self._add_line("Segment", X1, Y1, X2, Y2, Color, Width, Style, Label, Key)

    def AddRay(self, X1, Y1, X2=None, Y2=None, Color=None, Width=2, Style=0, Label="",
               Key: str = "") -> GraphItem:
        """A ray from X1, Y1 through X2, Y2 (or from one point item through another)."""
        return self._add_line("Ray", X1, Y1, X2, Y2, Color, Width, Style, Label, Key)

    def AddLine(self, X1, Y1, X2=None, Y2=None, Color=None, Width=2, Style=0, Label="",
                Key: str = "") -> GraphItem:
        """The whole line through X1, Y1 and X2, Y2 (or through two point items)."""
        return self._add_line("Line", X1, Y1, X2, Y2, Color, Width, Style, Label, Key)

    def AddVector(self, X1, Y1, X2=None, Y2=None, Color=None, Width=2, Style=0, Label="",
                  Key: str = "") -> GraphItem:
        """An arrow from X1, Y1 to X2, Y2 (or between two point items)."""
        return self._add_line("Vector", X1, Y1, X2, Y2, Color, Width, Style, Label, Key)

    def AddPolygon(self, Points, Color=None, FillColor=None, Width=2, Style=0, Label="",
                   Key: str = "") -> GraphItem:
        """A closed polygon through Points ((x, y) pairs or point items, which it
        follows), filled with FillColor (unset: not filled)."""
        return self._items._add("Polygon", Key, Points=Points, Color=Color, FillColor=FillColor,
                                Width=Width, Style=Style, Label=Label)

    def AddRegion(self, F, G=None, XMin=None, XMax=None, FillColor=None, Color=None,
                  Key: str = "") -> GraphItem:
        """The region between the curves F and G (unset: the X axis) from XMin
        to XMax, shaded (FillColor unset: Color, see-through)."""
        item = self._items._add("Region", Key, F=F, G=G if G is not None else 0, XMin=XMin,
                                XMax=XMax, FillColor=FillColor, Color=Color)
        item._function("F", ("x",))
        item._function("G", ("x",))
        return item

    def AddInequality(self, Text, Color=None, FillColor=None, Key: str = "") -> GraphItem:
        """The points where an inequality in x and y holds (``"y < 2x + 1"``,
        ``"x >= 3"``, ``"x^2 + y^2 <= 9"``, ``"-2 < x < 3"``), shaded; its edge
        dashed when strict (< or >), solid otherwise."""
        item = self._items._add("Inequality", Key, Text=str(Text), Color=Color,
                                FillColor=FillColor)
        _relations(Text)  # (errors now)
        return item

    def AddLabel(self, Text, X, Y, Color=None, Alignment=0, Key: str = "") -> GraphItem:
        """Text at X, Y (``$…$`` is maths), starting there (vpLeftJustify), ending
        there (vpRightJustify) or centered on it (vpCenter)."""
        return self._items._add("Label", Key, Text=str(Text), X=X, Y=Y, Color=Color,
                                Alignment=int(Alignment))

    def AddInterval(self, Low, High, LowClosed=True, HighClosed=True, Color=None, Width=4,
                    Draggable=False, Key: str = "") -> GraphItem:
        """An interval on the number line from Low to High (None or ±math.inf:
        no end), each end closed (a filled circle) or open (a hollow one)."""
        low = -_INF if Low is None else Low
        high = _INF if High is None else High
        return self._items._add("Interval", Key, Low=low, High=high, LowClosed=bool(LowClosed),
                                HighClosed=bool(HighClosed), Color=Color, Width=Width,
                                Draggable=Draggable)

    def _data_added(self, item: GraphItem) -> GraphItem:
        if self._values.get("Mode") == DATA:
            self.ZoomToFit()
        return item

    def AddHistogram(self, Values, Bins=None, Color=None, FillColor=None,
                     Key: str = "") -> GraphItem:
        """A histogram of Values: Bins is how many bins (unset: Sturges' rule)
        or their edges; ``Edges`` and ``Counts`` are what it drew."""
        return self._data_added(self._items._add(
            "Histogram", Key, Values=Values, Bins=list(Bins) if isinstance(Bins, (list, tuple))
            else Bins, Color=Color, FillColor=FillColor, Width=1))

    def AddDotPlot(self, Values, Color=None, Key: str = "") -> GraphItem:
        """A dot plot: a dot for each value, those of the same value stacked."""
        return self._data_added(self._items._add("DotPlot", Key, Values=Values, Color=Color))

    def AddBoxPlot(self, Values, Y=1.0, Height=0.6, Color=None, FillColor=None,
                   Key: str = "") -> GraphItem:
        """A box plot of Values across, centred at Y, Height tall: whiskers to
        ``Min`` and ``Max``, the box from ``Q1`` to ``Q3``, the ``Median``."""
        return self._data_added(self._items._add("BoxPlot", Key, Values=Values, Y=Y,
                                                 Height=Height, Color=Color,
                                                 FillColor=FillColor))

    def AddScatter(self, Points, Ys=None, FitLine=False, Color=None, Key: str = "") -> GraphItem:
        """A scatter plot of (x, y) Points (or Xs and Ys); FitLine draws the
        least-squares line (``Slope``, ``Intercept``, ``Correlation``)."""
        points = list(zip(Points, Ys)) if Ys is not None else Points
        return self._data_added(self._items._add("Scatter", Key, Points=points,
                                                 FitLine=FitLine, Color=Color))

    # -- answers ----------------------------------------------------------------------------------
    @property
    def Intervals(self) -> list:
        """The number line's intervals (its visible Interval items), as
        ``vp6edu.answers.Interval``s."""
        from vp6edu.answers import Interval

        return [Interval(i.Low, i.High, i.LowClosed, i.HighClosed)
                for i in self._items._list if i._kind == "Interval" and i.Visible]

    @property
    def Answer(self):
        """What the user placed (PlaceMode): the point item, the line item, or
        the placed intervals as ``vp6edu.answers.Interval``s; None while
        nothing is."""
        mode = self._values.get("PlaceMode", PLACE_NONE)
        placed = self._placed
        if mode == PLACE_INTERVAL:
            from vp6edu.answers import Interval

            return [Interval(i.Low, i.High, i.LowClosed, i.HighClosed)
                    for i in placed if i._kind == "Interval"] or None
        kind = {PLACE_POINT: "Point", PLACE_LINE: "Line"}.get(mode)
        return next((item for item in placed if item._kind == kind), None)

    def ClearAnswer(self) -> None:
        """Remove what the user placed."""
        for item in list(self._placed):
            if item in self._items._list:
                self._items.Remove(item)
        self._placed.clear()

    def _apply_PlaceMode(self, v):
        if not self._building:
            self.ClearAnswer()

    def _snapped(self, value: float) -> float:
        snap = float(self._values.get("Snap") or 0)
        return round(round(value / snap) * snap, 10) if snap > 0 else value

    # -- pictures ---------------------------------------------------------------------------------
    @property
    def Picture(self):
        """What it shows, as a Picture (read-only)."""
        from .picture import Picture

        return Picture(_image=self._widget.grab().toImage())

    def EditCopy(self) -> None:
        """Copy the graph to the clipboard, as a picture."""
        QApplication.clipboard().setImage(self._widget.grab().toImage())

    # -- the mouse ---------------------------------------------------------------------------------
    def _handle_at(self, px: float, py: float):
        """The draggable point or interval end under the mouse: (item, "X") or
        (interval, "Low"/"High"), or None."""
        to_px = self._mapping()[0]
        best, nearest = None, _HANDLE
        line = self._values.get("Mode") == NUMBER_LINE
        for item in reversed(self._items._list):
            if not item.Visible or not item._fields.get("Draggable"):
                continue
            if item._kind == "Point":
                ends = [("X", item.X, 0.0 if line else item.Y)]
            elif item._kind == "Interval":
                ends = [(name, item._fields[name], 0.0) for name in ("Low", "High")
                        if math.isfinite(item._fields[name])]
            else:
                continue
            for name, x, y in ends:
                hx, hy = to_px(x, y)
                distance = math.hypot(hx - px, hy - py)
                if distance < nearest:
                    best, nearest = (item, name), distance
        return best

    def _on_qt_event(self, watched, event):
        if self._design_mode:
            return False
        etype = event.type()
        if etype == QEvent.Wheel and self._values.get("PanZoom", True):
            position = event.position()
            x, y = self._mapping()[1](position.x(), position.y())
            steps = event.angleDelta().y() or event.angleDelta().x()
            if steps:
                self._zoom(0.999 ** steps, x, y)
            return True
        if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._press_at(event.position())
        elif etype == QEvent.MouseMove:
            self._move_to(event.position(), bool(event.buttons() & Qt.LeftButton))
        result = super()._on_qt_event(watched, event)  # (MouseDown... in graph units)
        if etype == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._release_at(event.position())
        return result

    def _press_at(self, position: QPointF) -> None:
        px, py = position.x(), position.y()
        handle = self._handle_at(px, py)
        self.__dict__["_press"] = (px, py, handle)
        mode = self._values.get("PlaceMode", PLACE_NONE)
        if handle is not None:
            self.__dict__["_drag"] = ("handle", handle[0], handle[1], False)
        elif mode == PLACE_INTERVAL:
            x = self._snapped(self._mapping()[1](px, py)[0])
            item = self.AddInterval(x, x, Draggable=True)
            self._placed.append(item)
            self.__dict__["_drag"] = ("handle", item, "High", True)
            self._fire("PointMoved", item)
        elif self._values.get("PanZoom", True):
            self.__dict__["_drag"] = ("pan", px, py, self._view())

    def _move_to(self, position: QPointF, pressed: bool) -> None:
        px, py = position.x(), position.y()
        drag = self._drag
        if drag is None or not pressed:
            if self._values.get("MousePointer", 0) == 0:
                if self._handle_at(px, py) is not None:
                    self._widget.setCursor(Qt.OpenHandCursor)
                else:
                    self._widget.unsetCursor()
            return
        if drag[0] == "pan":
            _kind, sx, sy, (x0, x1, y0, y1) = drag
            area = self._area()
            dx = (px - sx) * (x1 - x0) / area.width()
            dy = (py - sy) * (y1 - y0) / area.height()
            self._set_view(x0 - dx, x1 - dx, y0 + dy, y1 + dy)
            self._widget.setCursor(Qt.ClosedHandCursor)
            return
        _kind, item, name, _new = drag
        if item not in self._items._list:
            return
        x, y = self._mapping()[1](px, py)
        if item._kind == "Point":
            x, y = self._snapped(x), self._snapped(y)
            fields = item._fields
            if self._values.get("Mode") == NUMBER_LINE:
                y = fields["Y"]
            if (x, y) != (fields["X"], fields["Y"]):
                fields["X"], fields["Y"] = x, y
                self._changed()
                self._fire("PointMoved", item)
        else:
            self._move_end(item, name, x, px)
        self._widget.setCursor(Qt.ClosedHandCursor)

    def _move_end(self, item: GraphItem, name: str, x: float, px: float) -> None:
        """An interval's end dragged to x (past the area's edge: no end)."""
        area = self._area()
        fields = item._fields
        if px <= area.left() + 2:
            x = -_INF
        elif px >= area.right() - 2:
            x = _INF
        else:
            x = self._snapped(x)
        other = "High" if name == "Low" else "Low"
        if (name == "Low" and x > fields["High"]) or (name == "High" and x < fields["Low"]):
            # (dragged past the other end: they swap)
            fields[name], fields[other] = fields[other], x
            closed = name + "Closed", other + "Closed"
            fields[closed[0]], fields[closed[1]] = fields[closed[1]], fields[closed[0]]
            drag = self._drag
            self.__dict__["_drag"] = (drag[0], item, other, drag[3])
            name = other
        if fields[name] != x:
            fields[name] = x
            if math.isinf(x):
                fields[name + "Closed"] = False
            self._changed()
            self._fire("PointMoved", item)

    def _release_at(self, position: QPointF) -> None:
        press, drag = self._press, self._drag
        self.__dict__["_press"] = self.__dict__["_drag"] = None
        if self._values.get("MousePointer", 0) == 0:
            self._widget.unsetCursor()
        if press is None:
            return
        px, py = position.x(), position.y()
        if math.hypot(px - press[0], py - press[1]) >= 4:
            return  # (dragged: not a click)
        handle = press[2]
        x, y = self._mapping()[1](px, py)
        if handle is not None and handle[0]._kind == "Interval" and \
                not (drag is not None and drag[3]):  # (an end clicked: open or closed)
            item, name = handle
            item._fields[name + "Closed"] = not item._fields[name + "Closed"]
            self._changed()
            self._fire("PointMoved", item)
        elif handle is None:
            self._place(x, y)
        self._fire("Click", x, y)

    def _place(self, x: float, y: float) -> None:
        mode = self._values.get("PlaceMode", PLACE_NONE)
        x, y = self._snapped(x), self._snapped(y)
        if self._values.get("Mode") == NUMBER_LINE:
            y = 0.0
        placed = self._placed
        if mode == PLACE_POINT:
            point = next((item for item in placed if item._kind == "Point"), None)
            if point is None:
                point = self.AddPoint(x, y, Draggable=True)
                placed.append(point)
            else:
                point._fields["X"], point._fields["Y"] = x, y
                self._changed()
            self._fire("PointMoved", point)
        elif mode == PLACE_LINE:
            points = [item for item in placed if item._kind == "Point"]
            if len(points) >= 2:
                return  # (both are there: they are dragged now)
            point = self.AddPoint(x, y, Draggable=True)
            placed.append(point)
            if points:
                placed.append(self.AddLine(points[0], point))
            self._fire("PointMoved", point)

    # -- painting ---------------------------------------------------------------------------------
    def _dark(self) -> bool:
        return self._widget.palette().color(QPalette.Window).lightness() < 128

    def _scheme_colors(self) -> tuple[QColor, QColor, QColor, QColor]:
        """(background, ink, grid, minor grid)."""
        palette = self._widget.palette()
        values = self._values
        back = self._qcolor(values["BackColor"]) if values.get("BackColor") is not None else \
            palette.color(QPalette.Base)
        ink = self._qcolor(values["ForeColor"]) if values.get("ForeColor") is not None else \
            palette.color(QPalette.Text)
        if values.get("GridColor") is not None:
            grid = self._qcolor(values["GridColor"])
            minor = QColor(grid)
            minor.setAlphaF(grid.alphaF() * 0.45)
        else:
            grid = _blend(ink, back, 0.22 if self._dark() else 0.17)
            minor = _blend(ink, back, 0.11 if self._dark() else 0.07)
        return back, ink, grid, minor

    def _item_color(self, item: GraphItem) -> QColor:
        color = item._fields["Color"]
        if color is not None:
            return self._qcolor(color)
        if item._kind == "Label":
            return self._scheme_colors()[1]
        light, dark = PLOT_COLORS[item._auto % len(PLOT_COLORS)]
        return QColor(dark if self._dark() else light)

    def _fill_color(self, item: GraphItem, alpha: float) -> QColor | None:
        fill = item._fields["FillColor"]
        if fill is not None:
            return self._qcolor(fill)
        if item._kind in ("Polygon",):
            return None
        color = QColor(self._item_color(item))
        color.setAlphaF(alpha)
        return color

    def _pen(self, item: GraphItem, style=None) -> QPen:
        pen = QPen(self._item_color(item), max(0.5, float(item._fields["Width"])))
        style = int(item._fields["Style"] if style is None else style)
        pen.setStyle(_DRAW_PENS.get(style, Qt.SolidLine))
        pen.setCapStyle(Qt.RoundCap if pen.style() == Qt.SolidLine else Qt.FlatCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _paint(self, widget) -> None:
        painter = QPainter(widget)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        back, ink, grid, minor = self._scheme_colors()
        painter.fillRect(widget.contentsRect(), back)
        area = self._area()
        mode = self._values.get("Mode", PLANE)
        ticks = self._tick_steps()
        painter.save()
        painter.setClipRect(area)
        if self._values.get("ShowGrid", True) and mode != NUMBER_LINE:
            self._paint_grid(painter, ticks, grid, minor)
        shown = [item for item in self._items._list
                 if item.Visible and item.__dict__["_error"] is None]
        for item in shown:
            if item._kind in _FILLED:
                self._paint_item(painter, item)
        for item in shown:
            if item._kind not in _FILLED + _ON_TOP:
                self._paint_item(painter, item)
        painter.restore()
        if self._values.get("ShowAxes", True):
            self._paint_axes(painter, ticks, ink, back)
        painter.save()
        painter.setClipRect(area)
        for item in shown:  # (points and intervals over the axes)
            if item._kind in _ON_TOP:
                self._paint_item(painter, item)
        if not self._design_mode:
            self._paint_drawings(painter)
        painter.restore()
        painter.end()

    def _paint_drawings(self, painter: QPainter) -> None:
        """The graphics methods: what was drawn outside Paint, then the Paint event."""
        origin = self._drawing_origin()
        painter.save()
        painter.translate(origin)
        try:
            if self._drawn:
                self._replay(painter)
            if self._handler("Paint") is not None:
                state = self._draw_state()
                state["painter"] = painter
                try:
                    self._fire("Paint")
                finally:
                    state["painter"] = None
        finally:
            painter.restore()

    def _paint_item(self, painter: QPainter, item: GraphItem) -> None:
        try:
            getattr(self, "_paint_" + item._kind.lower())(painter, item)
        except Exception as error:  # noqa: BLE001 - (a function of the program's failed)
            item.__dict__["_error"] = error  # (not drawn again until it changes)
            from .app import report_runtime_error

            QTimer.singleShot(0, lambda error=error: report_runtime_error(error))

    # -- the axes and the grid ---------------------------------------------------------------------
    def _tick_steps(self):
        """((x step, x minor, π?), (y step, y minor))."""
        x0, x1, y0, y1 = self._view()
        area = self._area()
        values = self._values
        metrics = QFontMetricsF(self._widget.font())
        least = max(40.0, metrics.horizontalAdvance("−0.00") + 14)
        if values.get("PiTicks"):
            multiple = pi_step(x1 - x0, area.width(), least)
            x_step = float(multiple) * math.pi
            x_minor = x_step / (3 if multiple.denominator in (3, 6, 12) else 2)
            x_ticks = (x_step, x_minor, multiple)
        else:
            x_step = float(values.get("XStep") or 0) or nice_step(x1 - x0, area.width(), least)
            x_ticks = (x_step, _minor(x_step), None)
        y_step = float(values.get("YStep") or 0) or \
            nice_step(y1 - y0, area.height(), max(28.0, metrics.lineSpacing() * 1.8))
        return x_ticks, (y_step, _minor(y_step))

    def _paint_grid(self, painter: QPainter, ticks, grid: QColor, minor: QColor) -> None:
        x0, x1, y0, y1 = self._view()
        to_px = self._mapping()[0]
        area = self._area()
        (x_step, x_minor, _pi), (y_step, y_minor) = ticks
        for step, color, major in ((x_minor, minor, False), (x_step, grid, True)):
            if not major and step * area.width() / (x1 - x0) < 8:
                continue
            painter.setPen(QPen(color, 1))
            for k in _ticks(x0, x1, step):
                if not major and _on_step(k * step, x_step):
                    continue
                px = round(to_px(k * step, 0)[0]) + 0.5
                painter.drawLine(QPointF(px, area.top()), QPointF(px, area.bottom()))
        for step, color, major in ((y_minor, minor, False), (y_step, grid, True)):
            if not major and step * area.height() / (y1 - y0) < 8:
                continue
            painter.setPen(QPen(color, 1))
            for k in _ticks(y0, y1, step):
                if not major and _on_step(k * step, y_step):
                    continue
                py = round(to_px(0, k * step)[1]) + 0.5
                painter.drawLine(QPointF(area.left(), py), QPointF(area.right(), py))

    def _paint_axes(self, painter: QPainter, ticks, ink: QColor, back: QColor) -> None:
        mode = self._values.get("Mode", PLANE)
        x0, x1, y0, y1 = self._view()
        to_px = self._mapping()[0]
        area = self._area()
        font = self._widget.font()
        metrics = QFontMetricsF(font)
        painter.setFont(font)
        numbers = self._values.get("ShowNumbers", True)
        (x_step, x_minor, multiple), (y_step, _y_minor) = ticks
        pen = QPen(ink, 1.2)
        painter.setPen(pen)
        # Where the axes cross: at 0 when it's shown (Plane), else at the edges
        if mode == DATA:
            ax, ay = area.left(), area.bottom()
        else:
            ax = min(max(to_px(0, 0)[0], area.left()), area.right())
            ay = min(max(to_px(0, 0)[1], area.top()), area.bottom())
            ax, ay = round(ax) + 0.5, round(ay) + 0.5
        painter.drawLine(QPointF(area.left(), ay), QPointF(area.right(), ay))
        if mode != NUMBER_LINE:
            painter.drawLine(QPointF(ax, area.top()), QPointF(ax, area.bottom()))
        if mode == PLANE:  # (arrows at the positive ends)
            _arrow_head(painter, QPointF(area.right() - 1, ay), 0.0, ink, 8)
            _arrow_head(painter, QPointF(ax, area.top() + 1), -math.pi / 2, ink, 8)
        elif mode == NUMBER_LINE:
            _arrow_head(painter, QPointF(area.right() - 1, ay), 0.0, ink, 8)
            _arrow_head(painter, QPointF(area.left() + 1, ay), math.pi, ink, 8)
        size = 4.0 if mode != NUMBER_LINE else 6.0
        halo = QColor(back)
        halo.setAlphaF(0.85)
        # Ticks and numbers along X
        if mode == NUMBER_LINE and x_minor * area.width() / (x1 - x0) >= 6:
            painter.setPen(QPen(ink, 1))
            for k in _ticks(x0, x1, x_minor):
                px = round(to_px(k * x_minor, 0)[0]) + 0.5
                painter.drawLine(QPointF(px, ay - 3), QPointF(px, ay + 3))
        below = mode == DATA or ay + size + metrics.height() + 2 <= area.bottom() or \
            mode == NUMBER_LINE
        for k in _ticks(x0, x1, x_step):
            value = k * x_step
            px = round(to_px(value, 0)[0]) + 0.5
            painter.setPen(QPen(ink, 1.2))
            painter.drawLine(QPointF(px, ay - (0 if mode == DATA else size)),
                             QPointF(px, ay + size))
            if not numbers or (mode == PLANE and k == 0 and x0 < 0 < x1 and y0 < 0 < y1):
                continue
            text = pi_text(k * multiple) if multiple is not None else number_text(value, x_step)
            width = metrics.horizontalAdvance(text)
            top = ay + size + 2 if below else ay - size - 2 - metrics.height()
            rect = QRectF(px - width / 2 - 1, top, width + 2, metrics.height())
            if mode == DATA or area.left() + width / 2 <= px <= area.right() - width / 2:
                if mode == PLANE:
                    painter.fillRect(rect, halo)
                painter.setPen(ink)
                painter.drawText(rect, Qt.AlignCenter, text)
        # Ticks and numbers along Y
        if mode != NUMBER_LINE:
            right = mode == PLANE and ax - size - 4 - metrics.horizontalAdvance("−00") < \
                area.left()
            for k in _ticks(y0, y1, y_step):
                value = k * y_step
                py = round(to_px(0, value)[1]) + 0.5
                painter.setPen(QPen(ink, 1.2))
                painter.drawLine(QPointF(ax - size, py), QPointF(ax + (0 if mode == DATA else
                                                                       size), py))
                if not numbers or (mode == PLANE and k == 0 and x0 < 0 < x1 and y0 < 0 < y1):
                    continue
                text = number_text(value, y_step)
                width = metrics.horizontalAdvance(text)
                left = ax + size + 3 if right else ax - size - 3 - width
                rect = QRectF(left - 1, py - metrics.height() / 2, width + 2, metrics.height())
                if mode == DATA or area.top() < py - metrics.height() / 2 and \
                        py + metrics.height() / 2 < area.bottom():
                    if mode == PLANE:
                        painter.fillRect(rect, halo)
                    painter.setPen(ink)
                    painter.drawText(rect, Qt.AlignCenter, text)
        if numbers and mode == PLANE and x0 < 0 < x1 and y0 < 0 < y1:  # (one 0 at the origin)
            width = metrics.horizontalAdvance("0")
            rect = QRectF(ax - size - 3 - width, ay + 2, width + 2, metrics.height())
            painter.fillRect(rect, halo)
            painter.setPen(ink)
            painter.drawText(rect, Qt.AlignCenter, "0")
        self._paint_axis_names(painter, ax, ay, ink, metrics)

    def _paint_axis_names(self, painter, ax, ay, ink, metrics) -> None:
        mode = self._values.get("Mode", PLANE)
        area = self._area()
        x_name, y_name = self._values.get("XLabel", ""), self._values.get("YLabel", "")
        font = self._widget.font()
        if mode == DATA:
            if x_name:
                width = text_width(x_name, font)
                bottom = self._widget.contentsRect().bottom() - metrics.descent() - 2
                draw_text(painter, x_name, area.center().x() - width / 2, bottom, font, ink)
            if y_name:
                width = text_width(y_name, font)
                painter.save()
                painter.translate(self._widget.contentsRect().left() + metrics.ascent() + 3,
                                  area.center().y() + width / 2)
                painter.rotate(-90)
                draw_text(painter, y_name, 0, 0, font, ink)
                painter.restore()
            return
        italic = _italic(font)
        if x_name and mode == PLANE:
            width = text_width(x_name, italic)
            draw_text(painter, x_name, area.right() - width - 6, ay - 7 - metrics.descent(),
                      italic, ink)
        if y_name and mode == PLANE:  # (a number line: no names)
            draw_text(painter, y_name, ax + 9, area.top() + metrics.ascent() + 2, italic, ink)

    # -- the plots ---------------------------------------------------------------------------------
    def _paint_function(self, painter: QPainter, item: GraphItem) -> None:
        f = item._fields
        x0, x1, _y0, _y1 = self._view()
        low = max(x0, f["XMin"]) if f["XMin"] is not None else x0
        high = min(x1, f["XMax"]) if f["XMax"] is not None else x1
        if high < low:
            return
        path = self._function_path(item._function("F", ("x",)), low, high)
        painter.setPen(self._pen(item))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        self._paint_curve_label(painter, item, path)

    def _function_path(self, fn, low: float, high: float) -> QPainterPath:
        """y = fn(x) from low to high as a path, broken where it isn't defined or
        jumps (an asymptote: the curve leaves the view and comes back elsewhere)."""
        to_px, _from_px = self._mapping()
        area = self._area()
        limit = area.height() * 20
        top, bottom = area.top() - limit, area.bottom() + limit
        count = max(2, int(area.width() * (high - low) / max(1e-12, self._view()[1] -
                                                              self._view()[0])) + 1)
        path = QPainterPath()
        previous = None  # (x, y in pixels) of the last point drawn, or None: a break

        def clamp(py):
            return min(max(py, top), bottom)

        def join(xa, ya, xb, yb, depth):
            """The points between two samples (pixels): a list, or None for a break."""
            # (in clamped pixels: a pole's sides stay far apart however close the samples
            # get; a steep curve's come together)
            pa, pb = clamp(to_px(xa, ya)[1]), clamp(to_px(xb, yb)[1])
            if abs(pa - pb) < area.height() / 2 or depth > 10:
                return [] if depth <= 10 or abs(pa - pb) < area.height() else None
            xm = (xa + xb) / 2
            ym = fn(xm)
            if not math.isfinite(ym):
                return None
            left, right = join(xa, ya, xm, ym, depth + 1), join(xm, ym, xb, yb, depth + 1)
            if left is None or right is None:
                return None
            return left + [(xm, ym)] + right

        last = None
        for k in range(count):
            x = low + (high - low) * k / (count - 1)
            y = fn(x)
            if not math.isfinite(y):
                last = previous = None
                continue
            if last is not None:
                between = join(last[0], last[1], x, y, 0)
                if between is None:
                    previous = None
                else:
                    for bx, by in between:
                        px, py = to_px(bx, by)
                        path.lineTo(px, clamp(py))
            px, py = to_px(x, y)
            if previous is None:
                path.moveTo(px, clamp(py))
            else:
                path.lineTo(px, clamp(py))
            previous = last = (x, y)
        return path

    def _curve_points(self, item: GraphItem, count: int) -> list[tuple[float, float]]:
        f = item._fields
        points = []
        if item._kind == "Parametric":
            fx, fy = item._function("X", ("t",)), item._function("Y", ("t",))
            low, high = f["TMin"], f["TMax"]
            for k in range(count + 1):
                t = low + (high - low) * k / count
                points.append((fx(t), fy(t)))
        else:
            fr = item._function("R", ("theta", "t"))
            low, high = f["ThetaMin"], f["ThetaMax"]
            for k in range(count + 1):
                theta = low + (high - low) * k / count
                r = fr(theta, theta)
                points.append((r * math.cos(theta), r * math.sin(theta)))
        return points

    def _paint_parametric(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        area = self._area()
        jump = math.hypot(area.width(), area.height()) / 3
        path = QPainterPath()
        previous = None
        for x, y in self._curve_points(item, 720):
            if not (math.isfinite(x) and math.isfinite(y)):
                previous = None
                continue
            px, py = to_px(x, y)
            if previous is None or math.hypot(px - previous[0], py - previous[1]) > jump:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
            previous = (px, py)
        painter.setPen(self._pen(item))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        self._paint_curve_label(painter, item, path)

    _paint_polar = _paint_parametric

    def _paint_curve_label(self, painter: QPainter, item: GraphItem, path: QPainterPath) -> None:
        """A curve's Label near where it leaves the view (or its end), on the side
        of the curve toward the middle of the view."""
        label = item._fields["Label"]
        if not label or path.isEmpty():
            return
        area = self._area().adjusted(4, 4, -4, -4)
        inside = [QPointF(e.x, e.y) for e in (path.elementAt(k) for k in
                                              range(path.elementCount()))
                  if area.contains(QPointF(e.x, e.y))]
        if not inside:
            return
        font = self._widget.font()
        width = text_width(label, font)
        metrics = QFontMetricsF(font)
        stroke = QPainterPathStroker()
        stroke.setWidth(float(item._fields["Width"]) + 4)
        curve = stroke.createStroke(path)
        center = area.center()
        last, travelled, first = inside[-1], 0.0, None
        for k in range(len(inside) - 1, 0, -1):  # (back along the curve from its end)
            here, there = inside[k], inside[k - 1]
            step = math.hypot(here.x() - there.x(), here.y() - there.y())
            travelled += step
            if travelled < 12 or step == 0:
                continue
            dx, dy = (here.x() - there.x()) / step, (here.y() - there.y()) / step
            mx, my = -dy, dx  # (across the curve: toward the middle first)
            if mx * (center.x() - here.x()) + my * (center.y() - here.y()) < 0:
                mx, my = dy, -dx
            for gap in (6, 18):
                for nx, ny in ((mx, my), (-mx, -my)):
                    x, y = here.x() + nx * gap, here.y() + ny * gap
                    box = QRectF(x if nx >= 0 else x - width,
                                 y if ny >= 0 else y - metrics.height(), width, metrics.height())
                    first = first or box
                    if area.contains(box) and not curve.intersects(box):
                        draw_text(painter, label, box.left(), box.top() + metrics.ascent(),
                                  font, self._item_color(item))
                        return
            if travelled > 160:
                break
        box = first or QRectF(last.x(), last.y(), width, metrics.height())
        left = min(max(box.left(), area.left()), area.right() - width)
        top = min(max(box.top(), area.top()), area.bottom() - metrics.height())
        draw_text(painter, label, left, top + metrics.ascent(), font, self._item_color(item))

    def _paint_point(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        line = self._values.get("Mode") == NUMBER_LINE
        x, y = item.X, (0.0 if line else item.Y)
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        px, py = to_px(x, y)
        self._dot(painter, item, px, py, item._fields["Open"], item._fields["Size"])
        label = item._fields["Label"]
        if label:
            font = self._widget.font()
            size = item._fields["Size"]
            draw_text(painter, label, px + size + 3, py - size - 2, font,
                      self._item_color(item))

    def _dot(self, painter, item, px, py, hollow: bool, size: float) -> None:
        color = self._item_color(item)
        painter.setPen(QPen(color, 2 if hollow else 1))
        painter.setBrush(self._scheme_colors()[0] if hollow else color)
        painter.drawEllipse(QPointF(px, py), size, size)

    def _line_ends(self, item: GraphItem):
        """A line item's ends in pixels: Segment/Vector as they are, a Ray or Line
        drawn on past the view."""
        to_px = self._mapping()[0]
        (ax, ay), (bx, by) = item.Points
        a, b = to_px(ax, ay), to_px(bx, by)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        if item._kind in ("Segment", "Vector"):
            return a, b
        area = self._area()
        far = (math.hypot(area.width(), area.height()) * 2 +
               math.hypot(a[0] - area.center().x(), a[1] - area.center().y())) / length
        end = (a[0] + dx * far, a[1] + dy * far)
        start = a if item._kind == "Ray" else (a[0] - dx * far, a[1] - dy * far)
        return start, end

    def _paint_segment(self, painter: QPainter, item: GraphItem) -> None:
        ends = self._line_ends(item)
        if ends is None:
            return
        (ax, ay), (bx, by) = ends
        pen = self._pen(item)
        painter.setPen(pen)
        if item._kind == "Vector":
            angle = math.atan2(by - ay, bx - ax)
            head = 6 + pen.widthF() * 2.5
            # (the shaft stops where the head starts)
            shaft = QPointF(bx - math.cos(angle) * head * 0.8, by - math.sin(angle) * head * 0.8)
            painter.drawLine(QPointF(ax, ay), shaft)
            _arrow_head(painter, QPointF(bx, by), angle, pen.color(), head)
        else:
            painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
        label = item._fields["Label"]
        if label:
            if item._kind in ("Segment", "Vector"):
                mx, my = (ax + bx) / 2, (ay + by) / 2
            else:
                (px, py), (qx, qy) = (self._mapping()[0](*p) for p in item.Points)
                mx, my = (px + qx) / 2, (py + qy) / 2
            draw_text(painter, label, mx + 6, my - 6, self._widget.font(),
                      self._item_color(item))

    _paint_ray = _paint_line = _paint_vector = _paint_segment

    def _paint_polygon(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        points = [QPointF(*to_px(x, y)) for x, y in item.Points]
        if len(points) < 2:
            return
        fill = self._fill_color(item, 0.25)
        painter.setPen(self._pen(item))
        painter.setBrush(fill if fill is not None else Qt.NoBrush)
        painter.drawPolygon(QPolygonF(points))

    def _paint_region(self, painter: QPainter, item: GraphItem) -> None:
        f = item._fields
        x0, x1, _y0, _y1 = self._view()
        low = max(x0, f["XMin"]) if f["XMin"] is not None else x0
        high = min(x1, f["XMax"]) if f["XMax"] is not None else x1
        if high <= low:
            return
        fn, gn = item._function("F", ("x",)), item._function("G", ("x",))
        to_px = self._mapping()[0]
        area = self._area()
        limit = area.height() * 20
        count = max(2, int(area.width() * (high - low) / (x1 - x0)) + 1)
        runs, run = [], []
        for k in range(count):
            x = low + (high - low) * k / (count - 1)
            a, b = fn(x), gn(x)
            if math.isfinite(a) and math.isfinite(b):
                px, pa = to_px(x, a)
                pb = to_px(x, b)[1]
                run.append((px, min(max(pa, area.top() - limit), area.bottom() + limit),
                            min(max(pb, area.top() - limit), area.bottom() + limit)))
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._fill_color(item, 0.28))
        for run in runs:
            polygon = [QPointF(px, pa) for px, pa, _pb in run] + \
                [QPointF(px, pb) for px, _pa, pb in reversed(run)]
            painter.drawPolygon(QPolygonF(polygon))

    def _paint_inequality(self, painter: QPainter, item: GraphItem) -> None:
        relations = _relations(item._fields["Text"])
        fill = self._fill_color(item, 0.2)
        x0, x1, y0, y1 = self._view()
        to_px, from_px = self._mapping()
        area = self._area()
        strict = any(op in ("<", ">") for _g, op in relations)
        if len(relations) == 1:
            g, op = relations[0]
            linear = _linear_in_y(g, x0, x1, y0, y1)
            if linear is not None:
                self._paint_half_plane(painter, item, g, op, linear, fill)
                return
        # Any other: the cells where they all hold, and the edges between
        cell = 3
        columns, rows = int(area.width() / cell) + 2, int(area.height() / cell) + 2
        xs = [from_px(area.left() + c * cell, 0)[0] for c in range(columns)]
        ys = [from_px(0, area.top() + r * cell)[1] for r in range(rows)]
        values = [[[g(x, y) for x in xs] for y in ys] for g, _op in relations]
        image = QImage(columns, rows, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        for r in range(rows):
            for c in range(columns):
                if all(_holds(values[i][r][c], op) for i, (_g, op) in enumerate(relations)):
                    image.setPixelColor(c, r, fill)
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(QRectF(area.left() - cell / 2, area.top() - cell / 2,
                                 columns * cell, rows * cell), image)
        painter.restore()
        painter.setPen(self._pen(item, 1 if strict else 0))
        for i in range(len(relations)):
            grid = values[i]
            for r in range(rows - 1):
                for c in range(columns - 1):
                    for (ax, ay), (bx, by) in _contour(grid, r, c):
                        painter.drawLine(QPointF(area.left() + ax * cell, area.top() + ay * cell),
                                         QPointF(area.left() + bx * cell, area.top() + by * cell))

    def _paint_half_plane(self, painter, item, g, op, linear, fill) -> None:
        """g(x, y) = a(x)·y + b(x) op 0: below or above the edge y = −b/a (or, with no
        y in it, the strips of x where b(x) op 0)."""
        x0, x1, _y0, _y1 = self._view()
        to_px = self._mapping()[0]
        area = self._area()
        strict = op in ("<", ">")
        count = int(area.width()) + 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        if linear == "x":  # (vertical edges: where b(x) changes)
            strips, start = [], None
            edges = []
            last = None
            for k in range(count):
                x = x0 + (x1 - x0) * k / (count - 1)
                holds = _holds(g(x, 0.0), op)
                if holds and start is None:
                    start = x
                if not holds and start is not None:
                    strips.append((start, x))
                    start = None
                if last is not None and holds != last:
                    edges.append(x)
                last = holds
            if start is not None:
                strips.append((start, x1))
            for a, b in strips:
                left, right = to_px(a, 0)[0], to_px(b, 0)[0]
                painter.drawRect(QRectF(left, area.top(), right - left, area.height()))
            painter.setPen(self._pen(item, 1 if strict else 0))
            for x in edges:
                px = to_px(x, 0)[0]
                painter.drawLine(QPointF(px, area.top()), QPointF(px, area.bottom()))
            return
        above = (linear > 0) == (op in (">", ">="))  # (a > 0: g grows upwards)
        edge = QPainterPath()
        region = QPainterPath()
        limit = area.height() * 20
        start = None
        for k in range(count):
            x = x0 + (x1 - x0) * k / (count - 1)
            b, a = g(x, 0.0), g(x, 1.0) - g(x, 0.0)
            if not (math.isfinite(a) and math.isfinite(b)) or a == 0:
                continue
            px, py = to_px(x, -b / a)
            py = min(max(py, area.top() - limit), area.bottom() + limit)
            if start is None:
                edge.moveTo(px, py)
                start = px
            else:
                edge.lineTo(px, py)
        if start is None:
            return
        last = edge.currentPosition()
        region.addPath(edge)
        y_edge = area.top() - 2 if above else area.bottom() + 2
        region.lineTo(last.x(), y_edge)
        region.lineTo(start, y_edge)
        region.closeSubpath()
        painter.drawPath(region)
        painter.setPen(self._pen(item, 1 if strict else 0))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(edge)

    def _paint_label(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        px, py = to_px(item.X, item.Y)
        font = self._widget.font()
        text = item._fields["Text"]
        width = text_width(text, font)
        alignment = item._fields["Alignment"]
        left = px - width if alignment == 1 else px - width / 2 if alignment == 2 else px
        metrics = QFontMetricsF(font)
        draw_text(painter, text, left, py + (metrics.ascent() - metrics.descent()) / 2, font,
                  self._item_color(item))

    def _paint_interval(self, painter: QPainter, item: GraphItem) -> None:
        f = item._fields
        to_px = self._mapping()[0]
        area = self._area()
        line = self._values.get("Mode") == NUMBER_LINE
        y = 0.0
        pen = self._pen(item)
        pen.setCapStyle(Qt.FlatCap)
        color = pen.color()
        low, high = f["Low"], f["High"]
        left = area.left() + 4 if math.isinf(low) else to_px(low, y)[0]
        right = area.right() - 4 if math.isinf(high) else to_px(high, y)[0]
        py = to_px(0, y)[1]
        if line:
            py = min(max(round(py) + 0.5, area.top()), area.bottom())
        size = max(4.5, pen.widthF() + 1.5)
        painter.setPen(pen)
        if right > left:
            start = left + (pen.widthF() * 2 if math.isinf(low) else 0)
            end = right - (pen.widthF() * 2 if math.isinf(high) else 0)
            painter.drawLine(QPointF(start, py), QPointF(end, py))
        if math.isinf(low):
            _arrow_head(painter, QPointF(left, py), math.pi, color, 6 + pen.widthF() * 1.5)
        if math.isinf(high):
            _arrow_head(painter, QPointF(right, py), 0.0, color, 6 + pen.widthF() * 1.5)
        for value, closed, px in ((low, f["LowClosed"], left), (high, f["HighClosed"], right)):
            if math.isfinite(value):
                self._dot(painter, item, px, py, not closed, size)

    def _paint_histogram(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        edges, counts = histogram_bins(item._fields["Values"], item._fields["Bins"])
        pen = self._pen(item)
        painter.setPen(QPen(pen.color(), max(1.0, item._fields["Width"])))
        painter.setBrush(self._fill_color(item, 0.4))
        for i, count in enumerate(counts):
            left, top = to_px(edges[i], count)
            right, bottom = to_px(edges[i + 1], 0)
            painter.drawRect(QRectF(QPointF(left, top), QPointF(right, bottom)))

    def _paint_dotplot(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        x0, x1, y0, y1 = self._view()
        area = self._area()
        size = max(2.0, min(7.0, area.height() / (y1 - y0) * 0.42))
        seen: dict[float, int] = {}
        for value in item._fields["Values"]:
            level = seen[value] = seen.get(value, 0) + 1
            px, py = to_px(value, level)
            self._dot(painter, item, px, py, False, size)

    def _paint_boxplot(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        low, q1, median, q3, high = five_numbers(item._fields["Values"])
        if not math.isfinite(low):
            return
        y, half = item._fields["Y"], item._fields["Height"] / 2
        pen = self._pen(item)
        pen.setWidthF(max(1.0, pen.widthF() * 0.75))
        painter.setPen(pen)
        top, middle, bottom = to_px(0, y + half)[1], to_px(0, y)[1], to_px(0, y - half)[1]
        xs = {name: to_px(value, y)[0] for name, value in
              (("low", low), ("q1", q1), ("median", median), ("q3", q3), ("high", high))}
        painter.drawLine(QPointF(xs["low"], middle), QPointF(xs["q1"], middle))
        painter.drawLine(QPointF(xs["q3"], middle), QPointF(xs["high"], middle))
        cap = (bottom - top) / 4
        for x in (xs["low"], xs["high"]):
            painter.drawLine(QPointF(x, middle - cap), QPointF(x, middle + cap))
        painter.setBrush(self._fill_color(item, 0.25))
        painter.drawRect(QRectF(QPointF(xs["q1"], top), QPointF(xs["q3"], bottom)))
        painter.drawLine(QPointF(xs["median"], top), QPointF(xs["median"], bottom))

    def _paint_scatter(self, painter: QPainter, item: GraphItem) -> None:
        to_px = self._mapping()[0]
        points = item._fields["Points"]
        if item._fields["FitLine"]:
            slope, intercept, _r = least_squares(points)
            if math.isfinite(slope):
                x0, x1, _y0, _y1 = self._view()
                pen = self._pen(item)
                pen.setWidthF(max(1.0, pen.widthF() * 0.75))
                painter.setPen(pen)
                painter.drawLine(QPointF(*to_px(x0, slope * x0 + intercept)),
                                 QPointF(*to_px(x1, slope * x1 + intercept)))
        for x, y in points:
            px, py = to_px(x, y)
            self._dot(painter, item, px, py, False, 3.5)


for _name in _RECORDED:
    setattr(Graph, _name, _recorded(_name))
del _name
_add_validation(Graph)
_add_mouse_members(Graph)
CONTROL_TYPES["Graph"] = Graph  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")


# --- helpers ------------------------------------------------------------------------------------

def _minor(step: float) -> float:
    """The minor grid's step: fifths of 1 and 5, quarters of 2."""
    mantissa = step / 10 ** math.floor(math.log10(step)) if step > 0 else 1
    return step / (4 if round(mantissa) == 2 else 5)


def _on_step(value: float, step: float) -> bool:
    return abs(value / step - round(value / step)) < 1e-6


def _blend(a: QColor, b: QColor, amount: float) -> QColor:
    """a mixed into b: amount of a."""
    return QColor(round(a.red() * amount + b.red() * (1 - amount)),
                  round(a.green() * amount + b.green() * (1 - amount)),
                  round(a.blue() * amount + b.blue() * (1 - amount)))


def _italic(font):
    italic = type(font)(font)
    italic.setItalic(True)
    return italic


def _arrow_head(painter: QPainter, tip: QPointF, angle: float, color: QColor,
                size: float) -> None:
    """A filled arrowhead pointing at angle (radians, 0: right; y down)."""
    back = size
    wide = size * 0.45
    cos, sin = math.cos(angle), math.sin(angle)
    points = [tip,
              QPointF(tip.x() - back * cos - wide * sin, tip.y() - back * sin + wide * cos),
              QPointF(tip.x() - back * cos + wide * sin, tip.y() - back * sin - wide * cos)]
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF(points))
    painter.restore()


def _linear_in_y(g, x0, x1, y0, y1):
    """For g(x, y) = a(x)·y + b(x) with a(x) of one sign: that sign (1 or −1);
    "x" when there is no y in it; None otherwise."""
    signs = set()
    for k in range(9):
        x = x0 + (x1 - x0) * (k + 0.37) / 9
        b, a = g(x, 0.0), g(x, 1.0) - g(x, 0.0)
        for y in (y0, y1, (y0 + y1) / 2 + 0.31):
            v = g(x, y)
            if math.isfinite(v) and math.isfinite(a) and math.isfinite(b) and \
                    abs(v - (a * y + b)) > 1e-6 * (1 + abs(v)):
                return None
        if math.isfinite(a) and abs(a) > 1e-12:
            signs.add(1 if a > 0 else -1)
    if not signs:
        return "x"
    return signs.pop() if len(signs) == 1 else None


def _contour(grid, r: int, c: int):
    """Marching squares: the edge g = 0 crossing a cell (r, c) of sampled values,
    as segments in cell units."""
    corners = ((c, r, grid[r][c]), (c + 1, r, grid[r][c + 1]), (c + 1, r + 1, grid[r + 1][c + 1]),
               (c, r + 1, grid[r + 1][c]))
    if not all(math.isfinite(v) for _x, _y, v in corners):
        return []
    crossings = []
    for i in range(4):
        (xa, ya, va), (xb, yb, vb) = corners[i], corners[(i + 1) % 4]
        if (va < 0) != (vb < 0):
            t = va / (va - vb)
            crossings.append((xa + (xb - xa) * t, ya + (yb - ya) * t))
    if len(crossings) == 2:
        return [(crossings[0], crossings[1])]
    if len(crossings) == 4:
        return [(crossings[0], crossings[1]), (crossings[2], crossings[3])]
    return []


def _pieces(text: str):
    """Text and its ``$…$`` formulas: [(text or TeX, is it maths)]."""
    from vp6help.tex import math_spans

    pieces, at = [], 0
    for span in math_spans(text):
        if span.start > at:
            pieces.append((text[at:span.start], False))
        pieces.append((span.tex, True))
        at = span.end
    if at < len(text):
        pieces.append((text[at:], False))
    return pieces


def text_width(text: str, font) -> float:
    """How wide draw_text writes text (formulas laid out as TeX)."""
    from vp6help.texdraw import layout_of

    metrics = QFontMetricsF(font)
    return sum(layout_of(piece, False, font)[0].width if maths
               else metrics.horizontalAdvance(piece) for piece, maths in _pieces(text))


def draw_text(painter: QPainter, text: str, x: float, y: float, font, color: QColor) -> None:
    """Text with ``$…$`` maths, its baseline's left end at x, y."""
    from vp6help.texdraw import layout_of, paint

    metrics = QFontMetricsF(font)
    painter.save()
    painter.setFont(font)
    painter.setPen(color)
    for piece, maths in _pieces(text):
        if maths:
            shape, tex_metrics = layout_of(piece, False, font)
            paint(painter, shape, tex_metrics, x, y, color)
            x += shape.width
        else:
            painter.drawText(QPointF(x, y), piece)
            x += metrics.horizontalAdvance(piece)
    painter.restore()

