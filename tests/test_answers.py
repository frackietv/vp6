"""Checking answers (vp6edu.answers): reading typed maths leniently, every kind of
answer, the known mistakes, exercises and their makers."""

import math
import subprocess
import sys
import textwrap
from fractions import Fraction as F

import pytest

from vp6edu.answers import (ALL_REAL, NO_SOLUTION, NOT_YET, RIGHT, UNREADABLE, Choice,
                            Equation, Exercise, Expression, Inequality, Interval, Line, Number,
                            Pair, Point, Solutions, Unreadable, equivalent, generators,
                            load_exercises, make, read, value, verify)


def status(answer, response):
    return answer.check(response).status


def mistake(answer, response):
    result = answer.check(response)
    assert result.status == NOT_YET, result
    return result.mistake


# --- reading -------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("2 1/3", F(7, 3)), ("-2 1/3", F(-7, 3)), ("2½", F(5, 2)), ("¾", F(3, 4)),
    ("25%", F(1, 4)), ("1,000", 1000), ("1,234,567.5", F(2469135, 2)), ("−5", -5),
    ("2×3÷4", F(3, 2)), ("2·3", 6), ("10⁻³", F(1, 1000)),
    ("3.2e5", 320000), ("2^3^2", 512), ("2**3", 8), ("-3^2", -9), ("(-3)^2", 9),
    ("√16", 4), ("sqrt(9/4)", F(3, 2)), ("∛-8", -2), ("8^(1/3)", 2),
    ("4^-1", F(1, 4)), ("|-3|", 3), ("2|-3|", 6), ("5!", 120), (".5", F(1, 2)),
    ("2(3)", 6), ("[1+2]{3}", 9), ("3/4 + 1/4", 1),
])
def test_numbers_read_leniently(text, expected):
    assert value(text) == expected


def test_irrational_values_are_floats():
    assert math.isclose(value("π"), math.pi) and math.isclose(value("2pi"), 2 * math.pi)
    assert math.isclose(value("√2"), math.sqrt(2)) and math.isclose(value("e"), math.e)
    assert math.isclose(value("sin(pi/2)"), 1) and math.isclose(value("ln(e^2)"), 2)
    assert math.isclose(value("log(1000)"), 3)


@pytest.mark.parametrize("text, shown", [
    ("2x", "2x"), ("x²", "x^2"), ("3(x+1)", "3(x + 1)"), ("√x", "√x"),
    ("xy", "xy"), ("2 sin x cos x", "2sin(x)cos(x)"), ("sin^2 x", "sin(x)^2"),
    ("|x - 1|", "|x - 1|"), ("θ", "θ"), ("theta", "θ"), ("x^2y", "x^2y"),
])
def test_expressions_read_leniently(text, shown):
    assert str(read(text)) == shown


def test_variables_and_euler():
    assert read("2xy + e^x").variables() == {"x", "y"}
    assert read("pix").variables() == {"x"}


@pytest.mark.parametrize("text, why", [
    ("2 3", "A number can't follow"), ("x2", "A number can't follow “x”"),
    ("(x+1", "closing bracket"), ("x+1)", "without its opening"), ("x+", "missing at the end"),
    ("|x", "closing “|”"), ("2 # 3", "can't read “#”"), ("", "nothing"),
    ("x = 2", "“=”"), ("sqrt", "What is sqrt of"),
])
def test_unreadable_says_why(text, why):
    with pytest.raises(Unreadable, match=why):
        read(text)


def test_values_that_are_undefined_or_have_letters():
    for text in ("1/0", "sqrt(-4)", "ln(0)", "(-8)^(1/2)"):
        with pytest.raises(ValueError, match="undefined"):
            value(text)
    with pytest.raises(ValueError, match="x has no value"):
        value("2x")


def test_equivalence_at_random_points():
    assert equivalent("(x+1)^2", "x^2 + 2x + 1")
    assert equivalent("2(x + y)", "2y + 2x")
    assert equivalent("sin(x)^2 + cos(x)^2", "1")
    assert equivalent("(x^2 - 1)/(x - 1)", "x + 1")   # (where both are defined)
    assert not equivalent("(x+1)^2", "x^2 + 1")
    assert not equivalent("x", "y")
    assert equivalent("sqrt(x)", "sqrt(x)") and not equivalent("sqrt(x)", "-sqrt(x)")


