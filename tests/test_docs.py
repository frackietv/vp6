"""The documentation must keep up with the code.

If a test here fails after a change:
* a new source or test file: describe it in docs/source-reference.md;
* a new public API name: document it in docs/api.md;
* changed properties, events or constants: run `python tools/apidocs.py`;
* a broken link: fix the link or the heading it points to.
"""

import re
import sys
from pathlib import Path

import pytest

import vp6
from vp6 import constants
from vp6.controls import CONTROL_TYPES

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "tools"))
import apidocs  # noqa: E402

MARKDOWN = sorted(DOCS.glob("*.md")) + [ROOT / name for name in
                                         ("README.md", "FEATURES.md", "BACKLOG.md")]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- coverage -------------------------------------------------------------------------------

def test_every_source_file_is_in_the_source_reference():
    reference = read(DOCS / "source-reference.md")
    missing = []
    for path in sorted((ROOT / "vp6").rglob("*.py")) + sorted((ROOT / "tools").glob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "templates" in path.parts:  # template files are described by name
            found = f"`{path.name}`" in reference or path.name in reference
        else:
            found = f"`{relative}`" in reference
        if not found:
            missing.append(relative)
    assert not missing, f"Describe these in docs/source-reference.md: {missing}"


def test_every_test_file_is_in_the_test_table():
    reference = read(DOCS / "source-reference.md")
    missing = [p.name for p in sorted((ROOT / "tests").glob("test_*.py"))
               if f"| `{p.name}` |" not in reference]
    assert not missing, f"Add these to the test table in docs/source-reference.md: {missing}"


def _documented_ranges(text: str) -> set[str]:
    """Names covered by ranges like `vpKeyA`..`vpKeyZ` (inclusive, by value)."""
    covered = set()
    for first, last in re.findall(r"`(vp\w+)`\.\.`(vp\w+)`", text):
        low, high = getattr(constants, first), getattr(constants, last)
        prefix = re.match(r"vp[A-Z][a-z]+", first).group(0)
        covered |= {name for name in constants.__all__
                    if name.startswith(prefix) and low <= getattr(constants, name) <= high
                    and len(name) <= len(last) + 1}
    return covered


def test_every_public_api_name_is_in_the_api_reference():
    api = read(DOCS / "api.md")
    covered = _documented_ranges(api)
    missing = [name for name in vp6.__all__
               if name not in covered and not re.search(rf"`{re.escape(name)}\b", api)]
    assert not missing, f"Document these in docs/api.md: {missing}"


# --- generated tables -------------------------------------------------------------------------

def test_generated_api_tables_are_up_to_date():
    text = read(DOCS / "api.md")
    assert apidocs.update(text) == text, "docs/api.md is out of date: run python tools/apidocs.py"


def test_every_control_has_a_generated_section():
    keys = apidocs.block_keys(read(DOCS / "api.md"))
    controls = {key.split(" ", 1)[1] for key in keys if key.startswith("control ")}
    assert controls == set(CONTROL_TYPES), (
        "docs/api.md needs a '### <Control>' section with "
        "'<!-- BEGIN GENERATED: control <Control> -->' for each control")
    for key in ("form-properties", "form-events", "common-properties", "event-arguments",
                "constants"):
        assert key in keys


def test_generator_reports_stale_docs(tmp_path, monkeypatch):
    stale = tmp_path / "api.md"
    stale.write_text("<!-- BEGIN GENERATED: form-events -->\nold\n<!-- END GENERATED -->\n")
    monkeypatch.setattr(apidocs, "API_MD", stale)
    assert apidocs.main(["--check"]) == 1
    assert apidocs.main([]) == 0
    assert "Events: `Load`" in stale.read_text()
    assert apidocs.main(["--check"]) == 0


# --- links ------------------------------------------------------------------------------------

def _slug(heading: str) -> str:
    """GitHub-style anchor for a Markdown heading."""
    heading = re.sub(r"[`*]", "", heading.strip().lower())
    heading = re.sub(r"[^\w\- ]", "", heading)
    return heading.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", read(path), flags=re.S)  # headings in code don't count
    return {_slug(h) for h in re.findall(r"^#+ (.+)$", text, re.M)}


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_links_resolve(path):
    text = re.sub(r"```.*?```", "", read(path), flags=re.S)
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+:", target):  # http:, mailto: ...
            continue
        file, _, anchor = target.partition("#")
        destination = (path.parent / file).resolve() if file else path
        if not destination.exists():
            broken.append(target)
        elif anchor and destination.suffix == ".md" and anchor not in _anchors(destination):
            broken.append(target)
    assert not broken, f"Broken links in {path.name}: {broken}"


def test_every_property_has_a_description():
    # Shown in the Properties window and in the generated API reference
    from vp6.form import Form

    missing = sorted({f"{cls.TypeName}.{spec.name}"
                      for cls in [Form, *CONTROL_TYPES.values()]
                      for spec in cls.Properties if not spec.description})
    assert not missing, f"Give these PropSpecs a description: {missing}"
