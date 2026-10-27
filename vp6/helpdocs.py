"""VP6's own help: its documents and the ``vp6`` package made into one
``vp6.vp6help`` file (with vp6help, the help system VP6 uses).

    path = help_file()   # VP6's help file (made first if need be), or None

Where it comes from:

* an installed VP6 has it in the package (``vp6/help/vp6.vp6help``, made
  when the wheel is built: ``setup.py``);
* VP6 run from its source (a checkout, or an editable install) makes it from
  the documents beside the package, once for each change to them or to the
  code, in a cache folder (``VP6_HELP_DIR``, or the system's temporary
  folder): in about a second.

This module uses only the standard library and vp6help (no Qt, nor the rest
of VP6), so that ``setup.py`` can load it on its own.
"""

from __future__ import annotations

import glob
import hashlib
import os
import tempfile

__all__ = ["DOCUMENTS", "TITLE", "make_help", "help_file", "sources_hash", "packaged_help"]

TITLE = "VP6 Help"
# The documents, in the order of the help's contents (paths from the source's root)
DOCUMENTS = ("README.md", "docs/ide.md", "docs/api.md", "docs/development-guide.md",
             "docs/education.md", "docs/architecture.md", "docs/source-reference.md",
             "packages/vp6help/README.md", "FEATURES.md")
FLAT = ("FEATURES.md",)  # (the release notes: one entry in the contents)
FILE_NAME = "vp6.vp6help"

PACKAGE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = os.path.dirname(PACKAGE)


def packaged_help() -> str | None:
    """The help file an installed VP6 keeps in the package (an executable made
    with vp6-make has one too)."""
    found = sorted(glob.glob(os.path.join(PACKAGE, "help", "*.vp6help")))
    return found[0] if found else None


def _has_sources(root: str) -> bool:
    return all(os.path.isfile(os.path.join(root, d)) for d in DOCUMENTS)


def sources_hash(root: str = SOURCE_ROOT) -> str:
    """What the help is made of (the documents, VP6's code and vp6help's
    version), as a hash: a new one means the help must be made again."""
    import vp6help

    digest = hashlib.sha256(f"vp6help {vp6help.__version__}\0".encode())
    files = [os.path.join(root, d) for d in DOCUMENTS]
    files += sorted(glob.glob(os.path.join(root, "vp6", "**", "*.py"), recursive=True))
    for path in files:
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        if "/templates/" in relative:
            continue
        with open(path, "rb") as f:
            digest.update(relative.encode() + b"\0" + f.read() + b"\0")
    return digest.hexdigest()


def make_help(output: str, root: str = SOURCE_ROOT) -> dict:
    """Make VP6's help file from the documents and the code under ``root``."""
    from vp6help.maker import HelpMaker

    maker = HelpMaker(TITLE, root=root, flat=FLAT)
    for document in DOCUMENTS:
        maker.add(os.path.join(root, document))
    # (only the package's own modules: run from the source, ``vp6`` is found there)
    import sys

    sys.path.insert(0, root)
    try:
        maker.add_packages(["vp6"], exclude=("vp6.ide.templates",))
        return maker.build(output)
    finally:
        sys.path.remove(root)


def cache_dir() -> str:
    return os.environ.get("VP6_HELP_DIR") or os.path.join(tempfile.gettempdir(), "vp6-help")


def help_file() -> str | None:
    """VP6's help file: the installed one, else one made from the source (made
    now when the documents or the code changed since). None when there is
    neither."""
    packaged = packaged_help()
    if packaged is not None:
        return packaged
    if not _has_sources(SOURCE_ROOT):
        return None
    folder = cache_dir()
    path = os.path.join(folder, f"vp6-{sources_hash()[:16]}.vp6help")
    if not os.path.isfile(path):
        os.makedirs(folder, exist_ok=True)
        for old in glob.glob(os.path.join(folder, "vp6-*.vp6help")):
            try:
                os.remove(old)
            except OSError:
                pass
        make_help(path)
    return path
