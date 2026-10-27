# vp6edu

Courses for [VP6](https://pypi.org/project/vp6/), as data: **subjects**
(Mathematics for now), each with **learning paths** of books, each book with
its **chapters** and **lessons**. A lesson is a folder with its text
(`lesson.md`, Markdown with maths), its exercises (`exercises.py`) and a VP6
project to try things in (`lab/`). Mathematics follows OpenStax's textbooks,
section by section: Prealgebra 2e → Elementary Algebra 2e → Intermediate
Algebra 2e → Algebra and Trigonometry 2e → Precalculus 2e → Calculus Volumes
1, 2 and 3, with Introductory Statistics 2e branching from Intermediate
Algebra 2e. The whole outline is here; lessons are *planned* until written.

```python
from vp6edu import load_subjects
math = load_subjects()["math"]
lesson = math.lesson("math/prealgebra-2e/1.2")
lesson.title, lesson.link, lesson.status          # "Add Whole Numbers", ...
[p.id for p in lesson.prerequisites]              # ["math/prealgebra-2e/1.1"]
lesson.attribution                                # the line its lesson.md carries
```

```bash
vp6edu-check                          # validate the subjects and the written lessons
vp6edu-check --subjects DIR           # ...of another folder of subjects
vp6edu-check --attribution math/prealgebra-2e/1.2
```

## The data

`vp6edu/subjects/<subject>/subject.json`:

```json
{"title": "Mathematics", "description": "...",
 "books": ["prealgebra-2e", "elementary-algebra-2e", "..."],
 "paths": [{"id": "main", "title": "Prealgebra to Calculus",
            "nodes": ["prealgebra-2e", "..."],
            "edges": [["prealgebra-2e", "elementary-algebra-2e"], ["..."]]}]}
```

`vp6edu/subjects/<subject>/<book>/book.json` (a book's id is its openstax.org
name):

```json
{"title": "Prealgebra 2e", "publisher": "OpenStax", "authors": ["..."],
 "link": "https://openstax.org/details/books/prealgebra-2e",
 "licence": {"name": "CC BY-NC-SA 4.0", "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"},
 "chapters": [{"number": 1, "title": "Whole Numbers", "sections": [
   {"number": "1.1", "title": "Introduction to Whole Numbers",
    "page": "1-1-introduction-to-whole-numbers"}]}]}
```

A section may also have:

* `"status": "written"` once its folder, `<book>/<chapter>/<section>/`, has
  `lesson.md` (starting with a `#` heading and carrying the attribution line),
  `exercises.py` and `lab/` (otherwise it's `"planned"`);
* `"shared": "<book>/<section>"`: the same section in an earlier book (the
  same OpenStax page), whose lesson it is; it has no folder of its own;
* `"requires": ["<book>/<section>", ...]`: prerequisites of its own, besides
  the section before it on its path.

A lesson's id is `<subject>/<book>/<section>`.

## Exercises and checking answers

A lesson's `exercises.py` has functions that make exercises from a seeded
`random.Random`, so each try can have new numbers; `vp6edu.answers` checks
what the student types:

```python
from fractions import Fraction
from vp6edu.answers import Exercise, Number, make

def add_fractions(rng):
    b = rng.randint(3, 9)
    a = rng.randint(1, b - 2)
    return Exercise(f"Add $\\frac{{{a}}}{{{b}}} + \\frac{{1}}{{{b}}}$.",
                    Number(Fraction(a + 1, b), form="simplest"),
                    hints=["The denominators are the same.", "Add the numerators."],
                    solution="Add the numerators and keep the denominator.")

exercise = make(add_fractions, seed=7)   # the same seed, the same numbers
result = exercise.check("6/8")           # Result(status, message, mistake)
result.status, result.message            # "not yet", "Right, but simplify it: ..."
exercise.hint()                          # the hints, one at a time
```

Typed maths is read leniently: `2x`, `x^2`, `x²`, `3(x+1)`, `sqrt(x)`, `√x`,
`π`, `½`, `2 1/3`, `25%`, `1,000`, `×`, `÷`, `−`, `|x|`. Every check returns
`right`, `not yet` or `unreadable`, with a message, and names the known
mistake it found (`sign`, `reciprocal`, `unsimplified`, `form`, `rounding`,
`approximate`, `units`, `swapped`, `endpoint`, `flipped`...). A lesson adds
its own with `mistakes={"7": "That's 3 + 4: multiply instead."}`.

| Kind | Right when | Asks for |
| --- | --- | --- |
| `Choice("B", options)` | the option (or options, given a list) chosen by letter, index or text | |
| `Number(value)` | the same number, exactly (fractions) or within `tolerance`, or rounded to `places` | `form`: integer, fraction, simplest, mixed, decimal, percent, scientific, simplified, any; `units` (with `convert`) |
| `Expression("2(x+3)")` | it equals the answer at random points | `form`: simplified, expanded, standard, factored |
| `Equation("y = 2x + 1")` | it says the same (a multiple, or the same solutions) | `form`: slope-intercept, standard; `solved_for` |
| `Solutions([2, -3])` | the same set of solutions (`NO_SOLUTION`, `ALL_REAL`) | |
| `Inequality("x > 3")` | the same set, in inequality or interval notation, or a number line's `Interval`s | `form`: interval, inequality |
| `Pair((2, 3))` | the same ordered pair or tuple | `names` for `x = 2, y = 3` |
| `Point(2, 3)`, `Line("y = 2x + 1")` | the point, or two points on the line, placed on a graph, or typed | `tolerance` |

`generators(module)` lists a module's makers (its public functions of one
argument), `load_exercises(path)` loads an `exercises.py`, and
`verify(maker)` checks that over many seeds each exercise's own answer
(`answer.text`) checks right.

## Licence

vp6edu's code is under the MIT License. OpenStax publishes the books under
CC BY-NC-SA 4.0, so the lessons adapted from them are under the same licence,
each attributed (see `LICENSE`). Lessons are our own adaptations, never
copies of the books' pages.
