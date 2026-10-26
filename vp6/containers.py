"""Containers with pages, and one that scrolls: ``ToolBox``, ``PageFrame``
and ``ScrollPanel``.

**Pages.** A control on a ToolBox or a PageFrame (or a WizardForm) is on one
of its pages: the designer writes which, right after its container
(``Label(self.tbxTools, Page=1, ...)``), and its ``Page`` property (from 0)
tells or changes it. The designer edits the page its container shows
(``CurrentPage``): click a ToolBox's page header, or choose Previous Page /
Next Page in the designer's context menu (or set CurrentPage in the
Properties window); controls drawn or pasted into the container go on that
page.

* **ToolBox** is the Outlook-style accordion: a header for each page, the
  open page's controls under it. ``Pages`` is a collection like a TabStrip's
  Tabs (by Index from 1 or by Key; each with ``Caption``, ``Key``,
  ``ToolTipText``, ``Picture`` (a picture file, or a Key or Index in its
  ``ImageList``), ``Enabled``); ``CurrentPage`` is the open page's number
  (from 0), ``SelectedItem`` the page itself. ``PageChange`` fires when
  another page opens.
* **PageFrame** shows one of its pages at a time, with no tabs: for wizards,
  and pages switched from code or a ListBox (``CurrentPage =
  List1.ListIndex``). ``PageCount``, ``AddPage(Index)``, ``RemovePage(Index)``
  (its controls go with it), ``PageChange``.
* **ScrollPanel** is a container whose controls scroll: ``ScrollBars``
  (shown when needed), ``ScrollLeft``/``ScrollTop``, the scrolled area's
  ``ScrollWidth``/``ScrollHeight`` (0: as large as its controls need),
  ``EnsureVisible(control)``, and ``Scroll`` while it scrolls. The designer
  scrolls it too (the mouse wheel over it).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QLabel, QScrollArea, QStackedWidget,
                               QStyle, QToolBox, QWidget)

from ._props import P, enum_choices
from .controls import (_COLORS, _COMMON, _FONT, CONTROL_TYPES, EVENT_ARGS, Control,
                       _add_mouse_members, _add_validation, _container_palette, _geometry,
                       _KeyedCollection, _KeyedItem, _picture_icon, _UsesImageList, parse_tab)

EVENT_ARGS.update({"PageChange": ""})


class _Paged:
    """A container with pages (ToolBox, PageFrame): its controls are on one
    page each (Control.Page); ``_pages()`` are the pages' widgets, in order."""

    IsContainer = True

    def _pages(self) -> list[QWidget]:
        raise NotImplementedError

    def _page_widget(self, page: int) -> QWidget:
        pages = self._pages()
        if not pages:
            self._ensure_a_page()
            pages = self._pages()
        return pages[max(0, min(int(page), len(pages) - 1))]

    def _ensure_a_page(self) -> None:
        raise NotImplementedError

    def _page_index_of(self, widget: QWidget | None) -> int | None:
        pages = self._pages()
        return pages.index(widget) if widget in pages else None

    def _container_widget(self) -> QWidget:
        """The page shown: where the designer puts new controls."""
        return self._page_widget(self._current())

    def _current(self) -> int:
        raise NotImplementedError

    def _drop_pages(self, keep: int) -> None:
        """Remove the pages from ``keep`` on; in the designer their controls go to
        the last page kept (else with them)."""
        pages = self._pages()
        for widget in pages[keep:]:
            if self._design_mode and keep:
                target = pages[keep - 1]
                for child in [c for c in widget.children() if isinstance(c, QWidget)]:
                    shown = not child.isHidden()
                    child.setParent(target)
                    if shown:
                        child.show()
            self._remove_page_widget(widget)
            widget.deleteLater()

    def _remove_page_widget(self, widget: QWidget) -> None:
        raise NotImplementedError

    def _page_controls(self, page: int) -> list[Control]:
        """The controls on that page (from 0)."""
        pages = self._pages()
        widget = pages[page] if 0 <= page < len(pages) else None
        return [c for c in self._form._controls if c.Parent is self and c._widget is not None
                and c._widget.parentWidget() is widget]

    def _show_page_for(self, control: Control) -> None:
        """In the designer: show the page a control is on (it was selected)."""
        page = self._page_index_of(control._widget.parentWidget()) \
            if control._widget is not None else None
        if page is not None and page != self._current():
            self._show_page(page)

    def _show_page(self, page: int) -> None:
        raise NotImplementedError


