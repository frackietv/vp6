"""The ``.vp6help`` file: a whole help system in one file.

It is a zip archive (as .chm files were compound files): ``vp6help.json``
describes the help (its title, home page, contents, index and the searchable
text of each section) and every other entry is a page (HTML) or a file the
pages use (pictures...), at its path inside the help:

    {"format": 1, "title": "...", "home": "README.html",
     "pages": [{"path": "docs/api.html", "title": "VP6 API reference"}, ...],
     "toc": [{"title": "...", "url": "docs/api.html", "children": [...]}, ...],
     "index": [["MsgBox", "docs/api.html#dialogs", "Dialogs"], ...],
     "sections": [{"url": "docs/api.html#dialogs", "title": "Dialogs",
                   "page": "VP6 API reference", "text": "..."}, ...],
     "sources": "<a hash of what it was made from>"}

A url is a page's path, with ``#anchor`` for a place in it. The help maker
(``vp6help.maker``) writes these files; ``HelpFile`` reads them, and finds
index entries and search results for the viewer.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass

__all__ = ["FORMAT", "MANIFEST", "EXTENSION", "HelpFile", "IndexEntry", "SearchHit",
           "write_help", "compile_pattern"]

FORMAT = 1
MANIFEST = "vp6help.json"
EXTENSION = ".vp6help"
_DATE = (1980, 1, 1, 0, 0, 0)  # (fixed: the same sources make the same file)


@dataclass(frozen=True)
class IndexEntry:
    keyword: str
    url: str
    title: str  # the section it leads to


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str  # the section's heading
    page: str  # its page's title
    count: int  # how many matches


def compile_pattern(text: str, regex: bool = False, case: bool = False) -> re.Pattern:
    """A filter or search as a pattern: the text as it is, or a regular
    expression (``re.error`` when it isn't one); matching case or not."""
    return re.compile(text if regex else re.escape(text), 0 if case else re.IGNORECASE)


def write_help(path: str, manifest: dict, files: dict[str, bytes]) -> None:
    """Write a help file: the manifest, then the files (pages first) in order."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(name: str, data: bytes) -> None:
            info = zipfile.ZipInfo(name, _DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)

        add(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=0,
                                 sort_keys=True).encode("utf-8"))
        for name, data in files.items():
            add(name, data)


class HelpFile:
    """A ``.vp6help`` file, open for reading."""

    def __init__(self, path: str):
        self.path = path
        self._zip = zipfile.ZipFile(path)
        try:
            manifest = json.loads(self._zip.read(MANIFEST).decode("utf-8"))
        except KeyError:
            raise ValueError(f"{path} is not a VP6 help file") from None
        if manifest.get("format", 0) > FORMAT:
            raise ValueError(f"{path} needs a newer vp6help (format {manifest['format']})")
        self.manifest = manifest
        self.title: str = manifest.get("title", "")
        self.home: str = manifest.get("home", "")
        self.pages: list[dict] = manifest.get("pages", [])
        self.toc: list[dict] = manifest.get("toc", [])
        # (a keyword's topics in the order of the documents)
        self.index = sorted((IndexEntry(*entry) for entry in manifest.get("index", [])),
                            key=lambda e: (e.keyword.casefold(), e.keyword))
        self.sections: list[dict] = manifest.get("sections", [])
        self._names = set(self._zip.namelist())

    def close(self) -> None:
        self._zip.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- contents ---------------------------------------------------------------------------
    def has(self, path: str) -> bool:
        return path.lstrip("/") in self._names

    def read(self, path: str) -> bytes | None:
        """A page's or file's bytes (None when the help has no such file)."""
        path = path.lstrip("/")
        if path not in self._names or path == MANIFEST:
            return None
        return self._zip.read(path)

    def page_title(self, path: str) -> str:
        path = path.partition("#")[0].lstrip("/")
        return next((p["title"] for p in self.pages if p["path"] == path), path)

    def section_title(self, url: str) -> str:
        url = url.lstrip("/")
        return next((s["title"] for s in self.sections if s["url"] == url),
                    self.page_title(url))

    # -- the index ------------------------------------------------------------------------
    def keywords(self, text: str = "", regex: bool = False, case: bool = False) -> list[str]:
        """The index's keywords containing a text (or matching a regular
        expression), alphabetically."""
        pattern = compile_pattern(text, regex, case) if text else None
        seen, result = set(), []
        for entry in self.index:
            if entry.keyword not in seen and (pattern is None or pattern.search(entry.keyword)):
                seen.add(entry.keyword)
                result.append(entry.keyword)
        return result

    def entries(self, keyword: str) -> list[IndexEntry]:
        """Where an index keyword leads (its topics)."""
        return [e for e in self.index if e.keyword == keyword]

    def lookup(self, keyword: str, case: bool = False) -> list[IndexEntry]:
        """The topics of a keyword: exactly that keyword (any case unless
        ``case``), else the keywords starting with it."""
        key = keyword if case else keyword.casefold()

        def norm(text):
            return text if case else text.casefold()

        exact = [e for e in self.index if norm(e.keyword) == key]
        return exact or [e for e in self.index if norm(e.keyword).startswith(key)]

    # -- search ---------------------------------------------------------------------------
    def search(self, text: str, regex: bool = False, case: bool = False) -> list[SearchHit]:
        """The sections whose text (or heading) contains a text or matches a
        regular expression, the most matches first."""
        if not text:
            return []
        pattern = compile_pattern(text, regex, case)
        hits = []
        for order, section in enumerate(self.sections):
            count = sum(1 for m in pattern.finditer(section["text"]) if m.end() > m.start())
            count += sum(1 for m in pattern.finditer(section["title"]) if m.end() > m.start())
            if count:
                hits.append((count, order, SearchHit(section["url"], section["title"],
                                                     section["page"], count)))
        hits.sort(key=lambda h: (-h[0], h[1]))
        return [hit for _, _, hit in hits]
