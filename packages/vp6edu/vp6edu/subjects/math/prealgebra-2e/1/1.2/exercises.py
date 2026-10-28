"""Exercises for 1.2 Add Whole Numbers: the properties, column addition with carrying,
words that mean addition, word problems and perimeters."""

from vp6edu.answers import Choice, Exercise, Number


def _tex(n):
    return f"{n:,}".replace(",", "{,}")


def _carries(a, b):
    """The column-by-column working of a + b, for a solution."""
    lines, carry, place = [], 0, 0
    names = ("Ones", "Tens", "Hundreds", "Thousands", "Ten thousands", "Hundred thousands",
             "Millions")
    while a or b or carry:
        x, y = a % 10, b % 10
        total = x + y + carry
        parts = " + ".join(str(v) for v in ([carry] if carry else []) + [x, y])
        note = f"write ${total % 10}$, carry $1$" if total >= 10 else f"write ${total}$"
        lines.append(f"- {names[min(place, 6)]}: ${parts} = {total}$: {note}.")
        carry, a, b, place = total // 10, a // 10, b // 10, place + 1
    return "\n".join(lines)


def add_zero(rng):
    n = rng.randint(10, 9999)
    left = rng.random() < 0.5
    shown = f"0 + {_tex(n)}" if left else f"{_tex(n)} + 0"
    return Exercise(f"Add: ${shown}$", Number(n),
                    hints=["Adding zero changes nothing: the identity property."],
                    solution=f"${shown} = {_tex(n)}$", skill="the identity property")


def order_of_addends(rng):
    a, b = rng.randint(100, 999), rng.randint(100, 999)
    return Exercise(f"$ {a} + {b} = {a + b}$. Without adding, what is ${b} + {a}$?",
                    Number(a + b),
                    hints=["The order of the addends doesn't change the sum: the commutative "
                           "property."],
                    solution=f"${b} + {a} = {a} + {b} = {a + b}$",
                    skill="the commutative property")


def name_the_parts(rng):
    a, b = rng.randint(10, 99), rng.randint(10, 99)
    return Exercise(f"In ${a} + {b} = {a + b}$, what is ${a + b}$ called?",
                    Choice("B", ["an addend", "the sum", "the plus"]),
                    hints=["The numbers added are addends; the result has its own name."],
                    solution=f"${a + b}$ is the sum; ${a}$ and ${b}$ are the addends.",
                    skill="addition notation")


def add_two_digit_numbers(rng):
    a = rng.randint(1, 8) * 10 + rng.randint(1, 9)
    b = rng.randint(1, 8) * 10 + rng.randint(10 - a % 10, 9)  # (the ones regroup)
    return Exercise(f"Add: ${a} + {b}$", Number(a + b),
                    hints=["Add the ones first: ten or more ones make a ten to carry."],
                    solution=_carries(a, b) + f"\n\nSo ${a} + {b} = {a + b}$.",
                    skill="adding with regrouping")


def add_three_digit_numbers(rng):
    a, b = rng.randint(100, 999), rng.randint(100, 999)
    return Exercise(f"Add: ${a} + {b}$", Number(a + b),
                    hints=["Line up the places and add each column from the ones.",
                           "Carry a ten to the next column when a column's sum is 10 or more."],
                    solution=_carries(a, b) + f"\n\nSo ${a} + {b} = {_tex(a + b)}$.",
                    skill="adding with regrouping")


def add_large_numbers(rng):
    a, b = rng.randint(10000, 999999), rng.randint(1000, 99999)
    return Exercise(f"Add: ${_tex(a)} + {_tex(b)}$", Number(a + b),
                    hints=["Write the smaller number under the larger, ones under ones."],
                    solution=_carries(a, b) + f"\n\nSo ${_tex(a)} + {_tex(b)} = "
                                              f"{_tex(a + b)}$.",
                    skill="adding large numbers")