def _page_widget() -> QWidget:
    widget = QWidget()
    widget.setAutoFillBackground(False)
    return widget


# --- ToolBox ---------------------------------------------------------------------------------

class ToolBoxPage(_KeyedItem):
    """One page of a ToolBox (``ToolBox1.Pages(1)`` or by Key)."""

    def __init__(self, box: "ToolBox", key: str = "", caption: str = ""):
        self._box = box
        self._key = key
        self._caption = caption
        self._tooltip = ""
        self._picture = ""
        self._enabled = True
        self._widget: QWidget | None = None
        self.Tag = ""

    def __repr__(self):
        return f"<ToolBoxPage {self.Index} {self._key or self._caption!r}>"

    def _prop(name, attribute, convert, doc):  # noqa: N805 - (builds the properties below)
        def fget(self):
            return getattr(self, attribute)

        def fset(self, value):
            setattr(self, attribute, convert(value))
            self._changed()
        return property(fget, fset, doc=doc)

    Caption = _prop("Caption", "_caption", str, "The page's header text (& marks its access key)")
    ToolTipText = _prop("ToolTipText", "_tooltip", str, "Text shown when the mouse rests on "
                                                        "its header")
    Picture = _prop("Picture", "_picture", lambda v: "" if v is None else v,
                    "The picture in its header: a file, or a Key or Index in the ImageList")
    Enabled = _prop("Enabled", "_enabled", bool, "Whether it can be opened")
    del _prop

    @property
    def Selected(self) -> bool:
        """Whether it is the open page; setting it True opens it."""
        return self._box.SelectedItem is self

    @Selected.setter
    def Selected(self, value):
        if value:
            self._box.SelectedItem = self


class _ToolBoxPages(_KeyedCollection):
    """ToolBox.Pages: its pages in order, by Index (from 1) or Key."""

    _noun = "page"

    def Add(self, Index=None, Key: str = "", Caption: str = "") -> ToolBoxPage:
        """A new page, at the end or at Index (from 1)."""
        page = self._insert(ToolBoxPage(self._owner, str(Key or ""), str(Caption)), Index)
        self._changed()
        return page


