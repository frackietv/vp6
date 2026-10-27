"""Exercises for the Chapter 1 practice test: one question of each kind the chapter
taught, from the sections' exercises.py (loaded from the folders beside this one), and
two problems that take two steps."""

from pathlib import Path

from vp6edu.answers import Exercise, Number, Pair, load_exercises

_CHAPTER = Path(__file__).resolve().parent.parent
_s1, _s2, _s3, _s4, _s5 = (load_exercises(_CHAPTER / section / "exercises.py")
                           for section in ("1.1", "1.2", "1.3", "1.4", "1.5"))


def _from(maker, rng, section):
    exercise = maker(rng)
    exercise.skill = f"{exercise.skill or maker.__name__.replace('_', ' ')} ({section})"
    return exercise


def question_1(rng):
    return _from(_s1.write_from_a_name, rng, "1.1")


def question_2(rng):
    return _from(_s1.digit_in_a_place, rng, "1.1")


def question_3(rng):
    return _from(_s1.round_with_a_carry, rng, "1.1")


def question_4(rng):
    return _from(_s2.add_three_numbers, rng, "1.2")


def question_5(rng):
    return _from(_s2.translate_a_sum, rng, "1.2")


def question_6(rng):
    return _from(_s3.subtract_large_numbers, rng, "1.3")


def question_7(rng):
    return _from(_s3.how_many_more, rng, "1.3")


def question_8(rng):
    return _from(_s4.multiply_three_by_two_digits, rng, "1.4")


def question_9(rng):
    return _from(_s4.zeros_at_the_ends, rng, "1.4")


def question_10(rng):
    return _from(_s5.divide_by_two_digits, rng, "1.5")


def question_11(rng):
    return _from(_s5.one_zero_and_itself, rng, "1.5")


def question_12(rng):
    boxes, each, classes = rng.randint(12, 40), rng.choice([12, 24, 36, 48]), rng.choice(
        [4, 6, 8, 12])
    total = boxes * each
    while total % classes:
        boxes += 1
        total = boxes * each
    return Exercise(f"A school orders {boxes} boxes of pencils with {each} pencils in each, and "
                    f"shares them equally among {classes} classes. How many pencils does each "
                    "class get?", Number(total // classes),
                    hints=["How many pencils are there? Multiply.",
                           "Then share them out: divide."],
                    solution=f"${boxes} \\times {each} = {total}$; ${total} \\div {classes} = "
                             f"{total // classes}$ pencils.", skill="two-step problems (1.4, 1.5)")


def question_13(rng):
    length, width = rng.randint(12, 40), rng.randint(8, 30)
    return Exercise(f"A garden is {length} feet long and {width} feet wide. How many feet of "
                    "fence go round it, and what is its area? Give (perimeter, area).",
                    Pair((2 * length + 2 * width, length * width), names=("perimeter", "area"),
                         mistakes={f"({length * width}, {2 * length + 2 * width})":
                                   "Those are the right numbers, the wrong way round: the "
                                   "perimeter comes first."}),
                    hints=["The fence goes round: add the four sides.",
                           "The area is length times width."],
                    solution=f"Perimeter ${length} + {width} + {length} + {width} = "
                             f"{2 * length + 2 * width}$ feet; area ${length} \\times {width} = "
                             f"{length * width}$ square feet.",
                    skill="perimeter and area (1.2, 1.4)")