# --- choices -------------------------------------------------------------------------------

def test_a_choice():
    answer = Choice("B", ["one", "two", "three"], mistakes={"C": "Three is one too many."})
    for response in ("B", "b", "(B)", "b)", " B. ", "two", "Two", 1):
        assert status(answer, response) == RIGHT, response
    assert answer.check("A").status == NOT_YET
    assert answer.check("C").message == "Three is one too many."
    assert answer.check("A, B").message == "Choose just one."
    assert status(answer, "D") == UNREADABLE and status(answer, "") == UNREADABLE
    assert answer.text == "B"
    assert Choice(2, ["a", "b", "c"]).text == "C" and Choice("three", ["a", "three"]).text == "B"


def test_a_choice_of_many():
    answer = Choice(["A", "C"], ["x", "y", "z"])
    for response in ("A, C", "C, A", "a and c", "AC", "A C", [0, 2], ["A", "C"]):
        assert status(answer, response) == RIGHT, response
    assert "another one" in answer.check("A").message
    assert answer.check("A, B").message == "B isn't right."
    assert answer.text == "A, C"
    assert answer.check([]).message == "Not yet: at least one of them is right."
    assert status(answer, "none") == NOT_YET


def test_a_choice_of_none():
    answer = Choice([], ["x", "y", "z"])
    assert answer.many and answer.text == "none"
    for response in ("none", "None of them.", "none of the above", [], ()):
        assert status(answer, response) == RIGHT, response
    assert status(answer, "A") == NOT_YET
    one = Choice("A", ["x", "y"])  # (choosing nothing isn't an answer to a choice of one)
    assert one.check([]).message == "Choose an option."
    assert status(one, "none") == UNREADABLE


# --- numbers -------------------------------------------------------------------------------

def test_a_number_exactly():
    answer = Number(F(3, 4))
    for response in ("3/4", "0.75", ".75", "75%", "x = 3/4", F(3, 4), 0.75, "¾"):
        assert status(answer, response) == RIGHT, response
    assert answer.check("6/8").message == "Right! It simplifies to 3/4."
    assert Number(F(7, 3)).check("14/6").message == "Right! It simplifies to 2 1/3."
    assert mistake(answer, "-3/4") == "sign"
    assert mistake(answer, "4/3") == "reciprocal"
    assert mistake(answer, "7.5") == "place value"
    assert answer.check("1/2") == answer.check("1/2") and answer.check("1/2").message == "Not yet."
    assert mistake(Number(5), "2 + 3") == "unevaluated"
    assert status(Number(5, form="any"), "2 + 3") == RIGHT
    assert answer.check("1/0").status == NOT_YET and "undefined" in answer.check("1/0").message
    assert status(answer, "3x") == UNREADABLE and status(answer, "x < 1") == UNREADABLE
    assert status(Number(1000), "1,000") == RIGHT and status(Number(-5), "−5") == RIGHT


def test_a_number_within_a_tolerance_and_approximations():
    assert status(Number(math.pi, tolerance=0.01), "3.14") == RIGHT
    assert status(Number(math.pi, tolerance=0.001), "3.14") == NOT_YET
    assert mistake(Number(F(1, 3)), "0.33") == "approximate"
    assert "(a fraction)" in Number(F(1, 3)).check("0.333").message
    assert mistake(Number("sqrt(2)"), "1.414") == "approximate"
    assert status(Number("sqrt(2)"), "√2") == RIGHT
    assert status(Number("2√3"), "√12") == RIGHT
    assert status(Number("pi/2"), "π/2") == RIGHT and Number("pi/2").text == "pi/2"


def test_a_number_rounded():
    answer = Number(F(2, 3), places=2)
    assert answer.text == "0.67" and status(answer, "0.67") == RIGHT
    assert mistake(answer, "0.66") == "rounding" and mistake(answer, "0.6667") == "rounding"
    assert "2 decimal places" in answer.check("0.6667").message
    assert status(Number(F(1, 2), places=2), "0.5") == RIGHT
    assert Number(F(-5, 2), places=0).text == "-3" and Number(1234.5678, places=1).text == "1234.6"
    assert status(Number("sqrt(2)", places=3), "1.414") == RIGHT


