"""The project, and files without a designer, as targets of the Properties
window.

The Properties window edits whatever it is bound to through the interface
``FormDesigner`` offers: ``selected_objects()``, ``all_objects()``,
``object_name(obj)``, ``select_by_name(name)``, ``set_property(prop, value)``,
``base_dir`` and the ``selectionChanged`` / ``designChanged`` signals.
``ProjectTarget`` provides the same interface for the open project, so
selecting the project in the Project Explorer shows and edits its properties.
``FileTarget`` does the same for a module, or a form whose designer isn't
open: just its (Name). ``GroupTarget`` shows a Project panel group's (Name).
"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QObject, Signal

from .._props import P, PropSpec
from ..project import SUB_MAIN, Project

# Shared with the Project Properties dialog: (value, label)
TYPE_CHOICES = (("exe", "Standard EXE"), ("console", "Console Application"))
COLOR_SCHEME_CHOICES = (
    ("system", "System (follow the OS appearance)"),
    ("light", "Light"),
    ("dark", "Dark"),
    ("ide", "Follow the IDE (its light/dark setting)"),
)


class _ProjectObject:
    """What the Properties window sees as the selected object: the project's
    fields under VB-style property names."""

    TypeName = "Project"

    def __init__(self, target: "ProjectTarget"):
        self._target = target

    @property
    def _specs(self) -> dict[str, PropSpec]:
        return {spec.name: spec for spec in self._target.specs()}

    @property
    def Type(self) -> str:
        return self._target.project.type

    @property
    def StartupObject(self) -> str:
        return self._target.project.startup

    @property
    def ColorScheme(self) -> str:
        return self._target.project.color_scheme


class ProjectTarget(QObject):
    selectionChanged = Signal()
    designChanged = Signal()

    def __init__(self, get_project: Callable[[], Project | None],
                 get_form_names: Callable[[], list[str]], on_changed: Callable[[], None]):
        super().__init__()
        self._get_project = get_project
        self._get_form_names = get_form_names
        self._on_changed = on_changed  # save the project and update the IDE
        self._object = _ProjectObject(self)

    @property
    def project(self) -> Project:
        return self._get_project()

    @property
    def base_dir(self) -> str:
        return self.project.directory

    def specs(self) -> list[PropSpec]:
        startup = [(name, name) for name in self._get_form_names()] + [(SUB_MAIN, SUB_MAIN)]
        return [
            P("ColorScheme", "enum", "system", COLOR_SCHEME_CHOICES,
              description="Light or dark appearance of every form whose ColorScheme is "
                          "'0 - Project Default'."),
            P("StartupObject", "enum", "Form1", startup,
              description="The form shown when the program starts, or Sub Main to call "
                          "Main() in a module."),
            P("Type", "enum", "exe", TYPE_CHOICES,
              description="Standard EXE (windowed) or Console Application."),
        ]

    # -- the Properties window's interface --------------------------------------------
    def selected_objects(self) -> list:
        return [self._object]

    def all_objects(self) -> list[tuple[str, str]]:
        return [(self.project.name, "Project")]

    def object_name(self, obj) -> str:
        return self.project.name

    def select_by_name(self, name: str) -> None:
        pass  # there is only the project

    def set_property(self, prop: str, value) -> str | None:
        """Change a project property. Returns an error message or None."""
        project = self.project
        if prop == "Name":
            name = str(value).strip()
            if not name.isidentifier():
                return f"'{name}' is not a valid project name"
            project.name = name
        elif prop == "Type":
            project.type = value
        elif prop == "StartupObject":
            project.startup = value
        elif prop == "ColorScheme":
            project.color_scheme = value
        else:
            return f"Unknown project property '{prop}'"
        self._on_changed()
        self.designChanged.emit()
        return None


class _FileObject:
    """What the Properties window sees for a file: only the (Name) row."""

    _specs: dict[str, PropSpec] = {}

    def __init__(self, target: "FileTarget"):
        self._target = target

    @property
    def TypeName(self) -> str:
        return self._target.type_name


class FileTarget(QObject):
    """A module, or a form whose designer isn't open: shows its (Name).

    ``rename(document, new_name)`` does the renaming and returns an error
    message or None (modules rename their file, forms their class)."""

    selectionChanged = Signal()
    designChanged = Signal()

    def __init__(self, document, rename: Callable[[object, str], str | None]):
        super().__init__()
        self.document = document
        self._rename = rename
        self._object = _FileObject(self)

    @property
    def type_name(self) -> str:
        return "Form" if self.document.kind == "form" else "Module"

    @property
    def base_dir(self) -> str:
        return os.path.dirname(self.document.path)

    def selected_objects(self) -> list:
        return [self._object]

    def all_objects(self) -> list[tuple[str, str]]:
        return [(self.document.name, self.type_name)]

    def object_name(self, obj) -> str:
        return self.document.name

    def select_by_name(self, name: str) -> None:
        pass

    def set_property(self, prop: str, value) -> str | None:
        if prop != "Name":
            return f"Unknown property '{prop}'"
        error = self._rename(self.document, str(value).strip())
        if error is None:
            self.designChanged.emit()
        return error


class _GroupObject:
    """What the Properties window sees for a group: only the (Name) row."""

    TypeName = "Group"
    _specs: dict[str, PropSpec] = {}


class GroupTarget(QObject):
    """A group of the Project panel (``group``: its path, a tuple of names):
    shows its (Name). ``rename(group, new_name)`` renames it and returns an
    error message or None."""

    selectionChanged = Signal()
    designChanged = Signal()
    name_description = ("The group's name in the Project panel. Groups only organize "
                        "the panel: renaming one changes no file.")

    def __init__(self, rename: Callable[[tuple, str], str | None]):
        super().__init__()
        self.group: tuple = ()
        self._rename = rename
        self._object = _GroupObject()

    def set_group(self, group) -> None:
        """Show another group (the Properties window refreshes)."""
        group = tuple(group)
        if group != self.group:
            self.group = group
            self.selectionChanged.emit()

    @property
    def base_dir(self) -> str:
        return ""

    def selected_objects(self) -> list:
        return [self._object]

    def all_objects(self) -> list[tuple[str, str]]:
        return [(self.group[-1], "Group")] if self.group else []

    def object_name(self, obj) -> str:
        return self.group[-1] if self.group else ""

    def select_by_name(self, name: str) -> None:
        pass

    def set_property(self, prop: str, value) -> str | None:
        if prop != "Name":
            return f"Unknown property '{prop}'"
        error = self._rename(self.group, str(value))
        if error is None:
            self.designChanged.emit()
        return error
