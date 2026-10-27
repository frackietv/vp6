"""Exercises for the Chapter 1 review: makers from each section's exercises.py (loaded
from the folders beside this one), then problems that mix the operations."""

from pathlib import Path

from vp6edu.answers import Exercise, Number, load_exercises

_CHAPTER = Path(__file__).resolve().parent.parent
_s1, _s2, _s3, _s4, _s5 = (load_exercises(_CHAPTER / section / "exercises.py")
                           for section in ("1.1", "1.2", "1.3", "1.4", "1.5"))


def _tex(n):
    return f"{n:,}".replace(",", "{,}")


def _thousand(n):
    return (n + 500) // 1000 * 1000  # (half up, as the lesson rounds: not Python's round)


def _from(maker, rng, section):
    exercise = maker(rng)
    exercise.skill = f"{exercise.skill or maker.__name__.replace('_', ' ')} ({section})"
    return exercise


def place_value(rng):
    return _from(_s1.value_of_a_digit, rng, "1.1")


def write_a_number(rng):
    return _from(_s1.write_from_a_name, rng, "1.1")


def rounding(rng):
    return _from(_s1.round_a_large_number, rng, "1.1")


def adding(rng):
    return _from(_s2.add_large_numbers, rng, "1.2")


def perimeter(rng):
    return _from(_s2.perimeter_of_a_rectangle, rng, "1.2")


def subtracting(rng):
    return _from(_s3.subtract_across_zeros, rng, "1.3")


def less_than(rng):
    return _from(_s3.translate_less_than, rng, "1.3")


def multiplying(rng):
    return _from(_s4.multiply_three_by_two_digits, rng, "1.4")


def area(rng):
    return _from(_s4.area_of_a_rectangle, rng, "1.4")


def dividing(rng):
    return _from(_s5.divide_by_two_digits, rng, "1.5")


def remainders(rng):
    return _from(_s5.divide_with_a_remainder, rng, "1.5")


def change_from_a_bill(rng):
    count, price = rng.randint(2, 6), rng.randint(6, 18)
    bill = next(b for b in (20, 50, 100, 200) if b > count * price)
    return Exercise(f"Ana buys {count} books at \\${price} each and pays with a \\${bill} bill. "
                    "How many dollars of change does she get?", Number(bill - count * price),
                    hints=["First find what the books cost: multiply.",
                           "Then the change: subtract the cost from the bill."],
                    solution=f"${count} \\times {price} = {count * price}$; ${bill} - "
                             f"{count * price} = {bill - count * price}$ dollars.",
                    skill="two-step problems")


def collect_then_pack(rng):
    students, each, box = rng.randint(18, 32), rng.randint(8, 25), rng.choice([10, 12, 20, 24])
    total = students * each
    return Exercise(f"{students} students collect {each} cans each and pack them in boxes of "
                    f"{box}. How many boxes can they fill?",
                    Number(total // box),
                    hints=["Find how many cans there are, then how many boxes of them.",
                           "Only full boxes count: leave out the remainder."],
                    solution=f"${students} \\times {each} = {total}$ cans; ${total} \\div {box} = "
                             f"{total // box}$ R ${total % box}$: {total // box} full boxes.",
                    skill="two-step problems")


def room_less_a_rug(rng):
    length, width = rng.randint(12, 24), rng.randint(10, 18)
    rug_l, rug_w = rng.randint(4, length - 4), rng.randint(3, width - 4)
    left = length * width - rug_l * rug_w
    return Exercise(f"A room is {length} feet by {width} feet. A rug {rug_l} feet by {rug_w} "
                    "feet lies on the floor. How many square feet of floor are not covered?",
                    Number(left),
                    hints=["Find both areas: length times width.", "Then subtract the rug's."],
                    solution=f"${length} \\times {width} - {rug_l} \\times {rug_w} = "
                             f"{length * width} - {rug_l * rug_w} = {left}$ square feet.",
                    skill="two-step problems")


def estimate_a_sum(rng):
    a, b = rng.randint(1000, 9499), rng.randint(1000, 9499)
    low, high = _thousand(a), _thousand(b)
    estimate = low + high
    return Exercise(f"Estimate ${_tex(a)} + {_tex(b)}$ by rounding each number to the nearest "
                    "thousand first. What is the estimate?",
                    Number(estimate, mistakes={str(a + b): "That's the exact sum: round each "
                                                           "number first."}),
                    hints=["Round each number to the nearest thousand, then add."],
                    solution=f"${_tex(low)} + {_tex(high)} = "
                             f"{_tex(estimate)}$ (exactly: ${_tex(a + b)}$).",
                    skill="estimating")
