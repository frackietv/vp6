"""Mathematics in Markdown: formulas found in Markdown ($…$, $$…$$, not in
code), TeX parsed (and its errors), laid out as TeX does (scripts, fractions,
roots, spacing classes, operators and their limits, delimiters that grow,
matrices, cases, aligned, accents, fonts, colours), compared as layouts with
made-up metrics; vp6help's HTML and viewer, and the MarkdownBox (preview,
visual editor, source colors, ApplyFormat, copying and pasting), compared as
grabs: the baseline, the text's font, size and colour, dark, high DPI, errors."""

import os

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QPainter, QPalette,
                           QTextCharFormat, QTextCursor, QTextDocument)
from PySide6.QtTest import QTest

import vp6.markdown
from vp6 import Form, MarkdownBox, vpMarkdownMath, vpMarkdownPreview, vpMarkdownVisual
from vp6.markdown import markdown_of
from vp6help import maker, tex, texdraw, viewer
from vp6help.markdown import to_html

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

M = tex.Metrics(16.0)  # (every glyph 8 px wide; ascent 11.2 or 7.2, descent 3.2 or 0)
MU = 16.0 / 18


def texts(shape) -> list[tuple]:
    return [(item.text, round(item.x, 3), round(item.y, 3), item.font, item.scale)
            for item in shape.items if isinstance(item, tex.Text)]


def text_item(shape, text):
    return next(item for item in shape.items if isinstance(item, tex.Text) and item.text == text)


# --- finding formulas ----------------------------------------------------------------------------

def test_math_spans():
    spans = tex.math_spans("a $x^2$ b $$\\frac12$$ c")
    assert [(s.tex, s.display) for s in spans] == [("x^2", False), ("\\frac12", True)]
    text = "a $x$ b"
    span = tex.math_spans(text)[0]
    assert text[span.start:span.end] == "$x$"
    # money, an escaped dollar and spaces inside the dollars aren't formulas
    assert tex.math_spans("It costs $5 and $10.") == []
    assert tex.math_spans("\\$x$ and $ y $") == []
    assert tex.math_spans("$x$5") == []  # (a digit after the closing $)
    # never in code
    assert tex.math_spans("`$x$` and ``$y$`` but $z$") == [tex.MathSpan(22, 25, "z", False)]
    assert [s.tex for s in tex.math_spans("```\n$x$\n```\n$y$\n~~~\n$z$\n")] == ["y"]
    # a formula can go on to the next line, but not past a blank one
    assert [s.tex for s in tex.math_spans("$a\nb$")] == ["a\nb"]
    assert tex.math_spans("$a\n\nb$") == []
    assert [(s.tex, s.display) for s in tex.math_spans("$$\nx = 1\n$$")] == [("x = 1", True)]
    # TeX's own \$ inside a formula
    assert [s.tex for s in tex.math_spans("$\\$5$")] == ["\\$5"]


# --- reading TeX -----------------------------------------------------------------------------------

@pytest.mark.parametrize("source, message", [
    ("\\frac{a}", "missing a denominator"), ("x^", "missing a superscript"),
    ("\\left( x", "\\left without \\right"), ("{x", "a { without its }"),
    ("x}", "a } without its {"), ("\\foo", "unknown command \\foo"),
    ("x^1^2", "two superscripts"), ("a & b", "& is only for"),
    ("\\begin{matrix} a", "without \\end{matrix}"), ("\\middle|", "\\middle without \\left"),
    ("\\right)", "\\right without \\left"), ("\\begin{pmatrix} a \\end{bmatrix}", "ended by"),
    ("\\left x \\right)", "needs a delimiter"), ("\\begin{foo} \\end{foo}", "unknown environment"),
    ("a \\\\ b", "only for the rows"), ("x\\limits", "only follows an operator"),
])
def test_errors(source, message):
    with pytest.raises(tex.TexError, match=message.replace("\\", "\\\\").replace("(", "\\(")
                       .replace("{", "\\{").replace("}", "\\}")):
        tex.layout(source, M)
    shape = tex.render(source, M)  # (the source in the error colour instead)
    assert message in shape.error
    assert [(i.text, i.color) for i in shape.items] == [(f"${source}$", tex.ERROR_COLOR)]
    assert tex.render(source, M, display=True).items[0].text == f"$${source}$$"


