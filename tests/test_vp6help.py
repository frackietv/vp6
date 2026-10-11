"""vp6help, the help system (packages/vp6help): Markdown to HTML, the help
maker (documents, links, pictures, contents, index, search text; Python
packages documented from their code), the .vp6help file (lookups, filters,
search) and the viewer (contents, index, search, pages, links, the command
line)."""

import os
import sys
import textwrap
import zipfile

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QPalette, QTextDocument

from vp6help import HelpFile, maker, pydoc, viewer
from vp6help.markdown import inline, to_html

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
       b"\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff"
       b"\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82")


# --- Markdown ---------------------------------------------------------------------------------

def test_markdown_blocks():
    html = to_html(textwrap.dedent("""\
        # Title `x`

        Setext
        ------

        A paragraph
        on two lines\\
        with a hard break.

        > quoted
        > text

        ---

            indented code

        ```python
        if a < b:
            pass
        ```
        <!-- keywords: a, b -->
        After the comment.
        """))
    assert "<h1>Title <code>x</code></h1>" in html and "<h2>Setext</h2>" in html
    assert "<p>A paragraph\non two lines<br />\nwith a hard break.</p>" in html
    assert "<blockquote>\n<p>quoted\ntext</p>\n</blockquote>" in html and "<hr />" in html
    assert "<pre><code>indented code</code></pre>" in html
    assert '<pre><code class="language-python">if a &lt; b:\n    pass</code></pre>' in html
    assert "<!-- keywords: a, b -->\n<p>After the comment.</p>" in html  # (comments end there)


def test_markdown_lists():
    tight = to_html("* one\n  continued\n* two\n  - nested\n  - [x] done\n  - [ ] to do\n")
    assert tight == ("<ul>\n<li>one\ncontinued</li>\n<li>two\n<ul>\n<li>nested</li>\n"
                     "<li>\u2612 done</li>\n<li>\u2610 to do</li>\n</ul></li>\n</ul>\n")
    loose = to_html("1. one\n\n2. two\n\n   more of two\n")
    assert loose == ("<ol>\n<li><p>one</p></li>\n<li><p>two</p>\n<p>more of two</p></li>\n"
                     "</ol>\n")
    assert '<ol start="3">' in to_html("3) three\n4) four\n")
    # A different kind of list starts a new one
    assert to_html("- a\n\n1. b\n").count("<li>a</li>") == 1


def test_markdown_tables():
    html = to_html("| Name | Value |\n|:--|--:|\n| `a \\| b` | **x** |\n| c |\n")
    assert '<th align="left">Name</th><th align="right">Value</th>' in html
    assert '<td align="left"><code>a | b</code></td><td align="right"><strong>x</strong></td>' \
        in html
    assert '<td align="left">c</td><td align="right"></td>' in html  # (a short row)


def test_markdown_inline():
    assert inline("*em* **strong** _em_ __strong__ ~~gone~~") == \
        "<em>em</em> <strong>strong</strong> <em>em</em> <strong>strong</strong> <del>gone</del>"
    assert inline("snake_case_name a * b") == "snake_case_name a * b"
    assert inline("`` a `b` `` and `<i>`") == "<code>a `b`</code> and <code>&lt;i&gt;</code>"
    assert inline('[the `api`](api.md#x "Title")') == \
        '<a href="api.md#x" title="Title">the <code>api</code></a>'
    assert inline("![a *b*](pic.png)") == '<img src="pic.png" alt="a b" />'
    assert inline("<https://a.b/c> and https://x.y/z_1.") == \
        '<a href="https://a.b/c">https://a.b/c</a> and <a href="https://x.y/z_1">' \
        'https://x.y/z_1</a>.'
    assert inline("<kbd>Ctrl</kbd> & \\*not\\*") == "<kbd>Ctrl</kbd> &amp; *not*"


# --- making help files ------------------------------------------------------------------------

