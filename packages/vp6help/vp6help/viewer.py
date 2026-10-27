"""The help viewer: a ``.vp6help`` file in a window, as .chm help was shown.

On the left, three tabs: **Contents** (the documents and their headings),
**Index** (the keywords alphabetically, narrowed by what is typed: text or a
regular expression, matching case or not) and **Search** (every section of
the help, text or a regular expression, the most matches first; the matches
are highlighted on the page). On the right, the page, with Back, Forward and
Home, and links between pages; web links open in the browser.

Any page, place, keyword or search can be asked for:

    vp6help MyHelp.vp6help docs/api.html#textbox      # a page (and a place in it)
    vp6help MyHelp.vp6help --keyword MsgBox            # what the index has for it
    vp6help MyHelp.vp6help --index "^Show" --regex     # the index, narrowed
    vp6help MyHelp.vp6help --search "Tab(Index|Stop)" --regex --case
    vp6help MyHelp.vp6help --list [--keyword K | --search S]   # print, no window

    show_help("MyHelp.vp6help", keyword="MsgBox")       # from Python (a Qt program)

Pages are addressed as ``vp6help:///<page path>#<anchor>`` inside the viewer.
Formulas (``$…$`` in the Markdown) are drawn in the page's font and colours;
copying them gives their TeX.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from PySide6.QtCore import QEvent, QPoint, QRegularExpression, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QImage, QKeySequence, QPalette, QTextDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QPushButton, QSplitter, QStyle, QTabWidget,
                               QTextBrowser, QTextEdit, QToolBar, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import __version__, texdraw
from .helpfile import HelpFile, compile_pattern

__all__ = ["SCHEME", "HelpViewer", "show_help", "main"]

SCHEME = "vp6help"
URL_ROLE = Qt.UserRole
_viewers: dict[str, "HelpViewer"] = {}  # one window per help file (show_help)


def help_url(path: str) -> QUrl:
    """The viewer's address of a page (``docs/api.html#textbox``)."""
    if path.startswith(f"{SCHEME}:"):
        return QUrl(path)
    page, _, anchor = path.partition("#")
    url = QUrl()
    url.setScheme(SCHEME)
    url.setPath("/" + page.lstrip("/"))
    if anchor:
        url.setFragment(anchor)
    return url


def page_of(url: QUrl) -> str:
    """A page's path and anchor in the help from its address."""
    path = url.path().lstrip("/")
    return f"{path}#{url.fragment()}" if url.fragment() else path


def _css(palette: QPalette) -> str:
    text, base = palette.color(QPalette.Text), palette.color(QPalette.Base)
    dark = base.lightness() < 128

    def mix(amount: float) -> str:
        return "#%02x%02x%02x" % tuple(round(b + (t - b) * amount) for t, b in
                                       ((text.red(), base.red()), (text.green(), base.green()),
                                        (text.blue(), base.blue())))

    link = palette.color(QPalette.Link)
    luminance = 0.2126 * link.redF() + 0.7152 * link.greenF() + 0.0722 * link.blueF()
    link = "#6cb6ff" if dark and luminance < 0.3 else link.name()  # (readable on dark)
    mono = "Menlo, Consolas, 'DejaVu Sans Mono', 'Courier New', monospace"
    return f"""
a {{ color: {link}; text-decoration: none; }}
code {{ font-family: {mono}; background-color: {mix(0.08)}; }}
pre {{ font-family: {mono}; background-color: {mix(0.06)}; margin-top: 4px;
       margin-bottom: 8px; padding: 6px; white-space: pre-wrap; }}
pre code {{ background-color: transparent; }}
table {{ border-collapse: collapse; border-style: solid; border-width: 1px;
         border-color: {mix(0.25)}; margin-top: 4px; margin-bottom: 8px; }}
th {{ background-color: {mix(0.1)}; font-weight: bold; }}
td, th {{ padding: 4px; border-style: solid; border-width: 1px;
          border-color: {mix(0.25)}; }}
h1, h2, h3 {{ margin-top: 14px; margin-bottom: 6px; }}
blockquote {{ color: {mix(0.7)}; margin-left: 16px; }}
p.kind {{ color: {mix(0.55)}; font-style: italic; margin-top: 0px; }}
"""


