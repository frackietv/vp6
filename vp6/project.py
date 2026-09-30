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
        "user_controls": [],          # your own controls (UserControl classes)
        "color_scheme": "system",     # "system", "light", "dark" or "ide"
        "icon": [],                   # the program's icon; [] = the VP6 icon
        "groups": [                   # how the Project panel shows them
            {"group": "Forms", "items": ["Form1.py"]},
            {"group": "Modules", "items": ["Module1.py"]},
        ],
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

``forms`` and ``modules`` say which files are forms and modules (the runner
needs nothing else). ``icon`` is the program's icon: image files relative to
the project, sizes of one picture (a single string is one file); without any
(as in new projects) the program shows the VP6 icon, from the VP6
installation. ``groups`` organizes them in the Project panel,
independently of where the files are on disk: a list of entries, each a file
(its path relative to the project) or a group ``{"group": name, "items":
[entries]}``, so groups can hold files and other groups, and files can also
be at the top level. Without ``groups`` (older projects) there are two
groups, "Forms" and "Modules", holding the forms and the modules.
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

_FIELDS = ("name", "type", "startup", "forms", "modules", "user_controls", "color_scheme", "icon",
           "groups")
_COMMENTS = {
    "icon": "the program's icon: image files (sizes of it), or []",
    "type": '"exe" (GUI) or "console"',
    "startup": 'a form class name, or "Sub Main"',
    "color_scheme": '"system", "light", "dark" or "ide"; forms inherit it',
    "groups": "how the Project panel shows them (not where they are on disk)",
    "user_controls": "your own controls (UserControl classes), placed on forms",
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


# The VP6 icon, in several sizes (the package's images/ folder): the icon of every
# program without one of its own (new projects have none), used from the installation.
VP6_ICON_DIR = os.path.join(os.path.dirname(__file__), "images")
VP6_ICON_FILES = tuple(os.path.join(VP6_ICON_DIR, f"vp6icon-{n}x{n}.png")
                       for n in (32, 64, 128, 256))


class ProjectFileError(ValueError):
    pass


@dataclass
class Project:
    name: str = "Project1"
    type: str = "exe"
    startup: str = "Form1"
    forms: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    # Your own controls: files with a UserControl class, designed like forms
    user_controls: list[str] = field(default_factory=list)
    color_scheme: str = "system"  # system, light, dark or ide; forms inherit it
    # The program's icon: image files relative to the project (one picture in
    # several sizes; one file is enough). [] = the VP6 icon.
    icon: list[str] = field(default_factory=list)
    # The Project panel's tree (None: Forms and Modules groups); compared by tree()
    groups: list | None = field(default=None, compare=False)
    path: str = field(default="", compare=False)  # the .vp6p file

    def __eq__(self, other):
        if not isinstance(other, Project):
            return NotImplemented
        fields = ("name", "type", "startup", "forms", "modules", "user_controls", "color_scheme",
                  "icon")
        return all(getattr(self, f) == getattr(other, f) for f in fields) and \
            self.tree() == other.tree()

    @property
    def directory(self) -> str:
        return os.path.dirname(os.path.abspath(self.path)) if self.path else os.getcwd()

    def abspath(self, relative: str) -> str:
        return os.path.join(self.directory, relative)

    def files(self) -> list[str]:
        """Every form, user control and module (relative paths)."""
        return self.forms + self.user_controls + self.modules

    # -- the icon -------------------------------------------------------------------------------
    def icon_paths(self) -> list[str]:
        """The icon's files, as absolute paths."""
        return [self.abspath(relative) for relative in self.icon]

    # -- groups: how the Project panel shows the files ----------------------------------------
    # A group is found by its path: the names from the top, e.g. ("Forms", "Pages");
    # () is the project itself. An item is a file's relative path, or a group's path
    # as a tuple.

    def kind_of(self, relative: str) -> str | None:
        if relative in self.forms:
            return "form"
        if relative in self.user_controls:
            return "usercontrol"
        return "module" if relative in self.modules else None

    def tree(self) -> list:
        """The groups, with every form and module exactly once: files that
        are no longer in the project are left out, and files that aren't in
        any group are placed like new ones (see place_file)."""
        if self.groups is None:
            tree = [{"group": "Forms", "items": list(self.forms)},
                    {"group": "Modules", "items": list(self.modules)}]
            if self.user_controls:
                tree.insert(1, {"group": "User Controls", "items": list(self.user_controls)})
            return tree
        seen = set()

        def clean(entries) -> list:
            result = []
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict) and isinstance(entry.get("group"), str):
                    result.append({"group": entry["group"],
                                   "items": clean(entry.get("items", []))})
                elif isinstance(entry, str) and self.kind_of(entry) and entry not in seen:
                    seen.add(entry)
                    result.append(entry)
            return result

        tree = clean(self.groups)
        for relative in self.files():
            if relative not in seen:
                self._add_to(tree, relative, self._default_group(tree, relative))
        return tree

    def _normalize(self) -> list:
        self.groups = self.tree()
        return self.groups

    def _items(self, path, tree=None) -> list:
        """The item list of a group (``()`` is the top level)."""
        items = self.groups if tree is None else tree
        for name in tuple(path):
            group = next((e for e in items if isinstance(e, dict) and e["group"] == name), None)
            if group is None:
                raise ValueError(f"No group {'/'.join(path)!r}")
            items = group["items"]
        return items

    def group_paths(self) -> list[tuple]:
        """Every group's path, depth first."""
        paths = []

        def walk(items, prefix):
            for entry in items:
                if isinstance(entry, dict):
                    paths.append(prefix + (entry["group"],))
                    walk(entry["items"], prefix + (entry["group"],))

        walk(self.tree(), ())
        return paths

    def group_of(self, relative: str) -> tuple:
        """The path of the group holding a file (``()``: the top level)."""
        def find(items, prefix):
            for entry in items:
                if entry == relative:
                    return prefix
                if isinstance(entry, dict):
                    found = find(entry["items"], prefix + (entry["group"],))
                    if found is not None:
                        return found
            return None

        found = find(self.tree(), ())
        return () if found is None else found

    def _default_group(self, tree, relative) -> tuple:
        """Where a new file goes without a chosen group: the first group
        (depth first) holding a file of the same kind, or the top level."""
        kind = self.kind_of(relative)

        def find(items, prefix):
            for entry in items:
                if isinstance(entry, str) and entry != relative and self.kind_of(entry) == kind:
                    return prefix
            for entry in items:
                if isinstance(entry, dict):
                    found = find(entry["items"], prefix + (entry["group"],))
                    if found is not None:
                        return found
            return None

        # A group with a file of that kind anywhere in it; the top level's own
        # files only count when no group has one
        for entry in tree:
            if isinstance(entry, dict):
                found = find(entry["items"], (entry["group"],))
                if found is not None:
                    return found
        return ()

    def _add_to(self, tree, relative, group) -> None:
        self._items(group, tree).append(relative)

    def place_file(self, relative: str, group=None) -> None:
        """Put a file (already in forms or modules) in a group; None: where
        new files of its kind go (see _default_group)."""
        tree = self._normalize()
        self._remove_entry(tree, relative)
        target = self._default_group(tree, relative) if group is None else tuple(group)
        self._add_to(tree, relative, target)

    @staticmethod
    def _remove_entry(items, relative) -> bool:
        for index, entry in enumerate(items):
            if entry == relative:
                del items[index]
                return True
            if isinstance(entry, dict) and Project._remove_entry(entry["items"], relative):
                return True
        return False

    def remove_file(self, relative: str) -> None:
        """Take a file out of the project (not off the disk)."""
        for files in (self.forms, self.user_controls, self.modules):
            if relative in files:
                files.remove(relative)
        self._normalize()

    def rename_file(self, old: str, new: str) -> None:
        """A file renamed on disk keeps its place."""
        tree = self._normalize()
        self.forms = [new if f == old else f for f in self.forms]
        self.user_controls = [new if u == old else u for u in self.user_controls]
        self.modules = [new if m == old else m for m in self.modules]

        def rename(items):
            for index, entry in enumerate(items):
                if entry == old:
                    items[index] = new
                elif isinstance(entry, dict):
                    rename(entry["items"])

        rename(tree)

    @staticmethod
    def _check_name(items, name, ignore=None) -> str:
        name = str(name).strip()
        if not name:
            raise ValueError("A group needs a name")
        if any(isinstance(e, dict) and e["group"] == name and e is not ignore for e in items):
            raise ValueError(f"There is already a group {name!r} there")
        return name

    def add_group(self, parent, name: str) -> tuple:
        """A new, empty group in a group (``()``: at the top). Its path."""
        items = self._items(parent, self._normalize())
        name = self._check_name(items, name)
        items.append({"group": name, "items": []})
        return tuple(parent) + (name,)

    def _group(self, path, tree=None) -> tuple[list, dict]:
        """(the items it is in, the group) for a group's path, in ``tree`` (by
        default the groups, made complete first)."""
        path = tuple(path)
        if not path:
            raise ValueError("That is the project, not a group")
        siblings = self._items(path[:-1], self._normalize() if tree is None else tree)
        group = next((e for e in siblings if isinstance(e, dict) and e["group"] == path[-1]),
                     None)
        if group is None:
            raise ValueError(f"No group {'/'.join(path)!r}")
        return siblings, group

    def rename_group(self, path, name: str) -> tuple:
        siblings, group = self._group(path)
        group["group"] = self._check_name(siblings, name, ignore=group)
        return tuple(path)[:-1] + (group["group"],)

    def delete_group(self, path) -> None:
        """Remove a group; what it held moves to where the group was."""
        siblings, group = self._group(path)
        index = siblings.index(group)
        siblings[index:index + 1] = group["items"]

    def move(self, item, target) -> None:
        """Move a file (its relative path) or a group (its path, a tuple) into
        a group (``()``: the top level)."""
        target = tuple(target)
        tree = self._normalize()
        if isinstance(item, str):
            items = self._items(target, tree)
            self._remove_entry(tree, item)
            items.append(item)
            return
        item = tuple(item)
        if target[:len(item)] == item:
            raise ValueError("A group can't go into itself")
        siblings, group = self._group(item, tree)
        items = self._items(target, tree)
        if items is siblings:
            return
        self._check_name(items, group["group"])
        siblings.remove(group)
        items.append(group)

    # -- reading ----------------------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, encoding="utf-8") as f:
            data = parse(f.read())
        known = {k: data[k] for k in _FIELDS if k in data}
        if isinstance(known.get("icon"), str):  # one file
            known["icon"] = [known["icon"]] if known["icon"] else []
        return cls(**known, path=os.path.abspath(path))

    # -- writing ----------------------------------------------------------------------------
    def region(self) -> str:
        data = asdict(self)
        data["groups"] = self.tree()
        lines = [REGION_START, "PROJECT = {"]
        for key in _FIELDS:
            if key == "groups":  # a tree: one entry per line
                value = json.dumps(data[key], indent=4).replace("\n", "\n    ")
            else:
                value = json.dumps(data[key])
            line = f"    {json.dumps(key)}: {value},"
            if key in _COMMENTS:
                first, _, rest = line.partition("\n")
                line = f"{first:<40}# {_COMMENTS[key]}" + (f"\n{rest}" if rest else "")
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