@pytest.mark.parametrize("form, right, wrong", [
    ("integer", ["12", "x = 12"], [("24/2", "form"), ("12.0", "form")]),
    ("decimal", ["0.75"], [("3/4", "form"), ("75%", "form")]),
    ("percent", ["75%"], [("0.75", "form"), ("75", "percent"), ("0.75%", "percent")]),
    ("fraction", ["3/4", "3 / 4"], [("6/8", "unsimplified"), ("0.75", "form")]),
    ("simplest", ["3/4"], [("6/8", "unsimplified"), ("75%", "form")]),
])
def test_number_forms(form, right, wrong):
    answer = Number(12 if form == "integer" else F(3, 4), form=form)
    for response in right:
        assert status(answer, response) == RIGHT, response
    for response, name in wrong:
        assert mistake(answer, response) == name, response
    assert status(answer, answer.text) == RIGHT


def test_mixed_numbers_and_scientific_notation():
    mixed = Number(F(7, 3), form="mixed")
    assert mixed.text == "2 1/3" and status(mixed, "2 1/3") == RIGHT
    assert mistake(mixed, "7/3") == "form" and mistake(mixed, "1 4/3") == "unsimplified"
    assert mistake(mixed, "2 2/6") == "unsimplified"
    assert status(Number(F(-7, 3), form="mixed"), "-2 1/3") == RIGHT
    assert status(Number(F(1, 2), form="mixed"), "1/2") == RIGHT
    assert status(Number(F(7, 3), form="simplest"), "2 1/3") == RIGHT
    assert Number(F(7, 3), form="simplest").text == "7/3"
    sci = Number(1200, form="scientific")
    assert sci.text == "1.2 × 10^3"
    for response in ("1.2 × 10^3", "1.2*10^3", "1.2e3", "1.2 x 10^3".replace("x", "*")):
        assert status(sci, response) == RIGHT, response
    assert mistake(sci, "12 × 10^2") == "form" and mistake(sci, "1200") == "form"
    assert status(Number(F(3, 10000), form="scientific"), "3 × 10^-4") == RIGHT
    assert Number(F(3, 10000), form="scientific").text == "3 × 10^-4"


def test_simplified_radicals():
    answer = Number("2√3", form="simplified")
    assert status(answer, "2√3") == RIGHT and status(answer, "2sqrt(3)") == RIGHT
    assert "4 is a factor of 12" in answer.check("√12").message
    assert mistake(answer, "√12") == "unsimplified"
    half = Number("sqrt(2)/2", form="simplified")
    assert "Rationalize" in half.check("1/√2").message
    assert "no fraction under the root" in half.check("√(1/2)").message


def test_units():
    answer = Number(5, units="cm")
    assert answer.text == "5 cm"
    for response in ("5 cm", "5cm", "5 centimeters", "5 centimetres"):
        assert status(answer, response) == RIGHT, response
    assert mistake(answer, "5") == "units"
    assert "give it in cm" in answer.check("50 mm").message
    assert mistake(answer, "5 mm") == "units" and mistake(answer, "5 kg") == "units"
    assert "doesn't measure the same thing" in answer.check("3 kg").message
    assert status(Number(5, units="cm", convert=True), "50 mm") == RIGHT
    assert status(Number(5, units="cm", convert=True), "0.05 m") == RIGHT
    assert status(Number("12 cm^2"), "12 cm²") == RIGHT
    assert status(Number("12 cm^2"), "12 square centimeters") == RIGHT
    assert status(Number(1, units="L", convert=True), "1000 cubic cm") == RIGHT
    assert status(Number(60, units="mph", convert=True), "60 miles per hour") == RIGHT
    assert status(Number(50, units="km/h"), "50 km/h") == RIGHT
    money = Number(F(7, 2), units="$")
    assert money.text == "$7/2"
    assert status(money, "$3.50") == RIGHT and status(money, "3.50 dollars") == RIGHT
    assert status(money, "350 cents") == NOT_YET
    assert status(Number(F(7, 2), units="$", convert=True), "350 cents") == RIGHT
    assert status(Number("2pi cm"), "2π cm") == RIGHT
    with pytest.raises(ValueError, match="unknown unit"):
        Number(5, units="furlongs-per-fortnight")