class HelpBrowser(QTextBrowser):
    """The page: reads pages and pictures from the help file."""

    def __init__(self, viewer: "HelpViewer"):
        super().__init__()
        self.viewer = viewer
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def changeEvent(self, event):
        super().changeEvent(event)
        # (the page's own palette: the window's changes before it has it)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange) and \
                getattr(self.viewer, "browser", None) is self:
            self.viewer._restyle()

    def doSetSource(self, name, type=QTextDocument.UnknownResource):
        super().doSetSource(name, type)
        texdraw.install(self.document())  # (the page's formulas: drawn, not pictures)

    def createMimeDataFromSelection(self):
        return texdraw.mime_data(self.textCursor()) or super().createMimeDataFromSelection()

    def loadResource(self, kind, url):
        if url.scheme() == texdraw.SCHEME:  # (a formula: drawn once the page is in)
            image = QImage(1, 1, QImage.Format_ARGB32)
            image.fill(0)
            return image
        if url.scheme() != SCHEME:
            return super().loadResource(kind, url)
        help_ = self.viewer.help
        data = help_.read(url.path()) if help_ is not None else None
        if kind == QTextDocument.ImageResource:
            if data is None:
                return None
            image = QImage()
            image.loadFromData(data)
            return image
        if data is None:
            if kind == QTextDocument.HtmlResource:
                return self.viewer._missing_page(url)
            return None
        return data.decode("utf-8", errors="replace")