class ToolBox(_Paged, _UsesImageList, Control):
    """The Outlook-style accordion container (the module's documentation)."""

    TypeName = "ToolBox"
    DefaultEvent = "PageChange"
    DefaultSize = (201, 257)
    Events = ("PageChange", "Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("ImageList", "str", "",
          description="The name of an ImageList on the form: the pages' pictures are then "
                      "a Key or Index in it"),
        P("Pages", "tabs", ["Page 1|page1", "Page 2|page2"],
          description="The pages, set in the designer: one per line, "
                      "Caption|Key|ToolTipText|Picture (the Picture a file, or a Key or Index "
                      "in the ImageList)"),
        P("CurrentPage", "int", 0,
          description="The open page's number (from 0); in the designer, the page being "
                      "edited"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_page_items"] = _ToolBoxPages(self, self._update_pages)
        self.__dict__["_quiet"] = 0
        widget = QToolBox(parent)
        widget.setFrameShape(QFrame.StyledPanel)
        return widget

    def _connect_signals(self):
        self._widget.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, index):
        if not self._quiet:
            self._values["CurrentPage"] = index
            self._fire("PageChange")

    # -- pages ------------------------------------------------------------------------------
    def _pages(self) -> list[QWidget]:
        return [page._widget for page in self._page_items._list if page._widget is not None]

    def _ensure_a_page(self) -> None:
        self._page_items._insert(ToolBoxPage(self, "", "Page 1"))
        self._update_pages()

    def _remove_page_widget(self, widget: QWidget) -> None:
        index = self._widget.indexOf(widget)
        if index >= 0:
            self._widget.removeItem(index)
        widget.hide()
        widget.setParent(None)

    def _current(self) -> int:
        return max(self._widget.currentIndex(), 0)

    def _show_page(self, page: int) -> None:
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            self._widget.setCurrentIndex(page)
        finally:
            self.__dict__["_quiet"] = self._quiet - 1

    @property
    def Pages(self) -> _ToolBoxPages:
        return self._page_items

    @Pages.setter
    def Pages(self, lines):
        """In the designer (and InitializeComponent): the pages as lines of text
        (Caption|Key|ToolTipText|Picture)."""
        self._set_prop("Pages", lines)

    def _apply_Pages(self, lines):
        old = list(self._page_items._list)
        self._page_items._reset()
        for index, line in enumerate(lines or []):
            spec = parse_tab(line)
            page = ToolBoxPage(self, spec["Key"], spec["Caption"])
            page._tooltip = spec["ToolTipText"]
            page._picture = spec["Image"]
            if index < len(old):  # (the page in its place keeps its controls)
                page._widget = old[index]._widget
            self._page_items._insert(page)
        self._update_pages()

    def _update_pages(self) -> None:
        """Show the collection's pages (a page keeps its widget, and so its controls)."""
        box = self._widget
        items = self._page_items._list
        wanted = []
        for page in items:
            if page._widget is None:
                page._widget = _page_widget()
            wanted.append(page._widget)
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            current = box.currentWidget()
            dropped = [box.widget(i) for i in range(box.count())
                       if box.widget(i) not in wanted]
            if dropped:  # (their controls: to the last page in the designer)
                last = wanted[-1] if wanted else None
                for widget in dropped:
                    if self._design_mode and last is not None:
                        for child in [c for c in widget.children() if isinstance(c, QWidget)]:
                            shown = not child.isHidden()
                            child.setParent(last)
                            if shown:
                                child.show()
                    self._remove_page_widget(widget)
                    widget.deleteLater()
            for index, widget in enumerate(wanted):
                if box.indexOf(widget) != index:
                    if box.indexOf(widget) >= 0:
                        box.removeItem(box.indexOf(widget))
                    box.insertItem(index, widget, "")
            for index, page in enumerate(items):
                box.setItemText(index, page._caption)
                box.setItemToolTip(index, page._tooltip)
                box.setItemIcon(index, _picture_icon(self, page._picture))
                box.setItemEnabled(index, page._enabled)
            if current in wanted:
                box.setCurrentWidget(current)
            elif wanted:
                box.setCurrentIndex(min(self._values.get("CurrentPage", 0), len(wanted) - 1))
        finally:
            self.__dict__["_quiet"] = self._quiet - 1
        self._style_pages()

    def _style_pages(self) -> None:
        for widget in self._pages():
            if widget.palette() != self._widget.palette():
                widget.setPalette(self._widget.palette())

    def _refresh_images(self) -> None:
        if self._widget is not None:
            self._update_pages()

    def _read_CurrentPage(self):
        return self._widget.currentIndex() if self._widget.count() else 0

    def _apply_CurrentPage(self, v):
        if self._widget.count():
            self._widget.setCurrentIndex(max(0, min(int(v), self._widget.count() - 1)))

    @property
    def SelectedItem(self) -> "ToolBoxPage | None":
        """The open page."""
        index = self._widget.currentIndex()
        items = self._page_items._list
        return items[index] if 0 <= index < len(items) else None

    @SelectedItem.setter
    def SelectedItem(self, page):
        """Open a page (a ToolBoxPage, its Index or its Key): PageChange fires."""
        self._widget.setCurrentIndex(self._page_items._resolve(page).Index - 1)

    def _page_at(self, pos: QPoint) -> int | None:
        """The page whose header is at a point (in the ToolBox), or None."""
        box = self._widget
        headers = [b for b in box.findChildren(QAbstractButton)
                   if b.parentWidget() is box and b.isVisible()]
        for button in headers:
            if button.geometry().contains(pos):
                headers.sort(key=lambda b: b.y())
                return headers.index(button)
        return None

    def _apply_colors(self, _=None):
        _container_palette(self)
        if self._widget is not None:
            self._style_pages()

    _apply_BackColor = _apply_ForeColor = _apply_colors


