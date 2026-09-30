"""Run a VP6 project: ``./Project1.vp6p`` (the project file is a launcher
script that calls ``run_project``) or ``python -m vp6.runner Project1.vp6p``.

(Not named ``run``: importing a ``vp6.run`` submodule would replace the public
``vp6.run()`` function on the package, breaking ``run(Form1)`` in programs.)

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


def import_folders(project: Project) -> list[str]:
    """Where the project's files are imported from: its folder, then every
    folder (subfolders too) holding a form or module. Files are imported by
    their name (``from Module1 import *``) wherever they are, which is why the
    IDE keeps the file names of forms and modules unique in a project."""
    folders = [project.directory]
    for relative in project.files():
        folder = os.path.dirname(project.abspath(relative))
        if folder not in folders:
            folders.append(folder)
    return folders


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
    sys.path[:0] = import_folders(project)
    os.chdir(project.directory)
    from . import appearance
    from .app import App

    App.Title = project.name
    appearance.project_scheme = appearance.scheme_from_name(project.color_scheme)
    if project.icon and project.type != "console":  # (a console program has no windows)
        from .app import set_program_icon

        set_program_icon(project.icon_paths())  # else the VP6 icon
    if project.startup == SUB_MAIN:
        try:
            result = find_main(project)()
        except KeyboardInterrupt:
            # Ctrl+C before any window exists (e.g. at a console input()):
            # end quietly with the conventional exit code instead of a traceback
            return 130
        if project.type == "console":
            return result if isinstance(result, int) else 0
        from .app import run_event_loop

        return run_event_loop()
    from .form import run

    return run(find_form_class(project, project.startup))


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("usage: python -m vp6.runner PROJECT.vp6p")
    sys.exit(run_project(argv[0]))


if __name__ == "__main__":
    main()
