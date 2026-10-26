"""vp6edu: courses for VP6, as data: subjects, learning paths of books, lessons.

* ``load_subjects()`` (``vp6edu.subjects``) reads the subjects vp6edu has
  (Mathematics, after OpenStax's textbooks) or those in other folders;
* ``vp6edu-check`` (``vp6edu.check``) validates them and their written lessons.

    from vp6edu import load_subjects
    lesson = load_subjects()["math"].lesson("math/prealgebra-2e/1.2")

The core is pure Python (no Qt). The lessons are adapted from OpenStax's
books, each one attributed: see ``Lesson.attribution``.
"""

__version__ = "0.1.0"

from .subjects import (SUBJECTS, Book, Chapter, LearningPath, Lesson, Licence,  # noqa: E402
                       Subject, SubjectError, load_subject, load_subjects)

__all__ = ["__version__", "SUBJECTS", "Book", "Chapter", "LearningPath", "Lesson",
           "Licence", "Subject", "SubjectError", "load_subject", "load_subjects"]