def test_everything_lays_out():
    sources = [
        r"\alpha\beta\gamma\Gamma\Omega", r"a \le b \ne c \pm d \cdot e \times f \div g",
        r"\left\langle u, v \right\rangle \|v\| \lvert x \rvert", r"\sqrt[3]{x}\sqrt{\frac{a}{b}}",
        r"\sum_{i=1}^{n} \prod_k \int_a^b \iint \oint \bigcup_i", r"\lim_{x\to\infty} \max_k",
        r"\sin x \cos^2 y \log_2 n \ln e \operatorname{lcm}(a,b)",
        r"\begin{pmatrix}1\\2\end{pmatrix}\begin{bmatrix}a&b\end{bmatrix}\begin{Bmatrix}x\end{Bmatrix}",
        r"\begin{vmatrix}a\end{vmatrix}\begin{Vmatrix}a\end{Vmatrix}\begin{smallmatrix}a&b\end{smallmatrix}",
        r"\begin{array}{lcr} a & b & c \\ d & e & f \end{array}",
        r"\begin{cases} 1 & x>0 \\ 0 & \text{otherwise} \end{cases}", r"\begin{rcases}a\\b\end{rcases}",
        r"\begin{aligned} a &= b \\ &= c \end{aligned}", r"\begin{gathered} a \\ bb \end{gathered}",
        r"\hat x \check x \tilde x \bar x \dot x \ddot x \vec x \acute x \grave x \breve x \mathring x",
        r"\widehat{abc} \widetilde{abc} \overline{abc} \underline{abc}",
        r"\overrightarrow{AB} \overleftarrow{AB} \overleftrightarrow{AB} \underrightarrow{AB}",
        r"\underbrace{a+b}_{2} \overbrace{a+b}^{2} \cancel{x} \bcancel{x} \xcancel{x}",
        r"\boxed{x = 2} \phantom{x} \overset{?}{=} \underset{n}{\to} \stackrel{def}{=}",
        r"\mathrm{d}x \mathbf{v} \mathit{x} \mathbb{RZ1} \mathcal{AL} \mathsf{s} \mathtt{t} \boldsymbol{\alpha x}",
        r"\text{a } \textbf{b} \textit{c} \texttt{d} \mbox{e}", r"\color{red}x \textcolor{#0b5cad}{y}",
        r"\not= \not\in \not\approx \not\perp", r"a \bmod b \pmod{n} \mod{m}", r"f'(x) f'' g'''",
        r"\big( \Big[ \bigg\{ \Bigg| \bigl( \bigr) \bigm|", r"\left. x \right| \left/ x \right\backslash",
        r"\left\lfloor x \right\rfloor \left\lceil x \right\rceil \left[ x \right] \left\{ x \right\}",
        r"\displaystyle\sum \textstyle\sum \scriptstyle x \scriptscriptstyle x", r"x^{2^{3^{4}}}_{1_{2}}",
        r"a\,b\:c\;d\!e\quad f\qquad g\ h~i", r"\infty \partial \nabla \forall \exists \emptyset \ldots \cdots",
        r"\dfrac{1}{2} \tfrac{1}{2} \cfrac{1}{2} \binom{n}{k} \dbinom{n}{k} \tbinom{n}{k}",
        r"π ≤ θ × ∑ ∫", r"\% \$ \# \& \_ \{ \}", r"{}^{14}C", r"\sum\limits_i \int\limits_0^1",
    ]
    for source in sources:
        for display in (False, True):
            shape = tex.layout(source, M, display)
            assert shape.width > 0 and shape.error is None, source


# --- laying out ------------------------------------------------------------------------------------

def test_scripts():
    x = tex.layout("x", M)
    assert texts(x) == [("x", 0, 0, "it", 1.0)] and x.width == 8
    shape = tex.layout("x^2", M)
    x_item, two = text_item(shape, "x"), text_item(shape, "2")
    assert two.scale == 0.7 and two.y < 0 and two.x == 8  # (raised, after the x)
    assert -two.y == pytest.approx(max(0.363 * 16 * (0.45 / 0.431), 0 + 0.45 * 16 / 4))
    sub = text_item(tex.layout("x_1", M), "1")
    assert sub.y > 0 and sub.scale == 0.7
    both = tex.layout("x_1^2", M)
    up, down = text_item(both, "2"), text_item(both, "1")
    assert up.x == down.x == 8 and up.y < 0 < down.y
    # scripts of scripts are smaller still, and stop at scriptscript
    assert [t[4] for t in texts(tex.layout("x^{a^{b^{c}}}", M))] == [1.0, 0.7, 0.5, 0.5]
    # a prime is a glyph of its own, and takes a superscript
    assert [t[0] for t in texts(tex.layout("f''^2", M))] == ["f", "″", "2"]


