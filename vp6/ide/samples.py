"""Sample projects (other than the Kitchen Sink, which has ``kitchensink.py``):
each is the files of a folder in ``templates/`` copied into the new project.

``SAMPLES`` maps a template's key (as in the New Project dialog's
``TEMPLATES``) to what it is made of. A sample's forms run on their own too
(``python Form1.py``).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..project import Project

TEMPLATES = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class Sample:
    folder: str  # in templates/
    forms: tuple[str, ...]
    startup: str  # a form class, or "Sub Main"
    description: str  # the project's Description
    modules: tuple[str, ...] = field(default=())


SAMPLES = {
    "projection": Sample(
        "projection", ("Form1.py",), "Form1",
        "A model turning in eight parallel projections (orthographic and oblique): a cube, a "
        "pyramid, a torus, a house, a few boxes or a downtown; drag an axis, the axes or the "
        "model"),
    "perspectives": Sample(
        "perspectives", ("Form1.py",), "Form1",
        "A model turning in 1-, 2- or 3-point linear perspective or 4-, 5- or 6-point "
        "curvilinear perspective (cylindrical, fisheye, spherical): a cube, a pyramid, a torus, "
        "a house, a few boxes or a downtown; drag a vanishing point, the scene or the model; "
        "vanishing points at infinity in any direction"),
}


def create(key: str, directory: str, name: str) -> Project:
    """Copy a sample's files into ``directory`` and return its project (not
    saved yet)."""
    sample = SAMPLES[key]
    for filename in sample.forms + sample.modules:
        shutil.copyfile(TEMPLATES / sample.folder / filename, os.path.join(directory, filename))
    return Project(name=name, type="exe", startup=sample.startup, forms=list(sample.forms),
                   modules=list(sample.modules), description=sample.description)
