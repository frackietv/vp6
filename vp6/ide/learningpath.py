"""The learning path drawn as a graph: the Education tab's map of a subject.

Each book of a vp6edu learning path is a node, with its title and a progress
bar (its lessons done); arrows go from each book to the books that follow
it, so a branch (Statistics, leaving Intermediate Algebra) leaves the main
line. The books are placed by ``education.layout_path`` (columns along the
path, branches in rows below), the widget as large as they need, so in a
scroll area it scrolls when wider than the dialog. Clicking a book (or the
arrow keys) chooses it: ``bookChosen``. Light and dark, from the palette.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from .logic import education
from .theme import theme_manager


class LearningPathView(QWidget):
    """A learning path's books as nodes with progress bars, joined by arrows."""

    bookChosen = Signal(str)  # the book's id

    NODE_WIDTH, NODE_HEIGHT = 184, 56
    GAP_X, GAP_Y, MARGIN = 36, 14, 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = None
        self.places: dict[str, tuple[int, int]] = {}
        self.progress: dict[str, tuple[int, int, int]] = {}
        self.selected = ""
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        theme_manager().changed.connect(self.update)

    # -- the path ------------------------------------------------------------------------------
    def set_path(self, path, progress: dict | None = None) -> None:
        """Show a learning path (``vp6edu.LearningPath``); ``progress`` is
        ``{book id: (done, written, lessons)}``, by default each book's."""
        self.path = path
        self.places = education.layout_path(path) if path is not None else {}
        books = path.subject.books if path is not None else {}
        self.progress = progress if progress is not None else {
            node: education.book_progress(books[node]) for node in self.places if node in books}
        if self.selected not in self.places:
            self.selected = ""
        self.setFixedSize(self.sizeHint())
        self.update()

    def refresh_progress(self) -> None:
        """Count each book's lessons done again."""
        self.set_path(self.path)

    def select(self, book: str, emit: bool = False) -> None:
        if book in self.places and book != self.selected:
            self.selected = book
            self.update()
            if emit:
                self.bookChosen.emit(book)

    def node_rect(self, book: str) -> QRectF:
        column, row = self.places[book]
        return QRectF(self.MARGIN + column * (self.NODE_WIDTH + self.GAP_X),
                      self.MARGIN + row * (self.NODE_HEIGHT + self.GAP_Y),
                      self.NODE_WIDTH, self.NODE_HEIGHT)

    def book_at(self, point) -> str | None:
        for book in self.places:
            if self.node_rect(book).contains(QPointF(point)):
                return book
        return None

    def title(self, book: str) -> str:
        books = self.path.subject.books if self.path is not None else {}
        return books[book].title if book in books else book

    def sizeHint(self) -> QSize:
        if not self.places:
            return QSize(2 * self.MARGIN, 2 * self.MARGIN)
        columns = 1 + max(c for c, _ in self.places.values())
        rows = 1 + max(r for _, r in self.places.values())
        return QSize(2 * self.MARGIN + columns * self.NODE_WIDTH + (columns - 1) * self.GAP_X,
                     2 * self.MARGIN + rows * self.NODE_HEIGHT + (rows - 1) * self.GAP_Y)

    # -- choosing ------------------------------------------------------------------------------
    def mousePressEvent(self, event):
        book = self.book_at(event.position().toPoint())
        if book is not None:
            self.setFocus()
            self.select(book, emit=True)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        order = sorted(self.places, key=lambda b: self.places[b])  # (by column, then row)
        steps = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -1, Qt.Key_Down: 1}
        if event.key() in steps and order:
            at = order.index(self.selected) if self.selected in order else -1
            self.select(order[max(0, min(len(order) - 1, at + steps[event.key()]))], emit=True)
            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            self.update()
        super().changeEvent(event)

    # -- drawing -------------------------------------------------------------------------------
    def colors(self) -> dict:
        palette = self.palette()
        dark = theme_manager().app_is_dark()
        return {"background": palette.color(QPalette.Base),
                "node": palette.color(QPalette.Button),
                "border": palette.color(QPalette.Mid),
                "text": palette.color(QPalette.ButtonText),
                "dim": QColor("#9a9a9a" if dark else "#707070"),
                "selected": palette.color(QPalette.Highlight),
                "arrow": QColor("#8a8a8a" if dark else "#7a7a7a"),
                "track": QColor("#3a3a3a" if dark else "#dedede"),
                "done": QColor("#5cc96b" if dark else "#2e9e44")}

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = self.colors()
        painter.fillRect(self.rect(), colors["background"])
        for a, b in (self.path.edges if self.path is not None else []):
            if a in self.places and b in self.places:
                self._arrow(painter, self.node_rect(a), self.node_rect(b), colors["arrow"])
        for book in self.places:
            self._node(painter, book, colors)
        painter.end()

    def _arrow(self, painter, start: QRectF, end: QRectF, color: QColor) -> None:
        """From a book's right side to the next's left; to a book in another
        row, a curve that leaves sideways and arrives sideways."""
        a = QPointF(start.right(), start.center().y())
        b = QPointF(end.left() - 1, end.center().y())
        if abs(a.y() - b.y()) < 1:
            line = QPainterPath(a)
            line.lineTo(b)
        else:  # (a branch: leaving the bottom, curving into the side)
            a = QPointF(start.center().x() + start.width() / 4, start.bottom())
            line = QPainterPath(a)
            line.cubicTo(QPointF(a.x(), b.y()), QPointF(a.x(), b.y()), b)
        painter.setPen(QPen(color, 1.6))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(line)
        head = QPolygonF([b, QPointF(b.x() - 9, b.y() - 4.5), QPointF(b.x() - 9, b.y() + 4.5)])
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(head)

    def _node(self, painter, book: str, colors: dict) -> None:
        rect = self.node_rect(book)
        selected = book == self.selected
        painter.setPen(QPen(colors["selected"] if selected else colors["border"],
                            2.4 if selected else 1.0))
        painter.setBrush(colors["node"])
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)
        inner = rect.adjusted(10, 7, -10, -8)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(colors["text"])
        metrics = QFontMetrics(font)
        title = metrics.elidedText(self.title(book), Qt.ElideRight, int(inner.width()))
        painter.drawText(QRectF(inner.left(), inner.top(), inner.width(), metrics.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, title)
        done, written, total = self.progress.get(book, (0, 0, 0))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(colors["dim"])
        line = QRectF(inner.left(), inner.top() + metrics.height() + 1, inner.width(),
                      metrics.height())
        painter.drawText(line, Qt.AlignLeft | Qt.AlignVCenter,
                         f"{done} of {total} done" if written else f"{total} lessons, planned")
        bar = QRectF(inner.left(), inner.bottom() - 6, inner.width(), 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(colors["track"])
        painter.drawRoundedRect(bar, 3, 3)
        if total and done:
            filled = QRectF(bar.left(), bar.top(), max(6.0, bar.width() * done / total),
                            bar.height())
            painter.setBrush(colors["done"])
            painter.drawRoundedRect(filled, 3, 3)
