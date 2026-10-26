"""Projects in the IDE, without Qt: the New Project templates (in categories)
and making a project from one (``create_project``); the project's properties
as the Properties window and the Project Properties form show them
(``project_specs``, ``project_values``, ``set_project_property``); recent
projects; new files' unique names and checks of names on disk.
"""

from __future__ import annotations

import os

DEFAULT_LOCATION = os.path.join(os.path.expanduser("~"), "VP6 Projects")

# (key, title, icon, description, category): a category is a path of folders
# ("Sample Projects/Graphics"); "" is the top level
TEMPLATES = [
    ("exe", "Standard EXE", "Form",
     "A windowed application: Sub Main in Module1 shows Form1.", ""),
    ("console", "Console Application", "Console",
     "A text-mode program that starts in Sub Main (Module1) and uses print() / input(). "
     "Form1 is included for when you need a window.", ""),
    ("kitchensink", "Kitchen Sink", "KitchenSink",
     "A demo that shows every VP6 control and feature working. A good place to learn "
     "from and to copy code out of.", "Sample Projects"),
    ("projection", "Projection", "Isometric",
     "A model turning in a parallel projection on a single form, drawn with the graphics "
     "methods: isometric, elevation, plan, dimetric, trimetric, military, cavalier or "
     "top-down; a cube, a pyramid, a torus, a house, a few boxes or a downtown, solid and "
     "shaded or as a wireframe, the axes behind it. Drag an axis to move it, the space "
     "around to turn the axes, the model to turn it; sliders for its roll, pitch and "
     "tumble and their rates; the angles between the axes.",
     "Sample Projects/Graphics"),
    ("perspectives", "Perspectives", "Perspective",
     "A model turning in perspective on a single form, drawn with the graphics methods: "
     "1-, 2- or 3-point linear perspective, or 4-, 5- or 6-point curvilinear perspective "
     "(cylindrical, fisheye, the whole sphere); the same models and turns as Projection, "
     "with perspective lines to the vanishing points and the horizon instead of axes. Drag "
     "a vanishing point to move it, the space around to turn the scene, the model to turn "
     "it; put any axis's vanishing point at infinity up, down, left or right; move the eye "
     "nearer or farther, even inside the model.",
     "Sample Projects/Graphics"),
]

# The project's Type and ColorScheme: (value, label)
TYPE_CHOICES = (("exe", "Standard EXE"), ("console", "Console Application"))
COLOR_SCHEME_CHOICES = (
    ("system", "System (follow the OS appearance)"),
    ("light", "Light"),
    ("dark", "Dark"),
    ("ide", "Follow the IDE (its light/dark setting)"),
)

RECENT_LIMIT = 10


def categories() -> list[str]:
    """Every category of TEMPLATES and the folders above them, in order."""
    found: list[str] = []
    for *_, category in TEMPLATES:
        parts = category.split("/") if category else []
        for i in range(1, len(parts) + 1):
            path = "/".join(parts[:i])
            if path not in found:
                found.append(path)
    return found


def template(key: str) -> tuple:
    """A template's (key, title, icon, description, category)."""
    return next(t for t in TEMPLATES if t[0] == key)


def next_free_name(base: str, location: str) -> str:
    """``base`` and the first number not taken by a folder in ``location``."""
    i = 1
    while os.path.exists(os.path.join(location, f"{base}{i}")):
        i += 1
    return f"{base}{i}"


def new_project_problem(name: str, location: str) -> str | None:
    """Why a new project can't be made with that name there (None: it can)."""
    if not name.isidentifier():
        return "The project name must be a valid identifier (letters, digits, _)."
    target = os.path.join(location, name)
    if os.path.exists(target) and os.listdir(target):
        return f"{target} already exists and is not empty."
    return None


def create_project(location: str, name: str, template_key: str) -> str:
    """Create a new project folder from a template; returns the .vp6p path."""
    from vp6 import formfile
    from vp6.project import EXTENSION, SUB_MAIN, Project

    # Every new project has Form1 and Module1, and starts in Module1's Main():
    # a console Main talks through print()/input(), a windowed one shows Form1.
    directory = os.path.join(location, name)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name + EXTENSION)
    if template_key in ("kitchensink", "projection", "perspectives"):
        if template_key == "kitchensink":
            from vp6.ide import kitchensink

            project = kitchensink.create(directory, name)
        else:
            from vp6.ide import samples

            project = samples.create(template_key, directory, name)
        project.path = path
        project.save(path)
        return path
    console = template_key == "console"
    with open(os.path.join(directory, "Form1.py"), "w", encoding="utf-8") as f:
        f.write(formfile.new_form_source("Form1"))
    with open(os.path.join(directory, "Module1.py"), "w", encoding="utf-8") as f:
        f.write(formfile.new_module_source(with_main=True, console=console,
                                           startup_form=None if console else "Form1"))
    project = Project(name=name, type="console" if console else "exe", startup=SUB_MAIN,
                      forms=["Form1.py"], modules=["Module1.py"], path=path)
    project.save(path)  # (no icon of its own: the installed VP6 icon until it gets one)
    return path


# --- the project's properties ------------------------------------------------------------------