def add_three_numbers(rng):
    a, b, c = rng.randint(100, 9999), rng.randint(10, 999), rng.randint(10, 999)
    return Exercise(f"Add: ${_tex(a)} + {b} + {c}$", Number(a + b + c),
                    hints=["Add two of them, then add the third to that sum.",
                           "With three numbers, a column can carry 2."],
                    solution=f"${_tex(a)} + {b} = {_tex(a + b)}$, and ${_tex(a + b)} + {c} = "
                             f"{_tex(a + b + c)}$.", skill="adding several numbers")


def translate_a_sum(rng):
    a, b = rng.randint(12, 99), rng.randint(12, 99)
    phrase, shown = rng.choice([
        (f"the sum of {a} and {b}", f"{a} + {b}"),
        (f"{b} more than {a}", f"{a} + {b}"),
        (f"{a} increased by {b}", f"{a} + {b}"),
        (f"the total of {a} and {b}", f"{a} + {b}"),
        (f"{b} added to {a}", f"{a} + {b}")])
    return Exercise(f"Translate into maths and simplify: *{phrase}*.", Number(a + b),
                    hints=["*Sum*, *more than*, *increased by*, *total* and *added to* all mean "
                           "addition."],
                    solution=f"${shown} = {a + b}$", skill="words for addition")


def shopping_total(rng):
    items = rng.sample([("a jacket", 40, 120), ("shoes", 30, 90), ("a backpack", 20, 60),
                        ("a game", 15, 70), ("a lamp", 12, 45)], 3)
    prices = [rng.randint(lo, hi) for _, lo, hi in items]
    listed = ", ".join(f"{name} for \\${price}" for (name, _, _), price in zip(items, prices))
    return Exercise(f"Mia buys {listed}. How many dollars does she spend in all?",
                    Number(sum(prices)),
                    hints=["*In all* means add every price."],
                    solution=f"${' + '.join(map(str, prices))} = {sum(prices)}$: she spends "
                             f"\\${sum(prices)}.", skill="word problems")


def road_trip(rng):
    days = [rng.randint(180, 520) for _ in range(rng.randint(3, 4))]
    listed = ", ".join(map(str, days[:-1])) + f" and {days[-1]}"
    return Exercise(f"On a road trip a family drives {listed} miles on successive days. "
                    "How many miles do they drive altogether?", Number(sum(days)),
                    hints=["Add the distances, two at a time if you like."],
                    solution=f"${' + '.join(map(str, days))} = {_tex(sum(days))}$ miles.",
                    skill="word problems")


def population_growth(rng):
    before, more = rng.randint(20000, 90000), rng.randint(1000, 9000)
    return Exercise(f"A city had ${_tex(before)}$ people; ten years later it had ${_tex(more)}$ "
                    "more. How many people did it have then?", Number(before + more),
                    hints=["*More* than before: add."],
                    solution=f"${_tex(before)} + {_tex(more)} = {_tex(before + more)}$",
                    skill="word problems")


def perimeter_of_a_triangle(rng):
    sides = [rng.randint(5, 40) for _ in range(3)]
    sides.sort()
    while sides[0] + sides[1] <= sides[2]:
        sides[2] -= 1
    return Exercise(f"A triangle's sides are {sides[0]}, {sides[1]} and {sides[2]} inches long. "
                    "What is its perimeter, in inches?", Number(sum(sides)),
                    hints=["The perimeter is the distance around: add all the sides."],
                    solution=f"${sides[0]} + {sides[1]} + {sides[2]} = {sum(sides)}$ inches.",
                    skill="perimeter")


def perimeter_of_a_rectangle(rng):
    length, width = rng.randint(12, 90), rng.randint(5, 40)
    total = 2 * length + 2 * width
    return Exercise(f"A rectangular field is {length} yards long and {width} yards wide. What "
                    "is its perimeter, in yards?", Number(total),
                    hints=["A rectangle has two long sides and two short ones: add all four."],
                    solution=f"${length} + {width} + {length} + {width} = {total}$ yards.",
                    skill="perimeter")