@pytest.fixture
def documents(tmp_path):
    """A small set of documents: Markdown and HTML, a picture, links."""
    docs = tmp_path / "docs"
    (docs / "images").mkdir(parents=True)
    (docs / "images" / "dot.png").write_bytes(PNG)
    (tmp_path / "README.md").write_text(textwrap.dedent("""\
        # My Program

        Start with the [guide](docs/guide.md#saving-files) or the [API](docs/api.html).
        See https://example.com/ too.
        """))
    (docs / "guide.md").write_text(textwrap.dedent("""\
        # The guide

        ## Opening files
        <!-- keywords: Load, Read -->
        Use **Open** to open a file. ![a dot](images/dot.png)

        ### Recent files

        The recent files are listed.

        ## Saving files

        **`Save(path, overwrite=False) -> bool`**

        Saves the file. Saving twice saves twice.

        | Function | Use |
        |---|---|
        | `Close()` | closes it |
        | [`Open`](api.html) | linked: not indexed here |
        | `a + b` | not a name |
        """))
    (docs / "api.html").write_text(textwrap.dedent("""\
        <html><head><title>The API</title>
        <meta name="keywords" content="Programming, Interface"></head>
        <body><h1 id="top">API</h1><p>Back to the <a href="guide.md">guide</a>.</p>
        <h2>Calls &amp; more</h2><p>Call <code>Open</code>.</p>
        <script>var hidden = "not text";</script>
        <p>A <a href="missing.md">missing page</a>.</p></body></html>
        """))
    return tmp_path


def build(root, output, **options):
    help_maker = maker.HelpMaker(**options)
    help_maker.add(root / "README.md")
    help_maker.add(root / "docs")
    manifest = help_maker.build(output)
    return manifest, help_maker


def test_making_a_help_file(documents, tmp_path):
    output = tmp_path / "out" / "My.vp6help"
    manifest, help_maker = build(documents, output, title="My Help")
    assert [p["path"] for p in manifest["pages"]] == ["README.html", "docs/api.html",
                                                      "docs/guide.html"]
    assert manifest["home"] == "README.html" and manifest["title"] == "My Help"
    titles = {p["path"]: p["title"] for p in manifest["pages"]}
    assert titles == {"README.html": "My Program", "docs/api.html": "The API",
                      "docs/guide.html": "The guide"}
    assert help_maker.warnings == ["docs/api.html: missing.md doesn't exist"]
    with zipfile.ZipFile(output) as archive:
        assert archive.read("docs/images/dot.png") == PNG  # the picture, linked
        readme = archive.read("README.html").decode()
        guide = archive.read("docs/guide.html").decode()
        api = archive.read("docs/api.html").decode()
    # Links between the documents are links between pages; web links stay
    assert '<a href="/docs/guide.html#saving-files">guide</a>' in readme
    assert '<a href="/docs/api.html">API</a>' in readme
    assert '<a href="https://example.com/">' in readme
    assert '<img src="/docs/images/dot.png" alt="a dot" />' in guide
    assert '<a href="/docs/guide.html">guide</a>' in api
    # Every heading has an anchor the browser can go to (an id is kept)
    assert '<h2><a name="saving-files"></a>Saving files</h2>' in guide
    assert '<h1 id="top"><a name="top"></a>API</h1>' in api
    assert '<h2><a name="calls--more"></a>Calls &amp; more</h2>' in api


def test_contents_index_and_sections(documents, tmp_path):
    manifest, _ = build(documents, tmp_path / "My.vp6help")
    guide = next(node for node in manifest["toc"] if node["url"] == "docs/guide.html")
    assert [(c["title"], [g["title"] for g in c["children"]]) for c in guide["children"]] == \
        [("Opening files", ["Recent files"]), ("Saving files", [])]
    index = {(keyword, url) for keyword, url, _ in manifest["index"]}
    assert {("Opening files", "docs/guide.html#opening-files"),  # headings
            ("Load", "docs/guide.html#opening-files"),  # <!-- keywords -->
            ("Read", "docs/guide.html#opening-files"),
            ("Save", "docs/guide.html#saving-files"),  # a name standing alone
            ("Close", "docs/guide.html#saving-files"),  # a name starting a row
            ("Programming", "docs/api.html"),  # <meta name="keywords">
            ("Calls & more", "docs/api.html#calls--more")} <= index
    keywords = {keyword for keyword, _ in index}
    assert "Open" not in keywords and "a + b" not in keywords
    sections = {s["url"]: s for s in manifest["sections"]}
    saving = sections["docs/guide.html#saving-files"]
    assert saving["title"] == "Saving files" and saving["page"] == "The guide"
    assert "Saves the file. Saving twice saves twice." in saving["text"]
    assert "Saving files" not in saving["text"]  # (the heading is its title)
    assert "not text" not in sections["docs/api.html#calls--more"]["text"]  # (scripts)
    # The contents' depth; a flat document has no headings in them
    shallow, _ = build(documents, tmp_path / "Two.vp6help", toc_depth=2,
                       flat=("README.md",))
    guide = next(node for node in shallow["toc"] if node["url"] == "docs/guide.html")
    assert all(not c["children"] for c in guide["children"])


