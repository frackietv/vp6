"""Project files are executable launcher scripts."""

import os
import stat
import subprocess
import sys

import pytest

from vp6.formfile import new_module_source
from vp6.project import SUB_MAIN, Project, ProjectFileError, parse

VP6_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_console_project(tmp_path, body="    print('hello from', __name__)\n    return 3\n"):
    (tmp_path / "Module1.py").write_text(f"def Main():\n{body}")
    project = Project(name="Hello", type="console", startup=SUB_MAIN, modules=["Module1.py"])
    path = tmp_path / "Hello.vp6p"
    project.save(str(path))
    return project, path


def test_saved_project_is_an_executable_python_script(tmp_path):
    project, path = make_console_project(tmp_path)
    text = path.read_text()
    assert text.startswith('#!/bin/sh\n"exec" "${VP6_PYTHON:-python3}" "$0" "$@"\n')
    compile(text, str(path), "exec")  # valid Python
    mode = os.stat(path).st_mode
    assert mode & stat.S_IXUSR and mode & stat.S_IXGRP and mode & stat.S_IXOTH
    assert Project.load(str(path)) == project


def test_save_keeps_code_outside_the_region(tmp_path):
    project, path = make_console_project(tmp_path)
    path.write_text(path.read_text().replace(
        'if __name__ == "__main__":', '# my note\nif __name__ == "__main__":'))
    project.color_scheme = "dark"
    project.save()
    text = path.read_text()
    assert "# my note" in text and text.count("# region VP6 Project") == 1
    assert Project.load(str(path)).color_scheme == "dark"


def test_loading_never_executes_the_file(tmp_path):
    path = tmp_path / "Evil.vp6p"
    path.write_text("import os\nos.remove(__file__)\nPROJECT = {'name': 'Evil'}\n")
    assert Project.load(str(path)).name == "Evil"
    assert path.exists()


@pytest.mark.parametrize("text", ["not python (", "X = 1\n", "PROJECT = make()\n",
                                  "PROJECT = [1]\n"])
def test_invalid_project_files(text):
    with pytest.raises(ProjectFileError):
        parse(text)


def _env(**extra):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", **extra)
    env["PYTHONPATH"] = VP6_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return env


@pytest.mark.skipif(sys.platform == "win32", reason="hash-bang scripts are POSIX")
def test_running_the_script_directly_uses_vp6_python(tmp_path):
    _, path = make_console_project(tmp_path)
    result = subprocess.run([str(path)], capture_output=True, text=True, timeout=60,
                            env=_env(VP6_PYTHON=sys.executable))
    assert "hello from Module1" in result.stdout
    assert result.returncode == 3  # Main's return value is the exit code


def test_running_with_python(tmp_path):
    _, path = make_console_project(tmp_path)
    result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True,
                            timeout=60, env=_env())
    assert "hello from Module1" in result.stdout


def test_helpful_message_without_vp6(tmp_path):
    _, path = make_console_project(tmp_path)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    # -S: no site-packages, so VP6 (installed there) can't be imported
    result = subprocess.run([sys.executable, "-S", str(path)], capture_output=True, text=True,
                            timeout=60, env=env, cwd=str(tmp_path))
    assert result.returncode == 1
    assert "VP6 is not installed" in result.stderr


def test_new_console_template_runs_via_script(tmp_path):
    (tmp_path / "Module1.py").write_text(new_module_source(with_main=True, console=True))
    Project(name="Hi", type="console", startup=SUB_MAIN,
            modules=["Module1.py"]).save(str(tmp_path / "Hi.vp6p"))
    result = subprocess.run([sys.executable, str(tmp_path / "Hi.vp6p")], input="Ada\n",
                            capture_output=True, text=True, timeout=60, env=_env())
    assert "Hello, Ada!" in result.stdout



def test_files_in_subfolders_run(tmp_path):
    # Forms and modules in subfolders import each other by name, like at the top
    (tmp_path / "lib" / "deep").mkdir(parents=True)
    (tmp_path / "lib" / "deep" / "Helpers.py").write_text("def greet():\n    return 'hi'\n")
    (tmp_path / "Module1.py").write_text(
        "from Helpers import greet\n\n\ndef Main():\n    print(greet(), 'from a subfolder')\n")
    Project(name="Sub", type="console", startup=SUB_MAIN,
            modules=["Module1.py", "lib/deep/Helpers.py"]).save(str(tmp_path / "Sub.vp6p"))
    result = subprocess.run([sys.executable, str(tmp_path / "Sub.vp6p")],
                            capture_output=True, text=True, timeout=60, env=_env())
    assert "hi from a subfolder" in result.stdout, result.stderr