def test_spacing_classes():
    def xs(source):
        return [(t[0], round(t[1], 2)) for t in texts(tex.layout(source, M))]

    def at(*pairs):
        return [(text, round(x, 2)) for text, x in pairs]

    assert xs("a+b") == at(("a", 0), ("+", 8 + 4 * MU), ("b", 16 + 8 * MU))  # (medium)
    assert xs("a=b") == at(("a", 0), ("=", 8 + 5 * MU), ("b", 16 + 10 * MU))  # (thick)
    assert xs("-x") == at(("−", 0), ("x", 8))  # (a minus with nothing before: a sign)
    assert xs("a=-b") == at(("a", 0), ("=", 8 + 5 * MU), ("−", 16 + 10 * MU), ("b", 24 + 10 * MU))
    assert xs("(a)") == at(("(", 0), ("a", 8), (")", 16))
    assert xs("f(x),y")[-1] == at(("y", 40 + 3 * MU))[0]  # (a thin space after punctuation)
    assert xs("\\sin x") == at(("sin", 0), ("x", 24 + 3 * MU))  # (an operator, then a thin space)
    # in scripts, the medium and thick spaces go
    up = [t for t in texts(tex.layout("e^{a+b}", M)) if t[0] in "a+b"]
    assert up[1][1] - up[0][1] == pytest.approx(8 * 0.7, abs=0.01)
    # a comma between digits separates thousands; with a space after it, a pair
    assert xs("1,000")[-1] == ("0", 32)
    assert xs("(1, 2)")[3] == at(("2", 24 + 3 * MU))[0]
    # explicit spaces, in mu
    assert xs("a\\,b")[1] == at(("b", 8 + 3 * MU))[0] and xs("a\\quad b")[1] == ("b", 24)
    assert xs("a\\!b")[1][1] == pytest.approx(8 - 3 * MU, abs=0.01)


def test_fonts():
    fonts = {t[0]: t[3] for t in texts(tex.layout(
        r"x 2 \alpha \Gamma \mathrm{d} \mathbf{v} \text{if} \mathbb{R} \sin", M))}
    assert fonts == {"x": "it", "2": "rm", "α": "it", "Γ": "rm", "d": "rm", "v": "bf",
                     "if": "rm", "ℝ": "rm", "sin": "rm"}
    assert texts(tex.layout(r"\text{if } x", M))[0][0] == "if "  # (spaces kept in text)
    assert [t[0] for t in texts(tex.layout(r"\mathcal{L} \mathbb{N} \mathbb{x}", M))] == \
        ["ℒ", "ℕ", "\U0001d569"]
    assert [t[0] for t in texts(tex.layout(r"\not= \not\in a \le b", M))] == \
        ["≠", "∉", "a", "≤", "b"]


def test_fractions():
    shape = tex.layout(r"\frac{a}{b}", M)
    rule = next(i for i in shape.items if isinstance(i, tex.Rule))
    axis, theta = M.axis_height(), M.rule_thickness()
    assert rule.y + rule.height / 2 == pytest.approx(-axis)  # (the bar on the axis)
    a, b = text_item(shape, "a"), text_item(shape, "b")
    assert a.scale == b.scale == 0.7  # (text style: smaller)
    assert a.y + 0 < rule.y and b.y - b.scale * 16 * 0.45 > rule.y + rule.height
    assert rule.width == 8 * 0.7 and rule.x == pytest.approx(0.12 * 16)
    display = tex.layout(r"\frac{a}{b}", M, display=True)
    assert text_item(display, "a").scale == 1.0 and display.ascent > shape.ascent
    assert text_item(tex.layout(r"\dfrac{a}{b}", M), "a").scale == 1.0
    assert text_item(tex.layout(r"\tfrac{a}{b}", M, True), "a").scale == 0.7
    # the wider part sets the bar, the other is centred
    wide = tex.layout(r"\frac{abc}{d}", M, True)
    bar = next(i for i in wide.items if isinstance(i, tex.Rule))
    assert bar.width == 24 and text_item(wide, "d").x == pytest.approx(bar.x + 8)
    # a binomial: no bar, parentheses around
    binom = tex.layout(r"\binom{n}{k}", M, True)
    assert not [i for i in binom.items if isinstance(i, tex.Rule)]
    assert [i for i in binom.items if isinstance(i, tex.Shape)]


def test_roots():
    shape = tex.layout(r"\sqrt{x}", M)
    vinculum = next(i for i in shape.items if isinstance(i, tex.Rule))
    x = text_item(shape, "x")
    assert vinculum.y + vinculum.height < -7.2 and vinculum.x < x.x < vinculum.x + vinculum.width
    strokes = [i for i in shape.items if isinstance(i, tex.Shape)]
    assert len(strokes) == 3 and strokes[1].width > strokes[0].width  # (the thick down-stroke)
    taller = tex.layout(r"\sqrt{\frac{a}{b}}", M, True)
    assert taller.ascent > shape.ascent and taller.descent > shape.descent
    index = text_item(tex.layout(r"\sqrt[3]{x}", M), "3")
    assert index.scale == 0.5 and index.y < 0


