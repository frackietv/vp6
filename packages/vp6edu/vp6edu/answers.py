"""Checking answers: a student's typed maths, read leniently and checked by kind.

    from fractions import Fraction
    from vp6edu.answers import Exercise, Number, make

    def add_fractions(rng):                  # in a lesson's exercises.py
        a, b = rng.randint(1, 9), rng.randint(2, 9)
        return Exercise(f"Add $\\frac{{{a}}}{{{b}}} + \\frac{{1}}{{{b}}}$.",
                        Number(Fraction(a + 1, b), form="simplest"),
                        hints=["The denominators are the same: add the numerators."])

    exercise = make(add_fractions, seed=7)
    exercise.check("5/8").status             # "right", "not yet" or "unreadable"

``read`` takes what a student types: ``2x``, ``x^2``, ``x²``, ``3(x+1)``,
``sqrt(x)``, ``√x``, ``π``, ``½``, mixed numbers (``2 1/3``), percents,
``1,000``, ``×``, ``÷``, ``−``, ``|x|``. The kinds of answer are ``Choice``,
``Number`` (exact, within a tolerance, rounded, in a form, with units),
``Expression`` (equivalence at random points, and a form), ``Equation``,
``Solutions`` (an equation's, as a set), ``Inequality`` (inequality or
interval notation, or a number line's intervals), ``Pair`` (an ordered pair or
tuple), and ``Point`` and ``Line`` placed on a graph. Each ``check`` returns a
``Result``: ``right``, ``not yet`` or ``unreadable``, with a message, and the
known mistake when it found one (a sign error, the reciprocal, an
unsimplified answer...).

Pure Python: exact arithmetic with ``Fraction`` where it can be, floats where
it can't (roots that aren't exact, trigonometry, logarithms).
"""

from __future__ import annotations

import importlib.util
import inspect
import itertools
import math
import random
import re
import sys
import unicodedata
from collections import namedtuple
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

RIGHT, NOT_YET, UNREADABLE = "right", "not yet", "unreadable"
NO_SOLUTION, ALL_REAL = "no solution", "all real numbers"


class Unreadable(ValueError):
    """Text that can't be read as maths; the message says why, for the student."""


@dataclass
class Result:
    """What a check found: ``status`` (RIGHT, NOT_YET or UNREADABLE), a message
    for the student, and ``mistake``, the known mistake's name ("sign",
    "reciprocal", "unsimplified", "form", "units", "rounding", ...) or ""."""
    status: str
    message: str = ""
    mistake: str = ""

    @property
    def right(self) -> bool:
        return self.status == RIGHT


# --- reading -------------------------------------------------------------------------------

_REPLACEMENTS = [  # (spaces, invisible times and dashes by their code points)
    ("−", "-"), (chr(0x2013), "-"), (chr(0x2010), "-"), (chr(0x2011), "-"),
    (chr(0x2012), "-"), ("×", "*"), ("·", "*"), ("⋅", "*"), ("∙", "*"),
    ("✕", "*"), ("∗", "*"), ("÷", "/"), ("∕", "/"), ("⁄", "/"),
    ("≤", "<="), ("⩽", "<="), ("≥", ">="), ("⩾", ">="), ("≠", "!="),
    ("=<", "<="), ("=>", ">="), ("**", "^"), ("√", " sqrt "), ("∛", " cbrt "),
    ("π", " pi "), ("∞", " inf "), ("∪", " U "), ("⟨", "("),
    ("⟩", ")"), ("〈", "("), ("〉", ")"), (chr(0xa0), " "), (chr(0x2009), " "),
    (chr(0x202f), " "), (chr(0x2061), ""), (chr(0x2062), "*"),
]
_SUPERSCRIPT = re.compile("[⁰¹²³⁴-⁹⁻⁺]+")
_FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸"
                                  "⁹⁻⁺", "0123456789-+")
_GREEK = {"theta": "θ", "alpha": "α", "beta": "β", "phi": "φ",
          "lambda": "λ", "sigma": "σ", "delta": "δ", "mu": "μ"}
_FUNCTIONS = {"sqrt", "cbrt", "sin", "cos", "tan", "sec", "csc", "cot", "arcsin", "arccos",
              "arctan", "asin", "acos", "atan", "ln", "log", "exp", "abs"}
_CONSTANTS = {"pi", "inf", "infinity"}
_WORDS = {"or", "and"}
_NAMES = sorted(_FUNCTIONS | _CONSTANTS | _WORDS | set(_GREEK), key=len, reverse=True)
_RELATIONS = ("=", "<", ">", "<=", ">=", "!=")
_NUMBER = re.compile(r"(\d+)(\.\d*)?|\.()(\d+)")
_NUMBER_GROUPED = re.compile(r"(\d{1,3}(?:,\d{3})+(?![\d]|,\d)|\d+)(\.\d*)?|\.()(\d+)")
_EXPONENT = re.compile(r"[eE][+-]?\d+(?![^\W\d_])")
_OPERATORS = set("+-*/^()[]{}|,;!%=<>±")

_Token = namedtuple("_Token", "kind value text space")  # kind: "num", "name" or "op"


def _normalize(text: str) -> str:
    """Typed maths with its Unicode spelled the plain way (×, −, ², √, π, ½...)."""
    text = _SUPERSCRIPT.sub(lambda m: "^(" + m.group(0).translate(_FROM_SUPERSCRIPT) + ")",
                            str(text))
    for old, new in _REPLACEMENTS:
        text = text.replace(old, new)
    out = []
    for i, ch in enumerate(text):
        parts = unicodedata.decomposition(ch).split()
        if parts[:1] == ["<fraction>"]:  # (½: a mixed number after digits)
            digits = "".join(chr(int(p, 16)) for p in parts[1:]).replace("⁄", "/")
            out.append(f" {digits}" if i and text[i - 1].isdigit() else f"({digits})")
        else:
            out.append(ch)
    return "".join(out)


def _tokens(text: str, thousands: bool = True) -> list:
    text = _normalize(text)
    number = _NUMBER_GROUPED if thousands else _NUMBER
    tokens, i, space = [], 0, False
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            space, i = True, i + 1
            continue
        match = number.match(text, i)
        if match:
            literal = match.group(0).replace(",", "")
            end = match.end()
            exponent = _EXPONENT.match(text, end)
            if exponent:
                literal += exponent.group(0)
                end = exponent.end()
            kind = "sci" if exponent else ("dec" if "." in literal else "int")
            tokens.append(_Token("num", Fraction(literal if literal[0] != "." else "0" + literal),
                                 (kind, text[i:end]), space))
        elif ch.isalpha():
            end = i
            while end < len(text) and text[end].isalpha():
                end += 1
            run, pos = text[i:end], 0
            while pos < len(run):
                lower = run[pos:].lower()
                name = next((n for n in _NAMES if lower.startswith(n)), None)
                if name is None:
                    tokens.append(_Token("name", run[pos], run[pos], space if not pos else False))
                    pos += 1
                else:
                    tokens.append(_Token("name", _GREEK.get(name, name), run[pos:pos + len(name)],
                                         space if not pos else False))
                    pos += len(name)
        elif text[i:i + 2] in ("<=", ">=", "!="):
            tokens.append(_Token("op", text[i:i + 2], text[i:i + 2], space))
            end = i + 2
        elif ch in _OPERATORS:
            tokens.append(_Token("op", ch, ch, space))
            end = i + 1
        else:
            raise Unreadable(f"I can't read “{ch}”.")
        i, space = end, False
    return tokens


class Node:
    """A piece of a formula that ``read`` made: ``op`` is ``num`` (``value`` a
    Fraction, ``kind`` int/dec/sci, ``text`` as typed), ``mixed``, ``var`` and
    ``const`` (``value`` the name), ``neg``, ``add``, ``sub``, ``mul``,
    ``div``, ``pow``, ``func`` (``value`` the function), ``abs``, ``percent``
    or ``fact``, with its ``args``."""
    __slots__ = ("op", "args", "value", "kind", "text")

    def __init__(self, op, *args, value=None, kind="", text=""):
        self.op, self.args, self.value, self.kind, self.text = op, args, value, kind, text

    def variables(self) -> set[str]:
        """The letters it uses (``e`` is Euler's number, not a letter)."""
        if self.op == "var":
            return set() if self.value == "e" else {self.value}
        return set().union(*(arg.variables() for arg in self.args)) if self.args else set()

    def __repr__(self):
        return f"Node({_show(self)!r})"

    def __str__(self):
        return _show(self)


