"""Run a VP6 project: ``./Project1.vp6p`` (the project file is a launcher
script that calls ``run_project``) or ``python -m vp6.run Project1.vp6p``.

The startup object is either a form (shown, then the event loop runs until
all forms are closed) or ``Sub Main`` - a ``Main()`` function in one of the
project's modules. After Main returns, the event loop keeps running while
any form is still open, like VB6.
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys

from .project import SUB_MAIN, Project


def _import_file(project: Project, relative: str):
    name = os.path.splitext(os.path.basename(relative))[0]
    return importlib.import_module(name)


def find_form_class(project: Project, class_name: str):
    from .form import Form

    for relative in project.forms:
        module = _import_file(project, relative)
        cls = getattr(module, class_name, None)
        if inspect.isclass(cls) and issubclass(cls, Form):
            return cls
    raise SystemExit(f"Startup form '{class_name}' not found in project")


def find_main(project: Project):
    for relative in project.modules + project.forms:
        module = _import_file(project, relative)
        main = getattr(module, "Main", None)
        if callable(main):
            return main
    raise SystemExit("Startup is 'Sub Main' but no module defines Main()")


def run_project(path: str) -> int:
    project = Project.load(path)
    sys.path.insert(0, project.directory)
    os.chdir(project.directory)
    from . import appearance
    from .app import App

    App.Title = project.name
    appearance.project_scheme = appearance.scheme_from_name(project.color_scheme)
    if project.startup == SUB_MAIN:
        result = find_main(project)()
        if project.type == "console":
            return result if isinstance(result, int) else 0
        from .app import run_event_loop

        return run_event_loop()
    from .form import run

    return run(find_form_class(project, project.startup))


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("usage: python -m vp6.run PROJECT.vp6p")
    sys.exit(run_project(argv[0]))


if __name__ == "__main__":
    main()