def test_operators_and_limits():
    display = tex.layout(r"\sum_{i=1}^{n} i", M, display=True)
    sigma, n, i = text_item(display, "∑"), text_item(display, "n"), text_item(display, "1")
    assert sigma.scale == pytest.approx(1.9) and n.y < sigma.y - 16 and i.y > sigma.y
    assert n.x > sigma.x  # (above it, centred)
    inline = tex.layout(r"\sum_{i=1}^{n} i", M)
    sigma, n = text_item(inline, "∑"), text_item(inline, "n")
    assert sigma.scale == pytest.approx(1.3) and n.x >= sigma.x + 8 * 1.3  # (beside it)
    # integrals keep their bounds beside them, unless \limits
    integral = tex.layout(r"\int_0^1", M, display=True)
    assert text_item(integral, "1").x >= text_item(integral, "∫").x + 16
    limits = tex.layout(r"\int\limits_0^1", M, display=True)
    assert text_item(limits, "1").x < text_item(limits, "∫").x + 16
    assert text_item(tex.layout(r"\sum\nolimits_i", M, True), "i").x == pytest.approx(8 * 1.9)
    # lim's subscript below it when displayed
    lim = tex.layout(r"\lim_{x \to 0}", M, display=True)
    assert text_item(lim, "x").y > 0 and text_item(lim, "x").scale == 0.7
    # big operators are centred on the axis
    big = text_item(display, "∑")
    width, ascent, descent, _ = M.measure("∑", "rm", big.scale)
    assert (big.y - ascent + big.y + descent) / 2 == pytest.approx(-M.axis_height())


def test_delimiters_grow():
    small = tex.layout(r"\left( x \right)", M)
    assert [t[0] for t in texts(small)] == ["(", "x", ")"]  # (the font's own, tall enough)
    tall = tex.layout(r"\left( \frac{a}{b} \right)", M, True)
    shapes = [i for i in tall.items if isinstance(i, tex.Shape)]
    assert len(shapes) == 2 and all(s.fill for s in shapes)  # (drawn, as tall as the fraction)
    ys = [c[k] for c in shapes[0].commands for k in range(2, len(c), 2)]
    assert max(ys) - min(ys) >= 0.9 * (tall.ascent + tall.descent)  # (TeX's 90%)
    assert (max(ys) + min(ys)) / 2 == pytest.approx(-M.axis_height())
    # \middle grows too; a . is nothing
    middle = tex.layout(r"\left\{ \frac{a}{b} \middle| x \right.", M, True)
    assert len([i for i in middle.items if isinstance(i, (tex.Shape, tex.Rule))]) >= 2
    sizes = []
    for big in ("", r"\big", r"\Big", r"\bigg", r"\Bigg"):
        shape = tex.layout(big + "(", M)
        sizes.append(shape.ascent + shape.descent)
    assert sizes == sorted(sizes) and sizes[-1] >= 3 * 16 - 1


def test_matrices_cases_aligned():
    matrix = tex.layout(r"\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}", M, True)
    cells = {t[0]: (t[1], t[2]) for t in texts(matrix) if t[0] in "1234"}
    assert cells["1"][1] == cells["2"][1] < cells["3"][1] == cells["4"][1]  # (rows)
    assert cells["1"][0] == cells["3"][0] < cells["2"][0] == cells["4"][0]  # (columns)
    assert cells["2"][0] - cells["1"][0] == 8 + 16  # (a quad between the columns)
    assert len([i for i in matrix.items if isinstance(i, tex.Shape)]) == 2  # (the parentheses)
    # the rows' middle on the axis
    assert (cells["1"][1] + cells["3"][1]) / 2 == pytest.approx(-M.axis_height() + 0.0, abs=4)
    cases = tex.layout(r"\begin{cases} x & x \ge 0 \\ -x & x < 0 \end{cases}", M, True)
    brace = [i for i in cases.items if isinstance(i, tex.Shape)]
    assert len(brace) == 1 and not brace[0].fill  # (a brace on the left only)
    lefts = sorted({t[1] for t in texts(cases) if t[0] in ("x", "−")})
    assert len(lefts) >= 2  # (left-aligned columns: both rows' first cells start together)
    first_column = [t for t in texts(cases) if t[0] in ("x", "−") and t[1] == lefts[0]]
    assert len(first_column) == 2
    aligned = tex.layout(r"\begin{aligned} 2x + 3 &= 7 \\ x &= 2 \end{aligned}", M, True)
    equals = [t for t in texts(aligned) if t[0] == "="]
    assert len(equals) == 2 and equals[0][1] == equals[1][1]  # (lined up)
    seven = text_item(aligned, "7")
    assert seven.x == pytest.approx(equals[0][1] + 8 + 5 * MU, abs=0.01)  # (a relation's space kept)
    array = tex.layout(r"\begin{array}{lr} a & b \\ cc & dd \end{array}", M)
    a, b = text_item(array, "a"), text_item(array, "b")
    cs = sorted(t[1] for t in texts(array) if t[0] == "c")
    ds = sorted(t[1] for t in texts(array) if t[0] == "d")
    assert a.x == cs[0] and b.x == ds[1]  # (left, right)


