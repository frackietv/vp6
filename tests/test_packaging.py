"""The package as published (pyproject.toml): version, license, what the wheel
contains, and its commands."""

import fnmatch
import importlib
import os
import re
from pathlib import Path

import pytest

import vp6

ROOT = Path(__file__).resolve().parent.parent
tomllib = pytest.importorskip("tomllib")  # (Python 3.11+)
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
PROJECT = PYPROJECT["project"]


def test_version_and_license():
    assert PROJECT["version"] == vp6.__version__
    assert PROJECT["license"] == "MIT" and PROJECT["license-files"] == ["LICENSE"]
    text = (ROOT / "LICENSE").read_text()
    assert text.startswith("MIT License") and "FrackieTV" in text
    assert PROJECT["authors"] == [{"name": "FrackieTV"}]  # (no email published)
    assert PROJECT["readme"] == "README.md" and PROJECT["dependencies"] == ["PySide6>=6.6"]
    assert set(PROJECT["optional-dependencies"]["make"]) == {"pyinstaller>=6", "pillow"}


def test_every_data_file_goes_in_the_wheel():
    # Files in the package that aren't Python modules of a package (pictures,
    # the Kitchen Sink's templates) must match its package-data, or the wheel
    # leaves them out
    package_data = PYPROJECT["tool"]["setuptools"]["package-data"]
    missing = []
    for path in (ROOT / "vp6").rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        in_a_package = path.suffix == ".py" and (path.parent / "__init__.py").exists()
        if in_a_package:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if not any(fnmatch.fnmatch(relative, f"{package.replace('.', '/')}/{pattern}")
                   for package, patterns in package_data.items() for pattern in patterns):
            missing.append(relative)
    assert not missing, f"Add these to [tool.setuptools.package-data]: {missing}"


def test_the_commands():
    for name, target in PROJECT["scripts"].items():
        module, _, function = target.partition(":")
        assert callable(getattr(importlib.import_module(module), function)), name
    assert set(PROJECT["scripts"]) == {"vp6", "vp6-run", "vp6-make"}


def test_the_source_distribution_has_the_docs_and_tests():
    manifest = (ROOT / "MANIFEST.in").read_text()
    for line in ("include LICENSE README.md", "recursive-include docs *.md",
                 "recursive-include samples", "recursive-include tests *.py"):
        assert line in manifest
    assert (ROOT / "docs" / "api.md").exists() and os.listdir(ROOT / "samples")


def test_the_release_workflow_checks_the_version():
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    assert re.search(r'tags: \["v\*"\]', workflow)
    assert 'f"v{version}"' in workflow and "pypa/gh-action-pypi-publish" in workflow
    assert "id-token: write" in workflow  # trusted publishing: no token in the repository