# --- PageFrame -----------------------------------------------------------------------------------

class _StackedFrame(QStackedWidget):
    """A PageFrame's widget; in the designer it says which page is shown."""

    def __init__(self, parent, design: bool):
        super().__init__(parent)
        self.badge = None
        if design:
            self.badge = QLabel(self)
            self.badge.setStyleSheet("QLabel { background: rgba(31, 95, 191, 160); color: white;"
                                     " padding: 1px 5px; border-bottom-left-radius: 4px; }")
            self.badge.setAttribute(Qt.WA_TransparentForMouseEvents)

    def show_badge(self) -> None:
        if self.badge is None:
            return
        self.badge.setText(f"Page {self.currentIndex() + 1} of {self.count()}")
        self.badge.adjustSize()
        self.badge.move(self.width() - self.badge.width(), 0)
        self.badge.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.show_badge()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.badge is not None and self.frameShape() == QFrame.NoFrame:
            painter = QPainter(self)  # (in the designer: where it is, even without a border)
            painter.setPen(QPen(self.palette().color(QPalette.Mid), 1, Qt.DashLine))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.end()


class PageFrame(_Paged, Control):
    """A container of pages without tabs, one shown at a time (the module's
    documentation)."""

    TypeName = "PageFrame"
    DefaultEvent = "PageChange"
    DefaultSize = (257, 177)
    Events = ("PageChange", "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("PageCount", "int", 2, description="How many pages it has"),
        P("CurrentPage", "int", 0,
          description="The page shown (from 0); in the designer, the page being edited"),
        P("BorderStyle", "enum", 0, enum_choices("None", "Fixed Single"),
          description="A border around the pages"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_quiet"] = 0
        return _StackedFrame(parent, self._design_mode)

    def _connect_signals(self):
        self._widget.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, index):
        self._widget.show_badge()
        if not self._quiet and index >= 0:
            self._values["CurrentPage"] = index
            self._fire("PageChange")

    def _pages(self) -> list[QWidget]:
        widget = self._widget
        return [widget.widget(i) for i in range(widget.count())]

    def _ensure_a_page(self) -> None:
        self._set_count(1)

    def _remove_page_widget(self, widget: QWidget) -> None:
        self._widget.removeWidget(widget)
        widget.hide()
        widget.setParent(None)

    def _current(self) -> int:
        return max(self._widget.currentIndex(), 0)

    def _show_page(self, page: int) -> None:
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            self._widget.setCurrentIndex(page)
        finally:
            self.__dict__["_quiet"] = self._quiet - 1

    def _set_count(self, count: int) -> None:
        count = max(1, int(count))
        widget = self._widget
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            while widget.count() < count:
                widget.addWidget(_page_widget())
            if widget.count() > count:
                self._drop_pages(count)
        finally:
            self.__dict__["_quiet"] = self._quiet - 1
        self._values["PageCount"] = widget.count()
        widget.show_badge()

    def _apply_PageCount(self, v):
        self._set_count(v)
        self._apply_CurrentPage(self._values.get("CurrentPage", 0))

    def _read_PageCount(self):
        return self._widget.count()

    def _read_CurrentPage(self):
        return max(self._widget.currentIndex(), 0)

    def _apply_CurrentPage(self, v):
        index = max(0, min(int(v), self._widget.count() - 1))
        self._values["CurrentPage"] = index
        self._widget.setCurrentIndex(index)
        self._widget.show_badge()

    def AddPage(self, Index: int | None = None) -> int:
        """A new empty page, at the end or at Index (from 0); returns its number."""
        widget = self._widget
        index = widget.count() if Index is None else max(0, min(int(Index), widget.count()))
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            widget.insertWidget(index, _page_widget())
        finally:
            self.__dict__["_quiet"] = self._quiet - 1
        self._values["PageCount"] = widget.count()
        widget.show_badge()
        return index

    def RemovePage(self, Index: int) -> None:
        """Remove page Index (from 0) and the controls on it."""
        pages = self._pages()
        index = int(Index)
        if not 0 <= index < len(pages):
            raise IndexError(f"PageFrame '{self.Name}': no page {index} (it has {len(pages)})")
        if len(pages) == 1:
            raise ValueError(f"PageFrame '{self.Name}': its last page can't be removed")
        for control in self._page_controls(index):
            control._widget.hide()
        self._remove_page_widget(pages[index])
        pages[index].deleteLater()
        self._values["PageCount"] = self._widget.count()
        self._widget.show_badge()

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.Panel | QFrame.Sunken if v else QFrame.NoFrame)

    def _apply_colors(self, _=None):
        _container_palette(self)

    _apply_BackColor = _apply_ForeColor = _apply_colors