def test_accents_and_lines():
    hat = tex.layout(r"\hat{x}", M)
    stroke = next(i for i in hat.items if isinstance(i, tex.Shape))
    assert max(c[2] for c in stroke.commands) < -7.2  # (above the letter)
    over = tex.layout(r"0.\overline{3}", M)
    rule = next(i for i in over.items if isinstance(i, tex.Rule))
    assert rule.x == text_item(over, "3").x and rule.width == 8 and rule.y < -11.2
    vec = tex.layout(r"\vec{v}", M)
    assert any(isinstance(i, tex.Shape) for i in vec.items)
    arrow = tex.layout(r"\overleftrightarrow{AB}", M)
    shape = next(i for i in arrow.items if isinstance(i, tex.Shape))
    assert sum(1 for c in shape.commands if c[0] == "M") == 3  # (the line and both heads)
    boxed = tex.layout(r"\boxed{x}", M)
    assert len([i for i in boxed.items if isinstance(i, tex.Rule)]) == 4
    assert tex.layout(r"\phantom{x}", M).items == [] and tex.layout(r"\phantom{x}", M).width == 8


def test_colors():
    shape = tex.layout(r"a \color{red} b {c} \textcolor{blue}{d} e", M)
    assert {t.text: t.color for t in shape.items} == \
        {"a": None, "b": "red", "c": "red", "d": "blue", "e": "red"}
    assert {t.text: t.color for t in tex.layout(r"{\color{red} a} b", M).items} == \
        {"a": "red", "b": None}
    rule = next(i for i in tex.layout(r"\color{green}\frac{a}{b}", M).items
                if isinstance(i, tex.Rule))
    assert rule.color == "green"


def test_styles():
    inline = tex.layout(r"\sum_i", M)
    display = tex.layout(r"\displaystyle\sum_i", M)
    assert text_item(display, "∑").scale > text_item(inline, "∑").scale
    assert text_item(tex.layout(r"\scriptstyle x", M), "x").scale == 0.7


# --- vp6help's HTML ----------------------------------------------------------------------------------

def test_markdown_to_html():
    html = to_html("The $x^2$ of *it*, \\$5 and $5, `$code$`.\n")
    assert '<img class="math" src="vp6math:inline,x%5E2" alt="x^2" />' in html
    assert "$5 and $5" in html and "<code>$code$</code>" in html
    # TeX's stars and backslashes aren't Markdown
    assert 'alt="a*b*c \\{x\\}"' in to_html("$a*b*c \\{x\\}$")
    # displayed: a centred block, even across lines
    html = to_html("Text\n\n$$\n\\frac{a}{b}\n- c\n$$\n\nMore")
    assert '<p align="center"><img class="math" src="vp6math:display,%5Cfrac%7Ba%7D%7Bb%7D' \
           '%0A-%20c" alt="\\frac{a}{b}\n- c" /></p>' in html
    assert "<ul>" not in html
    # a formula across two lines of a paragraph, in a table, in a heading
    assert 'alt="a b"' in to_html("x $a\nb$ y")
    assert html.count("<img") == 1
    assert "vp6math:inline,y" in to_html("| a |\n| --- |\n| $y$ |")
    assert "<h1>A <img" in to_html("# A $z$")
    # $$ in a paragraph: displayed style, in the line
    assert "<p>See <img class=\"math\" src=\"vp6math:display,y\"" in to_html("See $$y$$ here")


# --- drawn with Qt ------------------------------------------------------------------------------------

def _font(pixels: int = 16) -> QFont:
    font = QFont(QGuiApplication.font())
    font.setPixelSize(pixels)
    return font


def _ink(image: QImage, background: QColor) -> list[QColor]:
    pixels = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if abs(color.lightness() - background.lightness()) > 60:
                pixels.append(color)
    return pixels