def test_the_same_documents_make_the_same_file(documents, tmp_path):
    first, _ = build(documents, tmp_path / "a.vp6help")
    second, _ = build(documents, tmp_path / "b.vp6help")
    assert (tmp_path / "a.vp6help").read_bytes() == (tmp_path / "b.vp6help").read_bytes()
    (documents / "docs" / "guide.md").write_text("# Changed\n")
    third, _ = build(documents, tmp_path / "c.vp6help")
    assert first["sources"] == second["sources"] != third["sources"]


def test_home_page_and_errors(documents, tmp_path):
    manifest, _ = build(documents, tmp_path / "a.vp6help", home="guide.md")
    assert manifest["home"] == "docs/guide.html"
    with pytest.raises(ValueError, match="home page"):
        build(documents, tmp_path / "b.vp6help", home="nowhere.md")
    with pytest.raises(ValueError, match="not a Markdown or HTML"):
        maker.HelpMaker().add(documents / "docs" / "images" / "dot.png")
    with pytest.raises(FileNotFoundError):
        maker.HelpMaker().add(documents / "nothing.md")


def test_the_make_command(documents, tmp_path, capsys):
    output = tmp_path / "cli.vp6help"
    arguments = tmp_path / "help.args"
    arguments.write_text(f"--title\nCLI Help\n{documents / 'README.md'}\n{documents / 'docs'}\n")
    assert maker.main(["-o", str(output), f"@{arguments}"]) == 0
    out, err = capsys.readouterr()
    assert "3 pages" in out and "missing.md doesn't exist" in err
    with HelpFile(str(output)) as help_:
        assert help_.title == "CLI Help"
    assert maker.main(["-o", str(output), str(documents / "nothing.md")]) == 1
    with pytest.raises(SystemExit):
        maker.main(["-o", str(output)])  # (nothing to make it of)


# --- Python packages --------------------------------------------------------------------------

@pytest.fixture
def package(tmp_path, monkeypatch):
    """A package to document: classes inheriting across modules, properties,
    constants in groups, names made public by the package."""
    root = tmp_path / "src"
    (root / "shapes").mkdir(parents=True)
    (root / "shapes" / "__init__.py").write_text(textwrap.dedent('''\
        """Shapes to draw."""
        from .base import Shape
        from .circle import Circle
        raise RuntimeError("documented without being imported")
        __all__ = ["Shape", "Circle", *[]]
        '''))
    (root / "shapes" / "base.py").write_text(textwrap.dedent('''\
        """The base class."""
        import json
        import helpers.tools


        class Shape:
            """A shape.

            Subclasses draw themselves."""

            sides = 0
            """How many sides."""

            def __init__(self, color="red"):
                self._color = color

            @property
            def color(self) -> str:
                """Its color."""
                return self._color

            @color.setter
            def color(self, value):
                self._color = value

            def area(self) -> float:
                """Its area, in ``square units``."""
                return 0.0

            def _hidden(self):
                pass


        # --- Colors ---
        RED = "red"
        BLUE = "blue"

        # --- Sizes ---
        SMALL = 1
        '''))
    (root / "shapes" / "circle.py").write_text(textwrap.dedent('''\
        from .base import Shape


        class Circle(Shape):
            """A round shape."""

            def area(self):
                return 3.14 * self.radius ** 2

            @staticmethod
            def unit(): ...
        '''))
    (root / "shapes" / "_private.py").write_text("SECRET = 1\n")
    (root / "helpers").mkdir()
    (root / "helpers" / "__init__.py").write_text('"""Helpers."""\n')
    (root / "helpers" / "tools.py").write_text('def tool(x, *, y=2):\n    """A tool."""\n')
    monkeypatch.syspath_prepend(str(root))
    return root