def test_known_mistakes_of_a_number():
    answer = Number(12, mistakes={"7": "That's 3 + 4: multiply instead.", 1.5: "Upside down."})
    assert answer.check("7").message == "That's 3 + 4: multiply instead."
    assert answer.check("7").mistake == "known"
    assert answer.check("3/2").message == "Upside down."


# --- expressions and equations ---------------------------------------------------------------

def test_an_expression():
    answer = Expression("2(x + 3)")
    for response in ("2x + 6", "6 + 2x", "2(x+3)", "(x + 3)2", "2*x + 2*3", "x + x + 6",
                     "y = 2x + 6", "2X + 6"):
        assert status(answer, response) == RIGHT, response
    assert mistake(answer, "-2x - 6") == "sign"
    assert mistake(answer, "2y + 6") == "letters"
    assert answer.check("2x + 3").message == "Not yet."
    assert status(answer, "2x + 6 = 0") == UNREADABLE
    assert answer.text == "2(x + 3)"
    assert status(Expression("a^2 - b^2"), "(a - b)(a + b)") == RIGHT


def test_expression_forms():
    simplified = Expression("5x + 2", form="simplified")
    assert status(simplified, "5x + 2") == RIGHT
    assert simplified.check("2x + 3x + 2").message == "Combine the like terms."
    assert mistake(simplified, "2x + 3x + 2") == "unsimplified"
    assert "multiply its numbers" in Expression("6x", form="simplified").check("2·3x").message
    assert "repeated letters" in Expression("x^2", form="simplified").check("x·x").message
    halves = Expression("x + 2", form="simplified").check("(2x + 4)/2")
    assert "share the factor 2" in halves.message
    cancels = Expression("x + 1", form="simplified").check("(x^2 - 1)/(x - 1)")
    assert "share a factor" in cancels.message
    assert status(Expression("x/2 + 1", form="simplified"), "x/2 + 1") == RIGHT
    expanded = Expression("x^2 + 2x + 1", form="expanded")
    assert status(expanded, "x^2 + 2x + 1") == RIGHT and status(expanded, "1 + 2x + x^2") == RIGHT
    assert "Multiply out" in expanded.check("(x + 1)^2").message
    standard = Expression("x^2 + 2x + 1", form="standard")
    assert status(standard, "x^2 + 2x + 1") == RIGHT
    assert "highest power" in standard.check("1 + 2x + x^2").message
    assert status(Expression("3√2 + √3", form="simplified"), "3√2 + √3") == RIGHT
    with pytest.raises(ValueError):
        Expression("x", form="tidy")


def test_factored_completely():
    answer = Expression("x^2 + 5x + 6", form="factored")
    for response in ("(x + 2)(x + 3)", "(x + 3)(x + 2)", "(3 + x)(2 + x)"):
        assert status(answer, response) == RIGHT, response
    assert answer.check("x^2 + 5x + 6").message == "Write it as a product of factors."
    assert answer.check("x(x + 5) + 6").message == "Write it as a product of factors."
    two = Expression("2x^2 - 8", form="factored")
    assert status(two, "2(x - 2)(x + 2)") == RIGHT
    assert "factored further" in two.check("2(x^2 - 4)").message
    assert "common factor 2" in two.check("(2x - 4)(x + 2)").message
    assert status(Expression("x^3 + x^2", form="factored"), "x^2(x + 1)") == RIGHT
    assert "common factor x" in Expression("x^3 + x^2", form="factored").check("x(x^2 + x)").message
    assert status(Expression("(x - 1)^2", form="factored"), "(x - 1)^2") == RIGHT
    assert status(Expression("x^2 + 1", form="factored"), "x^2 + 1") == RIGHT  # (prime)
    assert status(Expression("-(x - 1)(x + 1)", form="factored"), "-(x - 1)(x + 1)") == RIGHT