def _draw(source: str, font: QFont, color=QColor("black"), ratio: float = 1.0,
          display: bool = False) -> QImage:
    shape, metrics = texdraw.layout_of(source, display, font)
    image = QImage(int((shape.width + 4) * ratio), int((shape.ascent + shape.descent + 4) * ratio),
                   QImage.Format_ARGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(QColor("white") if color.lightness() < 128 else QColor("#1e1e1e"))
    painter = QPainter(image)
    texdraw.paint(painter, shape, metrics, 2, 2 + shape.ascent, color)
    painter.end()
    return image


def test_qt_metrics_follow_the_font(qapp):
    small, _ = texdraw.layout_of(r"\frac{x+1}{2}", False, _font(12))
    large, _ = texdraw.layout_of(r"\frac{x+1}{2}", False, _font(24))
    assert large.width == pytest.approx(2 * small.width, rel=0.15)
    assert large.ascent == pytest.approx(2 * small.ascent, rel=0.2)
    metrics = texdraw.QtMetrics(_font(16))
    assert metrics.em == 16 and 6 < metrics.x_height() < 11 and 3 < metrics.axis_height() < 7
    width, ascent, descent, _ = metrics.measure("g", "it", 1.0)
    assert width > 0 and ascent > 0 and descent > 0
    assert metrics.qfont("it", 0.7).italic() and metrics.qfont("it", 0.7).pixelSize() == 11


def test_drawn_glyphs_are_the_fonts(qapp):
    # a formula's letter is the font's italic letter, where its layout says
    font = _font(20)
    image = _draw("x", font)
    shape, metrics = texdraw.layout_of("x", False, font)
    expected = QImage(image.size(), QImage.Format_ARGB32)
    expected.fill(QColor("white"))
    painter = QPainter(expected)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(metrics.qfont("it", 1.0))
    painter.setPen(QColor("black"))
    painter.drawText(QPointF(2, 2 + shape.ascent), "x")
    painter.end()
    assert image == expected


def test_drawn_in_the_colour_dark_and_high_dpi(qapp):
    font = _font(16)
    light = _draw(r"\frac{a}{b}+\sqrt{x}", font, QColor("black"))
    dark = _draw(r"\frac{a}{b}+\sqrt{x}", font, QColor("#e6e6e6"))
    light_ink, dark_ink = _ink(light, QColor("white")), _ink(dark, QColor("#1e1e1e"))
    assert light_ink and dark_ink and abs(len(light_ink) - len(dark_ink)) < len(light_ink) * 0.2
    assert sum(c.lightness() < 128 for c in light_ink) > len(light_ink) * 0.75
    assert sum(c.lightness() > 128 for c in dark_ink) > len(dark_ink) * 0.75
    # twice the pixels: about four times the ink, nothing blurred into a smaller copy
    sharp = _draw(r"\frac{a}{b}+\sqrt{x}", font, QColor("black"), ratio=2.0)
    assert sharp.width() == pytest.approx(2 * light.width(), abs=2)
    assert len(_ink(sharp, QColor("white"))) == pytest.approx(4 * len(light_ink), rel=0.35)
    # \color colours its part; an error is red, readable on dark too
    red = _ink(_draw(r"\color{red} x", font), QColor("white"))
    assert red and sum(c.red() > c.green() + 60 for c in red) > len(red) * 0.8
    error = _ink(_draw(r"\frac{x}", font), QColor("white"))
    assert error and sum(c.red() > c.blue() + 40 for c in error) > len(error) * 0.8
    assert texdraw.error_color(QColor("white")).lightness() > texdraw.error_color(
        QColor("black")).lightness()


class Page(Form):
    def InitializeComponent(self):
        self.mdPreview = MarkdownBox(self, Mode=vpMarkdownPreview, Width=600, Height=300)
        self.mdVisual = MarkdownBox(self, Mode=vpMarkdownVisual, Left=0, Top=310, Width=600,
                                    Height=300)
        self.mdSource = MarkdownBox(self, Left=610, Width=300, Height=300)


@pytest.fixture
def page(qapp):
    form = Page()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def _formulas(document: QTextDocument) -> list[tuple[str, bool]]:
    found = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if texdraw.is_math(fragment.charFormat()):
                found.append((fragment.charFormat().property(texdraw.TEX_PROPERTY),
                              bool(fragment.charFormat().property(texdraw.DISPLAY_PROPERTY))))
        block = block.next()
    return found


TEXT = ("# The $x^2$\n\nInline $a*b*c$ and **bold $\\frac{1}{2}$**, costs \\$5.\n\n"
        "$$\\sum_{i=1}^n i = \\frac{n(n+1)}{2}$$\n\n- in a list: $\\sqrt{2}$\n\n"
        "`$code$` and <font color=\"#c0392b\">red $y$</font>\n")


def test_markdown_box_shows_formulas(page):
    for box in (page.mdPreview, page.mdVisual):
        box.Text = TEXT
        assert box.Text == TEXT
        document = box._widget.document()
        assert _formulas(document) == [("x^2", False), ("a*b*c", False), ("\\frac{1}{2}", False),
                                       ("\\sum_{i=1}^n i = \\frac{n(n+1)}{2}", True),
                                       ("\\sqrt{2}", False), ("y", False)]
        text = document.toPlainText()
        assert "$code$" in text and "costs $5" in text and "a*b*c" not in text
        displayed = document.findBlockByNumber(2)
        assert displayed.text() == texdraw.OBJECT
        assert displayed.blockFormat().alignment() & Qt.AlignHCenter
        # the format where it is: bold, a heading's size, the color span's colour
        cursor = QTextCursor(document)
        cursor.setPosition(document.toPlainText().index(texdraw.OBJECT) + 1)
        heading = cursor.charFormat().font()
        assert heading.pointSizeF() > document.defaultFont().pointSizeF()
    # what the visual editor writes back: the formulas' source
    assert markdown_of(page.mdVisual._widget.document()) == (
        "# The $x^2$\n\nInline $a*b*c$ and **bold $\\frac{1}{2}$**, costs \\$5.\n\n"
        "$$\\sum_{i=1}^n i = \\frac{n(n+1)}{2}$$\n\n- in a list: $\\sqrt{2}$\n\n"
        "`$code$` and <span style=\"color:#c0392b\">red $y$</span>\n")
    assert "$x^2$" in page.mdPreview.TextHTML and "\ufffc" not in page.mdPreview.TextHTML


def test_formulas_sit_on_the_baseline(page, monkeypatch):
    drawn = []
    real = texdraw.paint
    monkeypatch.setattr(texdraw, "paint", lambda painter, shape, metrics, x, y, color:
                        (drawn.append((shape, y)), real(painter, shape, metrics, x, y, color)))
    box = page.mdPreview
    box.Text = "a $x$ b $\\frac{a}{b}$ c $y_{1_{2}}$ d"
    box._widget.viewport().grab()
    document = box._widget.document()
    block = document.firstBlock()
    line = block.layout().lineAt(0)
    baseline = document.documentLayout().blockBoundingRect(block).top() + line.y() + line.ascent()
    assert len(drawn) == 3
    for shape, y in drawn:
        assert y == pytest.approx(baseline, abs=0.01)
    # a deep one is centred by Qt; the room left keeps its baseline right
    deep = [f for f in _formats(document) if f.property(texdraw.TEX_PROPERTY) == "\\frac{a}{b}"]
    assert deep[0].verticalAlignment() == QTextCharFormat.AlignMiddle
    shallow = [f for f in _formats(document) if f.property(texdraw.TEX_PROPERTY) == "x"]
    assert shallow[0].verticalAlignment() == QTextCharFormat.AlignBaseline


def _formats(document):
    out = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if texdraw.is_math(fragment.charFormat()):
                out.append(fragment.charFormat())
        block = block.next()
    return out


def test_formulas_follow_the_font_and_colour(page):
    box = page.mdPreview
    box.Text = "$\\frac{x+1}{2}$"
    document = box._widget.document()
    handler = document.documentLayout().handlerForObject(texdraw.MATH_OBJECT)

    def size():
        fmt = _formats(document)[0]
        return handler.intrinsicSize(document, 0, fmt)

    box.FontSize = 10
    small = size()
    box.FontSize = 20
    large = size()
    assert large.width() == pytest.approx(2 * small.width(), rel=0.2)
    # drawn in the text's colour: the palette's, and a dark one
    box.FontSize = 20
    box.Text = "$\\sqrt{x}$"
    box.BackColor, box.ForeColor = 0x1E1E1E, 0xE6E6E6  # (BGR, as VB's)
    image = box._widget.viewport().grab().toImage()
    ink = _ink(image, QColor("#1e1e1e"))
    assert ink and sum(c.lightness() > 128 for c in ink) > len(ink) * 0.75
    box.BackColor, box.ForeColor = 0xFFFFFF, 0x000000
    image = box._widget.viewport().grab().toImage()
    ink = _ink(image, QColor("white"))
    assert ink and sum(c.lightness() < 128 for c in ink) > len(ink) * 0.75


def test_errors_shown_in_red(page):
    page.mdPreview.Text = "A $\\frac{x}$ here"
    fmt = _formats(page.mdPreview._widget.document())[0]
    assert "missing a denominator" in fmt.toolTip()
    image = page.mdPreview._widget.viewport().grab().toImage()
    red = [c for c in _ink(image, QColor("white")) if c.red() > c.green() + 60]
    assert len(red) > 20


def test_copying_and_pasting_formulas(page, qapp):
    visual = page.mdVisual
    visual.Text = "Let $x^2$ be $$y$$ and z\n"
    widget = visual._widget
    cursor = widget.textCursor()
    cursor.select(QTextCursor.Document)
    widget.setTextCursor(cursor)
    data = widget.createMimeDataFromSelection()
    assert data.text() == "Let $x^2$ be $$y$$ and z" and not data.hasHtml()
    assert texdraw.text_of(cursor) == "Let $x^2$ be $$y$$ and z"
    # without formulas, copying is Qt's own
    cursor.setPosition(0)
    cursor.setPosition(3, QTextCursor.KeepAnchor)
    widget.setTextCursor(cursor)
    assert widget.createMimeDataFromSelection().hasHtml()
    # pasted text's formulas become formulas
    cursor.movePosition(QTextCursor.End)
    widget.setTextCursor(cursor)
    pasted = QMimeData()
    pasted.setText(" and $\\alpha$")
    widget.insertFromMimeData(pasted)
    assert visual.Text == "Let $x^2$ be $$y$$ and z and $\\alpha$\n"
    # a dollar typed as text stays a dollar
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.End)
    cursor.insertText(" for $5$")
    assert visual.Text == "Let $x^2$ be $$y$$ and z and $\\alpha$ for \\$5\\$\n"