class HelpViewer(QMainWindow):
    """A help file's window: the contents, index and search, and the pages."""

    pageChanged = Signal(str)  # the page (and anchor) shown

    def __init__(self, path: str | None = None, parent=None):
        super().__init__(parent)
        self.help: HelpFile | None = None
        self._pattern: QRegularExpression | None = None  # the search shown on the page
        self.resize(1000, 720)
        self.browser = HelpBrowser(self)
        self.browser.anchorClicked.connect(self.open_url)
        self.browser.sourceChanged.connect(self._on_source_changed)
        self._apply_style()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._contents_tab(), "&Contents")
        self.tabs.addTab(self._index_tab(), "I&ndex")
        self.tabs.addTab(self._search_tab(), "&Search")

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 720])
        self.splitter = splitter
        self.setCentralWidget(splitter)
        self._toolbar()
        if path is not None:
            self.load(path)

    # -- building ---------------------------------------------------------------------------
    def _toolbar(self) -> None:
        bar = QToolBar("Navigation")
        bar.setObjectName("navigation")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(bar)
        style = self.style()

        def action(text, icon, slot, keys=()):
            act = QAction(style.standardIcon(icon), text, self)
            act.triggered.connect(lambda _=False: slot())
            if keys:
                act.setShortcuts([QKeySequence(k) for k in keys])
            bar.addAction(act)
            return act

        self.act_back = action("Back", QStyle.SP_ArrowBack, self.browser.backward,
                               (QKeySequence.Back, "Alt+Left"))
        self.act_forward = action("Forward", QStyle.SP_ArrowForward, self.browser.forward,
                                  (QKeySequence.Forward, "Alt+Right"))
        self.act_home = action("Home", QStyle.SP_DirHomeIcon, self.go_home, ("Alt+Home",))
        self.act_locate = action("Locate", QStyle.SP_FileDialogContentsView,
                                 self.locate_in_contents)
        self.act_locate.setToolTip("Show the page in the contents")
        self.act_back.setEnabled(False)
        self.act_forward.setEnabled(False)
        self.browser.backwardAvailable.connect(self.act_back.setEnabled)
        self.browser.forwardAvailable.connect(self.act_forward.setEnabled)
        for keys, slot in ((QKeySequence.ZoomIn, lambda: self.browser.zoomIn(1)),
                           (QKeySequence.ZoomOut, lambda: self.browser.zoomOut(1)),
                           (QKeySequence.Close, self.close)):
            act = QAction(self)
            act.setShortcut(keys)
            act.triggered.connect(lambda _=False, s=slot: s())
            self.addAction(act)

    def _contents_tab(self) -> QWidget:
        self.contents = QTreeWidget()
        self.contents.setHeaderHidden(True)
        self.contents.itemClicked.connect(self._on_contents_item)
        self.contents.itemActivated.connect(self._on_contents_item)
        return self.contents

    def _options(self) -> tuple[QCheckBox, QCheckBox, QHBoxLayout]:
        regex, case = QCheckBox("Regular e&xpression"), QCheckBox("&Match case")
        row = QHBoxLayout()
        row.addWidget(regex)
        row.addWidget(case)
        row.addStretch(1)
        return regex, case, row

    def _index_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Type in the &keyword to find:"))
        self.index_filter = QLineEdit()
        self.index_filter.setClearButtonEnabled(True)
        layout.itemAt(0).widget().setBuddy(self.index_filter)
        layout.addWidget(self.index_filter)
        self.index_regex, self.index_case, row = self._options()
        layout.addLayout(row)
        self.index_list = QTreeWidget()
        self.index_list.setHeaderHidden(True)
        self.index_list.setUniformRowHeights(True)
        self.index_list.itemClicked.connect(self._on_index_item)
        self.index_list.itemActivated.connect(self._on_index_item)
        layout.addWidget(self.index_list)
        self.index_status = QLabel()
        layout.addWidget(self.index_status)
        self.index_filter.textChanged.connect(self._fill_index)
        self.index_filter.returnPressed.connect(self._open_first_index_item)
        self.index_regex.toggled.connect(self._fill_index)
        self.index_case.toggled.connect(self._fill_index)
        return page

    def _search_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Type in the &word(s) to search for:"))
        row = QHBoxLayout()
        self.search_text = QLineEdit()
        self.search_text.setClearButtonEnabled(True)
        layout.itemAt(0).widget().setBuddy(self.search_text)
        self.search_button = QPushButton("&List Topics")
        row.addWidget(self.search_text, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.search_regex, self.search_case, options = self._options()
        layout.addLayout(options)
        self.search_results = QTreeWidget()
        self.search_results.setHeaderLabels(["Topic", "Location", "Matches"])
        self.search_results.setRootIsDecorated(False)
        self.search_results.setUniformRowHeights(True)
        self.search_results.itemClicked.connect(self._on_search_item)
        self.search_results.itemActivated.connect(self._on_search_item)
        layout.addWidget(self.search_results)
        self.search_status = QLabel()
        layout.addWidget(self.search_status)
        self.search_text.returnPressed.connect(self.run_search)
        self.search_button.clicked.connect(lambda: self.run_search())
        return page

    # -- the help file ----------------------------------------------------------------------
    def load(self, path: str) -> None:
        """Show a help file (at its home page)."""
        help_ = HelpFile(path)
        if self.help is not None:
            self.help.close()
        self.help = help_
        self.contents.clear()
        self._fill_contents(self.contents.invisibleRootItem(), help_.toc)
        self._fill_index()
        self.search_results.clear()
        self.search_status.clear()
        self.browser.clearHistory()
        self.go_home()

    def _fill_contents(self, parent: QTreeWidgetItem, nodes: list[dict]) -> None:
        for node in nodes:
            item = QTreeWidgetItem(parent, [node["title"]])
            item.setData(0, URL_ROLE, node["url"])
            item.setToolTip(0, node["title"])
            if node.get("children"):
                self._fill_contents(item, node["children"])

    def _fill_index(self, *_):
        self.index_list.clear()
        if self.help is None:
            return
        try:
            keywords = self.help.keywords(self.index_filter.text(), self.index_regex.isChecked(),
                                          self.index_case.isChecked())
        except re.error as error:
            self.index_status.setText(f"Not a regular expression: {error}")
            return
        items = []
        for keyword in keywords:
            item = QTreeWidgetItem([keyword])
            entries = self.help.entries(keyword)
            item.setData(0, URL_ROLE, entries[0].url)
            if len(entries) > 1:
                for entry in entries:
                    child = QTreeWidgetItem(item, [self._topic_name(entry.title, entry.url)])
                    child.setData(0, URL_ROLE, entry.url)
            items.append(item)
        self.index_list.addTopLevelItems(items)
        total = len(self.help.keywords())
        self.index_status.setText(f"{len(keywords)} of {total} keywords" if
                                  self.index_filter.text() else f"{total} keywords")
        if items:
            self.index_list.setCurrentItem(items[0])

    def _topic_name(self, title: str, url: str) -> str:
        page = self.help.page_title(url)
        return title if title == page else f"{title} — {page}"

    # -- showing pages ----------------------------------------------------------------------
    def open_url(self, url: QUrl | str) -> None:
        """Follow a link: a page of the help, or a web address in the browser."""
        if isinstance(url, str):
            url = help_url(url) if not re.match(r"^[A-Za-z][\w+.-]*:", url) or \
                url.startswith(f"{SCHEME}:") else QUrl(url)
        if url.scheme() in ("", SCHEME):
            if not url.scheme():
                url = self.browser.source().resolved(url)
            self._pattern = None
            self._show(url)
        else:
            QDesktopServices.openUrl(url)

    def show_page(self, page: str) -> None:
        """Show a page of the help (its path, with ``#anchor`` for a place in it)."""
        self.open_url(help_url(page))

    def go_home(self) -> None:
        if self.help is not None and self.help.home:
            self.show_page(self.help.home)

    def _show(self, url: QUrl) -> None:
        current = self.browser.source()
        if current.isValid() and current == url:
            self.browser.reload()  # (the same place: setSource wouldn't scroll back)
            if url.fragment():
                self.browser.scrollToAnchor(url.fragment())
        else:
            self.browser.setSource(url)
        self._highlight()

    def current_page(self) -> str:
        """The page shown (and its anchor)."""
        return page_of(self.browser.source())

    def _on_source_changed(self, url: QUrl) -> None:
        page = page_of(url)
        if self.help is not None:
            title = self.help.page_title(page)
            self.setWindowTitle(f"{self.help.title} — {title}" if title != self.help.title
                                else self.help.title)
        self.pageChanged.emit(page)

    def _missing_page(self, url: QUrl) -> str:
        from html import escape

        return (f"<h1>Not found</h1><p>This help has no page <code>{escape(url.path())}"
                f"</code>.</p>")

    def locate_in_contents(self) -> None:
        """Select the contents item of the page shown (its nearest heading)."""
        page = self.current_page()
        path = page.partition("#")[0]
        best = None
        iterator = [self.contents.topLevelItem(i) for i in range(self.contents.topLevelItemCount())]
        while iterator:
            item = iterator.pop(0)
            url = item.data(0, URL_ROLE) or ""
            if url == page:
                best = item
                break
            if url == path and best is None:
                best = item
            iterator[:0] = [item.child(i) for i in range(item.childCount())]
        self.tabs.setCurrentIndex(0)
        if best is not None:
            self.contents.setCurrentItem(best)
            self.contents.scrollToItem(best)

    # -- contents, index and search -----------------------------------------------------------
    def _on_contents_item(self, item, _column=0) -> None:
        url = item.data(0, URL_ROLE)
        if url:
            self.show_page(url)

    def _on_index_item(self, item, _column=0) -> None:
        url = item.data(0, URL_ROLE)
        if item.childCount():
            item.setExpanded(True)
        if url:
            self.show_page(url)

    def _open_first_index_item(self) -> None:
        item = self.index_list.currentItem() or self.index_list.topLevelItem(0)
        if item is not None:
            self._on_index_item(item)

    def show_contents(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.contents.setFocus()

    def show_index(self, text: str = "", regex: bool = False, case: bool = False) -> None:
        """The Index tab, narrowed to the keywords containing a text (or
        matching a regular expression)."""
        self.tabs.setCurrentIndex(1)
        for box, value in ((self.index_regex, regex), (self.index_case, case)):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)
        self.index_filter.setText(text)
        self._fill_index()
        self.index_filter.setFocus()

    def show_keyword(self, keyword: str, context: str = "") -> bool:
        """Show what the index has for a keyword (the topic whose title or
        page mentions ``context`` first, e.g. a property's control); the
        Index tab lists it. False when the index hasn't got it."""
        self.show_index(keyword)
        entries = self.help.lookup(keyword) if self.help is not None else []
        if not entries:
            return False
        best = entries[0]
        if context:
            low = context.casefold()
            best = next((e for e in entries if e.title.casefold() == low), None) or next(
                (e for e in entries if low in e.title.casefold() or
                 low in self.help.page_title(e.url).casefold()), best)
        for i in range(self.index_list.topLevelItemCount()):
            item = self.index_list.topLevelItem(i)
            if item.text(0).casefold() == best.keyword.casefold():
                self.index_list.setCurrentItem(item)
                if item.childCount():
                    item.setExpanded(True)
                break
        self.show_page(best.url)
        return True

    def show_search(self, text: str, regex: bool = False, case: bool = False) -> int:
        """The Search tab with a search's results, the first one shown;
        returns how many sections matched."""
        self.tabs.setCurrentIndex(2)
        self.search_text.setText(text)
        self.search_regex.setChecked(regex)
        self.search_case.setChecked(case)
        return self.run_search(open_first=True)

    def run_search(self, open_first: bool = False) -> int:
        self.search_results.clear()
        text = self.search_text.text()
        if self.help is None or not text:
            self.search_status.clear()
            return 0
        regex, case = self.search_regex.isChecked(), self.search_case.isChecked()
        try:
            hits = self.help.search(text, regex, case)
        except re.error as error:
            self.search_status.setText(f"Not a regular expression: {error}")
            return 0
        for hit in hits:
            item = QTreeWidgetItem([hit.title, hit.page, str(hit.count)])
            item.setData(0, URL_ROLE, hit.url)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            self.search_results.addTopLevelItem(item)
        self.search_results.resizeColumnToContents(2)
        self.search_status.setText(f"{len(hits)} topics found" if hits else "No topics found")
        if hits:
            first = self.search_results.topLevelItem(0)
            self.search_results.setCurrentItem(first)
            if open_first:
                self._on_search_item(first)
        return len(hits)

    def _on_search_item(self, item, _column=0) -> None:
        url = item.data(0, URL_ROLE)
        if not url:
            return
        text = self.search_text.text()
        regex, case = self.search_regex.isChecked(), self.search_case.isChecked()
        pattern = QRegularExpression(text if regex else QRegularExpression.escape(text))
        if not case:
            pattern.setPatternOptions(QRegularExpression.CaseInsensitiveOption)
        self._show(help_url(url))
        self._pattern = pattern if pattern.isValid() and text else None
        self._highlight()

    def _highlight(self) -> None:
        """Mark the search's matches on the page; the first one at or after the
        place shown is selected."""
        if self._pattern is None:
            self.browser.setExtraSelections([])
            return
        document = self.browser.document()
        selections = []
        color = self.palette().color(QPalette.Highlight)
        color.setAlpha(90)
        cursor = document.find(self._pattern, 0)
        while not cursor.isNull() and len(selections) < 2000:
            if cursor.hasSelection():
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(color)
                selections.append(selection)
                cursor = document.find(self._pattern, cursor)
            else:
                cursor = document.find(self._pattern, cursor.position() + 1)
        self.browser.setExtraSelections(selections)
        top = self.browser.cursorForPosition(QPoint(0, 0)).position()
        first = next((s.cursor for s in selections if s.cursor.selectionStart() >= top),
                     selections[0].cursor if selections else None)
        if first is not None:
            self.browser.setTextCursor(first)
            self.browser.ensureCursorVisible()

    def search_matches(self) -> list[str]:
        """The matches highlighted on the page."""
        return [s.cursor.selectedText() for s in self.browser.extraSelections()]

    # -- requests -----------------------------------------------------------------------------
    def apply(self, page: str | None = None, keyword: str | None = None,
              search: str | None = None, index: str | None = None, regex: bool = False,
              case: bool = False, context: str = "") -> None:
        """Show what was asked for: a page, a keyword, a search or the index
        (narrowed); otherwise the contents."""
        if search:
            self.show_search(search, regex, case)
        elif keyword:
            if not self.show_keyword(keyword, context):
                self.show_search(keyword)  # (not in the index: search for it)
        elif index is not None:
            self.show_index(index, regex, case)
        else:
            self.show_contents()
        if page:
            self.show_page(page)

    # -- appearance ----------------------------------------------------------------------------
    def _apply_style(self) -> None:
        self.browser.document().setDefaultStyleSheet(_css(self.browser.palette()))

    def _restyle(self) -> None:
        """The page's colors for a new palette (light or dark)."""
        self._apply_style()
        if self.browser.source().isValid():
            self.browser.reload()
            self._highlight()

    def closeEvent(self, event):
        super().closeEvent(event)
        for key, viewer in list(_viewers.items()):
            if viewer is self:
                del _viewers[key]


def show_help(path: str, page: str | None = None, keyword: str | None = None,
              search: str | None = None, index: str | None = None, regex: bool = False,
              case: bool = False, context: str = "", parent=None) -> HelpViewer:
    """Show a help file (in its window, if it is open already) at a page, at
    what its index has for a keyword, with a search's results, or with its
    index narrowed. Needs a QApplication."""
    key = os.path.normcase(os.path.abspath(path))
    viewer = _viewers.get(key)
    if viewer is not None:
        try:
            viewer.isVisible()
        except RuntimeError:  # (deleted with its parent)
            viewer = None
    if viewer is None:
        viewer = HelpViewer(path, parent)
        if parent is not None:
            viewer.setWindowFlag(Qt.Window, True)
        _viewers[key] = viewer
    viewer.apply(page, keyword, search, index, regex, case, context)
    viewer.show()
    viewer.raise_()
    viewer.activateWindow()
    return viewer


# --- the command line ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vp6help", description="Show a VP6 help file (.vp6help): its contents, index and "
                                    "search, at a page, keyword or search.")
    parser.add_argument("file", help="the help file")
    parser.add_argument("page", nargs="?", help="a page to show, e.g. docs/api.html#textbox")
    parser.add_argument("-k", "--keyword", help="show what the index has for a keyword")
    parser.add_argument("-s", "--search", help="search the whole help")
    parser.add_argument("-i", "--index", metavar="FILTER",
                        help="show the index, narrowed to the keywords containing FILTER")
    parser.add_argument("-r", "--regex", action="store_true",
                        help="--search and --index are regular expressions")
    parser.add_argument("-c", "--case", action="store_true",
                        help="--search and --index match case")
    parser.add_argument("-l", "--list", action="store_true",
                        help="print instead of showing: the pages and their sections, or "
                             "what --keyword, --search or --index find")
    parser.add_argument("--version", action="version", version=f"vp6help {__version__}")
    return parser


def _list(args, out) -> int:
    with HelpFile(args.file) as help_:
        try:
            if args.search:
                for hit in help_.search(args.search, args.regex, args.case):
                    print(f"{hit.url}\t{hit.count}\t{hit.title} ({hit.page})", file=out)
            elif args.keyword:
                for entry in help_.lookup(args.keyword, args.case):
                    print(f"{entry.url}\t{entry.keyword}\t{entry.title}", file=out)
            elif args.index is not None:
                for keyword in help_.keywords(args.index, args.regex, args.case):
                    print(keyword, file=out)
            else:
                print(f"{help_.title} (home: {help_.home})", file=out)
                for section in help_.sections:
                    print(f"{section['url']}\t{section['title']}", file=out)
        except re.error as error:
            print(f"vp6help: not a regular expression: {error}", file=sys.stderr)
            return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not os.path.isfile(args.file):
        print(f"vp6help: no such file: {args.file}", file=sys.stderr)
        return 1
    if args.list:
        return _list(args, sys.stdout)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("vp6help")
    try:
        viewer = show_help(args.file, args.page, args.keyword, args.search, args.index,
                           args.regex, args.case)
    except ValueError as error:
        print(f"vp6help: {error}", file=sys.stderr)
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