# --- ScrollPanel ----------------------------------------------------------------------------------

class _ContentWatcher(QObject):
    """Keeps a ScrollPanel's content as large as its controls need: its
    controls added, removed, moved, resized, shown or hidden."""

    _EVENTS = (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide)

    def __init__(self, panel: "ScrollPanel", content: QWidget):
        super().__init__(content)
        self._panel = panel
        self._pending = False

    def eventFilter(self, watched, event):
        etype = event.type()
        if etype == QEvent.ChildAdded and isinstance(event.child(), QWidget):
            event.child().installEventFilter(self)
            self._schedule()
        elif etype == QEvent.ChildRemoved or (etype in self._EVENTS and
                                               watched is not self._panel._content):
            self._schedule()
        elif etype == QEvent.Resize and watched is self._panel._widget.viewport():
            self._schedule()
        return False

    def _schedule(self) -> None:
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self, self._update)

    def _update(self) -> None:
        self._pending = False
        self._panel._update_scroll_size()


class ScrollPanel(Control):
    """A container whose controls scroll (the module's documentation)."""

    TypeName = "ScrollPanel"
    DefaultEvent = "Scroll"
    DefaultSize = (201, 161)
    IsContainer = True
    Events = ("Scroll", "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("ScrollBars", "enum", 3, enum_choices("None", "Horizontal", "Vertical", "Both"),
          description="The scroll bars it may show, when its controls reach beyond its "
                      "edges (None: it doesn't scroll, but code can scroll it)"),
        P("ScrollWidth", "int", 0,
          description="The width of the area that scrolls; 0 = as far as its controls reach"),
        P("ScrollHeight", "int", 0,
          description="The height of the area that scrolls; 0 = as far as its controls reach"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A sunken border around it"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        area = QScrollArea(parent)
        area.setWidgetResizable(False)
        content = QWidget()
        area.setWidget(content)
        self.__dict__["_content"] = content
        watcher = _ContentWatcher(self, content)
        content.installEventFilter(watcher)
        area.viewport().installEventFilter(watcher)
        return area

    def _container_widget(self) -> QWidget:
        return self._content

    def _event_targets(self):
        return [self._widget, self._widget.viewport(), self._content]

    def _connect_signals(self):
        self._widget.horizontalScrollBar().valueChanged.connect(self._on_scrolled)
        self._widget.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    def _on_scrolled(self, *_):
        self._fire("Scroll")

    def _update_scroll_size(self) -> None:
        """The content: ScrollWidth x ScrollHeight, or as large as its controls
        need (at least the visible area)."""
        area = self._widget
        right = bottom = 0
        for child in self._content.children():
            if isinstance(child, QWidget) and not child.isHidden():
                right = max(right, child.geometry().right() + 1)
                bottom = max(bottom, child.geometry().bottom() + 1)
        width = self._values.get("ScrollWidth") or right
        height = self._values.get("ScrollHeight") or bottom
        full = area.contentsRect().size()  # (the visible area without scroll bars)
        if width <= full.width() and height <= full.height():
            self._content.resize(full)
            return
        view = area.viewport().size()
        self._content.resize(max(width, view.width()), max(height, view.height()))

    def _apply_ScrollBars(self, v):
        self._widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if v in (1, 3) else Qt.ScrollBarAlwaysOff)
        self._widget.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if v in (2, 3) else Qt.ScrollBarAlwaysOff)

    def _apply_ScrollWidth(self, v):
        self._update_scroll_size()

    _apply_ScrollHeight = _apply_ScrollWidth

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken if v else QFrame.NoFrame)

    @property
    def ScrollBarWidth(self) -> int:
        """The room a vertical scroll bar takes beside its contents when it shows
        (0 where scroll bars float over them, as macOS's do by default)."""
        area = self._widget
        if area.style().styleHint(QStyle.SH_ScrollBar_Transient, None, area):
            return 0
        return area.verticalScrollBar().sizeHint().width()

    @property
    def ScrollLeft(self) -> int:
        """How far its contents are scrolled to the left."""
        return self._widget.horizontalScrollBar().value()

    @ScrollLeft.setter
    def ScrollLeft(self, value):
        self._update_scroll_size()  # (controls just added or moved count already)
        self._widget.horizontalScrollBar().setValue(int(value))

    @property
    def ScrollTop(self) -> int:
        """How far its contents are scrolled up."""
        return self._widget.verticalScrollBar().value()

    @ScrollTop.setter
    def ScrollTop(self, value):
        self._update_scroll_size()
        self._widget.verticalScrollBar().setValue(int(value))

    def EnsureVisible(self, Control, Margin: int = 8) -> None:
        """Scroll so that one of its controls is in view (with a margin around it)."""
        widget = getattr(Control, "_widget", None)
        if widget is None or Control.Parent is not self:
            raise ValueError(f"ScrollPanel '{self.Name}': {Control!r} isn't in it")
        self._update_scroll_size()
        geometry = widget.geometry()
        center = geometry.center()
        self._widget.ensureVisible(center.x(), center.y(),
                                   geometry.width() // 2 + int(Margin),
                                   geometry.height() // 2 + int(Margin))

    def _design_wheel(self, delta: QPoint) -> bool:
        """The designer: the mouse wheel over it scrolls it. True: it scrolled."""
        bars = (self._widget.horizontalScrollBar(), self._widget.verticalScrollBar())
        self._update_scroll_size()
        moved = False
        for bar, step in zip(bars, (delta.x(), delta.y())):
            if step and bar.maximum() > 0:
                old = bar.value()
                bar.setValue(old - step // 2)
                moved = moved or bar.value() != old
        return moved

    def _apply_colors(self, _=None):
        _container_palette(self)
        if self._widget is not None:
            self._widget.viewport().setAutoFillBackground(False)
            self._content.setAutoFillBackground(False)

    _apply_BackColor = _apply_ForeColor = _apply_colors


_TYPES = (ToolBox, PageFrame, ScrollPanel)
for _cls in _TYPES:
    _add_validation(_cls)
    _add_mouse_members(_cls)
    CONTROL_TYPES[_cls.TypeName] = _cls  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