def test_apply_format_math(page):
    visual = page.mdVisual
    visual.Text = "Area: x^2\n"
    cursor = visual._widget.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(9, QTextCursor.KeepAnchor)
    visual._widget.setTextCursor(cursor)
    visual.ApplyFormat(vpMarkdownMath)
    assert visual.Text == "Area: $x^2$\n"
    assert visual._widget.textCursor().selectedText() == texdraw.OBJECT
    visual.ApplyFormat(vpMarkdownMath)  # (again: the TeX, selected, to edit)
    assert visual.Text == "Area: x^2\n" and visual._widget.textCursor().selectedText() == "x^2"
    visual.ApplyFormat(vpMarkdownMath)
    cursor = visual._widget.textCursor()
    cursor.setPosition(7)  # (the caret just after the formula)
    visual._widget.setTextCursor(cursor)
    visual.ApplyFormat(vpMarkdownMath)
    assert visual.Text == "Area: x^2\n"
    source = page.mdSource
    source.Text = "y = mx"
    cursor = source._widget.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(6, QTextCursor.KeepAnchor)
    source._widget.setTextCursor(cursor)
    source.ApplyFormat(vpMarkdownMath)
    assert source.Text == "$y = mx$"
    source.ApplyFormat(vpMarkdownMath)
    assert source.Text == "y = mx"


