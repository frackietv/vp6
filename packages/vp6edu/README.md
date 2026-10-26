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

## Licence

vp6edu's code is under the MIT License. OpenStax publishes the books under
CC BY-NC-SA 4.0, so the lessons adapted from them are under the same licence,
each attributed (see `LICENSE`). Lessons are our own adaptations, never
copies of the books' pages.
