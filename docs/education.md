# Writing Lessons

<!-- keywords: writing lessons, lesson.md, exercises.py, lab, vp6edu-check, attribution, Be Prepared, Try It, answer kinds, authoring -->

This is the guide to writing a lesson for **vp6edu**, VP6's courses: its text
with maths, its exercises, its lab project, its attribution, and the checks
it must pass. The model to copy is chapter 1 of *Prealgebra 2e*, Whole
Numbers, written in full: five sections, the chapter's review and its
practice test, in `packages/vp6edu/vp6edu/subjects/math/prealgebra-2e/1/`.
How students use lessons is in the IDE's guide ([Lessons](ide.md#lessons)).

## Where a Lesson Lives

A subject (`subjects/math/`) has a `subject.json` (its books and learning
paths) and a folder per book with a `book.json`: the book's chapters and
their sections, each section a lesson. A lesson is *planned* until it's
written; writing one means making its folder and marking it written:

```json
{"number": "1.2", "title": "Add Whole Numbers", "page": "1-2-add-whole-numbers",
 "status": "written"}
```

The folder is `<book>/<chapter>/<section>/`, e.g. `prealgebra-2e/1/1.2/`:

| File | What it is |
|---|---|
| `lesson.md` | the lesson's text, in Markdown with maths |
| `exercises.py` | the makers of its exercises |
| `lab/` | its lab: a VP6 project the student gets a copy of |

A chapter ends with two more lessons of their own kinds, after its sections:
its **review** and its **practice test**, numbered `<chapter>-review` and
`<chapter>-test`, linked to the book's own pages:

```json
{"number": "1-review", "title": "Review Exercises", "page": "1-review-exercises",
 "kind": "review", "status": "written"},
{"number": "1-test", "title": "Practice Test", "page": "1-practice-test",
 "kind": "test", "status": "written"}
```

A section that an earlier book already has (the same OpenStax page) is
`shared` and has no folder of its own: it's the lesson written there.

## The Lesson's Text: `lesson.md`

A section's lesson has these parts, in this order:

1. **The heading:** `# 1.2 Add Whole Numbers`.
2. **`## Learning Objectives`:** a list of what the student will be able to
   do. The Education tab shows it under the list of lessons.
3. **`## Be Prepared`:** two or three quick questions (Try Its) on what the
   lesson needs, each pointing back to the lesson that teaches it with a
   link of the form `[1.1 Introduction to Whole Numbers](lesson:math/prealgebra-2e/1.1)`.
   A click on such a link opens that lesson. The first lesson of a path says
   it needs nothing more than counting.
4. **The explanation,** a `##` heading per objective: the idea in plain
   words, a **worked example** (`**Example 2.**` and its `*Solution.*`), and
   a **Try It** for the student to do at once.
5. **`## Key Concepts`:** the lesson in a few lines, then `## Key Terms`
   (optional).
6. **`## Lab`:** what to do with the lab: run it, what to look at, then two
   or three changes to make to its code. This section goes on the Lab tab,
   not the Lesson tab.
7. **The attribution,** after a `---` rule (see below).

A review goes through the chapter a section at a time (a link and two or
three Try Its for each), then problems that mix them. A test is a list of
Try Its, each naming its section, and links back to the sections and the
review.

### A Try It

A Try It is the question in the text, followed by a fenced block of
language `answer` holding its answer, written as Python with vp6edu's
answer kinds (below). The Lesson tab puts an answer field with a Check
button where the block is:

````markdown
**Try it.** Add $3{,}658 + 1{,}479$.

```answer
Number(5137)
```
````

### Markdown and Maths

The text is Markdown: headings, lists, tables, emphasis, links, code. Maths
goes between dollars, `$…$` in a line and `$$…$$` on a line of its own,
written in TeX and laid out as TeX lays it out: `$\frac{3}{4}$`,
`$a \times b$`, `$\sqrt{2}$`, `$x^2$`. A few habits of the pilot:

* Write a number of thousands as `$3{,}658$`: the braces keep TeX from
  putting a space after the comma.
* An amount of money is written with an escaped dollar, `\$18`: an
  unescaped `$` starts a formula.
* Every formula must lay out: `vp6edu-check` lays each one out and reports
  the ones that don't (an unknown command, a missing brace).

## The Exercises: `exercises.py`

Each public function of one argument is a **maker**: given a seeded
`random.Random`, it returns an `Exercise` with new numbers. The Exercises
tab goes through the makers in the order they're written; New Numbers calls
the same maker with another seed. A section has **10 to 20 makers** across
its skills, word problems included.

```python
from vp6edu.answers import Exercise, Number


def add_three_digit_numbers(rng):
    a, b = rng.randint(100, 999), rng.randint(100, 999)
    return Exercise(f"Add: ${a} + {b}$", Number(a + b),
                    hints=["Line up the places and add each column from the ones.",
                           "Carry a ten to the next column when a column's sum is 10 or more."],
                    solution=f"${a} + {b} = {a + b}$",
                    skill="adding with regrouping")
```

