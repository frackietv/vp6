"""Exercises for 1.3 Subtract Whole Numbers: subtraction as undoing addition, borrowing,
across zeros, checking, words that mean subtraction, and word problems."""

from vp6edu.answers import Exercise, Number


def _tex(n):
    return f"{n:,}".replace(",", "{,}")


def _check(a, b):
    return f"Check: ${_tex(a - b)} + {_tex(b)} = {_tex(a)}$."


def from_an_addition(rng):
    a, b = rng.randint(12, 99), rng.randint(12, 99)
    return Exercise(f"Since ${a} + {b} = {a + b}$, what is ${a + b} - {b}$?", Number(a),
                    hints=["Subtraction undoes addition: taking away what was added leaves the "
                           "other addend."],
                    solution=f"${a + b} - {b} = {a}$ because ${a} + {b} = {a + b}$.",
                    skill="subtraction and addition")


def missing_addend(rng):
    a, b = rng.randint(15, 99), rng.randint(15, 99)
    return Exercise(f"What number makes this true? $\\square + {b} = {a + b}$",
                    Number(a),
                    hints=[f"Subtract: ${a + b} - {b}$."],
                    solution=f"${a + b} - {b} = {a}$", skill="subtraction and addition")


def subtract_without_borrowing(rng):
    digits = rng.randint(2, 4)
    top = [rng.randint(1, 9)] + [rng.randint(1, 9) for _ in range(digits - 1)]
    bottom = [rng.randint(0, d) for d in top]
    bottom[0] = rng.randint(0, top[0] - 1) if top[0] > 1 else 0
    a, b = int("".join(map(str, top))), int("".join(map(str, bottom)))
    return Exercise(f"Subtract: ${_tex(a)} - {_tex(b)}$", Number(a - b),
                    hints=["Subtract each column, starting with the ones."],
                    solution=f"${_tex(a)} - {_tex(b)} = {_tex(a - b)}$. " + _check(a, b),
                    skill="subtracting")


def subtract_with_borrowing(rng):
    a = rng.randint(30, 99) * 10 + rng.randint(0, 8)
    b = rng.randint(10, a // 10 - 5) * 10 + rng.randint(a % 10 + 1, 9)  # (the ones borrow)
    return Exercise(f"Subtract: ${a} - {b}$", Number(a - b),
                    hints=["The ones on top are fewer than below: borrow a ten from the tens "
                           "column.", "Check by adding your answer to the number taken away."],
                    solution=f"${a} - {b} = {a - b}$. " + _check(a, b),
                    skill="borrowing")


def subtract_across_zeros(rng):
    a = rng.randint(2, 9) * 1000 + rng.choice([0, 0, rng.randint(1, 9)])
    b = rng.randint(1001, a - 100)
    return Exercise(f"Subtract: ${_tex(a)} - {_tex(b)}$", Number(a - b),
                    hints=["The tens and hundreds are 0: borrow from the thousands first.",
                           "1 thousand is 9 hundreds, 9 tens and 10 ones."],
                    solution=f"${_tex(a)} - {_tex(b)} = {_tex(a - b)}$. " + _check(a, b),
                    skill="borrowing across zeros")


def subtract_large_numbers(rng):
    a = rng.randint(100000, 999999)
    b = rng.randint(10000, a - 1)
    return Exercise(f"Subtract: ${_tex(a)} - {_tex(b)}$", Number(a - b),
                    hints=["Line up the places; borrow where a top digit is too small."],
                    solution=f"${_tex(a)} - {_tex(b)} = {_tex(a - b)}$. " + _check(a, b),
                    skill="subtracting large numbers")


def translate_a_difference(rng):
    a = rng.randint(40, 99)
    b = rng.randint(11, a - 5)
    phrase = rng.choice([f"the difference of {a} and {b}", f"{a} minus {b}",
                         f"{a} decreased by {b}"])
    return Exercise(f"Translate into maths and simplify: *{phrase}*.", Number(a - b),
                    hints=["*Difference*, *minus* and *decreased by* mean subtraction, in the "
                           "order written."],
                    solution=f"${a} - {b} = {a - b}$", skill="words for subtraction")


def translate_less_than(rng):
    a = rng.randint(40, 99)
    b = rng.randint(11, a - 5)
    phrase = rng.choice([f"{b} less than {a}", f"{b} subtracted from {a}"])
    return Exercise(f"Translate into maths and simplify: *{phrase}*.",
                    Number(a - b, mistakes={str(b - a): "That's the order written, but *less "
                                                        "than* and *subtracted from* turn it "
                                                        "round."}),
                    hints=[f"*{b} less than {a}* starts from {a}."],
                    solution=f"${a} - {b} = {a - b}$", skill="words for subtraction")


def temperature_drop(rng):
    high = rng.randint(55, 98)
    low = rng.randint(20, high - 8)
    return Exercise(f"At noon it was {high} degrees; by midnight it was {low} degrees. By how "
                    "many degrees did the temperature fall?", Number(high - low),
                    hints=["How much it fell is the difference of the two temperatures."],
                    solution=f"${high} - {low} = {high - low}$ degrees.", skill="word problems")


def money_left(rng):
    saved = rng.randint(300, 2500)
    spent = rng.randint(100, saved - 20)
    return Exercise(f"Leo had \\${saved:,} in his account and paid \\${spent:,} for a bike. How "
                    "many dollars are left?", Number(saved - spent),
                    hints=["*Left* means take away what was paid."],
                    solution=f"${_tex(saved)} - {_tex(spent)} = {_tex(saved - spent)}$: "
                             f"\\${saved - spent:,} left.", skill="word problems")


def how_many_more(rng):
    a = rng.randint(1000, 9000)
    b = rng.randint(200, a - 100)
    place, other = rng.choice([("Ridgeway", "Elmwood"), ("North Hall", "South Hall")])
    return Exercise(f"{place} has ${_tex(a)}$ books and {other} has ${_tex(b)}$. How many more "
                    f"books does {place} have?", Number(a - b),
                    hints=["*How many more* compares: subtract the smaller from the larger."],
                    solution=f"${_tex(a)} - {_tex(b)} = {_tex(a - b)}$ more books.",
                    skill="word problems")


def seats_left(rng):
    seats = rng.randint(20, 80) * 1000 + rng.randint(0, 9) * 100
    sold = rng.randint(seats // 2, seats - 100)
    return Exercise(f"An arena has ${_tex(seats)}$ seats and ${_tex(sold)}$ tickets were sold. "
                    "How many seats are empty?", Number(seats - sold),
                    hints=["Empty seats: all the seats minus the ones sold.",
                           "Borrow across the zeros from the thousands."],
                    solution=f"${_tex(seats)} - {_tex(sold)} = {_tex(seats - sold)}$",
                    skill="word problems")