def project_specs(form_names: list[str]) -> list:
    """The project's properties (PropSpecs, by name) for the Properties window."""
    from vp6._props import P
    from vp6.project import SUB_MAIN

    startup = [(name, name) for name in form_names] + [(SUB_MAIN, SUB_MAIN)]
    return [
        P("Arguments", "str", "",
          description="The command line the program gets when the IDE runs it "
                      "(Command(), sys.argv[1:]), e.g. --verbose \"a file.txt\"."),
        P("ColorScheme", "enum", "system", COLOR_SCHEME_CHOICES,
          description="Light or dark appearance of every form whose ColorScheme is "
                      "'0 - Project Default'."),
        P("ArgumentsHelp", "text", "",
          description="The program's own command line arguments, one per line, as "
                      "--help lists them, e.g. --open FILE    open FILE at the start."),
        P("Command", "str", "",
          description="The command its wheel installs (vp6-make), e.g. myapp-gui; "
                      "empty: the project's name."),
        P("CompanyName", "str", "", description="App.CompanyName."),
        P("Description", "str", "", description="App.FileDescription: what the "
                                                "program is."),
        P("Icon", "file", "",
          description="The program's icon (its windows, and the Dock or taskbar): an "
                      "image file in the project's folder, square, e.g. 256 x 256 "
                      "pixels. Empty (as in new projects): the VP6 icon, from the VP6 "
                      "installation."),
        P("Package", "str", "",
          description="The Python package the project's folder is, e.g. myapp.gui "
                      "(folders myapp/gui with an __init__.py each): its forms and "
                      "modules are imported by package name (myapp.gui.Form1), and it "
                      "is started from the package (vp6.runner.run_package). Empty: "
                      "a project of its own."),
        P("ProductName", "str", "",
          description="App.ProductName; empty: the project's name."),
        P("StartupObject", "enum", "Form1", startup,
          description="The form shown when the program starts, or Sub Main to call "
                      "Main() in a module."),
        P("Type", "enum", "exe", TYPE_CHOICES,
          description="Standard EXE (windowed) or Console Application."),
        P("Version", "str", "1.0.0",
          description="Major.Minor.Revision: App.Major, App.Minor and App.Revision."),
    ]


_FIELDS = {"Type": "type", "StartupObject": "startup", "ColorScheme": "color_scheme",
           "Version": "version", "ProductName": "product_name",
           "CompanyName": "company_name", "Description": "description",
           "Arguments": "arguments", "ArgumentsHelp": "arguments_help", "Package": "package",
           "Command": "command"}


def project_values(project) -> dict:
    """The project's properties, by name (Icon: its last file, the largest
    size as new projects list them)."""
    values = {name: getattr(project, field) for name, field in _FIELDS.items()}
    values["Icon"] = project.icon[-1] if project.icon else ""
    values["Name"] = project.name
    return values


def set_project_property(project, prop: str, value) -> str | None:
    """Change a project property. Returns an error message (the project
    unchanged) or None."""
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
    elif prop == "Version":
        parts = str(value).strip().split(".")
        if not (1 <= len(parts) <= 3 and all(part.isdigit() for part in parts)):
            return f"'{value}' is not a version: Major.Minor.Revision, e.g. 1.2.0"
        project.version = ".".join(str(int(part)) for part in parts + ["0"] * (3 - len(parts)))
    elif prop in ("ProductName", "CompanyName", "Description", "Arguments"):
        setattr(project, _FIELDS[prop], str(value).strip())
    elif prop == "Package":
        package = str(value or "").strip()
        old, project.package = project.package, package
        problem = project.package_problem()
        if problem:
            project.package = old
            return problem
    elif prop == "Command":
        command = str(value or "").strip()
        if command and not all(c.isalnum() or c in "-_." for c in command):
            return f"'{command}' is not a command name (letters, digits, - _ .)"
        project.command = command
    elif prop == "ArgumentsHelp":
        project.arguments_help = str(value or "").strip("\n")
    elif prop == "Icon":  # one file now, whatever sizes it had
        value = str(value or "").strip().replace(os.sep, "/")
        project.icon = [value] if value else []
    else:
        return f"Unknown project property '{prop}'"
    return None


# --- recent projects and file names ---------------------------------------------------------

def remember(recent: list[str], path: str) -> list[str]:
    """The recent projects with ``path`` first (once), at most RECENT_LIMIT."""
    return [path] + [p for p in recent if p != path][:RECENT_LIMIT - 1]


def relative(project, path: str) -> str:
    """A path as the project lists it: relative to its folder, with /."""
    return os.path.relpath(path, project.directory).replace(os.sep, "/")


def import_names(paths, ignore: str | None = None) -> set[str]:
    """The file names (without .py, lower case) of the project's forms and
    modules: what a program not in a package imports them by."""
    return {os.path.splitext(os.path.basename(path))[0].lower()
            for path in paths if path != ignore}


def unique_file(base: str, folder: str, taken: set[str]) -> tuple[str, str]:
    """A new form's or module's name (``base`` and a number) and its file's
    path in ``folder``: a name not in ``taken`` (lower case) and no file there."""
    i = 1
    while f"{base}{i}".lower() in taken or \
            os.path.exists(os.path.join(folder, f"{base}{i}.py")):
        i += 1
    return f"{base}{i}", os.path.join(folder, f"{base}{i}.py")


def file_name_error(name: str) -> str | None:
    """Why a file's or folder's name can't be used (None: it can)."""
    name = name.strip()
    if not name or name in (".", "..") or "/" in name or os.sep in name:
        return f"'{name}' is not a valid name"
    return None


def is_identifier(name: str) -> bool:
    """A valid name for a form, a control or a module (not a keyword)."""
    import keyword

    return name.isidentifier() and not keyword.iskeyword(name)