def test_source_colors_formulas(page):
    source = page.mdSource
    source.Text = "a $x^2$ b\n\n$$\n\\frac{1}{2}\n$$\n\n`$c$` \\$5\n"
    document = source._widget.document()
    highlighter = source._highlighter
    math = QColor(vp6.markdown._MD_COLORS["math"][highlighter.dark])

    def color_at(block_number, column):
        block = document.findBlockByNumber(block_number)
        for fmt_range in block.layout().formats():
            if fmt_range.start <= column < fmt_range.start + fmt_range.length:
                return fmt_range.format.foreground().color()
        return None

    assert color_at(0, 3) == math and color_at(0, 0) != math and color_at(0, 8) != math
    assert color_at(3, 2) == math and color_at(2, 0) == math and color_at(4, 0) == math
    assert color_at(6, 1) != math and color_at(6, 7) != math


# --- vp6help's viewer -------------------------------------------------------------------------------

def test_viewer_draws_formulas(qapp, tmp_path):
    (tmp_path / "maths.md").write_text(
        "# Maths\n\nThe roots of $ax^2 + bx + c = 0$ are\n\n"
        "$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$\n\n`$x$` stays.\n", encoding="utf-8")
    help_maker = maker.HelpMaker(title="Maths")
    help_maker.add(tmp_path / "maths.md")
    help_maker.build(tmp_path / "maths.vp6help")
    window = viewer.HelpViewer(str(tmp_path / "maths.vp6help"))
    try:
        document = window.browser.document()
        assert _formulas(document) == [("ax^2 + bx + c = 0", False),
                                       ("x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}", True)]
        assert "$x$ stays" in document.toPlainText()
        cursor = window.browser.textCursor()
        cursor.select(QTextCursor.Document)
        window.browser.setTextCursor(cursor)
        copied = window.browser.createMimeDataFromSelection().text()
        assert "The roots of $ax^2 + bx + c = 0$ are" in copied
        # zooming in makes the formulas bigger too; going back to the page keeps them
        handler = document.documentLayout().handlerForObject(texdraw.MATH_OBJECT)
        before = handler.intrinsicSize(document, 0, _formats(document)[1]).width()
        window.browser.zoomIn(4)
        after = handler.intrinsicSize(document, 0, _formats(document)[1]).width()
        assert after > before * 1.2
        window.browser.reload()
        assert len(_formulas(window.browser.document())) == 2
        image = window.browser.viewport().grab().toImage()
        assert _ink(image, window.browser.palette().color(QPalette.Base))
    finally:
        window.close()
        window.deleteLater()
