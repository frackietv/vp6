"""Exercises for 1.1 Introduction to Whole Numbers: counting and whole numbers,
base-10 blocks, place value, names of numbers, rounding."""

from vp6edu.answers import Choice, Exercise, Number

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_PERIODS = ("", "thousand", "million", "billion")
_PLACES = ("ones", "tens", "hundreds", "thousands", "ten thousands", "hundred thousands",
           "millions", "ten millions", "hundred millions", "billions")


def _below_thousand(n):
    words = []
    if n >= 100:
        words.append(f"{_ONES[n // 100]} hundred")
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(_ONES[n])
    return " ".join(words)


def _name(n):
    """A whole number in words, as the lesson names it."""
    if n == 0:
        return "zero"
    parts, period = [], 0
    while n:
        n, group = divmod(n, 1000)
        if group:
            parts.append((_below_thousand(group) + " " + _PERIODS[period]).strip())
        period += 1
    return ", ".join(reversed(parts))


def _tex(n):
    """A number for a formula: thousands separated by {,} (no space after the commas)."""
    return f"{n:,}".replace(",", "{,}")


def _round(n, place):
    step = 10 ** place
    return (n + step // 2) // step * step


def _with_distinct_digits(rng, digits):
    first = rng.randint(1, 9)
    rest = rng.sample([d for d in range(10) if d != first], digits - 1)
    return int("".join(map(str, [first] + rest)))


def counting_or_whole(rng):
    numbers = [("0", "only a whole number"), (str(rng.randint(1, 999)), "both"),
               (f"\\frac{{{rng.randint(1, 4)}}}{{{rng.randint(5, 9)}}}", "neither"),
               (f"{rng.randint(1, 20)}.{rng.randint(1, 9)}", "neither")]
    shown, kind = rng.choice(numbers)
    options = ["both", "only a whole number", "neither"]
    return Exercise(f"Is ${shown}$ a counting number, a whole number, both or neither?\n\n"
                    "(A) both  (B) only a whole number  (C) neither",
                    Choice(kind, options),
                    hints=["The counting numbers start at 1; the whole numbers at 0.",
                           "Fractions and decimals that aren't whole are neither."],
                    solution=f"${shown}$: {kind}.", skill="counting and whole numbers")


def base_ten_blocks(rng):
    thousands, flats, rods, cubes = (rng.randint(0, 4), rng.randint(0, 9), rng.randint(0, 9),
                                     rng.randint(0, 9))
    value = 1000 * thousands + 100 * flats + 10 * rods + cubes
    if not value:
        cubes, value = 5, 5
    parts = ", ".join(f"{count} {name}" for count, name in (
        (thousands, "big cubes"), (flats, "flats"), (rods, "rods"), (cubes, "small cubes")))
    return Exercise(f"A big cube is $1{{,}}000$, a flat $100$, a rod $10$ and a small cube $1$. "
                    f"What number do {parts} show?", Number(value),
                    hints=["Multiply each count by what one block is worth.",
                           "A place with no blocks gets the digit 0."],
                    solution=f"${thousands} \\times 1000 + {flats} \\times 100 + {rods} \\times 10"
                             f" + {cubes} = {_tex(value)}$", skill="base-10 blocks")


def place_of_a_digit(rng):
    n = _with_distinct_digits(rng, rng.randint(5, 9))
    text = str(n)
    i = rng.randrange(len(text))
    place = _PLACES[len(text) - 1 - i]
    options = list(_PLACES[:len(text)])
    return Exercise(f"In ${_tex(n)}$, what is the place value of the digit ${text[i]}$?\n\n"
                    "Type the place's name (ones, tens, hundreds, thousands, ten thousands...).",
                    Choice(place, options),
                    hints=["Count the places from the right: ones, tens, hundreds, then "
                           "thousands, ten thousands, hundred thousands, millions..."],
                    solution=f"The ${text[i]}$ is in the {place} place.", skill="place value")


def digit_in_a_place(rng):
    n = rng.randint(10 ** 5, 10 ** 8 - 1)
    place = rng.randrange(len(str(n)))
    digit = n // 10 ** place % 10
    return Exercise(f"Which digit is in the {_PLACES[place]} place of ${_tex(n)}$?",
                    Number(digit),
                    hints=["The ones place is the last digit; each place to the left is ten "
                           "times bigger."],
                    solution=f"The {_PLACES[place]} digit of ${_tex(n)}$ is ${digit}$.",
                    skill="place value")


def value_of_a_digit(rng):
    n = _with_distinct_digits(rng, rng.randint(4, 7))
    text = str(n)
    i = rng.randrange(len(text) - 1)
    value = int(text[i]) * 10 ** (len(text) - 1 - i)
    return Exercise(f"What is the digit ${text[i]}$ in ${_tex(n)}$ worth?", Number(value),
                    hints=["Find its place, then write the digit with a zero for each place to "
                           "its right."],
                    solution=f"The ${text[i]}$ is in the {_PLACES[len(text) - 1 - i]} place: "
                             f"it is worth ${_tex(value)}$.", skill="place value")


def name_a_number(rng):
    n = rng.randint(1, 999) * 1000 + rng.choice([0, rng.randint(1, 99), rng.randint(100, 999)])
    if rng.random() < 0.4:
        n += rng.randint(1, 9) * 1000000
    wrong = {_name(n * 10 // 10 + 10 ** rng.randint(0, 2)), _name(n // 1000),
             _name(n // 1000 * 1000), _name(int(str(n)[::-1].lstrip("0") or 1))} - {_name(n)}
    options = [_name(n)] + sorted(wrong)[:3]
    rng.shuffle(options)
    letters = "ABCD"
    listed = "\n".join(f"- ({letters[i]}) {option}" for i, option in enumerate(options))
    return Exercise(f"Which is the name of ${_tex(n)}$?\n\n{listed}",
                    Choice(options.index(_name(n)), options),
                    hints=["Split the number into periods of three digits from the right.",
                           "Name each period's number, then the period's name."],
                    solution=f"${_tex(n)}$ is *{_name(n)}*.", skill="naming numbers")


def write_from_a_name(rng):
    n = rng.randint(1, 99) * 10 ** rng.choice([3, 6]) + rng.randint(0, 999)
    return Exercise(f"Write with digits: *{_name(n)}*.", Number(n),
                    hints=["Write each period's three digits, filling with zeros."],
                    solution=f"${_tex(n)}$", skill="writing numbers")


def round_to_tens_or_hundreds(rng):
    n = rng.randint(100, 99999)
    place = rng.choice([1, 2])
    answer = _round(n, place)
    return Exercise(f"Round ${_tex(n)}$ to the nearest {_PLACES[place][:-1]}.", Number(answer),
                    hints=[f"Look at the digit just right of the {_PLACES[place]} place.",
                           "5 or more rounds up; less than 5 leaves the digit as it is."],
                    solution=f"${_tex(n)} \\approx {_tex(answer)}$", skill="rounding")


def round_a_large_number(rng):
    n = rng.randint(10 ** 5, 10 ** 9)
    place = rng.randint(3, len(str(n)) - 1)
    answer = _round(n, place)
    name = _PLACES[place][:-1]
    return Exercise(f"Round ${_tex(n)}$ to the nearest {name}.", Number(answer),
                    hints=[f"Find the {name}s digit; the digit after it decides.",
                           "Every place after it becomes 0."],
                    solution=f"${_tex(n)} \\approx {_tex(answer)}$", skill="rounding")


def round_with_a_carry(rng):
    place = rng.choice([1, 2, 3])
    step = 10 ** place
    n = rng.randint(1, 9) * 10 * step - rng.randint(1, step // 2)
    answer = _round(n, place)
    return Exercise(f"Round ${_tex(n)}$ to the nearest {_PLACES[place][:-1]}.", Number(answer),
                    hints=["Rounding a 9 up makes it 10: carry the 1 into the place to its "
                           "left."],
                    solution=f"${_tex(n)} \\approx {_tex(answer)}$", skill="rounding")


def population_in_words(rng):
    n = rng.randint(10, 999) * 1000 + rng.randint(1, 999)
    town = rng.choice(["Riverton", "Lakeside", "Millbrook", "Harbor City", "Oakdale"])
    return Exercise(f"The population of {town} is *{_name(n)}*. Write it with digits.",
                    Number(n),
                    hints=["The thousands period comes first, then the ones period's three "
                           "digits."],
                    solution=f"${_tex(n)}$ people.", skill="writing numbers")


def round_a_price(rng):
    n = rng.randint(12000, 48999)
    item = rng.choice(["car", "boat", "kitchen", "tractor"])
    answer = _round(n, 3)
    return Exercise(f"A {item} costs \\${_tex(n).replace('{,}', ',')}. Round its price to the "
                    "nearest thousand dollars (give the number).", Number(answer),
                    hints=["The thousands digit stays or goes up by one: look at the hundreds."],
                    solution=f"\\${n:,} is about \\${answer:,}.", skill="rounding")
