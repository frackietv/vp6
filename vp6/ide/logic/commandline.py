"""The IDE's command line: ``vp6 [--help] [--no-splash] [PROJECT.vp6p]``."""

from __future__ import annotations

import argparse
import os


def argument_parser() -> argparse.ArgumentParser:
    from vp6 import __version__

    parser = argparse.ArgumentParser(
        prog="vp6", description=f"VP6 {__version__}: a VB6 style IDE for Python.",
        epilog="environment:\n"
               "  VP6_NO_OUTPUT_CAPTURE  show the IDE's own messages in the terminal, not in "
               "its Output window\n"
               "  VP6_SETTINGS_DIR       keep the IDE's settings in an INI file in this folder\n\n"
               "Other commands: vp6-run PROJECT.vp6p (run a project), vp6-make PROJECT.vp6p "
               "(build a wheel; --exe: an executable); both take --help.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", metavar="PROJECT.vp6p", nargs="?",
                        help="a project file to open")
    parser.add_argument("--no-splash", action="store_true",
                        help="start without the splash screen")
    return parser


def parse_arguments(argv: list[str]) -> tuple[str | None, bool]:
    """(the project to open or None, whether to show the splash screen) from
    the command line: ``vp6 [--help] [--no-splash] [Project.vp6p]`` (--help
    prints the help and exits). Arguments it doesn't know are left to Qt."""
    args, _ = argument_parser().parse_known_args(argv[1:])
    project = args.project if args.project and os.path.exists(args.project) else None
    return project, not args.no_splash