def test_known_mistakes_of_an_expression():
    answer = Expression("x^2 + 2x + 1", mistakes={"x^2 + 1": "(a + b)² isn't a² + b²."})
    assert answer.check("1 + x^2").message == "(a + b)² isn't a² + b²."


def test_an_equation():
    answer = Equation("y = 2x + 1")
    for response in ("y = 2x + 1", "y - 1 = 2x", "2x - y = -1", "2y = 4x + 2", "Y = 2X + 1"):
        assert status(answer, response) == RIGHT, response
    assert answer.check("y = 2x + 2").message == "Not yet."
    assert status(answer, "2x + 1") == UNREADABLE and status(answer, "y = 2x = 1") == UNREADABLE
    slope = Equation("y = 2x + 1", form="slope-intercept")
    assert status(slope, "y = 1 + 2x") == RIGHT
    assert mistake(slope, "2x - y = -1") == "form" and mistake(slope, "y = 2(x + 1/2)") == "form"
    standard = Equation("2x - y = -1", form="standard")
    assert status(standard, "2x - y = -1") == RIGHT
    assert mistake(standard, "y = 2x + 1") == "form"
    assert mistake(standard, "x - y/2 = -1/2") == "form"
    solved = Equation("A = l w", solved_for="w")
    assert status(solved, "w = A/l") == RIGHT and "w alone" in solved.check("A/w = l").message


# --- sets, tuples and graphs ---------------------------------------------------------------

def test_solutions():
    answer = Solutions([2, -3])
    for response in ("x = 2, x = -3", "x = 2 or x = -3", "2, -3", "{-3, 2}", "-3 and 2",
                     "x=-3; x=2", "X = 2, X = -3", [2, -3]):
        assert status(answer, response) == RIGHT, response
    assert answer.text == "x = 2, x = -3"
    assert mistake(answer, "x = 2") == "missing"
    assert mistake(answer, "x = -2, x = 3") == "sign"
    assert answer.check("x = 2, x = -3, x = 5").message == "x = 5 isn't a solution."
    assert status(answer, "y = 2") == UNREADABLE
    plus_minus = Solutions([3, -3])
    for response in ("x = ±3", "±3", "+-3", "x = +/- 3"):
        assert status(plus_minus, response) == RIGHT, response
    roots = Solutions(["1 + sqrt(2)", "1 - sqrt(2)"])
    assert status(roots, "x = 1 ± √2") == RIGHT
    assert roots.text == "x = 1 + sqrt(2), x = 1 - sqrt(2)"


def test_no_solution_and_all_real_numbers():
    none = Solutions(NO_SOLUTION)
    for response in ("no solution", "No solutions", "none", "∅", "{ }", "no real solutions"):
        assert status(none, response) == RIGHT, response
    assert "does x = 4 work" in none.check("x = 4").message
    every = Solutions(ALL_REAL)
    for response in ("all real numbers", "ℝ", "infinitely many solutions", "(-∞, ∞)"):
        assert status(every, response) == RIGHT, response
    assert status(every, "no solution") == NOT_YET
    assert "there is a solution" in Solutions([1]).check("no solution").message


def test_inequalities_and_intervals():
    answer = Inequality("x > 3")
    for response in ("x > 3", "3 < x", "(3, ∞)", "(3, inf)", "x>3",
                     [Interval(3, math.inf)], Interval(3, math.inf)):
        assert status(answer, response) == RIGHT, response
    assert mistake(answer, "x >= 3") == "endpoint" and mistake(answer, "[3, ∞)") == "endpoint"
    assert mistake(answer, "x < 3") == "flipped" and mistake(answer, "(-∞, 3]") == "flipped"
    assert answer.check("x > 4").message == "Not yet."
    assert "never included" in answer.check("(3, ∞]").message
    between = Inequality("-2 < x ≤ 5")
    for response in ("-2 < x <= 5", "5 >= x > -2", "(-2, 5]", "x > -2 and x <= 5"):
        assert status(between, response) == RIGHT, response
    assert status(between, "5 < x < -2") == NOT_YET
    assert status(between, "-2 < x > 5") == UNREADABLE
    assert status(between, "(5, -2]") == UNREADABLE
    either = Inequality("x < -1 or x >= 4")
    assert either.text == "x < -1 or x >= 4"
    for response in ("(-∞, -1) ∪ [4, ∞)", "(-inf, -1) U [4, inf)", "x >= 4 or x < -1"):
        assert status(either, response) == RIGHT, response
    other = Inequality("x != 2")
    assert status(other, "(-∞, 2) ∪ (2, ∞)") == RIGHT
    assert status(Inequality("all real numbers"), "(-∞, ∞)") == RIGHT
    assert status(Inequality("no solution"), "∅") == RIGHT
    assert status(Inequality("t <= 1", variable="t"), "t ≤ 1") == RIGHT
    assert status(answer, "y > 3") == UNREADABLE