# --- groups: how the Project panel shows the files --------------------------------------------

def _project():
    return Project(forms=["Form1.py", "Form2.py"], modules=["Module1.py"])


def test_default_groups():
    project = _project()  # no groups yet (like older project files): Forms and Modules
    assert project.tree() == [{"group": "Forms", "items": ["Form1.py", "Form2.py"]},
                              {"group": "Modules", "items": ["Module1.py"]}]
    assert project.group_paths() == [("Forms",), ("Modules",)]
    assert project.group_of("Module1.py") == ("Modules",)


def test_groups_nest_and_hold_anything():
    project = _project()
    project.add_group(("Forms",), "Dialogs")
    project.move("Form2.py", ("Forms", "Dialogs"))
    project.move("Module1.py", ("Forms", "Dialogs"))  # a module in a group of forms: fine
    project.add_group((), "Loose")
    project.move(("Forms", "Dialogs"), ("Loose",))  # a group into another
    assert project.tree() == [{"group": "Forms", "items": ["Form1.py"]},
                              {"group": "Modules", "items": []},
                              {"group": "Loose", "items": [
                                  {"group": "Dialogs", "items": ["Form2.py", "Module1.py"]}]}]
    project.move("Form1.py", ())  # files can be at the top level too
    assert project.group_of("Form1.py") == ()
    with pytest.raises(ValueError, match="itself"):
        project.move(("Loose",), ("Loose", "Dialogs"))
    with pytest.raises(ValueError, match="already"):
        project.add_group((), "Loose")
    with pytest.raises(ValueError, match="name"):
        project.add_group((), "  ")


def test_rename_and_delete_groups():
    project = _project()
    assert project.rename_group(("Forms",), "Windows") == ("Windows",)
    with pytest.raises(ValueError, match="already"):
        project.rename_group(("Windows",), "Modules")
    project.delete_group(("Windows",))  # what it held moves up, in its place
    assert project.tree() == ["Form1.py", "Form2.py", {"group": "Modules",
                                                       "items": ["Module1.py"]}]
    assert project.forms == ["Form1.py", "Form2.py"]  # nothing leaves the project


def test_new_files_find_their_place():
    project = _project()
    project.add_group(("Forms",), "Dialogs")
    project.forms.append("Form3.py")
    project.place_file("Form3.py", ("Forms", "Dialogs"))  # a chosen group
    project.forms.append("Form4.py")
    project.place_file("Form4.py")  # none: where the forms are (not by the group's name)
    project.modules.append("Module2.py")
    project.place_file("Module2.py")
    assert project.group_of("Form3.py") == ("Forms", "Dialogs")
    assert project.group_of("Form4.py") == ("Forms",)
    assert project.group_of("Module2.py") == ("Modules",)
    project.rename_group(("Modules",), "Code")
    project.modules.append("Module3.py")
    project.place_file("Module3.py")  # the group holding modules, whatever it's called
    assert project.group_of("Module3.py") == ("Code",)
    project.remove_file("Module3.py")
    assert "Module3.py" not in project.modules and "Module3.py" not in str(project.tree())
    project.rename_file("Form4.py", "frmMain.py")  # renamed on disk: same place
    assert project.group_of("frmMain.py") == ("Forms",) and "frmMain.py" in project.forms


def test_tree_repairs_itself():
    project = _project()
    project.groups = [{"group": "Forms", "items": ["Form1.py", "Gone.py", "Form1.py"]},
                      "Module1.py", 42, {"no group": True}]
    # Form2 wasn't in any group: it goes where the forms are; the rest is dropped
    assert project.tree() == [{"group": "Forms", "items": ["Form1.py", "Form2.py"]},
                              "Module1.py"]


def test_groups_are_saved_and_loaded(tmp_path):
    project = _project()
    project.add_group(("Forms",), "Dialogs")
    project.move("Form2.py", ("Forms", "Dialogs"))
    path = tmp_path / "Demo.vp6p"
    project.save(str(path))
    text = path.read_text()
    assert '"groups": [' in text and '"group": "Dialogs"' in text
    loaded = Project.load(str(path))
    assert loaded == project and loaded.group_of("Form2.py") == ("Forms", "Dialogs")
    # An older project file without groups: the two default groups
    path.write_text(text[:text.index('    "groups"')] + "}\n# endregion\n")
    assert Project.load(str(path)).tree()[0] == {"group": "Forms",
                                                 "items": ["Form1.py", "Form2.py"]}