class _Parser:
    def __init__(self, tokens):
        self.tokens, self.i, self.bars = tokens, 0, 0

    def peek(self, k=0):
        j = self.i + k
        return self.tokens[j] if 0 <= j < len(self.tokens) else None

    def at(self, *ops, k=0) -> bool:
        token = self.peek(k)
        return token is not None and token.kind == "op" and token.value in ops

    def take(self):
        self.i += 1
        return self.tokens[self.i - 1]

    def done(self) -> bool:
        return self.i >= len(self.tokens)

    def whole(self) -> Node:
        node = self.expression()
        if not self.done():
            self.leftover()
        return node

    def chain(self) -> list:
        """An expression or a chain of relations: [node, op, node, op, node...]."""
        items = [self.expression()]
        while self.at(*_RELATIONS):
            items += [self.take().value, self.expression()]
        if not self.done():
            self.leftover()
        return items

    def leftover(self):
        token, before = self.peek(), self.peek(-1)
        if token.kind == "num" and before is not None:
            shown = before.text[1] if before.kind == "num" else before.text
            raise Unreadable(f"A number can't follow “{shown}” like that: use * to "
                             "multiply, or ^ for a power.")
        if token.kind == "op" and token.value in ")]}":
            raise Unreadable(f"There's a “{token.value}” without its opening bracket.")
        if token.kind == "op" and token.value in _RELATIONS:
            raise Unreadable(f"There's a “{token.value}” where I expected just an expression.")
        text = token.text[1] if token.kind == "num" else token.text
        raise Unreadable(f"I can't read “{text}” there.")

    def expression(self) -> Node:
        node = self.term()
        while self.at("+", "-"):
            op = "add" if self.take().value == "+" else "sub"
            node = Node(op, node, self.term())
        return node

    def term(self) -> Node:
        node = self.unary()
        while True:
            if self.at("*", "/"):
                op = "mul" if self.take().value == "*" else "div"
                node = Node(op, node, self.unary())
            elif self.starts_factor():
                node = Node("mul", node, self.power(), kind="implicit")
            else:
                return node

    def starts_factor(self) -> bool:
        token = self.peek()
        if token is None:
            return False
        if token.kind == "name":
            return token.value not in _WORDS
        if token.kind == "num":  # ((x + 3)2, |x|3: a number after a bracket)
            before = self.peek(-1)
            closing = (")", "]", "}") if self.bars else (")", "]", "}", "|")
            return before.kind == "op" and before.value in closing
        return token.kind == "op" and (token.value in ("(", "[", "{")
                                       or (token.value == "|" and not self.bars))

    def unary(self) -> Node:
        if self.at("-"):
            self.take()
            return Node("neg", self.unary())
        if self.at("+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> Node:
        base = self.postfix()
        if self.at("^"):
            self.take()
            return Node("pow", base, self.unary())
        return base

    def postfix(self) -> Node:
        node = self.atom()
        while self.at("!", "%"):
            node = Node("fact" if self.take().value == "!" else "percent", node)
        return node

    def atom(self) -> Node:
        token = self.peek()
        if token is None:
            raise Unreadable("Something's missing at the end.")
        if token.kind == "num":
            self.take()
            node = Node("num", value=token.value, kind=token.text[0], text=token.text[1])
            if self._mixed(token):
                numerator = self.take()
                self.take()
                denominator = self.take()
                node = Node("mixed", node, *(Node("num", value=t.value, kind="int", text=t.text[1])
                                             for t in (numerator, denominator)))
            return node
        if token.kind == "name":
            self.take()
            name = token.value
            if name in _FUNCTIONS:
                exponent = None
                if self.at("^"):
                    self.take()
                    exponent = self.postfix()
                if self.peek() is None:
                    raise Unreadable(f"What is {name} of? Something's missing after it.")
                argument = (self.group() if self.at("(", "[", "{")
                            else self.unary() if self.at("-") else self.power())
                node = (Node("abs", argument) if name == "abs"
                        else Node("func", argument, value=name))
                return Node("pow", node, exponent) if exponent is not None else node
            if name in _CONSTANTS:
                return Node("const", value="inf" if name == "infinity" else name)
            if name in _WORDS:
                raise Unreadable(f"“{token.text}” can't go there.")
            return Node("var", value=name)
        if self.at("(", "[", "{"):
            return self.group()
        if self.at("|"):
            self.take()
            self.bars += 1
            inner = self.expression()
            if not self.at("|"):
                raise Unreadable("An absolute value's closing “|” is missing.")
            self.take()
            self.bars -= 1
            return Node("abs", inner)
        if token.value in ")]}":
            raise Unreadable(f"Something's missing before “{token.value}”.")
        raise Unreadable(f"Something's missing before “{token.text}”.")

    def group(self) -> Node:
        self.take()
        bars, self.bars = self.bars, 0
        inner = self.expression()
        self.bars = bars
        if not self.at(")", "]", "}"):
            if self.done():
                raise Unreadable("A closing bracket is missing.")
            self.leftover()
        self.take()
        return inner

    def _mixed(self, whole) -> bool:
        """2 1/3: a whole number, a space, then a fraction of whole numbers."""
        a, slash, b, after, before = (self.peek(), self.peek(1), self.peek(2), self.peek(3),
                                      self.peek(-2))
        return (whole.text[0] == "int" and a is not None and a.kind == "num" and a.space
                and a.text[0] == "int" and slash is not None and slash.kind == "op"
                and slash.value == "/" and b is not None and b.kind == "num"
                and b.text[0] == "int" and not (after is not None and after.kind == "op"
                                                and after.value in "^/")
                and not (before is not None and before.kind == "op" and before.value in "^/"))


def read(text: str, thousands: bool = True) -> Node:
    """A formula as a student types it (``2x``, ``x^2``, ``3(x+1)``, ``√x``, ``½``,
    ``2 1/3``, ``25%``, ``1,000``...). Raises ``Unreadable`` saying why it can't.
    ``thousands`` reads ``1,000`` as a thousand (lists turn it off)."""
    tokens = _tokens(text, thousands)
    if not tokens:
        raise Unreadable("There's nothing to read.")
    return _Parser(tokens).whole()


def _read_chain(text, thousands=True) -> list:
    tokens = _tokens(text, thousands)
    if not tokens:
        raise Unreadable("There's nothing to read.")
    return _Parser(tokens).chain()


_PRECEDENCE = {"add": 1, "sub": 1, "mul": 2, "div": 2, "neg": 3, "pow": 4}


def _show(node: Node, outer: int = 0) -> str:
    op = node.op
    if op == "num":
        text = node.text
    elif op == "mixed":
        text = " ".join([_show(node.args[0]), f"{_show(node.args[1])}/{_show(node.args[2])}"])
    elif op in ("var", "const"):
        text = {"pi": "π", "inf": "∞"}.get(node.value, node.value)
    elif op == "func":
        argument = node.args[0]
        inner = _show(argument, 5)
        if node.value == "sqrt":
            return "√" + inner
        return f"{node.value}({_show(argument)})"
    elif op == "abs":
        return f"|{_show(node.args[0])}|"
    elif op in ("percent", "fact"):
        return _show(node.args[0], 5) + ("%" if op == "percent" else "!")
    elif op == "neg":
        text = "-" + _show(node.args[0], 3)
    else:
        a, b = node.args
        level = _PRECEDENCE[op]
        if op == "mul" and node.kind == "implicit":
            text = _show(a, level) + _show(b, level + 1)
        else:
            symbol = {"add": " + ", "sub": " - ", "mul": "·", "div": "/", "pow": "^"}[op]
            left, right = (level + 1, level) if op == "pow" else (level, level + 1)
            text = _show(a, left) + symbol + _show(b, right)
        return f"({text})" if level < outer else text
    return f"({text})" if outer >= 5 and op in ("neg", "mixed") else text


# --- values --------------------------------------------------------------------------------

class _Free(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


_UNDEFINED = (ZeroDivisionError, ValueError, OverflowError, TypeError)


def _iroot(k: int, n: int) -> int:
    """The integer n-th root of k ≥ 0, rounded down."""
    if k < 2:
        return k
    x = 1 << -(-k.bit_length() // n)
    while True:
        y = ((n - 1) * x + k // x ** (n - 1)) // n
        if y >= x:
            return x
        x = y


def _root(q, n: int):
    """The exact n-th root of a Fraction, or None; ValueError for an even root of a negative."""
    if q < 0:
        if n % 2 == 0:
            raise ValueError("an even root of a negative number")
        root = _root(-q, n)
        return -root if root is not None else None
    a, b = _iroot(q.numerator, n), _iroot(q.denominator, n)
    return Fraction(a, b) if a ** n == q.numerator and b ** n == q.denominator else None


def _power(base, exponent):
    if isinstance(exponent, Fraction) and exponent.denominator == 1:
        n = exponent.numerator
        if isinstance(base, Fraction):
            if base == 0 and n < 0:
                raise ZeroDivisionError
            size = max(base.numerator.bit_length(), base.denominator.bit_length())
            return base ** n if size * abs(n) < 20000 else float(base) ** n
        return base ** n
    if isinstance(exponent, Fraction) and isinstance(base, Fraction) and exponent.denominator <= 64:
        root = _root(base, exponent.denominator)
        if root is not None:
            return _power(root, Fraction(exponent.numerator))
    b, e = float(base), float(exponent)
    if b < 0:
        if isinstance(exponent, Fraction) and exponent.denominator % 2:
            return (-1 if exponent.numerator % 2 else 1) * (-b) ** e
        raise ValueError("a power of a negative number")
    return b ** e


def _function(name, x):
    if name in ("sqrt", "cbrt"):
        n = 2 if name == "sqrt" else 3
        if isinstance(x, Fraction):
            root = _root(x, n)
            if root is not None:
                return root
        if n == 2:
            return math.sqrt(x)
        return math.copysign(abs(float(x)) ** (1 / 3), x)
    x = float(x)
    if name in ("sin", "cos", "tan"):
        return getattr(math, name)(x)
    if name == "sec":
        return 1 / math.cos(x)
    if name == "csc":
        return 1 / math.sin(x)
    if name == "cot":
        return math.cos(x) / math.sin(x)
    if name in ("arcsin", "asin"):
        return math.asin(x)
    if name in ("arccos", "acos"):
        return math.acos(x)
    if name in ("arctan", "atan"):
        return math.atan(x)
    if name == "ln":
        return math.log(x)
    if name == "log":
        return math.log10(x)
    return math.exp(x)


def _evaluate(node: Node, env: dict):
    """The value of a formula (a Fraction when exact, else a float); raises one of
    ``_UNDEFINED`` where it's undefined, ``_Free`` for a letter without a value."""
    op, args = node.op, node.args
    if op == "num":
        return node.value
    if op == "mixed":
        return args[0].value + args[1].value / args[2].value
    if op == "var":
        if node.value in env:
            return env[node.value]
        if node.value == "e":
            return math.e
        raise _Free(node.value)
    if op == "const":
        return math.pi if node.value == "pi" else math.inf
    values = [_evaluate(arg, env) for arg in args]
    if op == "neg":
        return -values[0]
    if op == "add":
        return values[0] + values[1]
    if op == "sub":
        return values[0] - values[1]
    if op == "mul":
        return values[0] * values[1]
    if op == "div":
        if values[1] == 0:
            raise ZeroDivisionError
        return values[0] / values[1]
    if op == "pow":
        return _power(*values)
    if op == "func":
        return _function(node.value, values[0])
    if op == "abs":
        return abs(values[0])
    if op == "percent":
        return values[0] / 100
    if op == "fact":
        x = values[0]
        if not (isinstance(x, Fraction) and x.denominator == 1 and 0 <= x <= 1000):
            raise ValueError("a factorial of a number that isn't a whole number")
        return Fraction(math.factorial(int(x)))
    raise ValueError(op)


def value(text):
    """The value of a number as typed (``2 1/3``, ``√2``, ``25%``): a Fraction
    when exact, else a float. Raises ``Unreadable``, or ValueError when it's
    undefined or has letters in it."""
    try:
        return _evaluate(read(text), {})
    except _Free as free:
        raise ValueError(f"{free.name} has no value") from None
    except _UNDEFINED as error:
        raise ValueError(f"{text} is undefined") from error


def _same(a, b, tolerance=0) -> bool:
    if isinstance(a, Fraction) and isinstance(b, Fraction) and not tolerance:
        return a == b
    try:
        a, b = float(a), float(b)
    except OverflowError:  # (a whole number too big for a float isn't the answer)
        return False
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= max(float(tolerance), 1e-9 * max(abs(a), abs(b)), 1e-12)


def _sample(rng):
    """A value for a letter: small whole numbers and fractions of both signs, never 0."""
    sign = rng.choice((1, -1))
    if rng.random() < 0.5:
        return Fraction(sign * rng.randint(1, 9))
    return Fraction(sign * rng.randint(1, 20), rng.choice((2, 3, 4, 5, 7)))


def _try(node, env):
    try:
        return _evaluate(node, env)
    except _UNDEFINED:
        return None


def equivalent(a, b, variables=(), tries: int = 12):
    """Whether two formulas (text or ``Node``) are equal wherever both are
    defined, tried at random points (exactly with fractions where they can be).
    None when they're never both defined."""
    a = read(a) if isinstance(a, str) else a
    b = read(b) if isinstance(b, str) else b
    names = sorted(a.variables() | b.variables() | set(variables))
    rng = random.Random(0x5EED)
    good = apart = 0
    for _ in range(tries * 6):
        env = {name: _sample(rng) for name in names}
        x, y = _try(a, env), _try(b, env)
        if x is None and y is None:
            continue
        if x is None or y is None:
            apart += 1
            if apart > tries:
                return False
            continue
        if not _same(x, y):
            return False
        good += 1
        if good >= tries or not names:
            return True
    return True if good else None


def _number_text(q) -> str:
    if isinstance(q, Fraction):
        return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"
    return f"{q:.10g}"


def _rounded(q: Fraction, places: int) -> Fraction:
    """q to ``places`` decimal places, halves away from zero."""
    scale = Fraction(10) ** places
    n = math.floor(abs(q) * scale + Fraction(1, 2))
    return Fraction(n if q >= 0 else -n) / scale


def _decimal_text(q: Fraction, places: int) -> str:
    sign = "-" if q < 0 else ""
    n = abs(q) * 10 ** places
    if n.denominator != 1:
        n = Fraction(math.floor(n + Fraction(1, 2)))
    digits = str(n.numerator).rjust(places + 1, "0")
    return sign + (digits[:-places] + "." + digits[-places:] if places > 0 else digits)


def _terminating(q: Fraction) -> int | None:
    """The decimal places q needs, or None when its decimal doesn't end."""
    d, places = q.denominator, 0
    twos = fives = 0
    while d % 2 == 0:
        d, twos = d // 2, twos + 1
    while d % 5 == 0:
        d, fives = d // 5, fives + 1
    return max(twos, fives) if d == 1 else None


# --- polynomials and forms -------------------------------------------------------------------

def _is_int(node) -> bool:
    return node.op == "num" and node.kind == "int"


def _strip_sign(node):
    sign = 1
    while node.op == "neg":
        sign, node = -sign, node.args[0]
    return sign, node


def _literal(node):
    """How a number is written: (kind, info) with kind int, dec, sci, fraction,
    mixed, percent or other; info the scientific coefficient or the fraction's
    (whole, numerator, denominator)."""
    _, node = _strip_sign(node)
    if node.op == "num":
        if node.kind == "sci":
            return "sci", Fraction(re.split("[eE]", node.text)[0])
        return node.kind, None
    if node.op == "mixed":
        return "mixed", tuple(arg.value for arg in node.args)
    if node.op == "percent":
        inner, _ = _literal(node.args[0])
        plain = inner in ("int", "dec") and node.args[0].op == "num"
        return ("percent" if plain else "other"), None
    if node.op == "div" and all(_is_int(_strip_sign(arg)[1]) for arg in node.args):
        return "fraction", (0, _strip_sign(node.args[0])[1].value,
                            _strip_sign(node.args[1])[1].value)
    power, coefficient = node, Fraction(1)
    if node.op == "mul" and node.args[0].op == "num" and node.args[0].kind in ("int", "dec"):
        coefficient, power = node.args[0].value, node.args[1]
    if (power.op == "pow" and _is_int(power.args[0]) and power.args[0].value == 10
            and _is_int(_strip_sign(power.args[1])[1])):
        return "sci", coefficient
    return "other", None


def _poly(node):
    """A polynomial as {monomial: Fraction}, a monomial a sorted tuple of
    (letter, power); None when the formula isn't one."""
    op = node.op
    if op in ("num", "mixed", "percent"):
        try:
            return {(): _evaluate(node, {})}
        except (*_UNDEFINED, _Free):
            return None
    if op == "var":
        return None if node.value == "e" else {((node.value, 1),): Fraction(1)}
    if op == "neg":
        p = _poly(node.args[0])
        return None if p is None else {k: -c for k, c in p.items()}
    if op in ("add", "sub", "mul", "div", "pow"):
        p = _poly(node.args[0])
        if p is None:
            return None
        if op == "pow":
            b = node.args[1]
            try:
                n = _evaluate(b, {})
            except (*_UNDEFINED, _Free):
                return None
            if not (isinstance(n, Fraction) and n.denominator == 1 and 0 <= n <= 32):
                return None
            result = {(): Fraction(1)}
            for _ in range(int(n)):
                result = _poly_mul(result, p)
            return result
        q = _poly(node.args[1])
        if q is None:
            return None
        if op == "add":
            return _poly_add(p, q)
        if op == "sub":
            return _poly_add(p, {k: -c for k, c in q.items()})
        if op == "mul":
            return _poly_mul(p, q)
        if set(q) != {()} or not q[()]:
            return None
        return {k: c / q[()] for k, c in p.items()}
    return None


def _poly_add(p, q):
    result = dict(p)
    for k, c in q.items():
        result[k] = result.get(k, 0) + c
    return {k: c for k, c in result.items() if c}


def _poly_mul(p, q):
    result = {}
    for k1, c1 in p.items():
        for k2, c2 in q.items():
            powers = dict(k1)
            for name, n in k2:
                powers[name] = powers.get(name, 0) + n
            key = tuple(sorted(powers.items()))
            result[key] = result.get(key, 0) + c1 * c2
    return {k: c for k, c in result.items() if c}


def _degree(p) -> int:
    return max((sum(n for _, n in k) for k in p), default=0)


def _univariate(p):
    """(letter, [coefficients from the constant up]) of a polynomial in one letter, or None."""
    names = {name for k in p for name, _ in k}
    if len(names) != 1:
        return None
    name = names.pop()
    coefficients = [Fraction(0)] * (_degree(p) + 1)
    for k, c in p.items():
        coefficients[k[0][1] if k else 0] = c
    return name, coefficients


def _content(p) -> int:
    """The whole number every coefficient shares (1 when they aren't all whole)."""
    if any(c.denominator != 1 for c in p.values()):
        return 1
    g = 0
    for c in p.values():
        g = math.gcd(g, int(c))
    return g or 1


def _divisors(n: int) -> list[int]:
    n, small = abs(n), []
    for d in range(1, math.isqrt(n) + 1):
        if n % d == 0:
            small += [d, n // d]
    return sorted(set(small))


def _rational_root(coefficients):
    """A rational root of a polynomial (coefficients from the constant up), or None."""
    scale = math.lcm(*(c.denominator for c in coefficients))
    integers = [int(c * scale) for c in coefficients]
    if integers[0] == 0:
        return Fraction(0)
    if abs(integers[0]) > 10 ** 8 or abs(integers[-1]) > 10 ** 8:
        return None
    for p in _divisors(integers[0]):
        for q in _divisors(integers[-1]):
            for root in (Fraction(p, q), Fraction(-p, q)):
                if sum(c * root ** i for i, c in enumerate(integers)) == 0:
                    return root
    return None


def _poly_gcd_degree(a, b) -> int:
    """The degree of the common factor of two polynomials in one letter."""
    a, b = list(a), list(b)
    while b and any(b):
        while b and b[-1] == 0:
            b.pop()
        if not b:
            break
        while len(a) >= len(b) and any(a):
            factor = a[-1] / b[-1]
            shift = len(a) - len(b)
            for i, c in enumerate(b):
                a[i + shift] -= factor * c
            while a and a[-1] == 0:
                a.pop()
        a, b = b, a
    return max(len(a) - 1, 0)


def _terms(node):
    """The terms of a sum, each (sign, node)."""
    sign, node = _strip_sign(node)
    if node.op == "add":
        return _terms_signed(node.args[0], sign) + _terms_signed(node.args[1], sign)
    if node.op == "sub":
        return _terms_signed(node.args[0], sign) + _terms_signed(node.args[1], -sign)
    return [(sign, node)]


def _terms_signed(node, sign):
    return [(sign * s, n) for s, n in _terms(node)]


def _factors(node):
    """The factors of a product (signs and numbers' divisions included)."""
    _, node = _strip_sign(node)
    if node.op == "mul":
        return _factors(node.args[0]) + _factors(node.args[1])
    if node.op == "div" and _poly(node.args[1]) is not None and set(_poly(node.args[1])) <= {()}:
        return _factors(node.args[0]) + [node.args[1]]
    return [node]


def _monomial(node):
    """(key, untidy) for a term that's a monomial, or None: key its letters'
    powers (and numeric roots, which make unlike terms), untidy when it
    multiplies numbers or a letter more than once."""
    numbers, powers, roots, untidy = 0, {}, [], False
    for factor in _factors(node):
        base, n = factor, 1
        if factor.op == "pow" and _is_int(factor.args[1]):
            base, n = factor.args[0], int(factor.args[1].value)
        if base.op in ("num", "mixed") or (base.op == "div" and _literal(base)[0] == "fraction"):
            numbers += 1
        elif base.op == "const" and base.value == "pi":
            roots.append(("π", n))
        elif base.op == "func" and base.value in ("sqrt", "cbrt") and _is_int(base.args[0]):
            roots.append((base.value, int(base.args[0].value)))
        elif base.op == "var":
            if base.value in powers:
                untidy = True
            powers[base.value] = powers.get(base.value, 0) + n
        else:
            return None
    return tuple(sorted(powers.items())) + tuple(sorted(roots)), numbers > 1 or untidy


def _walk(node):
    yield node
    for arg in node.args:
        yield from _walk(arg)


def _square_factor(k: int, n: int = 2) -> int:
    """The largest m > 1 with m^n dividing k, or 1."""
    if k > 10 ** 8:
        return 1
    for m in range(_iroot(k, n), 1, -1):
        if k % m ** n == 0:
            return m
    return 1


def _radical_problem(node, below=False):
    if node.op == "func" and node.value in ("sqrt", "cbrt"):
        if below:
            return "Rationalize the denominator: leave no root below the line."
        argument, n = node.args[0], 2 if node.value == "sqrt" else 3
        if _is_int(argument):
            k = int(argument.value)
            m = _square_factor(k, n)
            if m > 1:
                square = Node("num", value=m ** n, kind="int", text=str(m ** n))
                return (f"Simplify {_show(node)}: {m ** n} is a factor of {k}, and "
                        f"{_show(Node('func', square, value=node.value))} = {m}.")
        elif argument.op == "div" and _literal(argument)[0] == "fraction":
            return f"Simplify {_show(node)}: leave no fraction under the root."
    if node.op == "div":
        return _radical_problem(node.args[0], below) or _radical_problem(node.args[1], True)
    for arg in node.args:
        problem = _radical_problem(arg, below)
        if problem:
            return problem
    return None


def _fraction_problem(node):
    for each in _walk(node):
        if each.op != "div":
            continue
        top, bottom = (_strip_sign(arg)[1] for arg in each.args)
        if _is_int(top) and _is_int(bottom):
            a, b = int(top.value), int(bottom.value)
            if b == 1:
                return f"{a}/1 is just {a}."
            if math.gcd(a, b) > 1:
                return f"Simplify {a}/{b}: {math.gcd(a, b)} divides both."
            continue
        p, q = _poly(top), _poly(bottom)
        if p is None or q is None:
            continue
        if set(q) <= {()}:
            common = math.gcd(_content(p), int(q[()])) if q and q[()].denominator == 1 else 1
            if common > 1 and len(p) > 1:
                return (f"The top and the bottom of {_show(each)} share the factor {common}: "
                        "cancel it.")
            continue
        common = math.gcd(_content(p), _content(q))
        if common > 1:
            return f"The top and the bottom of {_show(each)} share the factor {common}: cancel it."
        up, down = _univariate(p), _univariate(q)
        if up and down and up[0] == down[0] and _poly_gcd_degree(up[1], down[1]) > 0:
            return f"The top and the bottom of {_show(each)} share a factor: cancel it."
    return None


def _like_terms_problem(node):
    for each in _walk(node):
        if each.op not in ("add", "sub"):
            continue
        keys = set()
        for _, term in _terms(each):
            found = _monomial(term)
            if found is None:
                continue
            key, untidy = found
            if untidy:
                return (f"Simplify the term {_show(term)}: multiply its numbers, and write "
                        "repeated letters as powers.")
            if key in keys:
                return "Combine the like terms."
            keys.add(key)
    if node.op not in ("add", "sub"):
        found = _monomial(node)
        if found is not None and found[1]:
            return (f"Simplify {_show(node)}: multiply its numbers, and write repeated "
                    "letters as powers.")
    return None


def _simplified_problem(node):
    return _radical_problem(node) or _fraction_problem(node) or _like_terms_problem(node)


def _expanded_problem(node):
    problem = _like_terms_problem(node)
    if problem:
        return problem
    if any(_monomial(term) is None for _, term in _terms(node)):
        return "Multiply out the brackets: write it as a sum of terms."
    return _radical_problem(node) or _fraction_problem(node)


def _factored_problem(node):
    _, body = _strip_sign(node)
    whole = _poly(body)
    if body.op in ("add", "sub"):
        if whole is not None and _irreducible(whole):
            return None  # (a prime polynomial: it is its own factored form)
        return "Write it as a product of factors."
    for factor in _factors(body):
        base = factor.args[0] if factor.op == "pow" else factor
        p = _poly(base)
        if p is None or set(p) <= {()}:
            continue
        common = _content(p)
        if common > 1 and len(p) > 1:
            return f"Take the common factor {common} out of {_show(base)}."
        if len(p) > 1:
            shared = None
            for k in p:
                powers = dict(k)
                shared = powers if shared is None else {n: min(e, powers.get(n, 0))
                                                        for n, e in shared.items() if n in powers}
            if shared:
                return f"Take the common factor {''.join(sorted(shared))} out of {_show(base)}."
        if not _irreducible(p):
            return f"{_show(base)} can be factored further."
    return None


def _irreducible(p) -> bool:
    """No common factor, and (in one letter) no rational root when of degree 2 or more."""
    if _content(p) > 1 and len(p) > 1:
        return False
    one = _univariate(p)
    if one is None or len(one[1]) <= 2:
        return True
    return _rational_root(one[1]) is None


def _standard_problem(node):
    problem = _expanded_problem(node)
    if problem:
        return problem
    degrees = []
    for _, term in _terms(node):
        p = _poly(term)
        degrees.append(_degree(p) if p is not None else 0)
    if any(a < b for a, b in zip(degrees, degrees[1:])):
        return "Write the terms from the highest power down."
    return None


_EXPRESSION_FORMS = {"simplified": _simplified_problem, "expanded": _expanded_problem,
                     "standard": _standard_problem, "factored": _factored_problem}


def _mistake_of(message: str) -> str:
    return "unsimplified" if message.startswith(("Simplify", "Combine", "The top", "Take the",
                                                 "Rationalize")) else "form"


def _rename_case(node, names):
    """Letters typed in the other case (X for x) taken as the question's."""
    if node.op == "var" and node.value not in names:
        for other in (node.value.lower(), node.value.upper()):
            if other in names:
                return Node("var", value=other)
    if not node.args:
        return node
    return Node(node.op, *(_rename_case(arg, names) for arg in node.args), value=node.value,
                kind=node.kind, text=node.text)


# --- units ---------------------------------------------------------------------------------

_M, _G, _S, _RAD = (("m", 1),), (("g", 1),), (("s", 1),), (("rad", 1),)
_M2, _M3 = (("m", 2),), (("m", 3),)
_UNIT_TABLE = [
    (("mm", "millimeter", "millimetre"), _M, Fraction(1, 1000)),
    (("cm", "centimeter", "centimetre"), _M, Fraction(1, 100)),
    (("m", "meter", "metre"), _M, Fraction(1)),
    (("km", "kilometer", "kilometre"), _M, Fraction(1000)),
    (("in", "inch", "inches"), _M, Fraction(254, 10000)),
    (("ft", "foot", "feet"), _M, Fraction(3048, 10000)),
    (("yd", "yard"), _M, Fraction(9144, 10000)),
    (("mi", "mile"), _M, Fraction(1609344, 1000)),
    (("mg", "milligram"), _G, Fraction(1, 1000)),
    (("g", "gram"), _G, Fraction(1)),
    (("kg", "kilogram"), _G, Fraction(1000)),
    (("oz", "ounce"), _G, Fraction(28349523125, 10 ** 9)),
    (("lb", "lbs", "pound"), _G, Fraction(45359237, 10 ** 5)),
    (("s", "sec", "second"), _S, Fraction(1)),
    (("min", "minute"), _S, Fraction(60)),
    (("h", "hr", "hour"), _S, Fraction(3600)),
    (("day",), _S, Fraction(86400)),
    (("wk", "week"), _S, Fraction(604800)),
    (("yr", "year"), _S, Fraction(31557600)),
    (("mL", "ml", "milliliter", "millilitre"), _M3, Fraction(1, 10 ** 6)),
    (("L", "l", "liter", "litre"), _M3, Fraction(1, 1000)),
    (("gal", "gallon"), _M3, Fraction(3785411784, 10 ** 12)),
    (("qt", "quart"), _M3, Fraction(946352946, 10 ** 12)),
    (("pt", "pint"), _M3, Fraction(473176473, 10 ** 12)),
    (("c", "cup"), _M3, Fraction(2365882365, 10 ** 16)),
    (("fl oz", "fluid ounce"), _M3, Fraction(295735295625, 10 ** 19)),
    (("tbsp", "tablespoon"), _M3, Fraction(1478676478125, 10 ** 20)),
    (("tsp", "teaspoon"), _M3, Fraction(492892159375, 10 ** 20)),
    (("acre",), _M2, Fraction(40468564224, 10 ** 7)),
    (("ha", "hectare"), _M2, Fraction(10000)),
    (("mph",), (("m", 1), ("s", -1)), Fraction(1609344, 3600000)),
    (("°", "deg", "degree"), _RAD, math.pi / 180),
    (("rad", "radian"), _RAD, Fraction(1)),
    (("$", "dollar", "usd"), (("$", 1),), Fraction(1)),
    (("¢", "cent"), (("$", 1),), Fraction(1, 100)),
    (("°C", "celsius", "degrees celsius", "degree celsius"), (("°C", 1),), Fraction(1)),
    (("°F", "fahrenheit", "degrees fahrenheit", "degree fahrenheit"), (("°F", 1),),
     Fraction(1)),
    (("K", "kelvin"), (("K", 1),), Fraction(1)),
]
_UNITS = {}
for _names, _dimension, _factor in _UNIT_TABLE:
    for _name in _names:
        _UNITS[_name] = (_dimension, _factor)
        if len(_name) > 2 and _name[-1] not in "s" and _name not in ("feet", "inches", "celsius"):
            _UNITS.setdefault(_name + "s", (_dimension, _factor))
_UNIT_START = re.compile(r"[^\W\d_]|[°¢$]")


def _unit(text):
    """(dimension, factor) of a unit like cm, cm^2, square feet, km/h or miles per
    hour; None when it isn't one."""
    text = re.sub(r"\s+per\s+", "/", text.strip())
    text = re.sub(r"\^\((-?\d+)\)", r"^\1", text)
    if not text:
        return None
    dimension, factor = {}, Fraction(1)
    for index, part in enumerate(text.split("/")):
        match = re.fullmatch(r"(?:(square|sq\.?|cubic|cu\.?)\s+)?(.+?)(?:\s*\^?\s*([23]))?",
                             part.strip())
        if not match:
            return None
        prefix, name, exponent = match.groups()
        power = 2 if prefix and prefix.startswith("s") else 3 if prefix else int(exponent or 1)
        entry = _UNITS.get(name) or _UNITS.get(name.lower())
        if entry is None:
            return None
        sign = 1 if index == 0 else -1
        for base, n in entry[0]:
            dimension[base] = dimension.get(base, 0) + n * power * sign
        factor *= entry[1] ** (power * sign)
    return tuple(sorted((b, n) for b, n in dimension.items() if n)), factor


def _split_units(text: str):
    """(the number, the unit or None) of an answer like ``5 cm``, ``$3.50`` or ``12 km/h``."""
    text = _normalize(text).strip()
    match = re.match(r"([-+]?)\s*\$\s*(?=[\d.])", text)
    if match:
        return match.group(1) + text[match.end():], "$"
    for found in _UNIT_START.finditer(text):
        i = found.start()
        if i == 0 or not (text[i - 1].isdigit() or text[i - 1] in " ).%"):
            continue
        tail = text[i:].strip()
        if tail.lower() in ("pi", "e") or tail.lower().startswith(("pi ", "sqrt")):
            continue
        if _unit(tail) is not None:
            return text[:i].strip(), tail
    return text, None


# --- the kinds of answer ---------------------------------------------------------------------

class Answer:
    """An answer to check a response against: subclasses read a response
    (``_read``, raising ``Unreadable``) and judge it (``_judge``). ``mistakes``
    maps known wrong answers (as the student would type them) to their
    feedback; ``text`` is the answer as a student would type it."""

    def __init__(self, mistakes=None):
        self.mistakes = dict(mistakes or {})

    @property
    def text(self) -> str:
        raise NotImplementedError

    def check(self, response) -> Result:
        """``right``, ``not yet`` or ``unreadable``, with a message."""
        if isinstance(response, str) and not response.strip():
            return Result(UNREADABLE, "Type your answer first.")
        try:
            got = self._read(response)
        except Unreadable as error:
            return Result(UNREADABLE, str(error))
        return self._judge(got)

    def _read(self, response):
        raise NotImplementedError

    def _judge(self, got) -> Result:
        raise NotImplementedError

    def _same_answer(self, got, other) -> bool:
        raise NotImplementedError

    def _known(self, got):
        """The feedback for one of ``mistakes``, if the response is one."""
        for wrong, message in self.mistakes.items():
            try:
                if self._same_answer(got, self._read(wrong)):
                    return Result(NOT_YET, message, "known")
            except Unreadable:
                continue
        return None


def _labels(count):
    return [chr(ord("A") + i) for i in range(count)]


class Choice(Answer):
    """A multiple choice: ``correct`` is an option's letter (``"B"``), index or
    text, or a list of them when several are right. Responses: ``"b"``,
    ``"(B)"``, ``"B, D"``, an option's text, an index or a list."""

    def __init__(self, correct, options=(), mistakes=None):
        super().__init__(mistakes)
        self.options = list(options)
        self.many = isinstance(correct, (list, tuple, set, frozenset))
        items = correct if self.many else [correct]
        self.correct = frozenset(self._label(item) for item in items)

    @property
    def labels(self):
        return _labels(len(self.options)) if self.options else _labels(26)

    def _label(self, item) -> str:
        if isinstance(item, bool):
            raise Unreadable("Choose an option.")
        if isinstance(item, int):
            if not 0 <= item < len(self.labels):
                raise Unreadable("There's no such option.")
            return self.labels[item]
        text = " ".join(str(item).split()).strip("().: ").upper()
        if text in self.labels:
            return text
        for label, option in zip(_labels(len(self.options)), self.options):
            if " ".join(str(option).split()).upper() == " ".join(str(item).split()).upper():
                return label
        raise Unreadable(f"Choose one of {', '.join(self.labels[:len(self.options) or 4])}.")

    @property
    def text(self):
        return ", ".join(sorted(self.correct))

    def _read(self, response):
        if isinstance(response, (list, tuple, set, frozenset)):
            return frozenset(self._label(item) for item in response)
        if isinstance(response, int):
            return frozenset([self._label(response)])
        text = str(response).strip()
        try:
            return frozenset([self._label(text)])
        except Unreadable:
            pass
        parts = [p for p in re.split(r"\s*(?:,|;|\band\b|&|\s)\s*", text, flags=re.I) if p]
        if (len(parts) == 1 and len(parts[0]) > 1
                and all(c.upper() in self.labels for c in parts[0])):
            parts = list(parts[0])
        return frozenset(self._label(part) for part in parts)

    def _same_answer(self, got, other):
        return got == other

    def _judge(self, got):
        if got == self.correct:
            return Result(RIGHT, "Right!")
        if not self.many and len(got) > 1:
            return Result(NOT_YET, "Choose just one.")
        for label in sorted(got - self.correct):
            if label in self.mistakes:
                return Result(NOT_YET, self.mistakes[label], "known")
        known = self._known(got)
        if known:
            return known
        wrong, missing = got - self.correct, self.correct - got
        if self.many and not wrong:
            more = "another one is" if len(missing) == 1 else f"{len(missing)} more are"
            return Result(NOT_YET, f"Those are right, but {more} too.")
        if self.many and wrong and got & self.correct:
            verb = "isn't" if len(wrong) == 1 else "aren't"
            return Result(NOT_YET, f"{', '.join(sorted(wrong))} {verb} right.")
        return Result(NOT_YET, "Not yet.")


@dataclass
class _NumberReading:
    value: object           # a Fraction, a float, or None when undefined
    node: Node | None
    unit: str | None
    kind: str
    info: object = None


NUMBER_FORMS = (None, "any", "integer", "fraction", "simplest", "mixed", "decimal", "percent",
                "scientific", "simplified")


class Number(Answer):
    """A number: exact (``Fraction``s compare exactly), or within ``tolerance``,
    or rounded to ``places`` decimal places. ``value`` is a number or text
    (``"3/4"``, ``"2√3"``, ``"5 cm"``). ``form`` asks for a way of writing it:
    integer, fraction (reduced), simplest (a reduced fraction or mixed
    number), mixed, decimal, percent, scientific (a × 10^n, 1 ≤ a < 10),
    simplified (roots and fractions simplified), or any (an unworked
    expression like 2+3 is fine). Without a form the answer must be a
    single number, a fraction unreduced being right with a note. ``units``
    makes them needed (``"cm"``, ``"km/h"``, ``"$"``); ``convert`` accepts
    the same amount in other units of the kind."""

    def __init__(self, value, *, tolerance=0, places=None, form=None, units=None,
                 convert=False, mistakes=None):
        if form not in NUMBER_FORMS:
            raise ValueError(f"form {form!r} isn't one of {NUMBER_FORMS[1:]}")
        self._given = None
        if isinstance(value, str):
            number, unit = _split_units(value)
            units = units or unit
            self._given = number
            value = _evaluate(read(number), {})
        elif not isinstance(value, float):
            value = Fraction(value)
        self.value, self.tolerance, self.places, self.form = value, tolerance, places, form
        self.units, self.convert = units, convert
        self._unit = _unit(units) if units else None
        if units and self._unit is None:
            raise ValueError(f"unknown unit {units!r}")
        exact = value if isinstance(value, Fraction) else Fraction(repr(value))
        self.target = _rounded(exact, places) if places is not None else None
        super().__init__(mistakes)

    @property
    def rational(self) -> bool:
        return isinstance(self.value, Fraction)

    @property
    def text(self):
        if self.target is not None:
            text = _decimal_text(self.target, self.places)
        elif not self.rational:
            text = self._given or f"{self.value:.10g}"
        else:
            text = self._form_text(self.value)
        if not self.units:
            return text
        if self.units == "$":
            return "-$" + text[1:] if text.startswith("-") else "$" + text
        return f"{text} {self.units}"

    def _form_text(self, q: Fraction) -> str:
        form = self.form
        if form == "percent":
            places = _terminating(q * 100)
            return (_decimal_text(q * 100, places) if places is not None
                    else _number_text(q * 100)) + "%"
        if form == "mixed" and abs(q) > 1 and q.denominator != 1:
            whole, part = divmod(abs(q), 1)
            return f"{'-' if q < 0 else ''}{whole} {part.numerator}/{part.denominator}"
        if form == "decimal" and q.denominator != 1:
            places = _terminating(q)
            return _decimal_text(q, places) if places is not None else f"{float(q):.12g}"
        if form == "scientific" and q:
            exponent = 0
            while abs(q) / Fraction(10) ** exponent >= 10:
                exponent += 1
            while abs(q) / Fraction(10) ** exponent < 1:
                exponent -= 1
            coefficient = q / Fraction(10) ** exponent
            places = _terminating(coefficient)
            digits = (_decimal_text(coefficient, places) if places is not None
                      else f"{float(coefficient):.10g}")
            return f"{digits} × 10^{exponent}"
        return _number_text(q)

    def _read(self, response):
        if isinstance(response, bool):
            raise Unreadable("Type a number.")
        if isinstance(response, (int, Fraction)):
            q = Fraction(response)
            return _NumberReading(q, None, None, "int" if q.denominator == 1 else "fraction",
                                  (0, abs(q.numerator), q.denominator))
        if isinstance(response, float):
            return _NumberReading(response, None, None, "dec")
        number, unit = _split_units(str(response))
        if not number:
            raise Unreadable("Type the number too.")
        chain = _read_chain(number)
        if len(chain) == 3 and chain[1] == "=" and chain[0].op == "var":
            chain = chain[2:]
        if len(chain) > 1:
            raise Unreadable("Give just the number.")
        node = chain[0]
        try:
            q = _evaluate(node, {})
        except _Free as free:
            raise Unreadable(f"The answer is a number, without letters ({free.name}).") from None
        except _UNDEFINED:
            q = None
        kind, info = _literal(node)
        return _NumberReading(q, node, unit, kind, info)

    def _same_answer(self, got, other):
        return got.value is not None and other.value is not None and _same(got.value, other.value)

    def _matches(self, q) -> bool:
        if self.target is not None:
            return _same(q, self.target, 0 if isinstance(q, Fraction) else 1e-12)
        return _same(q, self.value, self.tolerance)

    def _judge(self, got):
        q = got.value
        if q is None:
            return Result(NOT_YET, "That's undefined (a division by zero, or a root of a "
                                   "negative number).")
        if got.unit and self._unit:
            theirs = _unit(got.unit)
            if theirs[0] != self._unit[0]:
                if self._matches(q):
                    return Result(NOT_YET, f"Right number, but check the units: the answer is "
                                           f"in {self.units}.", "units")
                return Result(NOT_YET, f"{got.unit} doesn't measure the same thing as "
                                       f"{self.units}.", "units")
            if theirs[1] != self._unit[1]:
                converted = q * theirs[1] / self._unit[1]
                if self.convert:
                    q = converted
                elif self._matches(converted):
                    return Result(NOT_YET, f"That's right in {got.unit}: now give it in "
                                           f"{self.units}.", "units")
                elif self._matches(q):
                    return Result(NOT_YET, f"Right number, but check the units: the answer is "
                                           f"in {self.units}.", "units")
        if self._matches(q):
            if self._unit and not got.unit:
                return Result(NOT_YET, f"Right! Now give the units too ({self.units}).", "units")
            problem = self._form_problem(got)
            if problem:
                return Result(NOT_YET, problem[0], problem[1])
            if self.form is None and got.kind in ("fraction", "mixed"):
                whole, a, b = got.info
                if math.gcd(int(a), int(b)) > 1:
                    return Result(RIGHT, f"Right! It simplifies to {self._simplest(q)}.")
            return Result(RIGHT, "Right!")
        known = self._known(got)
        return known or self._mistake(got, q) or Result(NOT_YET, "Not yet.")

    def _simplest(self, q):
        if abs(q) > 1 and q.denominator != 1 and self.form != "fraction":
            whole, part = divmod(abs(q), 1)
            return f"{'-' if q < 0 else ''}{whole} {part.numerator}/{part.denominator}"
        return _number_text(q)

    def _form_problem(self, got):
        """(message, mistake) when the answer's value is right but not its form."""
        form, kind, q = self.form, got.kind, got.value
        if form == "any" or got.node is None:
            return None
        if kind == "other" and form not in ("simplified",) and (self.rational or form):
            if self.rational:
                return "Right, but work it out: give a single number.", "unevaluated"
        if form is None:
            return None
        if form == "integer" and kind != "int":
            return "Write it as a whole number.", "form"
        if form == "decimal" and kind not in ("int", "dec"):
            return "Write it as a decimal.", "form"
        if form == "percent" and kind != "percent":
            return "Write it as a percent.", "form"
        if form == "scientific":
            if kind != "sci" or not 1 <= abs(got.info) < 10:
                return ("Write it in scientific notation: a × 10^n, with a at least 1 "
                        "and less than 10.", "form")
        if form in ("fraction", "simplest", "mixed"):
            allowed = {"fraction": ("int", "fraction"), "simplest": ("int", "fraction", "mixed"),
                       "mixed": ("int", "mixed")}[form]
            if form == "mixed" and abs(q) < 1:
                allowed = ("int", "fraction", "mixed")
            if kind not in allowed:
                return {"fraction": "Write it as a fraction.",
                        "simplest": "Write it as a fraction in simplest form.",
                        "mixed": "Write it as a mixed number."}[form], "form"
            if kind in ("fraction", "mixed"):
                whole, a, b = got.info
                if b == 1:
                    return f"{a}/1 is just {a}.", "unsimplified"
                if math.gcd(int(a), int(b)) > 1:
                    return (f"Right, but simplify it: {math.gcd(int(a), int(b))} divides "
                            f"{a} and {b}.", "unsimplified")
                if kind == "mixed" and a >= b:
                    return "The fraction in a mixed number is less than 1.", "unsimplified"
            if kind == "fraction" and form == "mixed" and abs(q) > 1:
                return "Write it as a mixed number.", "form"
        if form == "simplified":
            problem = _radical_problem(got.node) or _fraction_problem(got.node)
            if problem:
                return problem, "unsimplified"
        return None

    def _mistake(self, got, q):
        expected = self.target if self.target is not None else self.value
        if self.places is not None and got.kind == "dec":
            exact = q if isinstance(q, Fraction) else Fraction(repr(q))
            if _rounded(exact, self.places) == self.target:
                return Result(NOT_YET, f"Round it to {self.places} decimal place"
                                       f"{'s' if self.places != 1 else ''}.", "rounding")
            if abs(exact - self.target) == Fraction(1, 10 ** self.places):
                return Result(NOT_YET, "Check your rounding: look at the next digit.", "rounding")
        if got.kind == "dec" and not self.tolerance and self.target is None and got.node:
            typed = _strip_sign(got.node)[1].text
            decimals = len(typed.split(".")[1]) if "." in typed else 0
            if decimals and abs(float(q) - float(expected)) <= 0.5 * 10 ** -decimals + 1e-12:
                kind = " (a fraction)" if self.rational else ""
                return Result(NOT_YET, f"Close: {typed} is rounded. Give the exact value{kind}.",
                              "approximate")
        if expected and _same(q, -expected):
            return Result(NOT_YET, "Check the sign.", "sign")
        if expected and abs(expected) != 1 and q and _same(q * expected, 1):
            return Result(NOT_YET, "That's the reciprocal: it's upside down.", "reciprocal")
        if expected and (got.kind == "percent" or self.form == "percent"):
            if _same(q, expected * 100):
                return Result(NOT_YET, f"Write it as a percent: {_number_text(expected * 100)}%.",
                              "percent")
            if _same(q, expected / 100):
                return Result(NOT_YET, "A percent is a number out of 100: check where the "
                                       "decimal point goes.", "percent")
        if expected and q:
            for k in (1, 2, 3):
                if _same(q, expected * 10 ** k) or _same(q, expected / 10 ** k):
                    return Result(NOT_YET, "Check the place value: where does the decimal "
                                           "point go?", "place value")
        return None


class Expression(Answer):
    """An expression, right when it equals ``expected`` at random points
    (exactly, with fractions, where it can). ``form`` asks for simplified
    (like terms combined, fractions reduced, roots simplified), expanded (no
    brackets), standard (expanded, highest power first) or factored
    (completely: no common factor left, no factor with a rational root)."""

    FORMS = (None,) + tuple(_EXPRESSION_FORMS)

    def __init__(self, expected, *, form=None, variables=(), mistakes=None):
        if form not in self.FORMS:
            raise ValueError(f"form {form!r} isn't one of {self.FORMS[1:]}")
        super().__init__(mistakes)
        self.expected, self.form = expected, form
        self.node = read(expected)
        self.names = sorted(self.node.variables() | set(variables))

    @property
    def text(self):
        return self.expected

    def _read(self, response):
        if isinstance(response, Node):
            return _rename_case(response, self.names)
        chain = _read_chain(str(response))
        if (len(chain) == 3 and chain[1] == "=" and chain[0].op == "var"
                and chain[0].value not in self.names):
            chain = chain[2:]  # (y = ... for an expression in x)
        if len(chain) > 1:
            raise Unreadable("This asks for an expression, not an equation.")
        return _rename_case(chain[0], self.names)

    def _same_answer(self, got, other):
        return bool(equivalent(got, other, self.names))

    def _judge(self, got):
        extra = got.variables() - set(self.names)
        if extra:
            return Result(NOT_YET, f"Your answer has {', '.join(sorted(extra))} in it, which the "
                                   "question doesn't.", "letters")
        same = equivalent(got, self.node, self.names)
        if same:
            problem = _EXPRESSION_FORMS[self.form](got) if self.form else None
            if problem:
                return Result(NOT_YET, problem, _mistake_of(problem))
            return Result(RIGHT, "Right!")
        known = self._known(got)
        if known:
            return known
        if same is None:
            return Result(NOT_YET, "I couldn't compare that with the answer: is it defined?")
        if equivalent(got, Node("neg", self.node), self.names):
            return Result(NOT_YET, "Check the signs.", "sign")
        return Result(NOT_YET, "Not yet.")


def _difference(chain):
    return Node("sub", chain[0], chain[2])


def _equations_equivalent(a, b, names, tries=12):
    """Whether two equations (as left − right) say the same: one a constant
    multiple of the other, or else the same solutions found along a letter
    they're linear in (A = lw and w = A/l)."""
    return _multiples(a, b, names, tries) or bool(_same_zeros(a, b, names, tries))


def _solve_linear(f, letter, env):
    """The value of ``letter`` making f zero, when f is linear in it there; else None."""
    y = [_try(f, dict(env, **{letter: Fraction(n)})) for n in (1, 2, 3)]
    if None in y:
        return None
    slope = y[1] - y[0]
    if _same(slope, 0) or not _same(y[2] - y[1], slope):
        return None
    return 1 - y[0] / slope


def _same_zeros(a, b, names, tries=12):
    rng = random.Random(0x5EED)
    for letter in names:
        directions = 0
        for p, q in ((a, b), (b, a)):
            found = 0
            for _ in range(tries * 4):
                env = {name: _sample(rng) for name in names if name != letter}
                root = _solve_linear(p, letter, env)
                if root is None:
                    continue
                env[letter] = root
                y = _try(q, env)
                if y is None:
                    continue
                if not _same(y, 0):
                    return False
                found += 1
                if found >= tries:
                    break
            if not found:
                break
            directions += 1
        if directions == 2:
            return True
    return None


def _multiples(a, b, names, tries):
    rng = random.Random(0x5EED)
    ratio, good = None, 0
    for _ in range(tries * 6):
        env = {name: _sample(rng) for name in names}
        x, y = _try(a, env), _try(b, env)
        if x is None or y is None:
            continue
        zero_x, zero_y = _same(x, 0), _same(y, 0)
        if zero_x != zero_y:
            return False
        good += 1
        if not zero_x:
            r = x / y
            if ratio is None:
                ratio = r
            elif not _same(r, ratio):
                return False
        if good >= tries:
            break
    return good > 0


EQUATION_FORMS = (None, "slope-intercept", "standard")


class Equation(Answer):
    """An equation, right when it says the same as ``expected`` (one side minus
    the other a constant multiple). ``form``: slope-intercept (y = mx + b),
    standard (Ax + By = C with whole numbers); ``solved_for`` a letter: it
    alone on the left."""

    def __init__(self, expected, *, form=None, solved_for=None, mistakes=None):
        if form not in EQUATION_FORMS:
            raise ValueError(f"form {form!r} isn't one of {EQUATION_FORMS[1:]}")
        super().__init__(mistakes)
        self.expected, self.form, self.solved_for = expected, form, solved_for
        self.chain = self._read(expected)
        self.names = sorted(_difference(self.chain).variables())

    @property
    def text(self):
        return self.expected

    def _read(self, response):
        chain = _read_chain(str(response))
        if len(chain) != 3 or chain[1] != "=":
            raise Unreadable("Write an equation, with one “=”.")
        names = getattr(self, "names", None)
        if names:
            chain = [_rename_case(chain[0], names), "=", _rename_case(chain[2], names)]
        return chain

    def _same_answer(self, got, other):
        return _equations_equivalent(_difference(got), _difference(other), self.names)

    def _judge(self, got):
        extra = _difference(got).variables() - set(self.names)
        if extra:
            return Result(NOT_YET, f"Your answer has {', '.join(sorted(extra))} in it, which the "
                                   "question doesn't.", "letters")
        if not _equations_equivalent(_difference(got), _difference(self.chain), self.names):
            return self._known(got) or Result(NOT_YET, "Not yet.")
        problem = _equation_form_problem(got, self.form, self.solved_for)
        if problem:
            return Result(NOT_YET, problem, "form")
        return Result(RIGHT, "Right!")


def _equation_form_problem(chain, form, solved_for):
    left, _, right = chain
    if solved_for and not (left.op == "var" and left.value == solved_for
                           and solved_for not in right.variables()):
        return f"Solve it for {solved_for}: {solved_for} alone on the left."
    if form == "slope-intercept":
        p = _poly(right)
        if (left.op != "var" or left.value != "y" or "y" in right.variables() or p is None
                or _degree(p) > 1 or _expanded_problem(right)):
            return "Write it in slope-intercept form, y = mx + b."
    if form == "standard":
        p, q = _poly(left), _poly(right)
        if (p is None or q is None or () in p or set(q) - {()} or _degree(p) != 1
                or any(c.denominator != 1 for c in list(p.values()) + list(q.values()))
                or _expanded_problem(left)):
            return "Write it in standard form, Ax + By = C, with whole numbers A, B and C."
    return None


def _number_of(item):
    if isinstance(item, str):
        return value(item)
    return item if isinstance(item, float) else Fraction(item)


def _strip_brackets(tokens):
    if (len(tokens) >= 2 and tokens[0].kind == "op" and tokens[-1].kind == "op"
            and tokens[0].value in "([{" and tokens[-1].value in ")]}"):
        depth = 0
        for i, token in enumerate(tokens):
            if token.kind == "op" and token.value in "([{":
                depth += 1
            elif token.kind == "op" and token.value in ")]}":
                depth -= 1
                if depth == 0 and i < len(tokens) - 1:
                    return tokens
        return tokens[1:-1]
    return tokens


def _split_tokens(tokens, separators=(",", ";"), words=()):
    """Tokens split at separators outside brackets: [(separator before, tokens)]."""
    pieces, current, depth, before = [], [], 0, None
    for token in tokens:
        if token.kind == "op" and token.value in "([{":
            depth += 1
        elif token.kind == "op" and token.value in ")]}":
            depth -= 1
        if depth == 0 and ((token.kind == "op" and token.value in separators)
                           or (token.kind == "name" and token.value in words)):
            pieces.append((before, current))
            current, before = [], token.value
            continue
        current.append(token)
    pieces.append((before, current))
    return pieces


def _constant(tokens):
    if not tokens:
        raise Unreadable("Something's missing between the commas.")
    node = _Parser(tokens).whole()
    try:
        return _evaluate(node, {})
    except _Free as free:
        raise Unreadable(f"Give numbers, without letters ({free.name}).") from None
    except _UNDEFINED:
        raise Unreadable("One of those numbers is undefined.") from None


class Pair(Answer):
    """An ordered pair or tuple of numbers, ``(2, 3)``; with ``names``, also
    typed as ``x = 2, y = 3`` (in any order). Responses may be tuples, or
    objects with X and Y (a graph's point)."""

    def __init__(self, values, *, names=None, tolerance=0, mistakes=None):
        super().__init__(mistakes)
        self.values = tuple(_number_of(v) for v in values)
        self.names, self.tolerance = tuple(names) if names else None, tolerance

    @property
    def text(self):
        return "(" + ", ".join(_number_text(v) for v in self.values) + ")"

    def _read(self, response):
        if not isinstance(response, str):
            if hasattr(response, "X") and hasattr(response, "Y"):
                response = (response.X, response.Y)
            elif hasattr(response, "x") and hasattr(response, "y"):
                response = (response.x, response.y)
            return tuple(_number_of(v) for v in response)
        tokens = _strip_brackets(_tokens(response, thousands=False))
        pieces = [piece for _, piece in _split_tokens(tokens)]
        if len(pieces) == 1:
            raise Unreadable("Write it as (a, b), with a comma between the numbers.")
        if self.names and all(len(p) > 2 and p[0].kind == "name" and p[1].value == "="
                              for p in pieces):
            named = {p[0].value.lower(): _constant(p[2:]) for p in pieces}
            if set(named) == {n.lower() for n in self.names}:
                return tuple(named[n.lower()] for n in self.names)
        return tuple(_constant(piece) for piece in pieces)

    def _same_answer(self, got, other):
        return len(got) == len(other) and all(_same(a, b, self.tolerance)
                                              for a, b in zip(got, other))

    def _judge(self, got):
        if len(got) != len(self.values):
            return Result(NOT_YET, f"Give {len(self.values)} numbers.")
        if self._same_answer(got, self.values):
            return Result(RIGHT, "Right!")
        known = self._known(got)
        if known:
            return known
        if len(got) == 2 and self._same_answer(got[::-1], self.values):
            first = f": {self.names[0]} comes first" if self.names else ""
            return Result(NOT_YET, f"They're the wrong way round{first}.", "swapped")
        right = [_same(a, b, self.tolerance) for a, b in zip(got, self.values)]
        if any(right):
            names = self.names or [f"number {i + 1}" for i in range(len(right))]
            wrong = [n for n, ok in zip(names, right) if not ok]
            return Result(NOT_YET, f"Nearly: check {' and '.join(wrong)}.")
        return Result(NOT_YET, "Not yet.")


class Point(Pair):
    """A point (x, y), typed or placed on a graph (an object with X and Y, or a
    tuple), within ``tolerance``."""

    def __init__(self, x, y, *, tolerance=0, mistakes=None):
        super().__init__((x, y), names=("x", "y"), tolerance=tolerance, mistakes=mistakes)


def _line_of(node):
    """(a, b, c) with a·x + b·y + c = 0 for a formula in x and y that's linear, or None."""
    f = lambda x, y: _try(node, {"x": Fraction(x), "y": Fraction(y)})  # noqa: E731
    c = f(0, 0)
    if c is None:
        return None
    ax, by = f(1, 0), f(0, 1)
    if ax is None or by is None:
        return None
    a, b = ax - c, by - c
    for x, y in ((2, 3), (-1, 5), (7, -4)):
        v = f(x, y)
        if v is None or not _same(v, a * x + b * y + c):
            return None
    return (a, b, c) if a or b else None


def _points_of(response):
    if hasattr(response, "Points"):
        response = response.Points
    elif all(hasattr(response, n) for n in ("X1", "Y1", "X2", "Y2")):
        response = ((response.X1, response.Y1), (response.X2, response.Y2))
    points = []
    for p in response:
        if hasattr(p, "X"):
            p = (p.X, p.Y)
        points.append((_number_of(p[0]), _number_of(p[1])))
    return points


class Line(Answer):
    """A straight line, ``"y = 2x + 1"``: typed as an equation (checked as one,
    ``form`` too), or placed on a graph as two points (an object with Points or
    X1, Y1, X2, Y2, or a pair of (x, y)), each within ``tolerance`` of the line."""

    def __init__(self, expected, *, tolerance=0, form=None, mistakes=None):
        super().__init__(mistakes)
        self.equation = Equation(expected, form=form)
        self.expected, self.tolerance = expected, tolerance
        self.line = _line_of(_difference(self.equation.chain))
        if self.line is None:
            raise ValueError(f"{expected!r} isn't a straight line")

    @property
    def text(self):
        return self.expected

    def _read(self, response):
        if isinstance(response, str):
            chain = self.equation._read(response)
            extra = _difference(chain).variables() - {"x", "y"}
            if extra:
                raise Unreadable(f"A line's equation has only x and y in it, not "
                                 f"{', '.join(sorted(extra))}.")
            line = _line_of(_difference(chain))
            if line is None:
                raise Unreadable("That isn't the equation of a straight line.")
            return chain, line, None
        points = _points_of(response)
        if len(points) != 2 or (_same(points[0][0], points[1][0])
                                and _same(points[0][1], points[1][1])):
            raise Unreadable("Place two different points on the line.")
        (x1, y1), (x2, y2) = points
        a, b = y2 - y1, x1 - x2
        return None, (a, b, -(a * x1 + b * y1)), points

    def _same_answer(self, got, other):
        return _parallel(got[1], other[1]) and _parallel(got[1][::2], other[1][::2]) and \
            _parallel(got[1][1:], other[1][1:])

    def _judge(self, got):
        chain, line, points = got
        a, b, c = self.line
        if points:
            norm = math.hypot(float(a), float(b))
            right = all(abs(float(a * x + b * y + c)) <= max(float(self.tolerance), 1e-9) * norm
                        for x, y in points)
        else:
            right = self._same_answer(got, (None, self.line, None))
        if right:
            if chain is not None:
                problem = _equation_form_problem(chain, self.equation.form, None)
                if problem:
                    return Result(NOT_YET, problem, "form")
            return Result(RIGHT, "Right!")
        known = self._known(got)
        if known:
            return known
        if _parallel(line[:2], self.line[:2]):
            return Result(NOT_YET, "Right slope, but the line is in the wrong place: check where "
                                   "it crosses the y-axis.", "intercept")
        if b and line[1] and _same(-line[0] / line[1], a / b) and a:
            return Result(NOT_YET, "Check the slope's sign: the line goes the wrong way.", "sign")
        if b and line[1] and _same(-line[2] / line[1], -c / b):
            return Result(NOT_YET, "Right y-intercept: now check the slope.", "slope")
        return Result(NOT_YET, "Not yet.")


def _parallel(u, v) -> bool:
    """Whether two vectors are multiples of each other."""
    nu = math.sqrt(sum(float(x) ** 2 for x in u))
    nv = math.sqrt(sum(float(x) ** 2 for x in v))
    if not nu or not nv:
        return nu == nv
    for i in range(len(u)):
        for j in range(i + 1, len(u)):
            if abs(float(u[i] * v[j] - u[j] * v[i])) > 1e-9 * nu * nv:
                return False
    return True


_NONE = re.compile(r"(no (real )?(solutions?|roots?|numbers?)|none|∅|ø|\{\s*\}|"
                   r"there (are|is) no (real )?(solutions?|roots?))\.?", re.I)
_ALL = re.compile(r"(all real numbers|all reals|every real number|any real number|all numbers|"
                  r"infinitely many( solutions)?|ℝ|r|x is any real number)\.?", re.I)


def _expand_plus_minus(tokens):
    """The tokens with each ± made + and then − (every combination)."""
    places = [i for i, t in enumerate(tokens) if t.kind == "op" and t.value == "±"]
    if len(places) > 4:
        raise Unreadable("Too many ± signs.")
    for signs in itertools.product("+-", repeat=len(places)):
        copy = list(tokens)
        for i, sign in zip(places, signs):
            copy[i] = _Token("op", sign, sign, tokens[i].space)
        yield copy


class Solutions(Answer):
    """An equation's solutions, as a set: ``values`` (numbers or text), or
    NO_SOLUTION, or ALL_REAL. Typed as ``x = 2, x = -3``, ``x = 2 or x = -3``,
    ``2, -3``, ``{2, -3}``, ``x = ±3``, ``no solution``, ``all real numbers``."""

    def __init__(self, values, *, variable="x", tolerance=0, mistakes=None):
        super().__init__(mistakes)
        self.variable, self.tolerance = variable, tolerance
        if isinstance(values, str) and values in (NO_SOLUTION, ALL_REAL):
            self.values = values
        else:
            self.values = tuple(_number_of(v) for v in values) or NO_SOLUTION
        self._texts = None if isinstance(self.values, str) else [
            v if isinstance(v, str) else _number_text(_number_of(v)) for v in values]

    @property
    def text(self):
        if isinstance(self.values, str):
            return self.values
        return ", ".join(f"{self.variable} = {t}" for t in self._texts)

    def _read(self, response):
        if not isinstance(response, str):
            return tuple(_number_of(v) for v in response) or NO_SOLUTION
        text = " ".join(response.split())
        if _NONE.fullmatch(text):
            return NO_SOLUTION
        if _ALL.fullmatch(text) or re.fullmatch(r"\(\s*-\s*(∞|inf)\s*,\s*\+?(∞|inf)\s*\)",
                                                text, re.I):
            return ALL_REAL
        text = text.replace("+/-", "±").replace("+-", "±")
        tokens = _strip_brackets(_tokens(text, thousands=False))
        found = []
        for _, piece in _split_tokens(tokens, words=("or", "and")):
            if len(piece) > 2 and piece[0].kind == "name" and piece[1].value == "=":
                if piece[0].value.lower() != self.variable.lower():
                    raise Unreadable(f"The letter here is {self.variable}.")
                piece = piece[2:]
            for each in _expand_plus_minus(piece):
                found.append(_constant(each))
        return tuple(found)

    def _same_answer(self, got, other):
        if isinstance(got, str) or isinstance(other, str):
            return got == other
        return (all(any(_same(a, b, self.tolerance) for b in other) for a in got)
                and all(any(_same(a, b, self.tolerance) for a in got) for b in other))

    def _judge(self, got):
        if self._same_answer(got, self.values):
            return Result(RIGHT, "Right!")
        known = self._known(got)
        if known:
            return known
        if isinstance(self.values, str):
            if isinstance(got, str):
                return Result(NOT_YET, "Not yet: try a number or two in the equation.")
            return Result(NOT_YET, f"Not yet: check, does {self.variable} = "
                                   f"{_number_text(got[0])} work?")
        if isinstance(got, str):
            return Result(NOT_YET, "Not yet: there " + ("is a solution." if len(self.values) == 1
                                                         else "are solutions."))
        wrong = [a for a in got if not any(_same(a, b, self.tolerance) for b in self.values)]
        missing = [b for b in self.values if not any(_same(a, b, self.tolerance) for a in got)]
        if wrong and missing and any(_same(a, -b) for a in wrong for b in missing):
            return Result(NOT_YET, "Check the sign.", "sign")
        if not wrong:
            return Result(NOT_YET, "Right so far, but there's " + (
                "another solution." if len(missing) == 1 else f"{len(missing)} more solutions."),
                "missing")
        names = ", ".join(f"{self.variable} = {_number_text(a)}" for a in wrong)
        verb = "isn't a solution" if len(wrong) == 1 else "aren't solutions"
        if len(wrong) < len(got):
            return Result(NOT_YET, f"{names} {verb}.", "extra")
        return Result(NOT_YET, "Not yet.")


@dataclass(frozen=True)
class Interval:
    """A part of the number line: from ``low`` to ``high`` (±math.inf for no
    end), each end included or not."""
    low: object = -math.inf
    high: object = math.inf
    low_closed: bool = False
    high_closed: bool = False

    def __str__(self):
        if _same(self.low, self.high):
            return "{" + _number_text(self.low) + "}"
        low = "-∞" if math.isinf(self.low) else _number_text(self.low)
        high = "∞" if math.isinf(self.high) else _number_text(self.high)
        return (("[" if self.low_closed else "(") + f"{low}, {high}"
                + ("]" if self.high_closed else ")"))


def _intervals(items):
    """A set as sorted intervals that neither overlap nor touch (empty ones dropped)."""
    items = [Interval(i.low, i.high, i.low_closed and not math.isinf(i.low),
                      i.high_closed and not math.isinf(i.high)) for i in items]
    items = [i for i in items if i.low < i.high or (i.low == i.high and i.low_closed
                                                     and i.high_closed)]
    items.sort(key=lambda i: (i.low, not i.low_closed))
    merged = []
    for i in items:
        if merged:
            last = merged[-1]
            if i.low < last.high or (i.low == last.high and (i.low_closed or last.high_closed)):
                if i.high > last.high or (i.high == last.high and i.high_closed):
                    merged[-1] = Interval(last.low, i.high, last.low_closed, i.high_closed)
                continue
        merged.append(i)
    return merged


def _complement(items):
    result, low, closed = [], -math.inf, False
    for i in items:
        result.append(Interval(low, i.low, closed, not i.low_closed))
        low, closed = i.high, not i.high_closed
    result.append(Interval(low, math.inf, closed, False))
    return _intervals(result)


def _intersection(a, b):
    result = []
    for i in a:
        for j in b:
            low = max(i.low, j.low)
            high = min(i.high, j.high)
            low_closed = (i.low_closed or i.low != low) and (j.low_closed or j.low != low)
            high_closed = (i.high_closed or i.high != high) and (j.high_closed or j.high != high)
            result.append(Interval(low, high, low_closed, high_closed))
    return _intervals(result)


def _same_sets(a, b, ends=True) -> bool:
    return len(a) == len(b) and all(
        _same(i.low, j.low) and _same(i.high, j.high)
        and (not ends or (i.low_closed == j.low_closed and i.high_closed == j.high_closed))
        for i, j in zip(a, b))


_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "=": "=", "!=": "!="}


def _relation_set(op, a):
    if op == "<":
        return [Interval(-math.inf, a)]
    if op == "<=":
        return [Interval(-math.inf, a, False, True)]
    if op == ">":
        return [Interval(a, math.inf)]
    if op == ">=":
        return [Interval(a, math.inf, True)]
    if op == "=":
        return [Interval(a, a, True, True)]
    return _complement([Interval(a, a, True, True)])


class Inequality(Answer):
    """An inequality's solution, a set of numbers: ``expected`` in inequality
    notation (``x > 3``, ``-2 < x <= 5``, ``x < -1 or x >= 4``), interval
    notation (``(3, ∞)``, ``(-∞, -1) ∪ [4, ∞)``), or as ``Interval``s.
    Responses in either notation, or a number line's intervals (a list of
    ``Interval``s, or an object with Intervals); ``form`` asks for
    "interval" or "inequality" notation."""

    def __init__(self, expected, *, variable="x", form=None, mistakes=None):
        if form not in (None, "interval", "inequality"):
            raise ValueError(f"form {form!r} isn't interval or inequality")
        super().__init__(mistakes)
        self.variable, self.form = variable, form
        self.expected = expected
        self.set = self._read(expected)[0]

    @property
    def text(self):
        if isinstance(self.expected, str) and (self.form is None
                                               or self._read(self.expected)[1] == self.form):
            return self.expected
        if self.form == "inequality":
            return self._inequality_text()
        return " ∪ ".join(str(i) for i in self.set) or "∅"

    def _inequality_text(self):
        x, parts = self.variable, []
        for i in self.set:
            low, high = _number_text(i.low), _number_text(i.high)
            if _same(i.low, i.high):
                parts.append(f"{x} = {low}")
            elif math.isinf(i.low) and math.isinf(i.high):
                return "all real numbers"
            elif math.isinf(i.low):
                parts.append(f"{x} {'<=' if i.high_closed else '<'} {high}")
            elif math.isinf(i.high):
                parts.append(f"{x} {'>=' if i.low_closed else '>'} {low}")
            else:
                parts.append(f"{low} {'<=' if i.low_closed else '<'} {x} "
                             f"{'<=' if i.high_closed else '<'} {high}")
        return " or ".join(parts) or "no solution"

    def _read(self, response):
        if not isinstance(response, str):
            if hasattr(response, "Intervals"):
                response = response.Intervals
            if isinstance(response, Interval):
                response = [response]
            return _intervals(response), "number line"
        text = " ".join(response.split())
        if _NONE.fullmatch(text):
            return [], None
        if _ALL.fullmatch(text):
            return [Interval()], None
        tokens = _tokens(text, thousands=False)
        if not tokens:
            raise Unreadable("Type your answer first.")
        first = tokens[0]
        if first.kind == "op" and first.value in "([{" and any(
                t.kind == "op" and t.value in _RELATIONS for t in tokens) is False:
            return self._interval_notation(tokens), "interval"
        return self._inequality_notation(tokens), "inequality"

    def _interval_notation(self, tokens):
        result = []
        for _, piece in _split_tokens(tokens, separators=(), words=("U", "u", "or")):
            if not piece:
                raise Unreadable("Something's missing next to ∪.")
            opening, closing = piece[0], piece[-1]
            if opening.kind != "op" or closing.kind != "op" or opening.value not in "([{" \
                    or closing.value not in ")]}":
                raise Unreadable("Write each interval as (a, b) or [a, b].")
            inner = _split_tokens(piece[1:-1])
            if opening.value == "{":
                result += [Interval(v, v, True, True) for v in (_constant(p) for _, p in inner)]
                continue
            if len(inner) != 2:
                raise Unreadable("An interval has two ends, with a comma between them.")
            low, high = (_constant(p) for _, p in inner)
            low_closed, high_closed = opening.value == "[", closing.value == "]"
            if (math.isinf(low) and low_closed) or (math.isinf(high) and high_closed):
                raise Unreadable("∞ is never included: put ( or ) next to it.")
            if low > high:
                raise Unreadable("The smaller end goes first: (a, b) with a less than b.")
            result.append(Interval(low, high, low_closed, high_closed))
        return _intervals(result)

    def _inequality_notation(self, tokens):
        result = None
        for word, piece in _split_tokens(tokens, separators=(), words=("or", "and")):
            if not piece:
                raise Unreadable(f"Something's missing next to “{word}”.")
            items = _Parser(piece).chain()
            here = self._piece(items)
            if result is None:
                result = here
            elif word == "and":
                result = _intersection(result, here)
            else:
                result = _intervals(result + here)
        return result

    def _piece(self, items):
        nodes, ops = items[::2], items[1::2]
        where = [i for i, n in enumerate(nodes) if n.op == "var"
                 and n.value.lower() == self.variable.lower()]
        if not ops:
            raise Unreadable(f"Write an inequality, like {self.variable} > 3.")
        if len(where) != 1:
            raise Unreadable(f"Write it with {self.variable} on one side, like "
                             f"{self.variable} > 3.")
        others = [_constant_node(n) for i, n in enumerate(nodes) if i != where[0]]
        if len(nodes) == 2:
            op = ops[0] if where[0] == 0 else _FLIP[ops[0]]
            return _intervals(_relation_set(op, others[0]))
        if len(nodes) == 3 and where[0] == 1:
            a, b = others
            if all(op in ("<", "<=") for op in ops):
                return _intervals([Interval(a, b, ops[0] == "<=", ops[1] == "<=")])
            if all(op in (">", ">=") for op in ops):
                return _intervals([Interval(b, a, ops[1] == ">=", ops[0] == ">=")])
            raise Unreadable("Both signs of a compound inequality point the same way.")
        raise Unreadable(f"Write it as a < {self.variable} < b, or with {self.variable} on "
                         "one side.")

    def _same_answer(self, got, other):
        return _same_sets(got[0], other[0])

    def _judge(self, got):
        found, notation = got
        if _same_sets(found, self.set):
            if self.form and notation in ("interval", "inequality") and notation != self.form:
                return Result(NOT_YET, f"Right! Now write it in {self.form} notation.", "form")
            return Result(RIGHT, "Right!")
        known = self._known(got)
        if known:
            return known
        if _same_sets(found, self.set, ends=False):
            for i, j in zip(found, self.set):
                for end, mine, theirs in ((i.low, i.low_closed, j.low_closed),
                                          (i.high, i.high_closed, j.high_closed)):
                    if mine != theirs:
                        return Result(NOT_YET, f"Check the end {_number_text(end)}: is it "
                                               "included?", "endpoint")
        if self.set and _same_sets(found, _complement(self.set), ends=False):
            return Result(NOT_YET, "It points the wrong way. Multiplying or dividing both "
                                   "sides by a negative number turns the sign round.", "flipped")
        return Result(NOT_YET, "Not yet.")


def _constant_node(node):
    try:
        return _evaluate(node, {})
    except _Free as free:
        raise Unreadable(f"Only one letter, please: what is {free.name}?") from None
    except _UNDEFINED:
        raise Unreadable("One of those numbers is undefined.") from None


# --- exercises -----------------------------------------------------------------------------

@dataclass
class Exercise:
    """One exercise: its ``prompt`` (Markdown with maths), its ``answer`` (an
    ``Answer``), ``hints`` given one at a time, a worked ``solution``
    (Markdown), the ``skill`` it practises, and the ``seed`` it was made from.
    ``graph``: the answer is placed on a Graph with these properties (a dict
    of the Graph's property names, ``{}`` for its defaults); a ``Point`` or
    ``Line`` answer is placed on one without it. ``check`` counts ``tries``
    and sets ``solved``."""
    prompt: str
    answer: Answer
    hints: list[str] = field(default_factory=list)
    solution: str = ""
    skill: str = ""
    seed: int | None = None
    graph: dict | None = None
    tries: int = 0
    hints_shown: int = 0
    solved: bool = False

    def check(self, response) -> Result:
        result = self.answer.check(response)
        if result.status != UNREADABLE:
            self.tries += 1
            self.solved = self.solved or result.right
        return result

    def hint(self) -> str | None:
        """The next hint, or None when they've all been given."""
        if self.hints_shown >= len(self.hints):
            return None
        self.hints_shown += 1
        return self.hints[self.hints_shown - 1]

    @property
    def hints_left(self) -> int:
        return len(self.hints) - self.hints_shown


def load_exercises(path):
    """A lesson's ``exercises.py`` loaded as a module."""
    path = Path(path)
    name = "vp6edu_exercises_" + re.sub(r"\W", "_", str(path.resolve().parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def generators(module) -> list:
    """The exercise makers of an ``exercises.py``: its public functions of one
    argument (a ``random.Random``), in the order they're written."""
    found = []
    for name, item in vars(module).items():
        if (name.startswith("_") or not inspect.isfunction(item)
                or item.__module__ != module.__name__):
            continue
        parameters = [p for p in inspect.signature(item).parameters.values()
                      if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY,
                                                             p.POSITIONAL_OR_KEYWORD)]
        if len(parameters) == 1:
            found.append(item)
    return found


def make(generator, seed=None) -> Exercise:
    """An exercise from a maker and a seed (a random one by default): the same
    seed gives the same numbers."""
    if seed is None:
        seed = random.randrange(2 ** 32)
    exercise = generator(random.Random(seed))
    if not isinstance(exercise, Exercise):
        raise TypeError(f"{generator.__name__} made {type(exercise).__name__}, not an Exercise")
    exercise.seed = seed
    exercise.skill = exercise.skill or generator.__name__.replace("_", " ")
    return exercise


def verify(generator, seeds=range(25)) -> list[str]:
    """What's wrong with a maker: over these seeds each exercise must have a
    prompt, and its answer's own ``text`` must check right."""
    problems = []
    for seed in seeds:
        try:
            exercise = make(generator, seed)
        except Exception as error:  # noqa: BLE001 (any error is the maker's problem)
            problems.append(f"{generator.__name__}, seed {seed}: {type(error).__name__}: {error}")
            continue
        if not exercise.prompt.strip():
            problems.append(f"{generator.__name__}, seed {seed}: no prompt")
        result = exercise.answer.check(exercise.answer.text)
        if not result.right:
            problems.append(f"{generator.__name__}, seed {seed}: its answer "
                            f"{exercise.answer.text!r} checks {result.status}: {result.message}")
    return problems


def answer_names() -> dict:
    """What an answer written as Python (a Try It's) can use: this module's
    names, ``Fraction``, ``math``, ``pi`` and ``inf``."""
    names = {name: globals()[name] for name in __all__}
    names.update(Fraction=Fraction, math=math, pi=math.pi, inf=math.inf)
    return names


def answer_of(source: str) -> Answer:
    """An answer from its Python, as a lesson's Try It writes it
    (``Number(Fraction(3, 4))``); ValueError (what's wrong) when it isn't one."""
    try:
        found = eval(compile(source, "<answer>", "eval", dont_inherit=True),  # noqa: S307
                     {"__builtins__": __builtins__, **answer_names()})
    except Exception as error:  # noqa: BLE001 (the lesson's mistake, reported)
        raise ValueError(f"{type(error).__name__}: {error}") from None
    if not isinstance(found, Answer):
        raise ValueError(f"{source!r} isn't an answer (Number(...), Choice(...)...)")
    return found


__all__ = ["RIGHT", "NOT_YET", "UNREADABLE", "NO_SOLUTION", "ALL_REAL", "NUMBER_FORMS",
           "EQUATION_FORMS", "Unreadable", "Result", "Node", "read", "value", "equivalent",
           "Answer", "Choice", "Number", "Expression", "Equation", "Pair", "Point", "Line",
           "Solutions", "Inequality", "Interval", "Exercise", "load_exercises", "generators",
           "make", "verify", "answer_names", "answer_of"]