def test_inequality_notation_asked_for():
    interval = Inequality("-2 < x <= 5", form="interval")
    assert interval.text == "(-2, 5]" and status(interval, "(-2, 5]") == RIGHT
    assert mistake(interval, "-2 < x <= 5") == "form"
    notation = Inequality("[4, ∞)", form="inequality")
    assert notation.text == "x >= 4" and status(notation, "x ≥ 4") == RIGHT
    assert mistake(notation, "[4, inf)") == "form"
    assert status(notation, [Interval(4, math.inf, True)]) == RIGHT  # (a number line's)


def test_pairs_and_tuples():
    answer = Pair((2, -3))
    for response in ("(2, -3)", "2, -3", "[2, -3]", "(2,-3)", "⟨2, -3⟩", (2, -3)):
        assert status(answer, response) == RIGHT, response
    assert answer.text == "(2, -3)"
    assert mistake(answer, "(-3, 2)") == "swapped"
    assert "check number 2" in answer.check("(2, 3)").message
    assert answer.check("(1, 2, 3)").message == "Give 2 numbers."
    assert status(answer, "(2)") == UNREADABLE and status(answer, "(2, y)") == UNREADABLE
    named = Pair((2, -3), names=("x", "y"))
    assert status(named, "x = 2, y = -3") == RIGHT and status(named, "y = -3, x = 2") == RIGHT
    assert "x comes first" in named.check("(-3, 2)").message
    assert status(Pair((1, 2, 3)), "(1, 2, 3)") == RIGHT
    assert status(Pair(("1/2", "sqrt(2)")), "(0.5, √2)") == RIGHT


class _GraphPoint:
    def __init__(self, x, y):
        self.X, self.Y = x, y


def test_points_on_a_graph():
    answer = Point(2, 3)
    assert status(answer, _GraphPoint(2, 3)) == RIGHT and status(answer, "(2, 3)") == RIGHT
    assert mistake(answer, _GraphPoint(3, 2)) == "swapped"
    assert "check y" in answer.check(_GraphPoint(2, 4)).message
    near = Point(2, 3, tolerance=0.25)
    assert status(near, _GraphPoint(2.1, 2.9)) == RIGHT
    assert status(near, _GraphPoint(2.5, 3)) == NOT_YET


def test_lines():
    answer = Line("y = 2x + 1")
    for response in ("y = 2x + 1", "2x - y = -1", ((0, 1), (1, 3)),
                     (_GraphPoint(-1, -1), _GraphPoint(2, 5))):
        assert status(answer, response) == RIGHT, response
    assert mistake(answer, "y = 2x + 3") == "intercept"
    assert mistake(answer, "y = -2x + 1") == "sign"
    assert mistake(answer, "y = 3x + 1") == "slope"
    assert mistake(answer, ((0, 3), (1, 5))) == "intercept"
    assert status(answer, ((0, 1), (0, 1))) == UNREADABLE
    assert status(answer, "y = x^2") == UNREADABLE
    assert status(Line("x = 3"), ((3, 0), (3, 5))) == RIGHT
    assert status(Line("y = x/3", tolerance=0.1), ((0, 0.05), (3, 1))) == RIGHT
    assert mistake(Line("y = 2x + 1", form="slope-intercept"), "2x - y = -1") == "form"
    with pytest.raises(ValueError):
        Line("y = x^2")


