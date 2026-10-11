"""The help maker: Markdown and HTML documents (and the pictures and files
they link to), and optionally Python packages, made into one ``.vp6help``
file with a table of contents, an index and searchable text.

    vp6help-make -o MyHelp.vp6help --title "My Help" README.md docs/
    vp6help-make -o api.vp6help --package mypackage --follow

From Python:

    maker = HelpMaker(title="My Help")
    maker.add("README.md")
    maker.add("docs")                      # its .md and .html files
    maker.add_packages(["mypackage"])
    maker.build("MyHelp.vp6help")

What goes where:

* **Contents:** each document in the order given (a folder's documents by
  name, its README or index first), with its headings (to ``--toc-depth``).
* **Index:** the headings; names in code that start a table row or stand
  alone in a paragraph (``**`MsgBox(prompt)`**`` gives ``MsgBox``); the
  keywords of ``<!-- keywords: a, b -->`` comments (for the section they are
  in) and of an HTML page's ``<meta name="keywords">``.
* **Search:** the text of every section (a heading and what follows it).

Links between the documents become links between their pages; pictures and
other files they link to (inside the root folder) go into the help file.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html as _html
import os
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

from . import __version__
from .helpfile import EXTENSION, FORMAT, write_help
from .markdown import escape, to_html
from .pydoc import package_pages

__all__ = ["HelpMaker", "main", "slug"]

MARKDOWN = (".md", ".markdown")
HTML = (".html", ".htm")
# Linked (not shown) files that go into the help: what a page may link to
RESOURCES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp", ".ico", ".pdf",
             ".txt", ".css", ".zip", ".csv", ".json"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "td", "th", "pre", "h1", "h2", "h3", "h4", "h5",
               "h6", "table", "ul", "ol", "blockquote", "hr", "dt", "dd", "section"}
_CODE_NAME = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(?:\(.*\))?\s*(?:->.*)?$", re.S)


def slug(heading: str) -> str:
    """A heading's anchor, as GitHub makes it."""
    text = re.sub(r"[`*]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _keyword_of_heading(text: str) -> str:
    text = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", " ".join(text.split()))
    return text.strip(" :.")


# --- reading a page ----------------------------------------------------------------------------

@dataclass
class _Analysis:
    html: str
    title: str
    headings: list[tuple[int, str, str]]  # (level, title, anchor)
    sections: list[tuple[str, str, str]]  # (anchor, title, text)
    keywords: list[tuple[str, str]]  # (keyword, anchor)


class _Analyzer(HTMLParser):
    """Copies a page's HTML, giving every heading an anchor and links their
    help addresses, and collects its title, headings, sections and keywords."""

    def __init__(self, resolve):
        super().__init__(convert_charrefs=False)
        self.resolve = resolve
        self.out: list[str] = []
        self.title = ""
        self.headings: list[tuple[int, str, str]] = []
        self.sections: list[tuple[str, str, str]] = []
        self.keywords: list[tuple[str, str]] = []
        self.anchors: set[str] = set()
        self._section = ("", "")  # the current section's (anchor, title)
        self._text: list[str] = []
        self._skip = 0  # inside <script>, <style> or <head>'s <title>
        self._in_title = False
        self._heading = None  # [level, insert at, anchor, text parts, has <a name>]
        self._capture = None  # [tag, code parts, other text?, codes, depth]
        self._row_cell = -1
        self._code_depth = 0
        self._link_depth = 0  # (code in a link names what it leads to: not indexed here)

    # -- output ------------------------------------------------------------------------------
    def _tag(self, tag, attrs, close=False):
        parts = [tag]
        for name, value in attrs:
            parts.append(name if value is None else f'{name}="{escape(value, True)}"')
        return "<" + " ".join(parts) + (" />" if close else ">")

    def _attrs(self, tag, attrs):
        result = []
        for name, value in attrs:
            if value is not None and (tag, name) in (("a", "href"), ("img", "src"),
                                                     ("link", "href"), ("script", "src"),
                                                     ("source", "src")):
                value = self.resolve(value, name)
            result.append((name, value))
        return result

    # -- text --------------------------------------------------------------------------------
    def _add_text(self, text: str):
        if self._skip:
            return
        if self._in_title:
            self.title += text
            return
        if self._heading is not None:
            self._heading[3].append(text)
            return
        self._text.append(text)
        if self._capture is not None:
            if self._code_depth:
                self._capture[1].append(text)
            elif text.strip():
                self._capture[2] = True

    def _end_section(self):
        text = re.sub(r"[ \t]+", " ", "".join(self._text))
        text = re.sub(r"\s*\n\s*", "\n", text).strip()
        if text or self._section[0]:
            self.sections.append((self._section[0], self._section[1], text))
        self._text = []

    # -- parsing -----------------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, close=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, close=True)

    def _start(self, tag, attrs, close):
        attrs = self._attrs(tag, attrs)
        values = dict(attrs)
        self.out.append(self._tag(tag, attrs, close))
        if tag in ("script", "style") and not close:
            self._skip += 1
        elif tag == "title" and not close:
            self._in_title = True
        elif tag == "meta" and (values.get("name") or "").lower() == "keywords":
            for keyword in (values.get("content") or "").split(","):
                if keyword.strip():
                    self.keywords.append((keyword.strip(), ""))
        elif re.fullmatch(r"h[1-6]", tag) and not close:
            self._end_section()
            self._heading = [int(tag[1]), len(self.out), values.get("id") or "", [], False]
        elif tag == "a" and self._heading is not None and (values.get("name") or
                                                           values.get("id")):
            self._heading[2] = values.get("name") or values.get("id")
            self._heading[4] = True
        elif tag == "tr":
            self._row_cell = -1
        elif tag in ("td", "th"):
            self._row_cell += 1
            if tag == "td" and self._row_cell == 0:
                self._capture = [tag, [], False, 0]
        elif tag == "p" and self._capture is None:
            self._capture = [tag, [], False, 0]
        elif tag == "code":
            self._code_depth += 1
            if self._capture is not None:
                self._capture[3] += 1 if not self._link_depth else 2
        elif tag == "a" and values.get("href") and not close:
            self._link_depth += 1
        if tag in _BLOCK_TAGS and self._heading is None:
            self._text.append("\n" if tag != "td" and tag != "th" else " ")

    def handle_endtag(self, tag):
        self.out.append(f"</{tag}>")
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "code":
            self._code_depth = max(0, self._code_depth - 1)
        elif tag == "a":
            self._link_depth = max(0, self._link_depth - 1)
        elif re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            level, at, anchor, parts, named = self._heading
            self._heading = None
            title = " ".join(_html.unescape("".join(parts)).split())
            if not anchor:
                anchor = base = slug(title) or "section"
                number = 0
                while anchor in self.anchors:
                    number += 1
                    anchor = f"{base}-{number}"
            self.anchors.add(anchor)
            if not named:  # (Qt's browser goes to <a name>s)
                self.out.insert(at, f'<a name="{escape(anchor, True)}"></a>')
            self.headings.append((level, title, anchor))
            self._section = (anchor, title)
            keyword = _keyword_of_heading(title)
            if keyword:
                self.keywords.append((keyword, anchor))
        elif self._capture is not None and tag == self._capture[0]:
            _, code, other, codes = self._capture
            self._capture = None
            if codes == 1 and not other:
                m = _CODE_NAME.match(_html.unescape("".join(code)))
                if m:
                    self.keywords.append((m.group(1), self._section[0]))
        if tag in _BLOCK_TAGS:
            self._text.append("\n")

    def handle_data(self, data):
        self.out.append(data)
        self._add_text(data)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")
        self._add_text(_html.unescape(f"&{name};"))

    def handle_charref(self, name):
        self.out.append(f"&#{name};")
        self._add_text(_html.unescape(f"&#{name};"))

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")
        m = re.match(r"\s*keywords?\s*:(.*)$", data, re.S | re.I)
        if m:
            for keyword in m.group(1).split(","):
                if keyword.strip():
                    self.keywords.append((_html.unescape(keyword.strip()), self._section[0]))

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")

    def unknown_decl(self, data):
        self.out.append(f"<![{data}]>")

    def analyse(self, text: str) -> _Analysis:
        self.feed(text)
        self.close()
        self._end_section()
        title = " ".join(_html.unescape(self.title).split())
        return _Analysis("".join(self.out), title, self.headings, self.sections, self.keywords)


# --- the maker -----------------------------------------------------------------------------

@dataclass
class _Source:
    path: str  # its path in the help
    file: Path | None  # the document it comes from (None: made here)
    html: str = ""  # made here: its HTML
    title: str = ""
    parent: str | None = None
    toc_depth: int | None = None


@dataclass
class _Built:
    source: _Source
    analysis: _Analysis
    title: str
    children: list = field(default_factory=list)


class HelpMaker:
    """Collects documents and packages, then builds a help file of them."""

    def __init__(self, title: str = "", root: str | None = None, home: str | None = None,
                 toc_depth: int = 3, flat: tuple[str, ...] = ()):
        self.title = title
        self.root = Path(root).resolve() if root else None
        self.home = home
        self.toc_depth = toc_depth
        self.flat = tuple(flat)
        self._files: list[Path] = []
        self._generated: list[_Source] = []
        self._packages: list[tuple[list[str], dict]] = []
        self.warnings: list[str] = []

    # -- input ---------------------------------------------------------------------------
    def add(self, path: str | os.PathLike) -> None:
        """A Markdown or HTML document, or a folder of them (and its subfolders)."""
        path = Path(path).resolve()
        if path.is_dir():
            found = [p for p in path.rglob("*")
                     if p.is_file() and p.suffix.lower() in MARKDOWN + HTML and
                     not any(part.startswith(".") for part in p.relative_to(path).parts)]

            def order(p: Path):
                first = p.stem.lower() in ("readme", "index")
                return (p.relative_to(path).parent.parts, not first, p.name.lower())

            self._files += [p for p in sorted(found, key=order) if p not in self._files]
        elif path.is_file():
            if path.suffix.lower() not in MARKDOWN + HTML:
                raise ValueError(f"{path}: not a Markdown or HTML document")
            if path not in self._files:
                self._files.append(path)
        else:
            raise FileNotFoundError(str(path))

    def add_page(self, path: str, title: str, html: str = "", markdown: str = "",
                 parent: str | None = None, toc_depth: int | None = None) -> None:
        """A page made by a program: its path in the help, and its HTML (or Markdown)."""
        self._generated.append(_Source(path, None, html or to_html(markdown), title, parent,
                                       toc_depth))

    def add_packages(self, names: list[str], follow: bool = False, follow_stdlib: bool = False,
                     private: bool = False, exclude: tuple[str, ...] = ()) -> None:
        """Python packages (or modules), documented from their code."""
        self._packages.append((list(names), dict(follow=follow, follow_stdlib=follow_stdlib,
                                                  private=private, exclude=tuple(exclude))))

    # -- building -------------------------------------------------------------------------
    def _root(self) -> Path:
        if self.root is not None:
            return self.root
        if not self._files:
            return Path.cwd()
        return Path(os.path.commonpath([str(f.parent) for f in self._files]))

    def build(self, output: str | os.PathLike) -> dict:
        """Write the help file; returns its manifest (what the file describes)."""
        root = self._root()
        sources: list[_Source] = []
        by_file: dict[Path, str] = {}
        for file in self._files:
            relative = Path(os.path.relpath(file, root)).as_posix()
            if relative.startswith("../"):
                relative = "_outside/" + file.name
            if file.suffix.lower() in MARKDOWN:
                relative = relative[: -len(file.suffix)] + ".html"
            depth = 1 if any(fnmatch.fnmatch(Path(relative).name, p) or
                             fnmatch.fnmatch(file.name, p) for p in self.flat) else None
            sources.append(_Source(relative, file, toc_depth=depth))
            by_file[file] = relative
        for names, options in self._packages:
            for page in package_pages(names, **options):
                sources.append(_Source(page.path, None, page.html, page.title, page.parent, 2))
        sources += self._generated

        resources: dict[str, bytes] = {}
        built: list[_Built] = []
        digest = hashlib.sha256(f"vp6help {FORMAT} {self.toc_depth} {self.flat}".encode())
        for source in sources:
            if source.file is not None:
                data = source.file.read_bytes()
                digest.update(source.path.encode() + b"\0" + data)
                text = data.decode("utf-8", errors="replace")
                html = to_html(text) if source.file.suffix.lower() in MARKDOWN else text
                base = source.file.parent
            else:
                html = source.html
                digest.update(source.path.encode() + b"\0" + html.encode())
                base = None
            resolve = self._resolver(source, base, root, by_file, resources)
            analysis = _Analyzer(resolve).analyse(html)
            title = source.title or analysis.title or next(
                (t for level, t, _ in analysis.headings if level == 1), "") or \
                Path(source.path).stem
            built.append(_Built(source, analysis, title))
        for name in sorted(resources):
            digest.update(name.encode() + b"\0" + resources[name])

        files: dict[str, bytes] = {}
        pages, sections, index = [], [], []
        seen_index = set()
        for page in built:
            path = page.source.path
            pages.append({"path": path, "title": page.title})
            files[path] = self._document(page).encode("utf-8")
            for anchor, title, text in page.analysis.sections:
                url = f"{path}#{anchor}" if anchor else path
                sections.append({"url": url, "title": title or page.title, "page": page.title,
                                 "text": text})
            titles = {anchor: title for _, title, anchor in page.analysis.headings}
            for keyword, anchor in page.analysis.keywords:
                url = f"{path}#{anchor}" if anchor else path
                entry = (keyword, url, titles.get(anchor, page.title))
                if entry not in seen_index:
                    seen_index.add(entry)
                    index.append(list(entry))
        files.update(sorted(resources.items()))

        home = self.home or (pages[0]["path"] if pages else "")
        if home and home not in files:
            matches = [p["path"] for p in pages if p["path"].endswith(home) or
                       Path(p["path"]).stem == Path(home).stem]
            if not matches:
                raise ValueError(f"The home page {home!r} isn't one of the documents")
            home = matches[0]
        title = self.title or next((p["title"] for p in pages if p["path"] == home), "Help")
        manifest = {"format": FORMAT, "title": title, "home": home, "pages": pages,
                    "toc": self._toc(built), "index": index, "sections": sections,
                    "sources": digest.hexdigest(), "generator": f"vp6help {__version__}"}
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        write_help(str(temporary), manifest, files)
        os.replace(temporary, output)
        return manifest

    def _resolver(self, source: _Source, base: Path | None, root: Path,
                  by_file: dict[Path, str], resources: dict[str, bytes]):
        def resolve(url: str, attribute: str) -> str:
            url = url.strip()
            if not url or url.startswith("#") or url.startswith("/") or \
                    re.match(r"^[A-Za-z][\w+.-]*:", url):
                return url
            if base is None:
                return url
            path, hash_, anchor = url.partition("#")
            path = path.partition("?")[0]
            target = (base / unquote(path)).resolve()
            fragment = hash_ + anchor
            if target in by_file:
                return "/" + by_file[target] + fragment
            if target.is_file() and (attribute == "src" or target.suffix.lower() in RESOURCES):
                relative = Path(os.path.relpath(target, root)).as_posix()
                if relative.startswith("../"):
                    relative = "_files/" + hashlib.sha1(str(target).encode()).hexdigest()[:8] \
                        + "/" + target.name
                resources[relative] = target.read_bytes()
                return "/" + relative + fragment
            if not target.exists():
                self.warnings.append(f"{source.path}: {url} doesn't exist")
            return url

        return resolve

    @staticmethod
    def _document(page: _Built) -> str:
        html = page.analysis.html
        if re.search(r"<html[\s>]", html, re.I):
            return html
        return (f"<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\" />"
                f"<title>{escape(page.title)}</title></head>\n<body>\n{html}</body></html>\n")

    def _toc(self, built: list[_Built]) -> list[dict]:
        nodes: dict[str, dict] = {}
        top: list[dict] = []
        for page in built:
            path = page.source.path
            node = {"title": page.title, "url": path, "children": []}
            depth = page.source.toc_depth or self.toc_depth
            headings = [h for h in page.analysis.headings if h[0] <= depth]
            if headings and headings[0][0] == 1:
                headings = headings[1:]  # (the page's own title)
            stack: list[tuple[int, dict]] = [(0, node)]
            for level, title, anchor in headings:
                child = {"title": title, "url": f"{path}#{anchor}", "children": []}
                while len(stack) > 1 and stack[-1][0] >= level:
                    stack.pop()
                stack[-1][1]["children"].append(child)
                stack.append((level, child))
            nodes[path] = node
            parent = nodes.get(page.source.parent) if page.source.parent else None
            (parent["children"] if parent is not None else top).append(node)
        return top


# --- the command line ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vp6help-make", fromfile_prefix_chars="@",
        description="Make a VP6 help file (.vp6help) of Markdown and HTML documents (with "
                    "the pictures and files they link to) and Python packages: one file "
                    "with a table of contents, an index and searchable text, for vp6help.",
        epilog="Arguments can come from a file, one per line: vp6help-make @MyHelp.args")
    parser.add_argument("inputs", nargs="*", metavar="DOCUMENT",
                        help="Markdown (.md) and HTML (.html) documents, or folders of them; "
                             "in the order the contents should have")
    parser.add_argument("-o", "--output", required=True, help=f"the help file ({EXTENSION})")
    parser.add_argument("--title", default="", help="the help's title (default: the home "
                                                   "page's)")
    parser.add_argument("--home", help="the page the help opens at (default: the first)")
    parser.add_argument("--root", help="the folder the pages' paths are relative to (default: "
                                       "the documents' common folder)")
    parser.add_argument("--toc-depth", type=int, default=3, metavar="N",
                        help="the heading levels in the contents (default 3)")
    parser.add_argument("--flat", action="append", default=[], metavar="PATTERN",
                        help="documents (file name patterns) whose headings stay out of "
                             "the contents")
    parser.add_argument("-p", "--package", action="append", default=[], metavar="NAME",
                        help="also document a Python package or module from its code "
                             "(javadoc-style; repeat for more)")
    parser.add_argument("--follow", action="store_true",
                        help="also document the packages they import (one level)")
    parser.add_argument("--follow-stdlib", action="store_true",
                        help="with --follow: Python's standard library too")
    parser.add_argument("--private", action="store_true",
                        help="include _private modules and members")
    parser.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                        help="modules not to document (e.g. 'mypackage.tests')")
    parser.add_argument("--version", action="version", version=f"vp6help {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.inputs and not args.package:
        _parser().error("nothing to make a help file of: give documents or --package")
    maker = HelpMaker(args.title, args.root, args.home, args.toc_depth, tuple(args.flat))
    try:
        for path in args.inputs:
            maker.add(path)
        if args.package:
            maker.add_packages(args.package, args.follow, args.follow_stdlib, args.private,
                               tuple(args.exclude))
        manifest = maker.build(args.output)
    except (OSError, ValueError, ImportError) as error:
        print(f"vp6help-make: {error}", file=sys.stderr)
        return 1
    for warning in maker.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"{args.output}: {len(manifest['pages'])} pages, {len(manifest['index'])} index "
          f"entries, {len(manifest['sections'])} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
