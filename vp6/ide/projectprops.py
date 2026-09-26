"""The project as a target of the Properties window.

The Properties window edits whatever it is bound to through the interface
``FormDesigner`` offers: ``selected_objects()``, ``all_objects()``,
``object_name(obj)``, ``select_by_name(name)``, ``set_property(prop, value)``,
``base_dir`` and the ``selectionChanged`` / ``designChanged`` signals.
``ProjectTarget`` provides the same interface for the open project, so
selecting the project in the Project Explorer shows and edits its properties.
"""

from __future__ import annotations

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
