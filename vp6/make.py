"""Package a VP6 project: a wheel (``vp6-make Calculator.vp6p``, or the IDE's
Project > Build Wheel) or a standalone executable, like VB's File > Make
Project1.exe (``vp6-make --exe Calculator.vp6p``, or the IDE's File > Make
Executable...). ``python -m vp6.make`` is ``vp6-make``.

**A wheel** (``make_wheel``) is a Python package of the program, to install
with pip where Python is: ``pip install Calculator-1.0.0-py3-none-any.whl``,
then run it with its command, ``Calculator`` (or ``python -m calculator``).
It holds the project's files (the ones an executable would) in a package
named after the project in lowercase, with a ``__main__`` that runs the
project file; the command is a GUI script for a windowed project (no console
window on Windows), a console script for a console one. It requires VP6 (this
version or later) and the installed distributions of what the code imports
(not the standard library's modules). Its version is the project's Version,
its summary the Description, its author the CompanyName. A wheel is written
by VP6 itself: nothing more needs to be installed.

**An executable**:

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
import base64
import hashlib
import importlib.metadata
import importlib.util
import os
import shutil
import site
import subprocess
import sys
import tempfile
import zipfile

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


def vp6_search_path(site_folders: list[str] | None = None) -> str | None:
    """The folder PyInstaller must search to find VP6, or None when it finds
    it anyway: a normal install is in site-packages, which PyInstaller
    searches (and mustn't be given); an editable one (pip install -e) is
    imported through a hook PyInstaller can't see, from the source folder."""
    folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if site_folders is None:
        site_folders = site.getsitepackages() + [site.getusersitepackages()]
    installed = {os.path.realpath(p) for p in site_folders if p}
    return None if os.path.realpath(folder) in installed else folder


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
    # VP6 itself, with its icon files (a program's default icon)
    package = os.path.dirname(os.path.abspath(__file__))
    folder = vp6_search_path()
    if folder is not None:
        command += ["--paths", folder]
    command += ["--add-data", f"{os.path.join(package, 'images')}{os.pathsep}vp6/images"]
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


# --- wheels -------------------------------------------------------------------------------

def wheel_package(project: Project) -> str:
    """The package the wheel installs the project's files in: its name in lowercase."""
    return project.name.lower()


def wheel_name(project: Project) -> str:
    """The wheel's file name: Name-major.minor.revision-py3-none-any.whl."""
    return f"{project.name}-{wheel_version(project)}-py3-none-any.whl"


def wheel_version(project: Project) -> str:
    return ".".join(str(n) for n in project.version_numbers())


def wheel_requirements(project: Project, log=print) -> list[str]:
    """What the wheel requires: VP6 (this version or later) and the installed
    distributions of the modules the project's code imports (not the
    standard library's, nor PySide6, which VP6 requires)."""
    from . import __version__

    requirements = [f"vp6>={__version__}"]
    distributions = importlib.metadata.packages_distributions()
    for module in imported_modules(project):
        if module in sys.stdlib_module_names or module in ("vp6", "PySide6", "shiboken6"):
            continue
        names = distributions.get(module)
        if not names:
            log(f"Note: '{module}' (imported by the project) isn't an installed package: "
                "the wheel doesn't require it")
            continue
        for name in names:
            if name.lower() not in {r.split(">")[0].lower() for r in requirements}:
                requirements.append(name)
    return requirements


def _wheel_launcher(project: Project) -> str:
    filename = os.path.basename(project.path)
    return (f'"""Runs {project.name} (a VP6 program): its command, or python -m '
            f'{wheel_package(project)}."""\n\n'
            "import os\n"
            "import sys\n\n\n"
            "def main():\n"
            "    from vp6.runner import run_project\n\n"
            "    folder = os.path.dirname(os.path.abspath(__file__))\n"
            f"    return run_project(os.path.join(folder, {filename!r}))\n\n\n"
            'if __name__ == "__main__":\n'
            "    sys.exit(main())\n")


def _metadata(project: Project, requirements: list[str]) -> str:
    lines = ["Metadata-Version: 2.1", f"Name: {project.name}",
             f"Version: {wheel_version(project)}",
             f"Summary: {project.description or project.product_name or project.name}"]
    if project.company_name:
        lines.append(f"Author: {project.company_name}")
    lines.append("Requires-Python: >=3.10")
    lines += [f"Requires-Dist: {requirement}" for requirement in requirements]
    return "\n".join(lines) + "\n"


def _record_line(path: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{path},sha256={digest},{len(data)}"


def make_wheel(project_path: str, dist: str | None = None, log=print) -> str:
    """Build the project's wheel in ``dist`` (default: the project's dist
    folder); returns its path. Raises MakeError."""
    from . import __version__

    project = Project.load(project_path)
    package = wheel_package(project)
    files = project_files(project)
    if "__main__.py" in files:
        raise MakeError("The project has a __main__.py of its own: the wheel's launcher "
                        "goes there (rename the project's)")
    if not package.isidentifier():
        raise MakeError(f"'{project.name}' can't be a package name")
    dist = os.path.abspath(dist or os.path.join(project.directory, "dist"))
    os.makedirs(dist, exist_ok=True)
    path = os.path.join(dist, wheel_name(project))
    info = f"{project.name}-{wheel_version(project)}.dist-info"
    script_kind = "console_scripts" if project.type == "console" else "gui_scripts"
    log(f"Building the wheel of {project.name} {wheel_version(project)}...")
    contents: list[tuple[str, bytes]] = []
    for relative in files:
        with open(project.abspath(relative), "rb") as f:
            contents.append((f"{package}/{relative}", f.read()))
    if "__init__.py" not in files:
        contents.append((f"{package}/__init__.py",
                         f'"""{project.name}, a VP6 program."""\n'.encode()))
    contents += [
        (f"{package}/__main__.py", _wheel_launcher(project).encode()),
        (f"{info}/METADATA",
         _metadata(project, wheel_requirements(project, log)).encode()),
        (f"{info}/WHEEL", (f"Wheel-Version: 1.0\nGenerator: vp6-make ({__version__})\n"
                           "Root-Is-Purelib: true\nTag: py3-none-any\n").encode()),
        (f"{info}/entry_points.txt",
         f"[{script_kind}]\n{project.name} = {package}.__main__:main\n".encode()),
        (f"{info}/top_level.txt", f"{package}\n".encode()),
    ]
    record = [_record_line(name, data) for name, data in contents] + [f"{info}/RECORD,,"]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as wheel:
        for name, data in contents:
            wheel.writestr(name, data)
        wheel.writestr(f"{info}/RECORD", "\n".join(record) + "\n")
    log(f"{len(files)} files of the project, in the package '{package}'; the command "
        f"'{project.name}' runs it")
    log(f"Made {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vp6-make", description="Package a VP6 project: a wheel (the default), or with "
        "--exe a standalone executable (for the platform this runs on).")
    parser.add_argument("project", help="the project file (Name.vp6p)")
    parser.add_argument("--exe", action="store_true",
                        help="a standalone executable (PyInstaller) instead of a wheel")
    parser.add_argument("--onefile", action="store_true",
                        help="an executable of one file instead of a folder (implies --exe; "
                        "not for a windowed program on macOS, which is an app)")
    parser.add_argument("--dist", help="where to put it (default: the project's dist folder)")
    args = parser.parse_args(argv)
    try:
        if args.exe or args.onefile:
            make(args.project, args.dist, args.onefile)
        else:
            make_wheel(args.project, args.dist)
    except MakeError as exc:
        print(f"vp6-make: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