def test_package_pages(package):
    pages = {page.path: page for page in pydoc.package_pages(["shapes"])}
    assert list(pages) == ["python/index.html", "python/shapes.html", "python/shapes.base.html",
                           "python/shapes.circle.html"]  # (not _private)
    assert "shapes" not in sys.modules  # read, not imported
    assert pages["python/shapes.base.html"].parent == "python/shapes.html"
    assert pages["python/shapes.html"].parent == "python/index.html"
    base = pages["python/shapes.base.html"].html
    assert '<h2 id="Shape">Shape</h2>' in base and "<pre>class Shape(color='red')" in base
    assert '<h3 id="Shape.color">Shape.color</h3><!-- keywords: color -->' in base
    assert "<pre>color: str</pre>" in base and "Its area, in <code>square units</code>" in base
    assert "<pre>sides = 0</pre>" in base and "How many sides." in base
    assert "<pre>area() -&gt; float</pre>" in base and "_hidden" not in base
    assert "<h3>Colors</h3>" in base and "<h3>Sizes</h3>" in base
    assert "<td><code>RED</code></td><td><code>'red'</code></td>" in base
    circle = pages["python/shapes.circle.html"].html
    assert 'bases: <a href="/python/shapes.base.html#Shape">Shape</a>' in circle
    assert "<pre>unit()</pre>" in circle and "static method" in circle
    assert 'Inherited from <a href="/python/shapes.base.html#Shape">Shape</a>: ' \
           '<a href="/python/shapes.base.html#Shape.color"><code>color</code></a>, ' \
           '<a href="/python/shapes.base.html#Shape.sides"><code>sides</code></a>' in circle
    package_page = pages["python/shapes.html"].html
    assert '<a href="/python/shapes.circle.html#Circle"><code>Circle</code></a>' in package_page
    assert "python/shapes._private.html" in {p.path for p in pydoc.package_pages(
        ["shapes"], private=True)}


def test_following_the_packages_used(package):
    paths = [page.path for page in pydoc.package_pages(["shapes"], follow=True)]
    assert "python/helpers.tools.html" in paths  # (imported by shapes.base)
    assert "python/json.html" not in paths  # (the standard library: not unless asked)
    paths = [page.path for page in pydoc.package_pages(["shapes"], follow=True,
                                                       exclude=("helpers",))]
    assert "python/helpers.html" not in paths
    with pytest.raises(ImportError):
        pydoc.package_pages(["no_such_package_here"])


def test_compiled_modules_are_inspected():
    import math

    page = next(p for p in pydoc.package_pages(["math"]) if p.path == "python/math.html")
    if not (getattr(math, "__file__", "") or "").endswith(".py"):
        assert '<h3 id="sqrt">sqrt</h3>' in page.html and "<code>pi</code>" in page.html


def test_package_in_a_help_file(package, tmp_path):
    help_maker = maker.HelpMaker("Shapes")
    help_maker.add_packages(["shapes"])
    manifest = help_maker.build(tmp_path / "shapes.vp6help")
    assert manifest["toc"][0]["url"] == "python/index.html"
    shapes = manifest["toc"][0]["children"][0]
    assert shapes["url"] == "python/shapes.html"
    assert [c["url"] for c in shapes["children"] if "#" not in c["url"]] == \
        ["python/shapes.base.html", "python/shapes.circle.html"]
    with HelpFile(str(tmp_path / "shapes.vp6help")) as help_:
        assert [e.url for e in help_.lookup("area")] == ["python/shapes.base.html#Shape.area",
                                                         "python/shapes.circle.html#Circle.area"]
        assert help_.lookup("Circle")[0].url == "python/shapes.circle.html#Circle"
        assert help_.lookup("RED")[0].url == "python/shapes.base.html#colors"


# --- the help file --------------------------------------------------------------------------

@pytest.fixture
def help_file(documents, tmp_path):
    build(documents, tmp_path / "My.vp6help")
    with HelpFile(str(tmp_path / "My.vp6help")) as help_:
        yield help_


def test_lookups(help_file):
    assert [e.url for e in help_file.lookup("save")] == ["docs/guide.html#saving-files"]
    assert help_file.lookup("save", case=True) == []
    assert {e.keyword for e in help_file.lookup("sav")} == {"Save", "Saving files"}  # (prefix)
    assert help_file.keywords("open") == ["Opening files"]
    assert help_file.keywords("^(Load|Read)$", regex=True) == ["Load", "Read"]
    assert help_file.keywords("load", case=True) == []
    with pytest.raises(Exception):
        help_file.keywords("(", regex=True)
    keywords = help_file.keywords()
    assert keywords == sorted(keywords, key=str.casefold)
    assert help_file.page_title("docs/guide.html#x") == "The guide"
    assert help_file.section_title("docs/guide.html#recent-files") == "Recent files"
    assert help_file.read("docs/images/dot.png") == PNG and help_file.read("nope") is None
    assert help_file.read("vp6help.json") is None


