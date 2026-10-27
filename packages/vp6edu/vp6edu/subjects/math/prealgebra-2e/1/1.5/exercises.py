"""Exercises for 1.5 Divide Whole Numbers: division as undoing multiplication, dividing by
one, by itself and by zero, long division with and without remainders, checking, words
that mean division, and word problems."""

from vp6edu.answers import Choice, Exercise, Number, Pair


def _tex(n):
    return f"{n:,}".replace(",", "{,}")


def from_a_multiplication(rng):
    a, b = rng.randint(3, 12), rng.randint(3, 12)
    return Exercise(f"Since ${a} \\cdot {b} = {a * b}$, what is ${a * b} \\div {b}$?",
                    Number(a),
                    hints=["Division undoes multiplication."],
                    solution=f"${a * b} \\div {b} = {a}$ because ${a} \\cdot {b} = {a * b}$.",
                    skill="division and multiplication")


def missing_factor(rng):
    a, b = rng.randint(6, 25), rng.randint(3, 12)
    return Exercise(f"What number makes this true? $\\square \\cdot {b} = {a * b}$", Number(a),
                    hints=[f"Divide: ${a * b} \\div {b}$."],
                    solution=f"${a * b} \\div {b} = {a}$", skill="division and multiplication")


def one_zero_and_itself(rng):
    n = rng.randint(2, 99)
    case, answer = rng.choice([(f"{n} \\div 1", str(n)), (f"{n} \\div {n}", "1"),
                               (f"0 \\div {n}", "0"), (f"{n} \\div 0", "undefined")])
    options = [str(n), "1", "0", "undefined"]
    return Exercise(f"What is ${case}$?\n\n(A) ${n}$  (B) $1$  (C) $0$  (D) undefined",
                    Choice(answer, options),
                    hints=["Think of the multiplication: what times the divisor gives the "
                           "dividend?", "No number times 0 gives anything but 0."],
                    solution=f"${case}$: {answer}.", skill="dividing by 0, 1 and itself")


def divide_by_one_digit(rng):
    divisor, quotient = rng.randint(2, 9), rng.randint(24, 999)
    dividend = divisor * quotient
    return Exercise(f"Divide: ${_tex(dividend)} \\div {divisor}$", Number(quotient),
                    hints=["Divide, multiply, subtract, bring down the next digit; repeat.",
                           "Check: your answer times the divisor gives the dividend."],
                    solution=f"${_tex(dividend)} \\div {divisor} = {quotient}$. Check: "
                             f"${quotient} \\cdot {divisor} = {_tex(dividend)}$.",
                    skill="long division")


def divide_by_two_digits(rng):
    divisor, quotient = rng.randint(11, 49), rng.randint(12, 250)
    dividend = divisor * quotient
    return Exercise(f"Divide: ${_tex(dividend)} \\div {divisor}$", Number(quotient),
                    hints=["Round the divisor to estimate each digit of the quotient.",
                           "If a product is too big, try the next smaller digit."],
                    solution=f"${_tex(dividend)} \\div {divisor} = {quotient}$. Check: "
                             f"${quotient} \\cdot {divisor} = {_tex(dividend)}$.",
                    skill="long division")


def divide_with_a_remainder(rng):
    divisor = rng.randint(3, 25)
    quotient, remainder = rng.randint(10, 150), rng.randint(1, divisor - 1)
    dividend = divisor * quotient + remainder
    return Exercise(f"Divide: ${_tex(dividend)} \\div {divisor}$. Give the quotient and the "
                    "remainder as a pair: (quotient, remainder).",
                    Pair((quotient, remainder), names=("quotient", "remainder")),
                    hints=["The remainder is what is left after the last subtraction.",
                           "The remainder must be less than the divisor."],
                    solution=f"${_tex(dividend)} \\div {divisor} = {quotient}$ R ${remainder}$. "
                             f"Check: ${quotient} \\cdot {divisor} + {remainder} = "
                             f"{_tex(dividend)}$.", skill="remainders")


def check_a_division(rng):
    divisor = rng.randint(3, 15)
    quotient, remainder = rng.randint(10, 90), rng.randint(1, divisor - 1)
    dividend = divisor * quotient + remainder
    return Exercise(f"Someone found ${{?}} \\div {divisor} = {quotient}$ R ${remainder}$. What "
                    "was the dividend?", Number(dividend),
                    hints=["Quotient times divisor, plus the remainder, is the dividend."],
                    solution=f"${quotient} \\cdot {divisor} + {remainder} = {dividend}$",
                    skill="checking division")


def divide_with_zeros(rng):
    base, zeros = rng.randint(2, 99), rng.randint(1, 3)
    power = 10 ** zeros
    return Exercise(f"Divide: ${_tex(base * power)} \\div {_tex(power)}$", Number(base),
                    hints=[f"Dividing by ${_tex(power)}$ takes {zeros} zero"
                           f"{'s' if zeros > 1 else ''} off the end."],
                    solution=f"${_tex(base * power)} \\div {_tex(power)} = {base}$",
                    skill="dividing by 10, 100 and 1,000")


def translate_a_quotient(rng):
    b, q = rng.randint(3, 15), rng.randint(4, 30)
    a = b * q
    phrase = rng.choice([f"the quotient of {a} and {b}", f"{a} divided by {b}",
                         f"{a} divided into {b} equal parts"])
    return Exercise(f"Translate into maths and simplify: *{phrase}*.", Number(q),
                    hints=["*Quotient* and *divided by* mean division, in the order written."],
                    solution=f"${a} \\div {b} = {q}$", skill="words for division")


def share_equally(rng):
    people, each = rng.randint(3, 12), rng.randint(4, 40)
    total = people * each
    thing = rng.choice(["stickers", "marbles", "cards", "dollars"])
    return Exercise(f"{total} {thing} are shared equally among {people} friends. How many "
                    "does each friend get?", Number(each),
                    hints=["*Shared equally*: divide."],
                    solution=f"${total} \\div {people} = {each}$ {thing} each.",
                    skill="word problems")


def vans_needed(rng):
    seats = rng.choice([7, 8, 12, 15])
    riders = seats * rng.randint(4, 15) + rng.randint(1, seats - 1)
    vans = riders // seats + 1
    return Exercise(f"{riders} people go on a trip in vans that seat {seats} each. How many vans "
                    "are needed?",
                    Number(vans, mistakes={str(riders // seats): "Those vans are full, but some "
                                                                 "people are still waiting."}),
                    hints=["Divide, then think about the remainder: those people need a van "
                           "too."],
                    solution=f"${riders} \\div {seats} = {riders // seats}$ R "
                             f"${riders % seats}$: one more van for the rest, ${vans}$ vans.",
                    skill="word problems")


def price_of_one(rng):
    count, price = rng.randint(3, 24), rng.randint(3, 85)
    return Exercise(f"{count} identical notebooks cost \\${count * price} together. How many "
                    "dollars does one cost?", Number(price),
                    hints=["The total split evenly among the notebooks: divide."],
                    solution=f"${count * price} \\div {count} = {price}$: \\${price} each.",
                    skill="word problems")
