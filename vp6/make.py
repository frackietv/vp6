"""Make a standalone executable of a VP6 project, like VB's File > Make
Project1.exe: ``vp6-make Calculator.vp6p`` (or ``python -m vp6.make``, or the
IDE's File > Make Executable...).

The program runs without Python, PySide6 or VP6 installed: PyInstaller
bundles them with it. It needs PyInstaller where the executable is made
(``pip install "vp6[make]"``, which also installs Pillow to turn the project's
PNG icon into the platform's icon format). PyInstaller makes executables for
the platform it runs on, so make the macOS app on macOS, the Windows .exe on
Windows and the Linux program on Linux (docs/api.md has a CI recipe for all
three).

What goes in:

* the project's files as they are (forms, modules, pictures, the project file
  itself...), in the same folders, except ``build``, ``dist`` (where the
  executable goes), ``__pycache__`` and hidden files and folders. The runner
  imports the forms and modules from there, as it does in the project's
  folder, so a form finds its pictures relative to its own file;
* everything the program's code imports (read from its .py files with
  ``ast``, as PyInstaller can't see into files it doesn't analyze), and VP6
  with PySide6;
* the project's icon as the executable's icon (else the VP6 icon).

What comes out, in the project's ``dist`` folder: ``Name.app`` on macOS (for
a windowed project), a ``Name`` folder with the ``Name`` (``Name.exe``)
program in it, or with ``onefile`` a single ``Name`` (``Name.exe``) file
(not for a windowed program on macOS: apps are folders).
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

from .project import VP6_ICON_FILES, Project

# Never in the executable: what making it writes, caches, and hidden files
EXCLUDED_FOLDERS = {"build", "dist", "__pycache__", "venv"}


class MakeError(Exception):
    """Making the executable failed (the message says why)."""


def project_files(project: Project) -> list[str]:
    """The project's files that go into the executable, relative to its
    folder (with /)."""
    top = project.directory
    files = []
    for folder, subfolders, names in os.walk(top):
        subfolders[:] = sorted(d for d in subfolders
                               if d not in EXCLUDED_FOLDERS and not d.startswith("."))
        for name in sorted(names):
            if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                continue
            files.append(os.path.relpath(os.path.join(folder, name), top).replace(os.sep, "/"))
    return files


def imported_modules(project: Project) -> list[str]:
    """The top-level modules the project's Python files import, except its own
    forms and modules (and files): what PyInstaller must bundle for them."""
    own = {os.path.splitext(os.path.basename(f))[0] for f in project_files(project)
           if f.endswith(".py")}
    names = set()
    for relative in project_files(project):
        if not relative.endswith(".py"):
            continue
        try:
            with open(project.abspath(relative), encoding="utf-8") as f:
                tree = ast.parse(f.read(), relative)
        except (OSError, SyntaxError, ValueError):
            continue  # (not ours to judge: the program will report it)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.add(node.module.split(".")[0])
    return sorted(names - own)


def launcher_source(project: Project) -> str:
    """The executable's entry point: run the bundled project, as its project
    file does."""
    filename = os.path.basename(project.path)
    return (f'"""Starts {project.name}, made with VP6 (vp6.make)."""\n\n'
            "import os\n"
            "import sys\n\n"
            "from vp6.runner import run_project\n\n"
            "# The bundled project: next to this script, or where PyInstaller unpacked it\n"
            'folder = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))\n'
            f"sys.exit(run_project(os.path.join(folder, {filename!r})))\n")


def icon_file(project: Project) -> str | None:
    """The picture for the executable's icon: the project's (its largest size,
    the last listed), else the VP6 icon. None without Pillow (PyInstaller
    needs it to convert a PNG to .icns or .ico)."""
    if importlib.util.find_spec("PIL") is None:
        return None
    paths = [p for p in project.icon_paths() if os.path.isfile(p)]
    return paths[-1] if paths else VP6_ICON_FILES[-1]


def can_be_one_file(project: Project, platform: str = sys.platform) -> bool:
    """A windowed program on macOS is an app, which is a folder."""
    return not (platform == "darwin" and project.type != "console")


def output_path(project: Project, dist: str, onefile: bool, platform: str = sys.platform) -> str:
    """Where the executable will be."""
    name = project.name
    exe = name + (".exe" if platform == "win32" else "")
    if platform == "darwin" and project.type != "console":
        return os.path.join(dist, name + ".app")
    if onefile:
        return os.path.join(dist, exe)
    return os.path.join(dist, name, exe)


def pyinstaller_command(project: Project, launcher: str, dist: str, work: str,
                        onefile: bool = False, platform: str = sys.platform) -> list[str]:
    """The PyInstaller command line that makes the executable."""
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
               "--name", project.name, "--distpath", dist, "--workpath", work,
               "--specpath", work]
    command.append("--console" if project.type == "console" else "--windowed")
    if onefile and can_be_one_file(project, platform):
        command.append("--onefile")
    icon = icon_file(project)
    if icon:
        command += ["--icon", icon]
    # VP6 itself: found where it is (an editable install's import hook is
    # invisible to PyInstaller), with its icon files (a program's default icon)
    package = os.path.dirname(os.path.abspath(__file__))
    command += ["--paths", os.path.dirname(package),
                "--add-data", f"{os.path.join(package, 'images')}{os.pathsep}vp6/images"]
    for module in imported_modules(project) + ["vp6"]:
        command += ["--hidden-import", module]
    for relative in project_files(project):
        destination = os.path.dirname(relative) or "."
        command += ["--add-data", f"{project.abspath(relative)}{os.pathsep}{destination}"]
    command.append(launcher)
    return command


def make(project_path: str, dist: str | None = None, onefile: bool = False,
         log=print) -> str:
    """Make the executable of a project; returns its path. ``log`` gets
    PyInstaller's output, line by line. Raises MakeError."""
    if importlib.util.find_spec("PyInstaller") is None:
        raise MakeError("Making an executable needs PyInstaller: "
                        'pip install "vp6[make]" (or: pip install pyinstaller pillow)')
    project = Project.load(project_path)
    dist = os.path.abspath(dist or os.path.join(project.directory, "dist"))
    work = tempfile.mkdtemp(prefix="vp6-make-")
    try:
        launcher = os.path.join(work, f"{project.name}_launcher.py")
        with open(launcher, "w", encoding="utf-8") as f:
            f.write(launcher_source(project))
        command = pyinstaller_command(project, launcher, dist, work, onefile)
        log(f"Making {project.name} with PyInstaller (this takes a minute or so)...")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, cwd=work)
        for line in process.stdout:
            log(line.rstrip("\n"))
        if process.wait() != 0:
            raise MakeError(f"PyInstaller failed (exit code {process.returncode}): see its "
                            "messages above")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    path = output_path(project, dist, onefile and can_be_one_file(project))
    if not os.path.exists(path):
        raise MakeError(f"PyInstaller finished, but {path} isn't there")
    log(f"Made {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vp6-make", description="Make a standalone executable of a VP6 project "
        "(for the platform this runs on).")
    parser.add_argument("project", help="the project file (Name.vp6p)")
    parser.add_argument("--onefile", action="store_true",
                        help="one executable file instead of a folder (not for a windowed "
                        "program on macOS, which is an app)")
    parser.add_argument("--dist", help="where to put it (default: the project's dist folder)")
    args = parser.parse_args(argv)
    try:
        make(args.project, args.dist, args.onefile)
    except MakeError as exc:
        print(f"vp6-make: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