def test_search(help_file):
    hits = help_file.search("sav")
    assert hits[0].url == "docs/guide.html#saving-files" and hits[0].count == 5
    assert [h.count for h in hits] == sorted((h.count for h in hits), reverse=True)
    assert help_file.search("Sav", case=True)[0].count == 4
    assert [h.url for h in help_file.search(r"\btwice\b", regex=True)] == \
        ["docs/guide.html#saving-files"]
    assert help_file.search("") == [] and help_file.search("zzz") == []


def test_not_a_help_file(tmp_path):
    path = tmp_path / "other.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("x.txt", "x")
    with pytest.raises(ValueError, match="not a VP6 help file"):
        HelpFile(str(path))


# --- the viewer -------------------------------------------------------------------------------

@pytest.fixture
def window(qapp, documents, tmp_path):
    build(documents, tmp_path / "My.vp6help", title="My Help")
    help_window = viewer.show_help(str(tmp_path / "My.vp6help"))
    yield help_window
    help_window.close()


def test_viewer_opens_at_home(window):
    assert window.current_page() == "README.html"
    assert window.windowTitle() == "My Help \u2014 My Program"
    assert window.tabs.currentIndex() == 0
    top = [window.contents.topLevelItem(i).text(0)
           for i in range(window.contents.topLevelItemCount())]
    assert top == ["My Program", "The API", "The guide"]
    assert "Start with the guide" in window.browser.toPlainText()


def test_viewer_contents_and_links(window, monkeypatch):
    guide = window.contents.topLevelItem(2)
    window._on_contents_item(guide.child(1))  # Saving files
    assert window.current_page() == "docs/guide.html#saving-files"
    # A picture from the help file
    window.show_page("docs/guide.html")
    image = window.browser.document().resource(QTextDocument.ImageResource,
                                                QUrl("vp6help:///docs/images/dot.png"))
    assert image is not None and not image.isNull()
    # Links: to another page, back and forward, to the web
    window.open_url(QUrl("/docs/api.html"))
    assert window.current_page() == "docs/api.html"
    window.browser.backward()
    assert window.current_page() == "docs/guide.html"
    window.browser.forward()
    assert window.current_page() == "docs/api.html"
    opened = []
    monkeypatch.setattr(viewer.QDesktopServices, "openUrl", lambda url: opened.append(url))
    window.open_url(QUrl("https://example.com/"))
    assert opened == [QUrl("https://example.com/")] and window.current_page() == "docs/api.html"
    window.show_page("docs/nothing.html")
    assert "This help has no page /docs/nothing.html" in window.browser.toPlainText()
    window.show_page("docs/guide.html#recent-files")
    window.locate_in_contents()
    assert window.contents.currentItem().text(0) == "Recent files"
    window.go_home()
    assert window.current_page() == "README.html"


def test_viewer_index(window):
    window.show_index("files")
    shown = [window.index_list.topLevelItem(i).text(0)
             for i in range(window.index_list.topLevelItemCount())]
    assert shown == ["Opening files", "Recent files", "Saving files"]
    assert window.index_status.text() == f"3 of {len(window.help.keywords())} keywords"
    window.index_regex.setChecked(True)
    window.index_filter.setText("^(Load|Close)$")
    assert window.index_list.topLevelItemCount() == 2
    window.index_filter.setText("(")
    assert window.index_status.text().startswith("Not a regular expression")
    window.index_regex.setChecked(False)
    window.index_case.setChecked(True)
    window.index_filter.setText("load")
    assert window.index_list.topLevelItemCount() == 0
    window.index_case.setChecked(False)
    window.index_filter.returnPressed.emit()  # Enter: the first keyword's topic
    assert window.current_page() == "docs/guide.html#opening-files"
    assert window.show_keyword("Save")
    assert window.current_page() == "docs/guide.html#saving-files"
    assert window.index_list.currentItem().text(0) == "Save"
    assert not window.show_keyword("Nothing at all")