# --- exercises -----------------------------------------------------------------------------

EXERCISES = textwrap.dedent('''
    from fractions import Fraction
    from vp6edu.answers import Exercise, Expression, Inequality, Number, Solutions

    def add_fractions(rng):
        b = rng.randint(3, 9)
        a = rng.randint(1, b - 2)
        return Exercise(f"Add $\\\\frac{{{a}}}{{{b}}} + \\\\frac{{1}}{{{b}}}$.",
                        Number(Fraction(a + 1, b), form="simplest"),
                        hints=["The denominators are the same.", "Add the numerators."],
                        solution="Add the numerators, keep the denominator.")

    def solve_product(rng):
        r, s = rng.randint(-9, 9), rng.randint(-9, 9)
        return Exercise(f"Solve $(x - {r})(x - {s}) = 0$.", Solutions([r, s]))

    def inequality(rng):
        a = rng.randint(-9, 9)
        return Exercise(f"Write $x > {a}$ in interval notation.",
                        Inequality(f"x > {a}", form="interval"))

    def percent(rng):
        return Exercise("A percent.", Number(Fraction(rng.randint(1, 199), 100), form="percent"))

    def mixed(rng):
        return Exercise("A mixed number.",
                        Number(Fraction(rng.randint(-40, 40), rng.randint(2, 9)), form="mixed"))

    def rounding(rng):
        return Exercise("Round.", Number(Fraction(rng.randint(-999, 999), rng.randint(1, 97)),
                                         places=rng.randint(0, 3)))

    def scientific(rng):
        return Exercise("Scientific.", Number(rng.randint(1, 10 ** 6), form="scientific"))

    def factor(rng):
        a, b = rng.randint(1, 9), rng.randint(1, 9)
        return Exercise("Factor.", Expression(f"(x + {a})(x - {b})", form="factored"))

    def _helper(rng):
        return None

    def two_arguments(rng, other):
        return None
''')


@pytest.fixture
def module(tmp_path):
    path = tmp_path / "lesson" / "exercises.py"
    path.parent.mkdir()
    path.write_text(EXERCISES, encoding="utf-8")
    return load_exercises(path)


def test_makers_and_their_seeds(module):
    makers = generators(module)
    assert [m.__name__ for m in makers] == ["add_fractions", "solve_product", "inequality",
                                            "percent", "mixed", "rounding", "scientific",
                                            "factor"]
    first, again = make(makers[0], 7), make(makers[0], 7)
    assert first.prompt == again.prompt and first.seed == 7
    assert any(make(makers[0], seed).prompt != first.prompt for seed in range(8, 20))
    assert first.skill == "add fractions"
    assert make(makers[0]).seed is not None


def test_every_makers_own_answer_checks_right(module):
    for maker in generators(module):
        assert verify(maker, range(200)) == [], maker.__name__


def test_an_exercise_counts_tries_and_gives_hints(module):
    exercise = make(generators(module)[0], 7)
    assert exercise.hints_left == 2
    assert exercise.hint() == "The denominators are the same."
    assert exercise.hint() == "Add the numerators." and exercise.hint() is None
    assert exercise.hints_left == 0
    assert exercise.check("").status == UNREADABLE and exercise.tries == 0
    assert exercise.check("100").status == NOT_YET and not exercise.solved
    assert exercise.check(exercise.answer.text).right and exercise.solved
    assert exercise.tries == 2


def test_verify_reports_broken_makers():
    def wrong(rng):
        return Exercise("", Number(F(1, 3), form="decimal"))

    def raising(rng):
        raise RuntimeError("oops")

    def not_an_exercise(rng):
        return 5

    problems = verify(wrong, [1])
    assert any("no prompt" in p for p in problems) and any("checks not yet" in p for p in problems)
    assert verify(raising, [1]) == ["raising, seed 1: RuntimeError: oops"]
    assert "not an Exercise" in verify(not_an_exercise, [1])[0]


def test_answers_need_no_qt():
    code = ("import sys, vp6edu.answers; "
            "assert not [m for m in sys.modules if m.startswith('PySide6')]")
    subprocess.run([sys.executable, "-c", code], check=True, cwd="/")
