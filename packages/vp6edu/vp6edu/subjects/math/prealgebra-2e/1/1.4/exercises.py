"""Exercises for 1.4 Multiply Whole Numbers: zero and one, the commutative property,
arrays, partial products, zeros at the ends, words that mean multiplication, word
problems and areas."""

from vp6edu.answers import Exercise, Number


def _tex(n):
    return f"{n:,}".replace(",", "{,}")


def _partials(a, b):
    """The partial products of a × b, one per digit of b, for a solution."""
    lines, place = [], 0
    for digit in reversed(str(b)):
        if digit != "0":
            part = a * int(digit) * 10 ** place
            lines.append(f"- ${_tex(a)} \\times {_tex(int(digit) * 10 ** place)} = "
                         f"{_tex(part)}$")
        place += 1
    return "\n".join(lines) + f"\n\nAdd them: ${_tex(a)} \\times {_tex(b)} = {_tex(a * b)}$."


def zero_or_one(rng):
    n = rng.randint(10, 9999)
    one = rng.random() < 0.5
    shown = rng.choice([f"{_tex(n)} \\cdot {int(one)}", f"{int(one)} \\cdot {_tex(n)}"])
    return Exercise(f"Multiply: ${shown}$", Number(n if one else 0),
                    hints=["Anything times 0 is 0; anything times 1 is itself."],
                    solution=f"${shown} = {_tex(n) if one else 0}$",
                    skill="multiplying by 0 and 1")


def order_of_factors(rng):
    a, b = rng.randint(12, 99), rng.randint(12, 99)
    return Exercise(f"${a} \\times {b} = {_tex(a * b)}$. Without multiplying, what is "
                    f"${b} \\times {a}$?", Number(a * b),
                    hints=["Turning an array on its side doesn't change how many are in it."],
                    solution=f"${b} \\times {a} = {a} \\times {b} = {_tex(a * b)}$",
                    skill="the commutative property")


def count_an_array(rng):
    rows, columns = rng.randint(3, 12), rng.randint(3, 15)
    thing = rng.choice(["chairs", "tiles", "trees", "eggs"])
    return Exercise(f"{thing.capitalize()} are set out in {rows} rows of {columns}. How many "
                    f"{thing} are there?", Number(rows * columns),
                    hints=["Rows of the same size: multiply the rows by the number in each."],
                    solution=f"${rows} \\times {columns} = {rows * columns}$ {thing}.",
                    skill="arrays")


def multiply_by_one_digit(rng):
    a, b = rng.randint(100, 9999), rng.randint(2, 9)
    return Exercise(f"Multiply: ${_tex(a)} \\times {b}$", Number(a * b),
                    hints=["Multiply each digit from the ones, carrying as in addition."],
                    solution=f"${_tex(a)} \\times {b} = {_tex(a * b)}$",
                    skill="multiplying")


def multiply_two_digit_numbers(rng):
    a, b = rng.randint(12, 99), rng.randint(12, 99)
    return Exercise(f"Multiply: ${a} \\times {b}$", Number(a * b),
                    hints=[f"Multiply ${a}$ by the ones of ${b}$, then by its tens.",
                           "Add the two partial products."],
                    solution=_partials(a, b), skill="partial products")


def multiply_three_by_two_digits(rng):
    a, b = rng.randint(101, 999), rng.randint(12, 99)
    return Exercise(f"Multiply: ${a} \\times {b}$", Number(a * b),
                    hints=["One partial product for each digit of the second factor."],
                    solution=_partials(a, b), skill="partial products")


def multiply_by_ten_hundred_thousand(rng):
    a, zeros = rng.randint(2, 999), rng.randint(1, 3)
    power = 10 ** zeros
    return Exercise(f"Multiply: ${a} \\times {_tex(power)}$", Number(a * power),
                    hints=[f"Multiplying by ${_tex(power)}$ puts {zeros} zero"
                           f"{'s' if zeros > 1 else ''} on the end."],
                    solution=f"${a} \\times {_tex(power)} = {_tex(a * power)}$",
                    skill="multiplying by 10, 100 and 1,000")


def zeros_at_the_ends(rng):
    a = rng.randint(2, 9) * 10 ** rng.randint(1, 2)
    b = rng.randint(2, 9) * 10 ** rng.randint(1, 3)
    return Exercise(f"Multiply: ${_tex(a)} \\times {_tex(b)}$", Number(a * b),
                    hints=["Multiply the digits that aren't zeros, then put back every zero."],
                    solution=f"${_tex(a)} \\times {_tex(b)} = {_tex(a * b)}$",
                    skill="multiplying by 10, 100 and 1,000")


def translate_a_product(rng):
    a = rng.randint(12, 99)
    b = rng.randint(3, 19)
    phrase, factor = rng.choice([(f"the product of {a} and {b}", b), (f"{a} times {b}", b),
                                 (f"twice {a}", 2), (f"triple {a}", 3)])
    return Exercise(f"Translate into maths and simplify: *{phrase}*.", Number(a * factor),
                    hints=["*Product*, *times*, *twice* (2 times) and *triple* (3 times) mean "
                           "multiplication."],
                    solution=f"${factor} \\cdot {a} = {_tex(a * factor)}$",
                    skill="words for multiplication")


def boxes_of_cans(rng):
    boxes, each = rng.randint(12, 60), rng.choice([6, 12, 18, 24, 36, 48])
    return Exercise(f"A box holds {each} cans. How many cans are in {boxes} boxes?",
                    Number(boxes * each),
                    hints=["*Each* box holds the same: multiply."],
                    solution=f"${boxes} \\times {each} = {_tex(boxes * each)}$ cans.",
                    skill="word problems")


def ticket_cost(rng):
    people, price = rng.randint(3, 40), rng.randint(8, 65)
    return Exercise(f"Tickets cost \\${price} each. How many dollars do {people} tickets cost?",
                    Number(people * price),
                    hints=["The same price for every ticket: multiply."],
                    solution=f"${people} \\times {price} = {_tex(people * price)}$: "
                             f"\\${people * price:,}.", skill="word problems")


def area_of_a_rectangle(rng):
    length, width = rng.randint(6, 45), rng.randint(4, 30)
    unit = rng.choice(["feet", "metres", "yards"])
    return Exercise(f"A rectangular floor is {length} {unit} long and {width} {unit} wide. What "
                    f"is its area, in square {unit}?", Number(length * width),
                    hints=["The area of a rectangle is its length times its width."],
                    solution=f"${length} \\times {width} = {_tex(length * width)}$ square "
                             f"{unit}.", skill="area")