def test_viewer_keyword_with_several_topics(window, help_file):
    # Two pages with the same keyword: the topic named like the context first
    help_ = window.help
    from vp6help.helpfile import IndexEntry

    help_.index += [IndexEntry("Shared", "docs/guide.html#recent-files", "Recent files"),
                    IndexEntry("Shared", "docs/api.html#calls--more", "Calls & more")]
    window._fill_index()
    assert window.show_keyword("Shared")
    assert window.current_page() == "docs/guide.html#recent-files"
    item = window.index_list.currentItem()
    assert item.childCount() == 2 and item.child(1).text(0) == "Calls & more \u2014 The API"
    assert window.show_keyword("Shared", context="calls")
    assert window.current_page() == "docs/api.html#calls--more"


def test_viewer_search(window):
    count = window.show_search("saving")
    assert count == window.search_results.topLevelItemCount() > 0
    assert window.tabs.currentIndex() == 2
    assert window.current_page() == "docs/guide.html#saving-files"
    assert [m.lower() for m in window.search_matches()] == ["saving", "saving"]
    assert window.browser.textCursor().selectedText().lower() == "saving"
    assert window.show_search("Saving", case=True) > 0
    assert window.search_matches() == ["Saving", "Saving"]
    assert window.show_search(r"sav(es|ing)\b", regex=True) > 0
    assert sorted(set(window.search_matches())) == ["Saves", "Saving", "saves"]
    assert window.show_search("(", regex=True) == 0
    assert window.search_status.text().startswith("Not a regular expression")
    assert window.show_search("zzz") == 0 and window.search_status.text() == "No topics found"
    window.show_page("README.html")  # (going elsewhere: no more highlights)
    assert window.search_matches() == []


def test_viewer_requests_and_one_window_per_file(window):
    again = viewer.show_help(window.help.path, page="docs/api.html#calls--more")
    assert again is window and window.current_page() == "docs/api.html#calls--more"
    viewer.show_help(window.help.path, keyword="Close")
    assert window.current_page() == "docs/guide.html#saving-files"
    viewer.show_help(window.help.path, search="twice")
    assert window.tabs.currentIndex() == 2 and window.search_text.text() == "twice"
    viewer.show_help(window.help.path, index="^Re", regex=True)
    assert window.tabs.currentIndex() == 1 and window.index_list.topLevelItemCount() == 2
    viewer.show_help(window.help.path, keyword="Nothing like it")  # not indexed: searched
    assert window.tabs.currentIndex() == 2 and window.search_text.text() == "Nothing like it"


def test_viewer_colors_follow_the_palette(window):
    css = viewer._css(window.browser.palette())
    dark = QPalette(window.browser.palette())
    dark.setColor(QPalette.Base, "#1e1e1e")
    dark.setColor(QPalette.Text, "#e0e0e0")
    dark.setColor(QPalette.Link, "#0000ff")
    dark_css = viewer._css(dark)
    assert dark_css != css and "color: #6cb6ff" in dark_css  # (a readable link)
    window.browser.setPalette(dark)
    window.setPalette(dark)
    assert window.browser.document().defaultStyleSheet() == dark_css


def test_viewer_command_line(documents, tmp_path, capsys):
    path = str(tmp_path / "My.vp6help")
    build(documents, tmp_path / "My.vp6help")
    assert viewer.main([path, "--list"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("My Program (home: README.html)\n")
    assert "docs/guide.html#saving-files\tSaving files\n" in out
    assert viewer.main([path, "--list", "--keyword", "close"]) == 0
    assert capsys.readouterr().out == "docs/guide.html#saving-files\tClose\tSaving files\n"
    assert viewer.main([path, "--list", "--search", "twice"]) == 0
    assert capsys.readouterr().out.startswith("docs/guide.html#saving-files\t2\tSaving files")
    assert viewer.main([path, "--list", "--index", "^(save|close)$", "--regex"]) == 0
    assert capsys.readouterr().out == "Close\nSave\n"
    assert viewer.main([path, "--list", "--search", "(", "--regex"]) == 2
    assert viewer.main([str(tmp_path / "none.vp6help")]) == 1
    assert "no such file" in capsys.readouterr().err


def test_the_project(tmp_path):
    tomllib = pytest.importorskip("tomllib")
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "packages", "vp6help")
    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        project = tomllib.load(f)["project"]
    import vp6help

    assert project["name"] == "vp6help" and project["version"] == vp6help.__version__
    assert project["scripts"] == {"vp6help": "vp6help.viewer:main",
                                  "vp6help-make": "vp6help.maker:main"}
    assert project["dependencies"] == ["PySide6>=6.6"]