* `Exercise(prompt, answer, hints, solution, skill, graph)`: the prompt and
  the solution are Markdown with maths; the hints are given one at a time;
  `skill` names what it practises (by default the maker's name); `graph`
  places the answer on a Graph (its properties, e.g. `{"XMin": -5}`).
* Helpers start with `_` (`_tex`, `_name`), or they would be taken for
  makers.
* Every number comes from `rng`, so the same seed gives the same exercise.
* A maker must always finish: draw numbers that work (a digit from
  `rng.randint(a % 10 + 1, 9)`) rather than drawing again until they do.
* Round half up as the lessons teach (`(n + 50) // 100 * 100`), not with
  Python's `round`, which rounds halves to even.
* A review or a test may use the sections' makers: load them with
  `load_exercises(Path(__file__).parent.parent / "1.1" / "exercises.py")` and
  wrap the ones it wants in makers of its own.

### The Answer Kinds

| Kind | For | Example |
|---|---|---|
| `Number` | a number: exact, within a `tolerance`, rounded to `places`, in a `form`, with `units` | `Number(5137)`, `Number(Fraction(3, 4), form="simplest")` |
| `Choice` | one option, or every one that's right (several or none) | `Choice("B", ["1", "0", "1/2", "10"])`, `Choice(["A", "C"], [...])` |
| `Expression` | an expression, equivalent, maybe in a form | `Expression("2x + 6", form="expanded")` |
| `Equation` | an equation, maybe solved for a letter | `Equation("y = 2x + 1")` |
| `Solutions` | an equation's solutions, as a set | `Solutions([2, -3])` |
| `Inequality` | an inequality or interval | `Inequality("-2 < x <= 3")` |
| `Pair` | an ordered pair or tuple | `Pair((41, 8), names=("quotient", "remainder"))` |
| `Point`, `Line` | a point or a line, placed on a graph | `Point(3, -2)`, `Line("y = 2x + 1")` |

`mistakes` gives feedback for known wrong answers, as the student would
type them:

```python
Number(a - b, mistakes={str(b - a): "Less than turns the order round."})
```

A multiple choice is answered with buttons, not typed: the Lesson window
shows a `Choice`'s options under the question, lettered `(A)`, `(B)`…
Don't list them in the prompt as well.

* **One answer** (a, b, c or d): `Choice("B", options)`, shown as **radio
  buttons**.
* **Every one that's right** (a, b, c, a and b, a and c, b and c, all of
  them, none of them): `Choice(["A", "C"], options)`, shown as **check
  boxes**; `Choice([], options)` when none is right. Don't write the
  combinations as options of their own.
* Options are plain text: the buttons don't lay out maths, so a `$15$`
  shows as `15`. Keep `\frac` and other TeX out of them (write `1/2`).
* A `Choice` needs its options (`vp6edu-check` warns of one without them).

## The Lab Project: `lab/`

The lab is a small VP6 project that shows the lesson's idea and invites
changes: place value with draggable digits, column addition step by step, a
number line, arrays of squares, counters shared into groups, an arithmetic
game, a calculator. Opening the lesson copies `lab/` into the student's
lesson folder and makes a project of it: its `.py` files with a designer
region are its forms (`Form1` first, starting the program), the others its
modules. A `.vp6p` of its own in `lab/` gives the forms, modules and startup
instead.

* Make the forms in VP6's designer, so the designer region is the one it
  writes (`vp6edu-check --labs` runs them; the region must stay readable).
* Name things for what they are and comment the ideas: the student reads
  this code, and the Lab text names the functions to change.
* Draw in a picture's `Paint` event from the program's state, and call
  `Refresh()` when the state changes, so the picture follows a resize and
  the light and dark schemes. A picture of "paper" sets its own
  `BackColor`, so its dark ink stays readable in dark mode.
* The lab must start without the network, without files of the student's,
  and without errors: `vp6edu-check --labs` loads each form, shows it
  offscreen, lets its timers run and unloads it, and any run-time error is a
  problem.

## The Attribution

The lessons are adapted from OpenStax's books, licensed CC BY-NC-SA 4.0, so
every lesson ends with the line naming its section, book, authors,
publisher, link and licence, after a `---` rule. `vp6edu-check` prints it:

```text
vp6edu-check --attribution math/prealgebra-2e/1.2
```

"Adapted" means in our own words: new explanations and new numbers, the
book's order and objectives kept. The lessons are under the same licence.

## Checking: `vp6edu-check`

```text
vp6edu-check                 # the subjects and every written lesson
vp6edu-check --labs          # and run every lesson's lab (needs VP6)
vp6edu-check --seeds 300     # try each exercise maker with more seeds
vp6edu-check --attribution ID
```

It checks the outline (paths, numbering, page names, shared and required
lessons, prerequisites without cycles) and every written lesson:

* `lesson.md`: its heading and attribution; every formula lays out; every
  Try It's answer can be read, and its own answer checks right; every
  `lesson:` link leads to a lesson; a section has Learning Objectives, Be
  Prepared and Key Concepts (warnings); a `Choice` has its options
  (a warning).
* `exercises.py`: it loads; a section has 10 to 20 makers (a warning
  otherwise); over 50 seeds each maker makes an exercise whose prompt has
  something in it, whose formulas (prompt, hints, solution) lay out, and
  whose answer's own text checks right.
* `lab/`: it has files; with `--labs`, each form loads, shows and unloads
  without an error.

VP6's tests run `vp6edu-check --labs` over every written lesson, so a lesson
that breaks one of these breaks the build. Run it before you commit.
