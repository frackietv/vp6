"""VP6 project files (``*.vp6p``).

A project file is an executable Python script that starts the program::

    #!/bin/sh
    "exec" "${VP6_PYTHON:-python3}" "$0" "$@"
    # VP6 project - run this file to start the program.
    ...
    # region VP6 Project - maintained by the VP6 IDE, do not edit
    PROJECT = {
        "name": "Project1",
        "type": "exe",                # "exe" (GUI) or "console"
        "startup": "Form1",           # a form class name, or "Sub Main"
        "forms": ["Form1.py"],
        "modules": ["Module1.py"],
        "color_scheme": "system",     # "system", "light", "dark" or "ide"
    }
    # endregion

    if __name__ == "__main__":
        ...run_project(__file__)

The first two lines are both shell and Python: ``/bin/sh`` runs the second
line, which re-executes the file with ``$VP6_PYTHON`` (default: the first
``python3`` on PATH); to Python it is just a string expression. So
``./Project1.vp6p``, ``python3 Project1.vp6p`` and
``VP6_PYTHON=.venv/bin/python ./Project1.vp6p`` all work.

The IDE reads ``PROJECT`` with ``ast`` (the file is never executed) and only
rewrites the region when saving, so code added elsewhere is kept.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field

SUB_MAIN = "Sub Main"
EXTENSION = ".vp6p"

REGION_START = "# region VP6 Project - maintained by the VP6 IDE, do not edit"
REGION_END = "# endregion"
_START_RE = re.compile(r"^# region VP6 Project\b.*$", re.M)
_END_RE = re.compile(r"^# endregion\b.*$", re.M)

_FIELDS = ("name", "type", "startup", "forms", "modules", "color_scheme")
_COMMENTS = {
    "type": '"exe" (GUI) or "console"',
    "startup": 'a form class name, or "Sub Main"',
    "color_scheme": '"system", "light", "dark" or "ide"; forms inherit it',
}

_TEMPLATE = '''#!/bin/sh
"exec" "${{VP6_PYTHON:-python3}}" "$0" "$@"
# VP6 project - run this file to start the program:  ./{filename}
# It uses the first python3 on PATH; set VP6_PYTHON to use another one,
# e.g. a virtual environment where VP6 is installed:
#     VP6_PYTHON=/path/to/venv/bin/python ./{filename}

{region}

if __name__ == "__main__":
    import sys

    try:
        from vp6.runner import run_project
    except ImportError:
        sys.exit(f"VP6 is not installed for {{sys.executable}}.\\n"
                 "Set VP6_PYTHON to a Python that has VP6 installed, or install VP6 "
                 "into this one.")
    sys.exit(run_project(__file__))
'''


class ProjectFileError(ValueError):
    pass


@dataclass
class Project:
    name: str = "Project1"
    type: str = "exe"
    startup: str = "Form1"
    forms: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    color_scheme: str = "system"  # system, light, dark or ide; forms inherit it
    path: str = field(default="", compare=False)  # the .vp6p file

    @property
    def directory(self) -> str:
        return os.path.dirname(os.path.abspath(self.path)) if self.path else os.getcwd()

    def abspath(self, relative: str) -> str:
        return os.path.join(self.directory, relative)

    # -- reading ----------------------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, encoding="utf-8") as f:
            data = parse(f.read())
        known = {k: data[k] for k in _FIELDS if k in data}
        return cls(**known, path=os.path.abspath(path))

    # -- writing ----------------------------------------------------------------------------
    def region(self) -> str:
        data = asdict(self)
        lines = [REGION_START, "PROJECT = {"]
        for key in _FIELDS:
            line = f"    {json.dumps(key)}: {json.dumps(data[key])},"
            if key in _COMMENTS:
                line = f"{line:<40}# {_COMMENTS[key]}"
            lines.append(line)
        lines += ["}", REGION_END]
        return "\n".join(lines)

    def save(self, path: str | None = None) -> None:
        """Write the project script (only the region if the file exists) and
        make it executable."""
        if path:
            self.path = os.path.abspath(path)
        text = None
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                text = _replace_region(f.read(), self.region())
        if text is None:
            text = _TEMPLATE.format(filename=os.path.basename(self.path), region=self.region())
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)
        make_executable(self.path)


def parse(text: str) -> dict:
    """The PROJECT dict of a project script, read without executing it."""
    start, end = _START_RE.search(text), _END_RE.search(text)
    source = text[start.end():end.start()] if start and end and end.start() > start.end() \
        else text
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise ProjectFileError(f"Not a valid VP6 project file: {exc}") from exc
    for node in module.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "PROJECT"):
            try:
                data = ast.literal_eval(node.value)
            except ValueError as exc:
                raise ProjectFileError("PROJECT must be a literal dict") from exc
            if not isinstance(data, dict):
                raise ProjectFileError("PROJECT must be a dict")
            return data
    raise ProjectFileError("Not a VP6 project file: no PROJECT = {...} found")


def _replace_region(text: str, region: str) -> str | None:
    start, end = _START_RE.search(text), _END_RE.search(text)
    if not (start and end) or end.start() < start.end():
        return None
    return text[:start.start()] + region + text[end.end():]


def make_executable(path: str) -> None:
    """Add execute permission for everyone who can read the file (like
    ``chmod +x`` under a typical umask). A no-op on Windows."""
    if sys.platform == "win32":
        return
    mode = os.stat(path).st_mode
    os.chmod(path, mode | ((mode & 0o444) >> 2))
