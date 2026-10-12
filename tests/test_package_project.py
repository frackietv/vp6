"""A project that is part of a Python package (its ``package``): imported by
package name, started from the package (``run_package``, a console entry
point), its files found there, and built by vp6-make into the wheel of the
whole package."""

import os
import subprocess
import sys
import zipfile

import pytest

from vp6 import make, runner
from vp6.ide.dialogs import ProjectPropertiesDialog
from vp6.ide.projectprops import ProjectTarget
from vp6.project import SUB_MAIN, Project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(make.__file__)))


@pytest.fixture
def package(tmp_path):
    """``myapp`` with the project in ``myapp/gui``: a console program whose
    Sub Main uses a module named ``options`` (which mustn't shadow anything),
    a module in a subfolder, a data file and a module of the larger package."""
    files = {
        "myapp/__init__.py": "",
        "myapp/core.py": "def answer():\n    return 42\n",
        "myapp/gui/__init__.py": "",
        "myapp/gui/options.py": "VERBOSE = 'from the package'\n",
        "myapp/gui/pages/__init__.py": "",
        "myapp/gui/pages/Page1.py": "TITLE = 'page one'\n",
        "myapp/gui/data/message.txt": "a data file\n",
        "myapp/gui/Module1.py": (
            "import os\n\nfrom vp6 import App\n\n"
            "from ..core import answer\nfrom .options import VERBOSE\n"
            "from .pages.Page1 import TITLE\n\n\n"
            "def Main():\n    print(VERBOSE, TITLE, answer())\n"
            "    print(open(os.path.join(App.Path, 'data', 'message.txt')).read().strip())\n"
            "    print(__name__)\n"
            "    return 5\n"),
        "myapp/gui/build/x.txt": "", "myapp/__pycache__/c.pyc": "",
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    project = Project(name="MyApp", type="console", startup=SUB_MAIN, forms=[],
                      modules=["Module1.py", "options.py", "pages/Page1.py"],
                      package="myapp.gui", command="myapp-gui", version="2.1.0")
    project.save(str(tmp_path / "myapp" / "gui" / "MyApp.vp6p"))
    yield Project.load(project.path)
    for name in [n for n in sys.modules if n == "myapp" or n.startswith("myapp.")]:
        del sys.modules[name]  # (each test's package is another folder)


def _env(*paths):
    return dict(os.environ, PYTHONPATH=os.pathsep.join([*map(str, paths), ROOT]),
                QT_QPA_PLATFORM="offscreen")


def test_the_fields_are_saved(package):
    assert package.package == "myapp.gui" and package.command == "myapp-gui"
    assert package.command_name() == "myapp-gui"
    assert Project(name="P").command_name() == "P"
    with open(package.path) as f:
        text = f.read()
    assert '"package": "myapp.gui",' in text and '"command": "myapp-gui",' in text


def test_module_names(package, tmp_path):
    assert package.module_name("Module1.py") == "myapp.gui.Module1"
    assert package.module_name("pages/Page1.py") == "myapp.gui.pages.Page1"
    assert Project().module_name("pages/Page1.py") == "Page1"  # (not in a package)
    assert package.package_root() == str(tmp_path)
    # Only the folder holding the package is imported from: nothing shadows
    assert runner.import_folders(package) == [str(tmp_path)]


def test_package_problems(package, tmp_path):
    assert package.package_problem() is None
    assert package.found_package() == "myapp.gui"
    package.package = "other.gui"
    assert "isn't the package" in package.package_problem()
    package.package = "my-app"
    assert "not a package name" in package.package_problem()
    os.remove(tmp_path / "myapp" / "__init__.py")
    package.package = "myapp.gui"
    assert "no __init__.py" in package.package_problem()
    assert package.found_package() == "gui"
    assert Project(path=str(tmp_path / "P.vp6p")).package_problem() is None


def test_run_from_the_package(package, tmp_path):
    # run_package (what an entry point calls), python -m with a __main__, and the
    # project file itself; the working folder stays where it was started
    main = tmp_path / "myapp" / "gui" / "__main__.py"
    main.write_text("import sys\n\nfrom vp6.runner import run_package\n\n\n"
                    "def main():\n    return run_package(__package__)\n\n\n"
                    'if __name__ == "__main__":\n    sys.exit(main())\n')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    commands = [
        [sys.executable, "-c", "import sys; from vp6.runner import run_package; "
                               "sys.exit(run_package('myapp.gui'))"],
        [sys.executable, "-m", "myapp.gui"],
        [sys.executable, package.path],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60,
                                env=_env(tmp_path), cwd=str(elsewhere))
        assert result.returncode == 5, result.stderr
        assert result.stdout.split("\n")[:3] == ["from the package page one 42",
                                                 "a data file", "myapp.gui.Module1"]


def test_package_project_errors(package, tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="No package"):
        runner.package_project("no_such_package_here")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert runner.package_project("myapp.gui") == package.path
    assert runner.package_project("myapp.gui", "Other.vp6p").endswith("Other.vp6p")
    Project(name="Second").save(str(tmp_path / "myapp" / "gui" / "Second.vp6p"))
    with pytest.raises(SystemExit, match="2 project files"):
        runner.package_project("myapp.gui")
    with pytest.raises(SystemExit, match="no project file"):
        runner.package_project("myapp")
    # A package imported from elsewhere already can't be the project's
    sys.modules["myapp"] = type(sys)("myapp")
    sys.modules["myapp"].__path__ = [str(tmp_path / "other")]
    with pytest.raises(SystemExit, match="already imported"):
        runner._check_package(package)


def test_app_path_and_pictures(qapp, package, tmp_path, monkeypatch):
    from vp6 import LoadPicture
    from vp6.app import App, _App

    monkeypatch.setattr(_App, "_path", "")
    monkeypatch.setattr(_App, "_title", "")
    App._set_project(package)
    assert App.Path == package.directory
    from PySide6.QtGui import QImage

    image = QImage(4, 4, QImage.Format_ARGB32)
    image.fill(0xFF00FF00)
    image.save(str(tmp_path / "myapp" / "gui" / "dot.png"))
    monkeypatch.chdir(tmp_path)  # (not the project's folder)
    assert LoadPicture("dot.png").Width > 0  # found in App.Path
    with pytest.raises(FileNotFoundError):
        LoadPicture("missing.png")


def test_the_wheel_of_the_package(package, tmp_path):
    path = make.make_wheel(package.path, log=lambda line: None)
    assert os.path.basename(path) == "myapp-2.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as wheel:
        names = set(wheel.namelist())
        info = "myapp-2.1.0.dist-info"
        assert {"myapp/__init__.py", "myapp/core.py", "myapp/gui/MyApp.vp6p",
                "myapp/gui/pages/Page1.py", "myapp/gui/data/message.txt",
                "myapp/gui/__main__.py"} <= names
        assert not any("build/" in n or "__pycache__" in n for n in names)
        assert "myapp-gui = myapp.gui.__main__:main" in \
            wheel.read(f"{info}/entry_points.txt").decode()
        assert wheel.read(f"{info}/top_level.txt").decode() == "myapp\n"
        assert "Name: myapp\n" in wheel.read(f"{info}/METADATA").decode()
        assert "run_package(__package__ or 'myapp.gui', 'MyApp.vp6p')" in \
            wheel.read("myapp/gui/__main__.py").decode()
        wheel.extractall(tmp_path / "site")
    # Run from where the wheel puts it (python -m: not from a folder holding the source)
    result = subprocess.run([sys.executable, "-m", "myapp.gui"], capture_output=True,
                            text=True, timeout=60, env=_env(tmp_path / "site"),
                            cwd=str(tmp_path / "site" / info))
    assert result.returncode == 5, result.stderr
    assert result.stdout.split("\n")[1] == "a data file"


def test_the_wheel_with_its_own_main(package, tmp_path):
    main = tmp_path / "myapp" / "gui" / "__main__.py"
    main.write_text("print('no main function')\n")
    with pytest.raises(make.MakeError, match="no main"):
        make.make_wheel(package.path, log=lambda line: None)
    main.write_text("def main():\n    return 0\n")
    path = make.make_wheel(package.path, log=lambda line: None)
    with zipfile.ZipFile(path) as wheel:
        assert wheel.read("myapp/gui/__main__.py").decode() == "def main():\n    return 0\n"
    package.package = "wrong.name"
    package.save()
    with pytest.raises(make.MakeError, match="isn't the package"):
        make.make_wheel(package.path, log=lambda line: None)


def test_what_goes_in_and_the_executable(package):
    files = make.package_files(package)
    assert "myapp/core.py" in files and "myapp/gui/MyApp.vp6p" in files
    assert make.project_files(package)[0] == "Module1.py"  # (Save As: the project's own)
    assert make.imported_modules(package) == ["os", "vp6"]  # (not myapp)
    assert "run_project(os.path.join(folder, 'myapp/gui/MyApp.vp6p'))" in \
        make.launcher_source(package)
    command = make.pyinstaller_command(package, "launch.py", "dist", "work")
    data = [command[i + 1] for i, part in enumerate(command) if part == "--add-data"]
    assert f"{package.abspath('pages/Page1.py')}{os.pathsep}myapp/gui/pages" in data


def test_package_in_the_properties(qapp, package):
    changed = []
    target = ProjectTarget(lambda: package, lambda: [], lambda: changed.append(1))
    names = [spec.name for spec in target.specs()]
    assert "Package" in names and "Command" in names
    assert "isn't the package" in target.set_property("Package", "other")
    assert package.package == "myapp.gui"
    assert target.set_property("Package", "") is None and package.package == ""
    assert target.set_property("Package", "myapp.gui") is None
    assert target.selected_objects()[0].Package == "myapp.gui"
    assert "not a command name" in target.set_property("Command", "my app")
    assert target.set_property("Command", "my-app") is None
    assert target.selected_objects()[0].Command == "my-app"
    dialog = ProjectPropertiesDialog(package, [])
    assert dialog.package.text() == "myapp.gui" and dialog.command.text() == "my-app"
    dialog.package.setText("not.it")  # (not the folder: kept)
    dialog.command.setText("app-gui")
    dialog.apply(package)
    assert package.package == "myapp.gui" and package.command == "app-gui"
    dialog.deleteLater()


def test_user_controls_in_a_package(qapp, package, tmp_path, monkeypatch):
    from vp6 import formfile
    from vp6.usercontrol import load_user_control

    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "myapp" / "gui" / "Gauge.py"
    source = formfile.new_user_control_source("Gauge")
    path.write_text(source.replace("from vp6 import *\n",
                                   "from vp6 import *\nfrom .options import VERBOSE\n", 1))
    cls = load_user_control(str(path), module_name="myapp.gui.Gauge")
    assert cls.__module__ == "myapp.gui.Gauge"
    assert sys.modules["myapp.gui.Gauge"].VERBOSE == "from the package"
