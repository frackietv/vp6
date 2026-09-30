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

import argparse
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


HELP_OPTION = "--help"


def program_help(project: Project, prog: str) -> str:
    """What ``--help`` shows for a VP6 program: its name, version and
    description, its usage, and the arguments it lists in the project's
    ``arguments_help``."""
    major, minor, revision = project.version_numbers()
    title = f"{project.product_name or project.name} {major}.{minor}.{revision}"
    lines = [f"{title} - {project.description}" if project.description else title, "",
             f"usage: {prog} [{HELP_OPTION}] [ARGUMENTS...]", ""]
    if project.arguments_help.strip():
        lines += ["arguments:"] + ["  " + line for line in
                                   project.arguments_help.strip("\n").splitlines()] + [""]
    else:
        lines += ["The program reads its arguments with Command() (sys.argv[1:]).", ""]
    lines += ["options:", f"  {HELP_OPTION:<10}show this help and exit", ""]
    if not getattr(sys, "frozen", False):  # (the project file, not a made executable)
        lines += ["environment:",
                  "  VP6_PYTHON  the Python that runs the project file (default: python3)", ""]
    from . import __version__

    lines.append(f"Made with VP6 {__version__}.")
    return "\n".join(lines)


def show_help(text: str) -> None:
    """Print the help; a windowed program made into an executable on Windows
    has no console (no stdout), so there it is a message box."""
    if sys.stdout is not None:
        print(text)
        return
    from .dialogs import MsgBox

    MsgBox(text, 64, "Help")  # vpInformation


def run_project(path: str) -> int:
    project = Project.load(path)
    if HELP_OPTION in sys.argv[1:]:  # (before anything starts)
        show_help(program_help(project, os.path.basename(sys.argv[0]) or project.name))
        return 0
    sys.path[:0] = import_folders(project)
    os.chdir(project.directory)
    from . import appearance
    from .app import App

    App._set_project(project)
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


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vp6-run", description="Run a VP6 project (as running its project file does).",
        epilog="The arguments after the project are the program's own (Command(), "
               "sys.argv[1:]); PROJECT.vp6p --help shows the program's help.\n\n"
               "environment:\n"
               "  VP6_NO_ERROR_DIALOG  report run-time errors on stderr only, without the "
               "Run-time error box",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", metavar="PROJECT.vp6p", help="the project file")
    parser.add_argument("arguments", metavar="ARGUMENTS", nargs=argparse.REMAINDER,
                        help="the program's command line arguments")
    return parser


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    args = argument_parser().parse_args(argv)
    # The program's arguments in sys.argv[1:] (Command()), as when the project file runs itself
    sys.argv = [args.project] + args.arguments
    sys.exit(run_project(args.project))


if __name__ == "__main__":
    main()
