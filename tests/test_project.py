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
